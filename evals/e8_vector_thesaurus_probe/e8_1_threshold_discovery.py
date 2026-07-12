"""E-8.1 — vector-thesaurus threshold discovery.

The 2026-07-12 typo incident ('exlusive psalmody' → drought) proved the
ADR-0011 thesaurus's cliff-shape fragility: any near-miss to an exact
regex — typo, inflection, paraphrase, reordering, question form — falls
off the same cliff, producing a manifest that cascades into a BAML punt
and drought retrieval. Fuzzy edit-distance ≤1 only catches typos; a
paraphrase like 'psalms-only worship' still falls off.

The reviewer's proposal: embed the thesaurus keys, embed the user query,
match by cosine similarity above a tight threshold. This catches the
class (typo + inflection + paraphrase + question form), not the
instance. The correctness constraint: don't false-positive on adjacent-
but-different theological queries.

E-8.1 discovers whether a clean threshold exists between:
  SHOULD-MATCH:  typo / paraphrase / question-form variants of each key
  SHOULD-NOT:    real other theological queries (some intentionally
                 chosen to be nearby in embedding space to stress the
                 separation)

If a clean gap exists, we ship exact→vector hybrid with the discovered
threshold. If overlap, we fall back to exact+fuzzy and log near-misses.

Uses the same qwen3-embedding LiteLLM path as the runtime (via the
port-forward at localhost:4000).
"""
import io
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LITELLM_URL = "http://localhost:4000/embeddings"
MODEL = "qwen3-embedding"

# Thesaurus keys are the entries currently in backend/query_expansion.py.
KEYS = [
    "exclusive psalmody",
    "pactum salutis",
    "monergism",
    "regulative principle",
    "imputation",
]

# For each key, the shapes the vector matcher SHOULD reach — the class
# of near-misses that fell off the cliff with exact-match. Includes the
# typo Chris observed, plus inflections, paraphrases, question forms,
# reorderings.
SHOULD_MATCH = {
    "exclusive psalmody": [
        "exlusive psalmody",                                      # Chris's typo
        "exclusive psalms",                                       # inflection
        "psalms only worship",                                    # paraphrase, no shared token with key
        "is exclusive psalmody biblical?",                        # question form + wrapping
        "what was gill's opinion on the exclusive psalmody debate?",  # long question
        "should we sing only psalms in worship?",                 # full paraphrase, no shared theological token
        "psalmody exclusive position",                             # reordering
    ],
    "pactum salutis": [
        "paktum salutis",                                          # typo
        "pactum salutis doctrine",                                 # wrapping
        "covenant of redemption between father and son",           # Reformed English paraphrase
        "eternal covenant among the persons of the Trinity",       # long paraphrase
        "what does gill say about pactum salutis?",                # question form
    ],
    "monergism": [
        "monergistic",                                             # inflection
        "monergism vs synergism",                                  # comparison form
        "salvation entirely by God's work",                        # paraphrase
        "does gill teach monergism?",                              # question form
    ],
    "regulative principle": [
        "the regulative principle of worship",                     # full phrase form
        "regulative principle in worship",                         # inflection
        "worship regulated by scripture alone",                    # paraphrase
        "sola scriptura in worship",                               # theological synonym
    ],
    "imputation": [
        "imputation of Christ's righteousness",                    # descriptor form
        "imputed righteousness",                                   # inflection
        "does Christ's righteousness get credited to us?",         # paraphrase question
        "sin imputed to Christ",                                   # different-direction imputation
    ],
}

# Real other theological queries, some intentionally close in embedding
# space to stress the separation. If any of these lands within the
# should-match distance for any key, the threshold cannot cleanly gate.
SHOULD_NOT_MATCH = [
    "why the dietary laws",
    "covenant of grace",                    # covenantal — near pactum salutis
    "baptism",
    "the two thieves crucified with Christ",
    "universal atonement in Christ",        # soteriology — near monergism
    "did Esau eat pizza",
    "what does Gill say about Cain",
    "psalm singing in the Old Testament",   # ADJACENT — near exclusive psalmody, but different concept
    "singing at Passover",                  # ADJACENT to Hallel neighborhood, but different query
    "worship in the New Testament",         # ADJACENT to regulative principle
    "justification by faith",               # ADJACENT to imputation
    "Christ's righteousness",               # ADJACENT to imputation
    "who was Aquinas",
    "what is the covenant of grace monocovenantal",
]


def embed(text: str) -> list[float]:
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(
        LITELLM_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer anything",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    return d["data"][0]["embedding"]


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Weaviate-style cosine distance: 1 - cos_sim. Range [0, 2].
    Matches ADR-0010's thresholds (0.16-0.22 confident, 0.25 tier ceiling)."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 2.0
    return 1.0 - dot / (na * nb)


def main():
    print("=" * 100)
    print("E-8.1 — vector-thesaurus threshold discovery")
    print(f"model={MODEL}  distance=cosine (Weaviate style, lower=closer)")
    print("=" * 100)

    # Embed keys once.
    print("\nEmbedding thesaurus keys...")
    key_vecs = {k: embed(k) for k in KEYS}
    print(f"  embedded {len(key_vecs)} keys, dim={len(next(iter(key_vecs.values())))}")

    # For each key, distances to its should-match set.
    print()
    print("=" * 100)
    print("SHOULD-MATCH — each key's typo/paraphrase/question-form variants")
    print("=" * 100)
    should_match_dists: dict[str, list[tuple[str, float]]] = {}
    for key in KEYS:
        variants = SHOULD_MATCH.get(key, [])
        rows = []
        for v in variants:
            vec = embed(v)
            d = cosine_distance(key_vecs[key], vec)
            rows.append((v, d))
        should_match_dists[key] = rows
        print()
        print(f"KEY: {key!r}")
        for v, d in sorted(rows, key=lambda r: r[1]):
            print(f"  d={d:.4f}  {v!r}")

    # For each SHOULD-NOT query, distance to EVERY key. If any query lands
    # closer to a key than that key's SHOULD-MATCH worst case, the gap
    # is polluted.
    print()
    print("=" * 100)
    print("SHOULD-NOT-MATCH — for each query, its distance to every thesaurus key")
    print("=" * 100)
    should_not_dists: list[tuple[str, dict[str, float]]] = []
    for q in SHOULD_NOT_MATCH:
        vec = embed(q)
        row = {k: cosine_distance(key_vecs[k], vec) for k in KEYS}
        should_not_dists.append((q, row))

    for q, row in should_not_dists:
        min_key = min(row, key=row.get)
        min_d = row[min_key]
        print(f"\n  QUERY: {q!r}")
        print(f"    closest key: {min_key!r} at d={min_d:.4f}")
        for k in KEYS:
            print(f"      {k:24}  d={row[k]:.4f}")

    # ---- The threshold analysis ----
    print()
    print("=" * 100)
    print("THRESHOLD ANALYSIS")
    print("=" * 100)
    print()

    # Per key: what's the worst (highest) should-match distance? That's
    # the floor the threshold must clear.
    # Per key: what's the best (lowest) should-not-match distance? That's
    # the ceiling the threshold must stay below.
    for key in KEYS:
        sm = should_match_dists[key]
        if not sm:
            continue
        sm_worst = max(d for _, d in sm)
        sm_worst_variant = next(v for v, d in sm if d == sm_worst)

        # Best (lowest) should-not distance FOR THIS KEY across all should-not queries.
        sn_best = min(row[key] for _, row in should_not_dists)
        sn_best_q = next(q for q, row in should_not_dists if row[key] == sn_best)

        gap = sn_best - sm_worst
        verdict = "CLEAN" if gap > 0 else "OVERLAP"

        print(f"KEY: {key!r}")
        print(f"  worst should-match:  d={sm_worst:.4f}  ({sm_worst_variant!r})")
        print(f"  best  should-NOT:    d={sn_best:.4f}  ({sn_best_q!r})")
        print(f"  gap = {gap:+.4f}  ->  {verdict}")
        # Suggest a threshold midway if clean
        if gap > 0:
            suggested = round(sm_worst + gap / 2, 3)
            print(f"  suggested threshold: <= {suggested}")
        print()

    # Global summary: is there ANY threshold that covers all keys?
    max_sm_worst = max(
        max(d for _, d in should_match_dists[k])
        for k in KEYS if should_match_dists[k]
    )
    min_sn_best = min(
        row[k]
        for k in KEYS
        for _, row in should_not_dists
    )
    global_gap = min_sn_best - max_sm_worst
    print("=" * 100)
    print(f"GLOBAL:  worst should-match across all keys = {max_sm_worst:.4f}")
    print(f"         best  should-NOT across all keys   = {min_sn_best:.4f}")
    print(f"         gap = {global_gap:+.4f}")
    if global_gap > 0:
        suggested_global = round(max_sm_worst + global_gap / 2, 3)
        print(f"         CLEAN GLOBAL SEPARATION — single threshold <= {suggested_global}")
    else:
        print(f"         OVERLAP — no single threshold; per-key thresholds needed or fall back to fuzzy+exact")

    out = Path(__file__).parent / "e8_1_threshold_discovery_results.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump({
            "keys": KEYS,
            "should_match": {k: [{"query": v, "distance": d} for v, d in rows]
                             for k, rows in should_match_dists.items()},
            "should_not": [{"query": q, "distances": row} for q, row in should_not_dists],
        }, f, indent=2)
    print(f"\nRaw: {out}")


if __name__ == "__main__":
    main()
