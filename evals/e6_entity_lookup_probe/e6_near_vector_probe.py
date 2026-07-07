"""E-6 diagnostic probe (recall + precision + threshold).

Tests whether replacing the BM25/substring entity lookup with `near_vector`
(a) recovers the concept-bridge failures (Hallel for 'exclusive psalmody' etc.),
(b) keeps the top-K clean (not flooded with topically-off entities), and
(c) has a similarity CLIFF between "genuinely adjacent" and "vector always
    returns this" — the threshold that E-4's tiered merge will need.

The probe MUST test both polarities:
  IN-DOMAIN (3):   expect high-recall top-1/top-5, precision matters
  OUT-OF-DOMAIN (2): expect distances to stay ABOVE the threshold — if not,
                    E-4 needs a cap+threshold, not a plain union.

Weaviate cosine distance: 0 = identical, 2 = opposite. Lower is closer.
"""
import io
import json
import sys
import urllib.request
from pathlib import Path

# Force UTF-8 on stdout so entity descriptions with quotes/accents don't crash.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import weaviate
import weaviate.classes as wvc

WEAVIATE_HOST = "192.168.1.54"      # gya-test HTTP LB
WEAVIATE_GRPC_HOST = "192.168.1.53"  # gya-test gRPC LB
OLLAMA_URL = "http://192.168.1.179:11434/api/embeddings"
OLLAMA_MODEL = "qwen3-embedding"

# TOP-K for the diagnostic — deliberately much larger than the eventual
# retrieval K so we can see the score-cliff AND where our target entities
# actually rank on the semantic list.
K = 100

IN_DOMAIN = [
    ("exclusive psalmody", "Hallel"),
    ("universal atonement in Christ", "Atonement"),
    ("is the covenant of grace monocovenantal", "covenant of grace"),
]
OUT_OF_DOMAIN = [
    ("how do I write a for loop in javascript", None),
    ("did Esau eat pizza", None),
]
# Sanity probes — direct entity name / gloss lookups. If these do not top
# the list, qwen3-embedding is not tracking the entity vectors as we
# expect and near_vector alone is not sufficient regardless of threshold.
SANITY = [
    ("Hallel", "Hallel"),
    ("Passover hymn consisting of Psalms 113-118", "Hallel"),
    ("universal atonement", "Atonement"),
    ("covenant of grace", "covenant of grace"),
]


def embed(text: str) -> list[float]:
    body = json.dumps({"model": OLLAMA_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    v = d.get("embedding") or []
    if not v:
        raise RuntimeError(f"empty embedding for {text!r}: {d}")
    return v


def probe(client, query: str, target: str | None, k: int = K) -> dict:
    ents = client.collections.get("TheologicalEntity")
    vec = embed(query)
    resp = ents.query.near_vector(
        near_vector=vec,
        limit=k,
        return_metadata=wvc.query.MetadataQuery(distance=True),
        return_properties=["name", "category", "categories", "description"],
    )
    hits = []
    for i, o in enumerate(resp.objects):
        p = o.properties
        hits.append({
            "rank": i + 1,
            "distance": o.metadata.distance,
            "name": p.get("name"),
            "category": p.get("category"),
            "categories": p.get("categories"),
            "description": (p.get("description") or "")[:100],
        })
    target_rank = None
    if target:
        for h in hits:
            if h["name"] and h["name"].lower() == target.lower():
                target_rank = h["rank"]
                break
    return {"query": query, "target": target, "target_rank": target_rank, "hits": hits}


def print_result(r: dict, show: int = 25) -> None:
    q = r["query"]; target = r["target"]; tr = r["target_rank"]
    print()
    print("=" * 100)
    print(f"QUERY: {q!r}")
    if target:
        marker = f"rank {tr} of top-{K}" if tr else f"NOT IN TOP-{K}"
        print(f"  target: {target!r}  ->  {marker}")
    else:
        print("  target: (out-of-domain, no target)")
    print("-" * 100)
    print(f"  {'rk':>3} {'dist':>8} {'category':22} {'name':40} {'description':40}")
    print("-" * 100)
    for h in r["hits"][:show]:
        star = "*" if target and h["name"] and h["name"].lower() == target.lower() else " "
        print(f" {star}{h['rank']:>3} {h['distance']:>8.4f} {(h['category'] or '')[:22]:22} "
              f"{(h['name'] or '')[:40]:40} {h['description'][:40]}")
    if target and tr and tr > show:
        # Show a small window around the target row so we can see the
        # neighborhood at its actual rank.
        print("   ...")
        window = [h for h in r["hits"] if abs(h["rank"] - tr) <= 2]
        for h in window:
            star = "*" if h["name"] and h["name"].lower() == target.lower() else " "
            print(f" {star}{h['rank']:>3} {h['distance']:>8.4f} {(h['category'] or '')[:22]:22} "
                  f"{(h['name'] or '')[:40]:40} {h['description'][:40]}")
    # Distance-cliff diagnostic — look at gap between consecutive ranks
    # and print the biggest step-jumps in the top-K.
    ds = [h["distance"] for h in r["hits"]]
    gaps = [(i + 1, ds[i + 1] - ds[i]) for i in range(len(ds) - 1)]
    gaps.sort(key=lambda g: g[1], reverse=True)
    print("  biggest distance-jumps (rank X -> X+1, delta):")
    for rk, dg in gaps[:5]:
        print(f"    rank {rk} -> {rk+1}: +{dg:.4f}  (from {ds[rk-1]:.4f} to {ds[rk]:.4f})")


def main():
    client = weaviate.connect_to_custom(
        http_host=WEAVIATE_HOST, http_port=80, http_secure=False,
        grpc_host=WEAVIATE_GRPC_HOST, grpc_port=50051, grpc_secure=False,
        skip_init_checks=True,
    )
    try:
        results = {"sanity": [], "in_domain": [], "out_of_domain": []}
        print("\n" + "#" * 100)
        print("# E-6: near_vector probe -- recall + precision + threshold")
        print("# distance = cosine distance (0=identical, 2=opposite); LOWER = closer")
        print(f"# K={K}")
        print("#" * 100)

        print("\n\n" + "#" * 60 + "\n### SANITY (direct name / gloss lookups)\n" + "#" * 60)
        for q, tgt in SANITY:
            r = probe(client, q, tgt)
            results["sanity"].append(r)
            print_result(r, show=10)

        print("\n\n" + "#" * 60 + "\n### IN-DOMAIN (conceptual queries)\n" + "#" * 60)
        for q, tgt in IN_DOMAIN:
            r = probe(client, q, tgt)
            results["in_domain"].append(r)
            print_result(r, show=25)

        print("\n\n" + "#" * 60 + "\n### OUT-OF-DOMAIN\n" + "#" * 60)
        for q, _ in OUT_OF_DOMAIN:
            r = probe(client, q, None)
            results["out_of_domain"].append(r)
            print_result(r, show=15)

        print("\n\n" + "=" * 100)
        print("SUMMARY — distance distributions per query")
        print("=" * 100)
        print(f"  {'polarity':12} {'query':52} {'min':>7} {'max':>7} {'tgt_rk':>7} {'top1_name':30}")
        print("-" * 100)
        for pol, rows in [("sanity", results["sanity"]),
                          ("in-domain", results["in_domain"]),
                          ("OOD", results["out_of_domain"])]:
            for r in rows:
                ds = [h["distance"] for h in r["hits"]]
                lo = min(ds) if ds else float("nan")
                hi = max(ds) if ds else float("nan")
                top1 = (r["hits"][0]["name"] or "") if r["hits"] else ""
                tr = str(r["target_rank"] or "-") if r["target"] else "-"
                print(f"  {pol:12} {r['query'][:52]:52} {lo:>7.4f} {hi:>7.4f} {tr:>7} {top1[:30]:30}")

        out_path = Path(
            "C:/Users/cnogr/AppData/Local/Temp/claude/"
            "c--Users-cnogr-git-goat-yard-archive/af8134a4-98a5-4323-8e1d-fe16c91515a4/"
            "scratchpad/e6_near_vector_results.json"
        )
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n  Raw: {out_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
