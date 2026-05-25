#!/usr/bin/env python3
"""
Cross-model benchmark for the BAML ExtractGillKnowledge entity-extraction
prompt. Same prompt sent to multiple OpenRouter models against a fixed
10-page sample; reports per-model latency, throughput, within-page quality,
and cross-page consistency drift.

This is the entity-layer companion to evals/run_eval.py (which measures
end-to-end answer quality). Together they form the quality signal that
ADR-0004 and ADR-0005 Phase 5 describe.

Usage:
    # Requires COMMENTARY_DATA_DIR pointed at the dr-voluminous repo
    # (or wherever volume{N}/page{M}_image{N}.md files live).
    export COMMENTARY_DATA_DIR=/path/to/dr-voluminous/commentary
    python evals/entity_extraction_benchmark.py

    # Optionally pin output dir and trim to a single model for fast iteration:
    python evals/entity_extraction_benchmark.py --output-dir evals/output/run-2026-05 \
        --models grok-4.20

Why this benchmark exists
-------------------------
The 10-page sample was chosen for cross-page fragmentation diagnostic value:
- 4 Lev 16 pages (scapegoat / Azazel typology — entities re-appear across pages)
- 1 NT cross-reference to scapegoat (vol7 page 376)
- 5 diverse pages covering different categories (creation, Peter, John the
  Baptist, NT scapegoat references)

The fragmentation failure mode that motivated ADR-0005 (same entity
extracted with different `name` / `category` / `normalized_name` across
pages) is invisible on single-page tests. This benchmark surfaces it.

When to run
-----------
- Before a model upgrade (e.g. OpenRouter rotates Grok 4.20 to a newer slug).
- Periodically to detect silent drift in extraction quality.
- After any change to the BAML prompt in gill_extract.baml.
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from dotenv import load_dotenv

# Force UTF-8 stdout so Hebrew/Greek entity names don't crash on Windows cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parent.parent

# Default sample. Each entry is a relative path under COMMENTARY_DATA_DIR.
# Keep this list stable so historical benchmark results remain comparable.
DEFAULT_SAMPLE_PAGES = [
    # OT — Lev 16 scapegoat cluster (cross-page fragmentation hot zone)
    "volume1/page711_image1.md",  # Lev 16:8-10
    "volume1/page715_image1.md",  # Lev 16 detail
    "volume1/page716_image1.md",  # Lev 16
    "volume1/page720_image1.md",  # Lev 16
    # OT — scapegoat cross-reference and Genesis 1
    "volume1/page886_image1.md",  # scapegoat reference
    "volume1/page100_image1.md",  # Genesis 1:31
    # NT — vol7 diversity
    "volume7/page376_image7.md",  # scapegoat NT cross-ref
    "volume7/page421_image7.md",  # Mark 3:16 Peter
    "volume7/page766_image7.md",  # John 1:6 John the Baptist
    "volume7/page776_image7.md",  # NT scapegoat ref
]

DEFAULT_MODELS = {
    "grok-4.20":   "x-ai/grok-4.20",            # production bulk-extraction default
    "deepseek-v3": "deepseek/deepseek-chat",    # candidate / auto-merge judge
    "qwen3-235b":  "qwen/qwen3-235b-a22b-2507", # candidate / enrichment option
}

# Mirror the enum values in baml_src/gill_extract.baml. Keep in sync if the
# enums change. Validation uses these to detect "model invented a category".
CATEGORIES = [
    "Doctrine", "Heresy", "TypeOrSymbol",
    "BiblicalFigure", "HistoricalFigure", "CitedAuthority", "PeopleGroup",
    "Location", "TimePeriod",
    "OriginalWord", "ManuscriptOrVersion",
    "Unknown",
]
ERAS = ["OldTestament", "NewTestament", "Intertestamental", "ChurchHistory", "NotApplicable"]


# The prompt is intentionally NOT loaded from baml_src/gill_extract.baml —
# BAML inlines and templates it at codegen time and the runtime contract is
# the JSON shape, not the literal prompt string. We replicate the spirit here
# so a model can be tested without depending on a BAML codegen step.
SCHEMA = """{
  "entities": [
    {
      "name": "string (entity name verbatim from text)",
      "category": "one of: %s",
      "biblical_era": "one of: %s",
      "role": "string (optional, can be null) - disambiguating role",
      "normalized_name": "string (optional, can be null) - canonical form (legacy field)",
      "description": "string (5-10 words)"
    }
  ],
  "cross_references": ["string", ...]
}""" % (", ".join(CATEGORIES), ", ".join(ERAS))


PROMPT = """Analyze this commentary by John Gill. Extract key entities and scripture references.

**CRITICAL DISTINCTIONS:**
- 'BiblicalFigure': People who appear IN the Bible narrative (Abraham, Moses, Peter, Jesus, etc.)
- 'CitedAuthority': Scholars, Rabbis, or historians that GILL QUOTES (Josephus, Maimonides, Jerome, etc.)
- 'OriginalWord': Hebrew or Greek words that Gill defines or explains
- 'Location': Physical places mentioned
- 'TimePeriod': Historical periods or eras
- 'Doctrine': Theological concepts (Justification, Election, Trinity, etc.)
- 'Heresy': False teachings Gill refutes
- 'TypeOrSymbol': Biblical types/symbols (The Rock = Christ, Manna = Word of God, etc.)
- 'HistoricalFigure': Non-biblical historical persons mentioned
- 'PeopleGroup': Ethnic or religious groups
- 'ManuscriptOrVersion': Biblical manuscripts or versions (Septuagint, Vulgate, Targum)

**NORMALIZATION RULES (you MUST fill normalized_name for every entity):**
- For Jesus: Normalize "Christ", "the Lord", "our Saviour" -> "Jesus Christ"
- For God: Normalize "the Lord", "Jehovah", "the Almighty" -> "God"
- For locations: Use standard names (e.g., "the land of Canaan" -> "Canaan")
- For cited authorities: Include title if mentioned (e.g., "R. Solomon Jarchi", "Josephus")
- For ANY entity: If the name has unusual casing or punctuation (e.g. "scape-goat", "Scape-goat"), normalized_name should be a consistent canonical form. NEVER leave normalized_name null.

**DISAMBIGUATION:**
- For common names (Mary, Joseph, John, James), fill biblical_era and role accurately.
- INTRA-ERA COLLISIONS: If a name refers to multiple people in the SAME era, distinguish via role.

**SCRIPTURE CITATIONS:**
- Bible book abbreviations followed by chapter numbers (e.g. "Rom. i. 4") go in cross_references, NOT as entities.
- Normalize to BOOK_CH_VS format (e.g. "ROM_1_4").

**OUTPUT FORMAT (JSON only, no markdown, no preamble):**
%s

Commentary Text:
%s
""" % (SCHEMA, "{commentary}")


def search_key(name: str) -> str:
    """Match pipeline/scripts/ingest.py compute_search_key (Unicode-aware)."""
    return "".join(c for c in (name or "").lower() if c.isalnum())


def resolve_commentary_dir(cli_arg: Optional[str]) -> Path:
    """Find the commentary data directory; prefer CLI arg, fall back to env, fall back to a sibling repo guess."""
    if cli_arg:
        p = Path(cli_arg).expanduser().resolve()
    else:
        env = os.getenv("COMMENTARY_DATA_DIR")
        if env:
            p = Path(env).expanduser().resolve()
        else:
            # Heuristic: assume dr-voluminous is a sibling repo of this one.
            guess = REPO_ROOT.parent / "dr-voluminous" / "commentary"
            if guess.exists():
                p = guess.resolve()
            else:
                raise SystemExit(
                    "Could not locate commentary data. Set COMMENTARY_DATA_DIR "
                    "or pass --commentary-dir. Looked for: %s" % guess
                )
    if not p.is_dir():
        raise SystemExit(f"Commentary data dir not found: {p}")
    return p


def call_model(model_id: str, commentary: str, api_key: str) -> dict:
    prompt = PROMPT.replace("{commentary}", commentary)
    with httpx.Client(timeout=180) as client:
        r = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://goatyardarchive.org",
                "X-Title": "GYA Entity Extraction Benchmark",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    content = re.sub(r"^\s*```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```\s*$", "", content)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(m.group(0)) if m else {"_raw": content, "_parse_error": True}
    return {"parsed": parsed, "usage": usage}


def analyze_within_page(label: str, parsed: dict) -> dict:
    entities = parsed.get("entities", [])
    if not isinstance(entities, list):
        return {"label": label, "error": "entities is not a list", "raw": parsed}
    total = len(entities)
    if total == 0:
        return {"label": label, "total": 0}
    filled_norm = sum(1 for e in entities if e.get("normalized_name"))
    filled_role = sum(1 for e in entities if e.get("role"))
    invalid_category = sum(1 for e in entities if e.get("category") not in CATEGORIES)
    invalid_era = sum(1 for e in entities if e.get("biblical_era") not in ERAS)

    by_key: Dict[str, List[str]] = defaultdict(list)
    for e in entities:
        key = search_key(e.get("name") or "")
        if key:
            by_key[key].append(e.get("category"))
    cross_cat_dupes = {k: v for k, v in by_key.items() if len(set(v)) > 1}

    casings_per_key: Dict[str, set] = defaultdict(set)
    for e in entities:
        name = e.get("name") or ""
        key = search_key(name)
        if key:
            casings_per_key[key].add(name)
    multi_form_keys = {k: list(v) for k, v in casings_per_key.items() if len(v) > 1}

    has_scape = "scapegoat" in by_key
    has_azazel = "azazel" in by_key

    return {
        "label": label,
        "total": total,
        "normalized_name_fill_pct": round(100 * filled_norm / total, 1),
        "role_fill_pct": round(100 * filled_role / total, 1),
        "invalid_category": invalid_category,
        "invalid_era": invalid_era,
        "cross_category_duplicate_keys": list(cross_cat_dupes.keys()),
        "multi_form_keys": multi_form_keys,
        "has_scape_goat": has_scape,
        "has_azazel": has_azazel,
        "azazel_categories": by_key.get("azazel", []),
        "cross_references_count": len(parsed.get("cross_references", [])),
    }


def run_one(page_path: Path, page_rel: str, slot: str, model_id: str, out_dir: Path, api_key: str) -> dict:
    commentary = page_path.read_text(encoding="utf-8")
    page_label = page_path.stem
    t0 = time.perf_counter()
    try:
        result = call_model(model_id, commentary, api_key)
    except Exception as e:
        return {"page": page_label, "page_rel": page_rel, "model": slot, "label": slot, "error": str(e)[:200]}
    elapsed = time.perf_counter() - t0
    parsed = result["parsed"]
    usage = result["usage"]

    out_file = out_dir / f"{page_label}__{slot}.json"
    out_file.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")

    analysis = analyze_within_page(slot, parsed)
    analysis["elapsed_s"] = round(elapsed, 1)
    analysis["prompt_tokens"] = usage.get("prompt_tokens")
    analysis["completion_tokens"] = usage.get("completion_tokens")
    analysis["page"] = page_label
    analysis["page_rel"] = page_rel
    # Keep the raw entity list around for cross-page analysis (stripped from saved summary).
    analysis["_entities"] = parsed.get("entities", []) if isinstance(parsed.get("entities"), list) else []
    return analysis


def cross_page_analysis(rows: list) -> dict:
    by_key: Dict[str, list] = defaultdict(list)
    for row in rows:
        page = row["page"]
        for e in row.get("_entities", []):
            key = search_key(e.get("name") or "")
            if not key:
                continue
            by_key[key].append({
                "page": page,
                "name": e.get("name") or "",
                "category": e.get("category"),
                "biblical_era": e.get("biblical_era"),
                "normalized_name": e.get("normalized_name"),
            })

    recurring = {k: v for k, v in by_key.items() if len(v) > 1}
    name_drift, cat_drift, era_drift, norm_drift = [], [], [], []
    for k, entries in recurring.items():
        names = {e["name"] for e in entries}
        cats = {e["category"] for e in entries}
        eras = {e["biblical_era"] for e in entries}
        norms = {e["normalized_name"] for e in entries if e["normalized_name"]}
        pages = sorted({e["page"] for e in entries})
        if len(names) > 1:
            name_drift.append({"key": k, "forms": sorted(names), "pages": pages})
        if len(cats) > 1:
            cat_drift.append({"key": k, "categories": sorted(cats), "pages": pages})
        if len(eras) > 1:
            era_drift.append({"key": k, "eras": sorted(eras), "pages": pages})
        if len(norms) > 1:
            norm_drift.append({"key": k, "normalized_names": sorted(norms), "pages": pages})

    return {
        "recurring_entity_count": len(recurring),
        "name_drift_count": len(name_drift),
        "category_drift_count": len(cat_drift),
        "era_drift_count": len(era_drift),
        "normalized_name_drift_count": len(norm_drift),
        "examples_name_drift": name_drift[:6],
        "examples_category_drift": cat_drift[:6],
        "examples_era_drift": era_drift[:6],
        "examples_norm_drift": norm_drift[:6],
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--commentary-dir",
        help="Root of commentary data (defaults to $COMMENTARY_DATA_DIR or a sibling dr-voluminous repo).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "evals" / "output" / "entity_compare"),
        help="Where to write per-page model outputs + summary JSON.",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        choices=list(DEFAULT_MODELS.keys()),
        help="Subset of models to run (default: all).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Pages in flight per model (default: 3).",
    )
    args = parser.parse_args(argv)

    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY not set in environment or .env.")

    commentary_dir = resolve_commentary_dir(args.commentary_dir)
    pages = []
    missing = []
    for rel in DEFAULT_SAMPLE_PAGES:
        p = commentary_dir / rel
        if p.exists():
            pages.append((p, rel))
        else:
            missing.append(rel)
    if missing:
        print(f"WARNING: missing {len(missing)} page(s) from sample:")
        for m in missing:
            print(f"  - {m}")
    if not pages:
        raise SystemExit(f"No sample pages found under {commentary_dir}.")
    print(f"Commentary dir: {commentary_dir}")
    print(f"Running {len(pages)} page(s) against {len(args.models or DEFAULT_MODELS)} model(s).")

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output dir   : {out_dir}\n")

    models = {k: v for k, v in DEFAULT_MODELS.items() if (not args.models or k in args.models)}
    summary_rows = []

    for slot, model_id in models.items():
        print(f"{'#'*70}\n# MODEL: {slot} ({model_id})\n{'#'*70}", flush=True)
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {
                pool.submit(run_one, p, rel, slot, model_id, out_dir, api_key): (p, rel)
                for (p, rel) in pages
            }
            for fut in as_completed(futures):
                p, rel = futures[fut]
                row = fut.result()
                summary_rows.append(row)
                if "error" in row:
                    print(f"  [X] {p.stem}: ERROR - {row['error']}")
                else:
                    print(
                        f"  [OK] {p.stem}: "
                        f"entities={row['total']} "
                        f"norm_fill={row['normalized_name_fill_pct']}% "
                        f"latency={row['elapsed_s']}s "
                        f"cross-cat={len(row['cross_category_duplicate_keys'])} "
                        f"multi-form={len(row['multi_form_keys'])}",
                        flush=True,
                    )

    print(f"\n{'='*70}\nPER-MODEL SUMMARY\n{'='*70}")
    by_model: Dict[str, list] = defaultdict(list)
    for row in summary_rows:
        if "error" in row:
            continue
        by_model[row["label"]].append(row)

    cross_page_results: Dict[str, dict] = {}
    for slot, rows in by_model.items():
        n = len(rows)
        if n == 0:
            continue
        avg_total = sum(r["total"] for r in rows) / n
        avg_norm_fill = sum(r["normalized_name_fill_pct"] for r in rows) / n
        any_cross_cat = sum(len(r["cross_category_duplicate_keys"]) for r in rows)
        any_multi_form = sum(len(r["multi_form_keys"]) for r in rows)
        scape_hits = sum(int(r["has_scape_goat"]) for r in rows)
        azazel_hits = sum(int(r["has_azazel"]) for r in rows)
        total_completion_tok = sum((r.get("completion_tokens") or 0) for r in rows)
        total_prompt_tok = sum((r.get("prompt_tokens") or 0) for r in rows)
        total_elapsed = sum(r["elapsed_s"] for r in rows)
        avg_elapsed = total_elapsed / n
        tok_per_sec = (total_completion_tok / total_elapsed) if total_elapsed > 0 else 0
        print(
            f"\n{slot}:\n"
            f"  WITHIN-PAGE QUALITY:  entities/page={avg_total:.1f}  "
            f"norm_name fill={avg_norm_fill:.1f}%  "
            f"cross-cat dupes={any_cross_cat}  multi-form dupes={any_multi_form}\n"
            f"  COVERAGE:             scape_goat={scape_hits}/{n}  Azazel={azazel_hits}/{n}\n"
            f"  SPEED (per call):     avg_latency={avg_elapsed:.1f}s  "
            f"throughput={tok_per_sec:.1f} tok/s  "
            f"completion_tok_total={total_completion_tok}  "
            f"prompt_tok_total={total_prompt_tok}"
        )
        cross_page_results[slot] = cross_page_analysis(rows)

    print(f"\n{'='*70}\nCROSS-PAGE CONSISTENCY (the production failure mode)\n{'='*70}")
    print("Lower drift counts = better cross-page consistency = fewer fragmentation cases.\n")
    for slot, cp in cross_page_results.items():
        print(
            f"\n{slot}:\n"
            f"  recurring entities (in >= 2 pages)              : {cp['recurring_entity_count']}\n"
            f"  name-form drift (different casings/spellings)   : {cp['name_drift_count']}\n"
            f"  category drift (TypeOrSymbol vs OriginalWord)   : {cp['category_drift_count']}\n"
            f"  era drift (OT vs NotApplicable)                 : {cp['era_drift_count']}\n"
            f"  normalized_name drift                           : {cp['normalized_name_drift_count']}"
        )
        if cp["examples_name_drift"]:
            print(f"  -- examples of NAME drift:")
            for ex in cp["examples_name_drift"][:3]:
                print(f"     key='{ex['key']}'  forms={ex['forms']}  pages={ex['pages']}")
        if cp["examples_category_drift"]:
            print(f"  -- examples of CATEGORY drift:")
            for ex in cp["examples_category_drift"][:3]:
                print(f"     key='{ex['key']}'  cats={ex['categories']}  pages={ex['pages']}")
        if cp["examples_norm_drift"]:
            print(f"  -- examples of NORMALIZED_NAME drift:")
            for ex in cp["examples_norm_drift"][:3]:
                print(f"     key='{ex['key']}'  norms={ex['normalized_names']}  pages={ex['pages']}")

    summary_serializable = [{k: v for k, v in r.items() if k != "_entities"} for r in summary_rows]
    (out_dir / "summary.json").write_text(json.dumps(summary_serializable, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "cross_page.json").write_text(json.dumps(cross_page_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRaw outputs + summary.json + cross_page.json saved to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
