"""E-6c end-to-end retrieval comparison.

The reviewer's precondition: 'E-6b proved the manifest; one end-to-end
query per case proves the manifest helped.' This harness answers that by
calling search_gill directly with the PRE-fix and POST-fix manifests for
the same query, holding everything else constant, and comparing the
retrieved chunks.

Method:
  For each of universal_atonement and covenant_monocovenantal:
    (a) PRE-fix run — call search_gill(query, entities=<pre-fix manifest
        from e6_bm25_baseline_results.json>). This mirrors what the
        deployed backend would have used as the entity boost list.
    (b) POST-fix run — call search_gill(query, entities=<post-fix manifest
        of 5 entities from e6b_post_fix_results.json>).
    (c) Print the top-5 retrieved chunks (verse_ref + content snippet)
        for each, plus overlap analysis.

This isolates the effect of the manifest change on retrieval: same
Weaviate cluster, same embedding model, same query, only the entity
boost list differs. If the post-fix chunks are same-or-better, the fix
helps at the layer that matters, not just the layer above.

BAML's OptimizeSearchQuery is skipped intentionally — it would introduce
a second variable (BAML picks different subsets from different-sized
manifests). By passing the manifest directly, we measure the manifest's
CONTRIBUTION TO RETRIEVAL, which is the ADR's actual claim. BAML on top
of that only makes the effect stronger, not weaker.
"""
import asyncio
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Point the backend GillSearchEngine at the gya-test cluster.
os.environ["WEAVIATE_URL"] = "http://192.168.1.54:80"
os.environ["WEAVIATE_GRPC_HOST"] = "192.168.1.53"
os.environ["WEAVIATE_GRPC_PORT"] = "50051"
os.environ["LITELLM_PROXY_URL"] = "http://localhost:4000"  # via port-forward
os.environ.setdefault("APP_ENV", "e6c-probe")

# Ensure repo on path
sys.path.insert(0, str(Path("C:/Users/cnogr/git/goat-yard-archive")))

from dotenv import load_dotenv
load_dotenv()

from backend.gill_search import GillSearchEngine  # noqa: E402


# Pre-fix manifests: full output of the CURRENT get_relevant_entities
# for each query, taken from e6_bm25_baseline_results.json (BM25 + substring).
def load_pre_fix_manifest(query: str) -> list[str]:
    baseline_path = Path(__file__).parent / "e6_bm25_baseline_results.json"
    with baseline_path.open(encoding="utf-8") as f:
        data = json.load(f)
    for row in data:
        if row["query"] == query:
            return row["combined_names"]
    raise KeyError(f"no baseline row for query {query!r}")


CASES = [
    {
        "key": "universal_atonement",
        "query": "universal atonement in Christ",
        "target": "Atonement",
        "post_fix_manifest": [
            "atonement", "satisfaction of Christ", "propitiation",
            "day of atonement", "Universal History",
        ],
        "expected_verse_neighborhood": ["LEVITICUS 16", "JOHN 10", "ROMANS 5", "HEBREWS 9"],
    },
    {
        "key": "covenant_monocovenantal",
        "query": "is the covenant of grace monocovenantal",
        "target": "covenant of grace",
        "post_fix_manifest": [
            "covenant of grace", "covenant of works", "covenant of conservation",
            "everlasting covenant", "Angel of the covenant",
        ],
        "expected_verse_neighborhood": ["GENESIS 17", "GENESIS 9", "MATTHEW 26", "HEBREWS 8"],
    },
]


def _fmt_chunk(chunk: dict, i: int) -> str:
    vr = chunk.get("verse_ref", "?")
    sc = chunk.get("score")
    score_s = f"score={sc:.3f}" if isinstance(sc, (int, float)) else ""
    content = (chunk.get("content") or "").replace("\n", " ")[:140]
    return f"    {i}. [{vr}] {score_s}\n       {content}..."


def _canonical_ref_key(ref: str) -> str:
    """Return 'BOOK N' (book + chapter) for coarse neighborhood match."""
    if not ref:
        return ""
    parts = ref.split(":")
    return parts[0].strip()


async def run_case(engine: GillSearchEngine, case: dict, limit: int = 5) -> dict:
    q = case["query"]
    tgt = case["target"]
    neighborhood = case["expected_verse_neighborhood"]

    pre_manifest = load_pre_fix_manifest(q)
    post_manifest = case["post_fix_manifest"]

    print()
    print("=" * 100)
    print(f"CASE: {case['key']}  query={q!r}")
    print(f"  target entity: {tgt!r}")
    print(f"  expected verse neighborhood: {neighborhood}")
    print(f"  PRE-fix manifest size:  {len(pre_manifest)}")
    print(f"  POST-fix manifest size: {len(post_manifest)}")
    print()

    print(f"  PRE-fix manifest (first 10): {pre_manifest[:10]}")
    print(f"  POST-fix manifest:           {post_manifest}")

    # Run search_gill for each manifest against the SAME query & cluster.
    pre_results = await engine.search_gill(
        query=q, entities=pre_manifest, limit=limit, original_query=q,
    )
    post_results = await engine.search_gill(
        query=q, entities=post_manifest, limit=limit, original_query=q,
    )

    def summarize(rows: list[dict], label: str) -> dict:
        chunks = []
        for i, r in enumerate(rows, start=1):
            chunks.append({
                "rank": i,
                "verse_ref": r.get("verse_ref"),
                "score": r.get("score"),
                "content_head": (r.get("content") or "")[:200],
            })
        book_chapter_hits = [
            _canonical_ref_key(c["verse_ref"]) for c in chunks if c["verse_ref"]
        ]
        neighborhood_hits = sum(
            1 for h in book_chapter_hits
            if any(h.startswith(nb) or nb.startswith(h) for nb in neighborhood)
        )
        return {
            "label": label, "chunks": chunks,
            "book_chapter_refs": book_chapter_hits,
            "neighborhood_hit_count": neighborhood_hits,
        }

    pre_sum = summarize(pre_results, "PRE-fix")
    post_sum = summarize(post_results, "POST-fix")

    print()
    print("  --- PRE-fix retrieved chunks ---")
    for c in pre_sum["chunks"]:
        print(_fmt_chunk(c, c["rank"]))
    print()
    print("  --- POST-fix retrieved chunks ---")
    for c in post_sum["chunks"]:
        print(_fmt_chunk(c, c["rank"]))

    # Overlap and neighborhood analysis
    pre_verses = {c["verse_ref"] for c in pre_sum["chunks"] if c["verse_ref"]}
    post_verses = {c["verse_ref"] for c in post_sum["chunks"] if c["verse_ref"]}
    overlap = pre_verses & post_verses
    only_pre = pre_verses - post_verses
    only_post = post_verses - pre_verses

    print()
    print("  --- comparison ---")
    print(f"  overlap: {sorted(overlap)}")
    print(f"  only PRE-fix: {sorted(only_pre)}")
    print(f"  only POST-fix: {sorted(only_post)}")
    print(f"  expected-neighborhood hits PRE: {pre_sum['neighborhood_hit_count']}/{limit}")
    print(f"  expected-neighborhood hits POST: {post_sum['neighborhood_hit_count']}/{limit}")

    return {
        "case": case["key"], "query": q, "target": tgt,
        "pre": pre_sum, "post": post_sum,
        "overlap": sorted(overlap),
        "only_pre": sorted(only_pre),
        "only_post": sorted(only_post),
    }


async def main():
    print("\n" + "#" * 100)
    print("# E-6c END-TO-END RETRIEVAL COMPARISON")
    print("# Pre vs post entity-manifest; same query, same cluster, same embedding.")
    print("#" * 100)

    engine = GillSearchEngine()
    await engine.connect()
    try:
        results = []
        for case in CASES:
            r = await run_case(engine, case)
            results.append(r)

        print("\n" + "=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"  {'case':30} {'pre_hood_hits':>15} {'post_hood_hits':>15} {'overlap':>10} {'post_only':>10}")
        print("-" * 100)
        for r in results:
            print(f"  {r['case']:30} "
                  f"{r['pre']['neighborhood_hit_count']:>15} "
                  f"{r['post']['neighborhood_hit_count']:>15} "
                  f"{len(r['overlap']):>10} {len(r['only_post']):>10}")

        out_path = Path(__file__).parent / "e6c_end_to_end_results.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  Raw: {out_path}")
    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
