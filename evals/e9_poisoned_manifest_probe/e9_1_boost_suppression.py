"""E-9.1 — poisoned-manifest fallback (ADR-0012).

The reviewer's precondition after ADR-0011 v2 (2026-07-12): when the
BAML sentinel fires with `entities_given_none_returned`, the current
fallback re-uses the same manifest BAML just rejected as the entity
boost. That injects known-wrong signal into retrieval and produces the
'confidently wrong' failure mode (e.g. 'means of grace' -> GENESIS 6:8
Noah-grace commentary, not means-of-grace material).

Fix (ADR-0012): dispatch on the specific punt reason.
  - entities_given_none_returned -> suppress entity boost entirely,
    let retrieval run on hybrid BM25+vector alone.
  - other punts (empty_expansion, no_query_terms_present) -> keep the
    dedup-only fallback because the manifest itself may be fine.

Verification: for a drought-shaped query that reliably triggers
entities_given_none_returned, compare retrieval under two conditions:
  BEFORE Fix 2: search_gill(query, entities=<the poisoned manifest>)
  AFTER  Fix 2: search_gill(query, entities=[])

If retrieval reads the same, Fix 2 is inert. If retrieval shifts away
from the poisoned-manifest-driven chunks (like GENESIS 6:8 for 'means
of grace') toward more semantically-adjacent material — or at least
degrades to less-confident wrong hits — the fix converts the cliff
into a slope.
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
os.environ.setdefault("APP_ENV", "e9-probe")

sys.path.insert(0, str(Path("C:/Users/cnogr/git/goat-yard-archive")))

from dotenv import load_dotenv
load_dotenv()

from backend.gill_search import GillSearchEngine  # noqa: E402


# Cases sourced from the 2026-07-12 baseline probe against the deployed
# pod running f019969 (pre-Fix-2). Each was verified to trigger the
# entities_given_none_returned punt reason.
CASES = [
    {
        "key": "means_of_grace",
        "query": "means of grace",
        "poisoned_manifest": [
            "covenant of grace", "dew of heaven", "divine grace",
            "election of grace", "sovereign grace",
        ],
        "baseline_notable_chunks": ["GENESIS 6:8", "GENESIS 9:10", "JOHN 3:20"],
    },
    {
        "key": "unmatched_narrow_typo",
        "query": "pxlusive psalmoly",  # edit distance >= 2 from any thesaurus key
        "poisoned_manifest": [
            "Jesus Christ", "Apostle Paul", "Old Testament saints",
        ],
        "baseline_notable_chunks": ["JOHN 3:19", "JOHN 5:53", "LUKE 19:16"],
    },
]


def _fmt(c: dict, i: int) -> str:
    vr = c.get("verse_ref", "?")
    sc = c.get("score")
    score_s = f"score={sc:.3f}" if isinstance(sc, (int, float)) else ""
    content = (c.get("content") or "").replace("\n", " ")[:140]
    return f"    {i}. [{vr}] {score_s}\n       {content}..."


def _refs(chunks: list[dict]) -> list[str]:
    return [c.get("verse_ref", "") for c in chunks]


async def run_case(engine: GillSearchEngine, case: dict, limit: int = 5) -> dict:
    print()
    print("=" * 100)
    print(f"CASE: {case['key']}  query={case['query']!r}")
    print(f"  poisoned manifest (what BAML rejected): {case['poisoned_manifest']}")

    # BEFORE Fix 2: dedup fallback re-boosts on the poisoned manifest.
    before = await engine.search_gill(
        query=case["query"],
        entities=case["poisoned_manifest"],
        limit=limit,
        original_query=case["query"],
    )
    # AFTER  Fix 2: mapped_entities = [] -> no entity boost.
    after = await engine.search_gill(
        query=case["query"],
        entities=[],
        limit=limit,
        original_query=case["query"],
    )

    print()
    print("  --- BEFORE Fix 2 (poisoned-manifest boost) ---")
    for i, c in enumerate(before, start=1):
        print(_fmt(c, i))
    print()
    print("  --- AFTER Fix 2 (entities=[], no boost) ---")
    for i, c in enumerate(after, start=1):
        print(_fmt(c, i))

    b_refs = set(_refs(before))
    a_refs = set(_refs(after))
    overlap = b_refs & a_refs
    only_before = b_refs - a_refs
    only_after = a_refs - b_refs

    baseline_notable = set(case.get("baseline_notable_chunks") or [])
    before_hit_baseline = baseline_notable & b_refs
    after_dropped_baseline = before_hit_baseline & only_before

    print()
    print("  --- COMPARISON ---")
    print(f"  overlap between before/after: {sorted(overlap)}")
    print(f"  only-before: {sorted(only_before)}")
    print(f"  only-after:  {sorted(only_after)}")
    if baseline_notable:
        print(f"  baseline-notable chunks (poisoned-boost driven): {sorted(baseline_notable)}")
        print(f"    in BEFORE result: {sorted(before_hit_baseline)}")
        print(f"    DROPPED after fix: {sorted(after_dropped_baseline)}")

    return {
        "case": case["key"], "query": case["query"],
        "before_refs": _refs(before), "after_refs": _refs(after),
        "overlap": sorted(overlap), "only_before": sorted(only_before),
        "only_after": sorted(only_after),
        "baseline_notable_dropped": sorted(after_dropped_baseline),
    }


async def main():
    print("\n" + "#" * 100)
    print("# E-9.1 — poisoned-manifest fallback verification (ADR-0012)")
    print("# BEFORE Fix 2: search_gill(entities=<poisoned>)")
    print("# AFTER  Fix 2: search_gill(entities=[])")
    print("#" * 100)

    engine = GillSearchEngine()
    await engine.connect()
    try:
        results = []
        for case in CASES:
            r = await run_case(engine, case)
            results.append(r)

        print()
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        for r in results:
            n_dropped = len(r["baseline_notable_dropped"])
            print(f"  {r['case']:30}  chunks_diverged={len(r['only_before'])+len(r['only_after'])}  "
                  f"baseline_notable_dropped={n_dropped}")

        out = Path(__file__).parent / "e9_1_boost_suppression_results.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  Raw: {out}")
    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
