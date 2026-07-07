"""E-6 BM25 baseline — what does the CURRENT get_relevant_entities return
for the same three in-domain flagship queries + two OOD?

Faithfully replicates backend/gill_search.py:get_relevant_entities():
  (1) self.entities.query.bm25(query, limit=50) over entity NAMES
  (2) substring LIKE *canonicalized_token* on canonical search_key

Purpose (per 2026-07-07 reviewer directive): establish the COUNTERFACTUAL
so the ADR entry can show — not assert — that near_vector is a strict
improvement on universal_atonement/covenant, and no-regression on
exclusive_psalmody (which needs a separate query-expansion fix).
"""
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import weaviate
import weaviate.classes as wvc

WEAVIATE_HOST = "192.168.1.54"
WEAVIATE_GRPC_HOST = "192.168.1.53"

# Same STOPWORDS list as backend/gill_search.py._ENTITY_LOOKUP_STOPWORDS.
STOPWORDS = {
    "does", "gill", "what", "when", "where", "which", "with", "will",
    "have", "this", "that", "from", "into", "your", "were", "here", "there",
    "would", "could", "should", "about", "their", "them", "they",
    "than", "then", "some", "such", "much", "more", "most", "less", "least",
    "these", "those", "other", "another", "every", "each",
    "named", "between", "within", "without", "before", "after", "such",
    "some", "much", "more", "most", "less", "least", "very", "still",
    "only", "also", "ever", "even", "just", "really", "actually",
}


PROBES = [
    ("in-domain", "exclusive psalmody", "Hallel"),
    ("in-domain", "universal atonement in Christ", "Atonement"),
    ("in-domain", "is the covenant of grace monocovenantal", "covenant of grace"),
    ("OOD", "how do I write a for loop in javascript", None),
    ("OOD", "did Esau eat pizza", None),
]


def probe_bm25(client, query: str, target: str | None, limit: int = 50) -> dict:
    """Faithful replica of get_relevant_entities."""
    ents = client.collections.get("TheologicalEntity")

    bm25_names: list[str] = []
    try:
        resp = ents.query.bm25(
            query=query, limit=limit,
            return_metadata=wvc.query.MetadataQuery(score=True),
            return_properties=["name", "category", "description"],
        )
        bm25_hits = [{
            "path": "bm25",
            "score": o.metadata.score,
            "name": o.properties.get("name"),
            "category": o.properties.get("category"),
            "description": (o.properties.get("description") or "")[:80],
        } for o in resp.objects]
        bm25_names = [h["name"] for h in bm25_hits if h["name"]]
    except Exception as e:
        bm25_hits = []
        print(f"  BM25 error: {e}")

    # Substring pass — mirrors the code's tokenization and canonicalization.
    substring_hits = []
    seen = set(bm25_names)
    candidates = set()
    for tok in re.findall(r"[A-Za-z]{4,}", query):
        t_lower = tok.lower()
        if t_lower in STOPWORDS:
            continue
        t_key = "".join(c for c in t_lower if c.isalnum())
        if not t_key:
            continue
        candidates.add(t_key)
        if t_key.endswith("s") and len(t_key) > 4:
            candidates.add(t_key[:-1])
    for cand in candidates:
        try:
            resp = ents.query.fetch_objects(
                filters=wvc.query.Filter.by_property("search_key").like(f"*{cand}*"),
                limit=25,
                return_properties=["name", "category", "description"],
            )
            for o in resp.objects:
                nm = o.properties.get("name")
                if nm and nm not in seen:
                    seen.add(nm)
                    substring_hits.append({
                        "path": f"substring:{cand}",
                        "name": nm,
                        "category": o.properties.get("category"),
                        "description": (o.properties.get("description") or "")[:80],
                    })
        except Exception as e:
            print(f"  substring[{cand!r}] error: {e}")

    combined_names = bm25_names + [h["name"] for h in substring_hits]
    target_rank = None
    if target:
        for i, nm in enumerate(combined_names, start=1):
            if nm and nm.lower() == target.lower():
                target_rank = i
                break

    return {
        "query": query, "target": target, "target_rank": target_rank,
        "bm25_hits": bm25_hits, "substring_hits": substring_hits,
        "combined_names": combined_names,
        "substring_candidates": sorted(candidates),
    }


def print_result(pol: str, r: dict, show: int = 15) -> None:
    print()
    print("=" * 100)
    print(f"[{pol}] QUERY: {r['query']!r}")
    if r["target"]:
        marker = f"rank {r['target_rank']} in combined" if r["target_rank"] else "NOT IN COMBINED"
        print(f"  target: {r['target']!r} -> {marker}")
    print(f"  substring candidates: {r['substring_candidates']}")
    print("-" * 100)
    print(f"  BM25 top-{show}:")
    print(f"    {'rk':>3} {'score':>7} {'category':22} {'name':40} {'description':40}")
    for i, h in enumerate(r["bm25_hits"][:show], start=1):
        star = "*" if r["target"] and h["name"] and h["name"].lower() == r["target"].lower() else " "
        s = h.get("score") or 0.0
        print(f"   {star}{i:>3} {s:>7.4f} {(h['category'] or '')[:22]:22} "
              f"{(h['name'] or '')[:40]:40} {(h['description'] or '')[:40]}")
    print(f"  Substring hits added ({len(r['substring_hits'])}):")
    for i, h in enumerate(r["substring_hits"][:show], start=1):
        star = "*" if r["target"] and h["name"] and h["name"].lower() == r["target"].lower() else " "
        print(f"   {star}{i:>3}  {h['path']:22} {(h['category'] or '')[:22]:22} "
              f"{(h['name'] or '')[:40]:40} {(h['description'] or '')[:40]}")
    if not r["bm25_hits"] and not r["substring_hits"]:
        print("    (nothing surfaced — the fallback triggers to hardcoded 3 entities)")


def main():
    client = weaviate.connect_to_custom(
        http_host=WEAVIATE_HOST, http_port=80, http_secure=False,
        grpc_host=WEAVIATE_GRPC_HOST, grpc_port=50051, grpc_secure=False,
        skip_init_checks=True,
    )
    try:
        results = []
        print("\n" + "#" * 100)
        print("# E-6 BM25 BASELINE — replicates current get_relevant_entities exactly")
        print("# For each query: shows what the CURRENT lookup returns, so the")
        print("# E-4 fix can be measured against a concrete counterfactual.")
        print("#" * 100)
        for pol, q, tgt in PROBES:
            r = probe_bm25(client, q, tgt)
            r["polarity"] = pol
            results.append(r)
            print_result(pol, r)

        print("\n\n" + "=" * 100)
        print("SUMMARY — current vs vector (from E-6 near_vector probe)")
        print("=" * 100)
        print(f"  {'polarity':10} {'query':52} {'BM25_rank':>10} {'BM25_top1':30}")
        print("-" * 100)
        for r in results:
            top1 = r["bm25_hits"][0]["name"] if r["bm25_hits"] else "(none)"
            tr = str(r["target_rank"] or "-") if r["target"] else "-"
            print(f"  {r['polarity']:10} {r['query'][:52]:52} {tr:>10} {top1[:30]:30}")

        out_path = Path(
            "C:/Users/cnogr/AppData/Local/Temp/claude/"
            "c--Users-cnogr-git-goat-yard-archive/af8134a4-98a5-4323-8e1d-fe16c91515a4/"
            "scratchpad/e6_bm25_baseline_results.json"
        )
        with out_path.open("w", encoding="utf-8") as f:
            # bm25 hits from Weaviate v4 metadata may not serialize cleanly;
            # normalize.
            def _slim(r):
                r = {**r}
                r["bm25_hits"] = [{**h} for h in r["bm25_hits"]]
                r["substring_hits"] = [{**h} for h in r["substring_hits"]]
                return r
            json.dump([_slim(r) for r in results], f, indent=2)
        print(f"\n  Raw: {out_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
