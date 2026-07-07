"""E-7.5 — end-to-end validation of the ADR-0011 expansion fix.

Follows the pattern established by E-6b/E-6c for ADR-0010:
  Phase A — MANIFEST test: does `get_relevant_entities(expanded_query)`
    surface the anchor entity that the RAW query missed? For psalmody,
    the target is `Hallel` at MATTHEW 26:30.
  Phase B — RETRIEVAL test: does `search_gill` with the expanded
    manifest actually retrieve MATTHEW 26:30 in the top chunks?
  Phase C — NEGATIVE control: queries that do NOT contain narrow
    vocabulary should pass through unchanged (no expansion, no
    manifest drift, no regression).

Reads the actual retrieved chunk content — the reviewer's precision
lesson operationalized: 'the proxy said fine, the actual output said
otherwise, and reading the actual output was the whole game.'
"""
import asyncio
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["WEAVIATE_URL"] = "http://192.168.1.54:80"
os.environ["WEAVIATE_GRPC_HOST"] = "192.168.1.53"
os.environ["WEAVIATE_GRPC_PORT"] = "50051"
os.environ["LITELLM_PROXY_URL"] = "http://localhost:4000"
os.environ.setdefault("APP_ENV", "e7-probe")

sys.path.insert(0, str(Path("C:/Users/cnogr/git/goat-yard-archive")))

from dotenv import load_dotenv
load_dotenv()

from backend.gill_search import GillSearchEngine  # noqa: E402
from backend.query_expansion import expand_query   # noqa: E402


IN_DOMAIN = [
    {
        "key": "exclusive_psalmody",
        "query": "exclusive psalmody",
        "target_entity": "Hallel",
        "target_chunks_ideal": ["MATTHEW 26:30"],
    },
    {
        "key": "pactum_salutis",
        "query": "what does Gill say about the pactum salutis",
        "target_entity": "covenant engagements",
        "target_chunks_ideal": ["ROMANS", "HEBREWS"],
    },
]

NEGATIVE_CONTROL = [
    {
        "key": "no_narrow_terms",
        "query": "is the covenant of grace monocovenantal",
    },
    {
        "key": "no_narrow_terms_2",
        "query": "universal atonement in Christ",
    },
]


def _fmt_chunk(chunk: dict, i: int) -> str:
    vr = chunk.get("verse_ref", "?")
    sc = chunk.get("score")
    score_s = f"score={sc:.3f}" if isinstance(sc, (int, float)) else ""
    content = (chunk.get("content") or "").replace("\n", " ")[:180]
    return f"    {i}. [{vr}] {score_s}\n       {content}..."


async def phase_a_manifest(engine: GillSearchEngine, case: dict) -> dict:
    raw = case["query"]
    expanded, matches = expand_query(raw)
    print(f"\n  --- Phase A: MANIFEST ---")
    print(f"  raw query:      {raw!r}")
    print(f"  expansion:      {matches or '(no match)'}")
    print(f"  expanded query: {expanded!r}")

    raw_manifest = await engine.get_relevant_entities(query=raw)
    expanded_manifest = await engine.get_relevant_entities(query=expanded)

    print(f"  raw manifest:      {raw_manifest}")
    print(f"  expanded manifest: {expanded_manifest}")

    tgt = case["target_entity"]
    raw_hit = any((n or "").lower() == tgt.lower() for n in raw_manifest)
    exp_hit = any((n or "").lower() == tgt.lower() for n in expanded_manifest)
    print(f"  target {tgt!r} in raw manifest?      {raw_hit}")
    print(f"  target {tgt!r} in expanded manifest? {exp_hit}")

    return {
        "raw_query": raw, "expanded_query": expanded, "expansion_matches": matches,
        "raw_manifest": raw_manifest, "expanded_manifest": expanded_manifest,
        "raw_target_hit": raw_hit, "expanded_target_hit": exp_hit,
    }


async def phase_b_retrieval(engine: GillSearchEngine, case: dict, phase_a: dict, limit: int = 5) -> dict:
    print(f"\n  --- Phase B: RETRIEVAL ---")

    # Pre-fix: raw query + raw manifest
    pre_chunks = await engine.search_gill(
        query=phase_a["raw_query"],
        entities=phase_a["raw_manifest"],
        limit=limit,
        original_query=phase_a["raw_query"],
    )
    # Post-fix: raw query for search text (ADR-0011 keeps expansion lookup-only),
    # expanded manifest for entity boost.
    post_chunks = await engine.search_gill(
        query=phase_a["raw_query"],
        entities=phase_a["expanded_manifest"],
        limit=limit,
        original_query=phase_a["raw_query"],
    )

    print(f"  PRE-fix (raw manifest) retrieved:")
    for i, c in enumerate(pre_chunks, start=1):
        print(_fmt_chunk(c, i))
    print(f"  POST-fix (expanded manifest) retrieved:")
    for i, c in enumerate(post_chunks, start=1):
        print(_fmt_chunk(c, i))

    pre_refs = [(c.get("verse_ref") or "") for c in pre_chunks]
    post_refs = [(c.get("verse_ref") or "") for c in post_chunks]
    ideal = case.get("target_chunks_ideal", [])

    def _hit_count(refs: list[str], patterns: list[str]) -> int:
        return sum(1 for r in refs if any(p in r.upper() for p in patterns))

    pre_ideal_hits = _hit_count(pre_refs, ideal)
    post_ideal_hits = _hit_count(post_refs, ideal)
    print(f"  ideal-neighborhood ({ideal}) hits PRE:  {pre_ideal_hits}/{limit}")
    print(f"  ideal-neighborhood ({ideal}) hits POST: {post_ideal_hits}/{limit}")

    return {
        "pre_chunks": pre_chunks, "post_chunks": post_chunks,
        "pre_verse_refs": pre_refs, "post_verse_refs": post_refs,
        "pre_ideal_hits": pre_ideal_hits, "post_ideal_hits": post_ideal_hits,
    }


async def phase_c_negative(engine: GillSearchEngine, case: dict) -> dict:
    print(f"\n  --- Phase C: NEGATIVE CONTROL ---")
    raw = case["query"]
    expanded, matches = expand_query(raw)
    print(f"  raw query:      {raw!r}")
    print(f"  expansion matches: {matches}")
    print(f"  expanded query: {expanded!r}")
    if matches:
        print(f"  ✗ UNEXPECTED expansion — this query should not have matched.")
    else:
        print(f"  ✓ no expansion — passes through unchanged.")
    # Sanity: both manifests should be identical if no expansion fired.
    raw_manifest = await engine.get_relevant_entities(query=raw)
    print(f"  raw manifest: {raw_manifest}")
    return {"raw_query": raw, "expansion_matches": matches, "raw_manifest": raw_manifest}


async def main():
    print("\n" + "#" * 100)
    print("# E-7.5 END-TO-END VALIDATION — ADR-0011 query-expansion fix")
    print("# Phase A: manifest; Phase B: retrieval; Phase C: negative controls")
    print("#" * 100)

    engine = GillSearchEngine()
    await engine.connect()
    try:
        results = {"in_domain": [], "negative_control": []}
        for case in IN_DOMAIN:
            print()
            print("=" * 100)
            print(f"CASE: {case['key']}  query={case['query']!r}  target_entity={case['target_entity']!r}")
            phase_a = await phase_a_manifest(engine, case)
            phase_b = await phase_b_retrieval(engine, case, phase_a)
            results["in_domain"].append({
                "case": case["key"], "query": case["query"], "target": case["target_entity"],
                "phase_a": phase_a, "phase_b": phase_b,
            })

        for case in NEGATIVE_CONTROL:
            print()
            print("=" * 100)
            print(f"NEG-CTRL: {case['key']}  query={case['query']!r}")
            r = await phase_c_negative(engine, case)
            results["negative_control"].append(r)

        print("\n" + "=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"  {'case':30} {'expansion':40} {'raw_hit':>10} {'exp_hit':>10} {'pre_ideal':>11} {'post_ideal':>11}")
        print("-" * 120)
        for r in results["in_domain"]:
            pa = r["phase_a"]; pb = r["phase_b"]
            exp_str = str(pa["expansion_matches"])[:40]
            print(f"  {r['case']:30} {exp_str:40} {str(pa['raw_target_hit']):>10} "
                  f"{str(pa['expanded_target_hit']):>10} {pb['pre_ideal_hits']:>11} {pb['post_ideal_hits']:>11}")
        print()
        print(f"  Negative controls (should show no expansion):")
        for r in results["negative_control"]:
            m = r["expansion_matches"] or "(no match)"
            print(f"    - {r['raw_query'][:60]:60} matches={m}")

        out_path = Path(__file__).parent / "e7_5_end_to_end_results.json"
        with out_path.open("w", encoding="utf-8") as f:
            def _slim(o):
                if isinstance(o, dict):
                    return {k: _slim(v) for k, v in o.items()}
                if isinstance(o, list):
                    return [_slim(x) for x in o]
                return o
            json.dump(_slim(results), f, indent=2, default=str)
        print(f"\n  Raw: {out_path}")
    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
