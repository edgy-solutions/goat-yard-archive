"""E-6b post-fix validation.

Reproduces the ADR-0010 tiered lookup logic (confident vector <= 0.25 cap
3, then substring canonical-key, then BM25 cap 3, total union cap 5) and
prints the exact 5-entity manifest each flagship query would produce
against the deployed gya-test cluster. Purpose: establish the concrete
post-fix behavior BEFORE the commit ships, so the ADR's claims are
verified evidence, not asserted.
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
OLLAMA_URL = "http://192.168.1.179:11434/api/embeddings"
OLLAMA_MODEL = "qwen3-embedding"

# ADR-0010 constants
VECTOR_CONFIDENT_DIST_MAX = 0.25
VECTOR_TIER_CAP = 3
MANIFEST_TOTAL_CAP = 5

# Same stopword set as backend/gill_search.py._ENTITY_LOOKUP_STOPWORDS.
STOPWORDS = {
    "how", "many", "what", "when", "where", "which", "who", "whom", "why",
    "the", "and", "are", "was", "were", "for", "with", "that", "this",
    "from", "did", "does", "have", "has", "had", "been", "into", "out",
    "over", "than", "then", "there", "their", "they", "them", "those",
    "these", "your", "yours", "you", "his", "her", "him", "she", "all",
    "any", "one", "two", "but", "not", "can", "will", "should", "could",
    "would", "about", "say", "said", "tell", "told", "make", "made",
    "mean", "means", "meaning", "give", "given", "gives", "name", "names",
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


def embed(text: str) -> list[float]:
    body = json.dumps({"model": OLLAMA_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    return d.get("embedding") or []


def tiered_lookup(client, query: str) -> dict:
    ents = client.collections.get("TheologicalEntity")

    # Tier 1 — confident vector
    vector_names = []
    vector_details = []
    try:
        vec = embed(query)
        resp = ents.query.near_vector(
            near_vector=vec,
            limit=VECTOR_TIER_CAP,
            distance=VECTOR_CONFIDENT_DIST_MAX,
            return_metadata=wvc.query.MetadataQuery(distance=True),
            return_properties=["name"],
        )
        for o in resp.objects:
            nm = o.properties.get("name")
            if nm:
                vector_names.append(nm)
                vector_details.append({"name": nm, "distance": o.metadata.distance})
    except Exception as e:
        print(f"  vector error: {e}")

    # Tier 2 — substring canonical-key
    substring_names = []
    substring_details = []
    seen_lower = {n.lower() for n in vector_names}
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
                return_properties=["name"],
            )
            for o in resp.objects:
                nm = o.properties.get("name")
                if nm and nm.lower() not in seen_lower:
                    seen_lower.add(nm.lower())
                    substring_names.append(nm)
                    substring_details.append({"name": nm, "matched_via": cand})
        except Exception as e:
            print(f"  substring[{cand!r}] error: {e}")

    # Tier 3 — BM25
    bm25_names = []
    bm25_details = []
    try:
        resp = ents.query.bm25(
            query=query,
            limit=VECTOR_TIER_CAP,
            return_metadata=wvc.query.MetadataQuery(score=True),
            return_properties=["name"],
        )
        for o in resp.objects:
            nm = o.properties.get("name")
            if nm and nm.lower() not in seen_lower:
                seen_lower.add(nm.lower())
                bm25_names.append(nm)
                bm25_details.append({"name": nm, "score": o.metadata.score})
    except Exception as e:
        print(f"  bm25 error: {e}")

    combined = (vector_names + substring_names + bm25_names)[:MANIFEST_TOTAL_CAP]
    return {
        "query": query,
        "vector": vector_details,
        "substring": substring_details,
        "bm25": bm25_details,
        "combined": combined,
    }


def main():
    client = weaviate.connect_to_custom(
        http_host=WEAVIATE_HOST, http_port=80, http_secure=False,
        grpc_host=WEAVIATE_GRPC_HOST, grpc_port=50051, grpc_secure=False,
        skip_init_checks=True,
    )
    try:
        results = []
        print("\n" + "#" * 100)
        print("# E-6b POST-FIX VALIDATION")
        print(f"# ADR-0010 tiered lookup: vector(dist<={VECTOR_CONFIDENT_DIST_MAX}, cap {VECTOR_TIER_CAP})")
        print(f"#                       + substring canonical-key")
        print(f"#                       + BM25 (cap {VECTOR_TIER_CAP})")
        print(f"#                       -> dedup, total cap {MANIFEST_TOTAL_CAP}")
        print("#" * 100)

        for pol, q, tgt in PROBES:
            r = tiered_lookup(client, q)
            r["polarity"] = pol
            r["target"] = tgt
            r["target_in_manifest"] = tgt is not None and any(
                (n or "").lower() == tgt.lower() for n in r["combined"]
            )
            results.append(r)

            print()
            print("=" * 100)
            print(f"[{pol}] QUERY: {q!r}")
            if tgt:
                mark = "TARGET IN MANIFEST" if r["target_in_manifest"] else "TARGET ABSENT"
                print(f"  target: {tgt!r}  -> {mark}")
            print("-" * 100)
            print(f"  Tier 1 vector (dist<={VECTOR_CONFIDENT_DIST_MAX}, cap {VECTOR_TIER_CAP}):")
            if r["vector"]:
                for v in r["vector"]:
                    print(f"    - {v['name']!r} (d={v['distance']:.4f})")
            else:
                print(f"    (empty — no entity below distance threshold)")
            print(f"  Tier 2 substring (per-token, dedup):")
            if r["substring"][:5]:
                for s in r["substring"][:5]:
                    print(f"    - {s['name']!r} (via {s['matched_via']!r})")
                if len(r["substring"]) > 5:
                    print(f"    ... + {len(r['substring']) - 5} more (all dropped by total cap)")
            else:
                print(f"    (empty)")
            print(f"  Tier 3 BM25 (cap {VECTOR_TIER_CAP}, dedup):")
            if r["bm25"]:
                for b in r["bm25"]:
                    print(f"    - {b['name']!r} (score={b['score']:.4f})")
            else:
                print(f"    (empty — all dedup'd out)")
            print(f"  FINAL MANIFEST (top {MANIFEST_TOTAL_CAP}):")
            for i, n in enumerate(r["combined"], start=1):
                star = "*" if tgt and n.lower() == tgt.lower() else " "
                print(f"    {star}{i}. {n}")

        print("\n\n" + "=" * 100)
        print("SUMMARY — target-in-manifest by query")
        print("=" * 100)
        print(f"  {'polarity':10} {'query':52} {'target_in_manifest':>20} {'manifest_size':>15}")
        print("-" * 100)
        for r in results:
            tim = "YES" if r["target_in_manifest"] else ("-" if r["target"] is None else "no")
            print(f"  {r['polarity']:10} {r['query'][:52]:52} {tim:>20} {len(r['combined']):>15}")

        out_path = Path(__file__).parent / "e6b_post_fix_results.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n  Raw: {out_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
