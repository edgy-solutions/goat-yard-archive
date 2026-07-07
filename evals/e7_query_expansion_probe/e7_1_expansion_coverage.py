"""E-7.1 — does query-side vocabulary expansion bridge the psalmody gap?

ADR-0010 established that qwen3-embedding represents 'exclusive psalmody'
and 'Hallel' in DIFFERENT neighborhoods, and the theological association
between them lives in the reader's head, not in the embedding space.
ADR-0010's proposed fix (out of its own scope): rewrite the user query
BEFORE the entity lookup so it contains vocabulary that IS embedding-
adjacent to the anchor entity.

This probe measures whether that fix is architecturally viable by
testing several expansion shapes for 'exclusive psalmody':
  (1) direct-name injection: append 'Hallel'
  (2) descriptor injection: append 'Psalms 113-118 Passover hymn'
       (paraphrasing the entity's stored description)
  (3) domain-vocabulary injection: append 'psalms singing worship' (the
       general Reformed-worship neighborhood the entity sits in)
  (4) rephrasing: replace the narrow term entirely with a paraphrase

For each variant, we report:
  - Hallel's rank in near_vector top-100
  - Hallel's cosine distance
  - Whether Hallel enters ADR-0010's confident tier (dist <= 0.25)
  - Top-5 neighbors — for the precision-of-top-K read the reviewer named

A parallel probe on other Reformed-narrow-vocabulary terms (federal
headship, regulative principle, monergism, covenant of redemption)
establishes E-7.2's scope — which of these need expansion and which
already have adequate embedding anchors.
"""
import io
import json
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

CONFIDENT_TIER_MAX = 0.25   # per ADR-0010

# --- E-7.1: expansion shapes for the exclusive_psalmody flagship case ---
PSALMODY_VARIANTS = [
    ("baseline", "exclusive psalmody", "Hallel"),
    ("name-inject", "exclusive psalmody Hallel", "Hallel"),
    ("descriptor-inject", "exclusive psalmody Psalms 113-118 Passover hymn", "Hallel"),
    ("domain-vocab", "exclusive psalmody psalms singing worship hymn", "Hallel"),
    ("rephrase-modern", "Are Psalms the only songs a church should sing?", "Hallel"),
    ("rephrase-passover-focus", "singing Psalms at Passover Hallel", "Hallel"),
    ("rephrase-worship-focus", "singing psalms in Christian worship", "Hallel"),
]

# --- E-7.2 preview: does the same shape recur for other Reformed-narrow terms? ---
NARROW_TERM_PROBES = [
    ("federal headship",              "Adam"),      # Adam as federal head
    ("federal headship",              "Christ"),    # Christ as second Adam
    ("regulative principle",          None),        # no obvious single entity anchor
    ("monergism",                     "electing grace"),
    ("covenant of redemption",        "covenant engagements"),
    ("pactum salutis",                "covenant engagements"),
    ("sabbatarian",                   None),
    ("imputation",                    "justifying righteousness of Christ"),
    ("effectual calling",             "calling grace"),
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
        raise RuntimeError(f"empty embedding: {d}")
    return v


def near_vector_probe(client, query: str, target: str | None, k: int = 100) -> dict:
    ents = client.collections.get("TheologicalEntity")
    vec = embed(query)
    resp = ents.query.near_vector(
        near_vector=vec,
        limit=k,
        return_metadata=wvc.query.MetadataQuery(distance=True),
        return_properties=["name", "category", "description"],
    )
    hits = []
    for i, o in enumerate(resp.objects):
        p = o.properties
        hits.append({
            "rank": i + 1,
            "distance": o.metadata.distance,
            "name": p.get("name"),
            "category": p.get("category"),
            "description": (p.get("description") or "")[:80],
        })
    target_rank = None
    target_distance = None
    if target:
        for h in hits:
            if h["name"] and h["name"].lower() == target.lower():
                target_rank = h["rank"]
                target_distance = h["distance"]
                break
    top5 = hits[:5]
    return {
        "query": query, "target": target,
        "target_rank": target_rank, "target_distance": target_distance,
        "confident_tier_reached": target_distance is not None and target_distance <= CONFIDENT_TIER_MAX,
        "top5": top5,
    }


def _fmt_top5(top5: list[dict], target: str | None) -> str:
    out = []
    for h in top5:
        star = "*" if target and h["name"] and h["name"].lower() == target.lower() else " "
        out.append(f"    {star}{h['rank']}. d={h['distance']:.4f}  [{(h['category'] or '')[:16]:16}] {(h['name'] or '')[:38]:38} {h['description'][:40]}")
    return "\n".join(out)


def main():
    client = weaviate.connect_to_custom(
        http_host=WEAVIATE_HOST, http_port=80, http_secure=False,
        grpc_host=WEAVIATE_GRPC_HOST, grpc_port=50051, grpc_secure=False,
        skip_init_checks=True,
    )
    try:
        print("\n" + "#" * 100)
        print("# E-7.1 — psalmody expansion coverage: does adding descriptor vocabulary")
        print("# bridge 'exclusive psalmody' -> 'Hallel' at the vector layer?")
        print(f"# confident-tier threshold = {CONFIDENT_TIER_MAX} (ADR-0010)")
        print("#" * 100)

        psalmody_results = []
        for label, q, tgt in PSALMODY_VARIANTS:
            r = near_vector_probe(client, q, tgt)
            r["label"] = label
            psalmody_results.append(r)
            tr = r["target_rank"] or "(>100)"
            td = f"{r['target_distance']:.4f}" if r["target_distance"] is not None else "(n/a)"
            ct = "YES" if r["confident_tier_reached"] else "no "
            print()
            print("=" * 100)
            print(f"[{label:24}] query={q!r}")
            print(f"    target: {tgt!r}  rank: {tr}  dist: {td}  confident_tier: {ct}")
            print("    top-5:")
            print(_fmt_top5(r["top5"], tgt))

        print("\n\n" + "#" * 100)
        print("# E-7.2 preview — other Reformed-narrow vocabulary terms")
        print("# (which are already-reachable vs need-expansion)")
        print("#" * 100)

        narrow_results = []
        for q, tgt in NARROW_TERM_PROBES:
            r = near_vector_probe(client, q, tgt)
            narrow_results.append(r)
            tr = r["target_rank"] or "(>100 or no target)"
            td = f"{r['target_distance']:.4f}" if r["target_distance"] is not None else "-"
            ct = "YES" if r["confident_tier_reached"] else "no "
            print()
            print("=" * 100)
            print(f"query={q!r}  target_candidate={tgt!r}")
            print(f"    rank: {tr}  dist: {td}  confident_tier: {ct}")
            print("    top-5:")
            print(_fmt_top5(r["top5"], tgt))

        print("\n\n" + "=" * 100)
        print("SUMMARY — E-7.1: which expansion shape reaches Hallel?")
        print("=" * 100)
        print(f"  {'shape':24} {'rank':>10} {'dist':>10} {'confident_tier':>18}")
        print("-" * 100)
        for r in psalmody_results:
            tr = str(r["target_rank"]) if r["target_rank"] else ">100"
            td = f"{r['target_distance']:.4f}" if r["target_distance"] is not None else "-"
            ct = "YES" if r["confident_tier_reached"] else "no"
            print(f"  {r['label']:24} {tr:>10} {td:>10} {ct:>18}")

        print()
        print("=" * 100)
        print("SUMMARY — E-7.2: which narrow terms are already vector-reachable?")
        print("=" * 100)
        print(f"  {'query':30} {'candidate':30} {'rank':>10} {'dist':>10}")
        print("-" * 100)
        for r in narrow_results:
            tr = str(r["target_rank"]) if r["target_rank"] else "-"
            td = f"{r['target_distance']:.4f}" if r["target_distance"] is not None else "-"
            print(f"  {r['query'][:30]:30} {(r['target'] or '(no target)')[:30]:30} {tr:>10} {td:>10}")

        out_path = Path(__file__).parent / "e7_1_expansion_coverage_results.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump({
                "psalmody_variants": psalmody_results,
                "narrow_terms": narrow_results,
            }, f, indent=2)
        print(f"\n  Raw: {out_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
