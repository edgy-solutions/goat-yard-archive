"""E-11 — ceremonial-homonym sweep, partitioned by cause.

CAVEAT (ADR-0014, added 2026-07-26): the verdicts below are
MANIFEST-DEPENDENT and predate entity-lookup mode instrumentation. Each
row ran in whatever litellm health dictated that hour, unrecorded. The
'atonement' "no hijack" result specifically is conditional on a HEALTHY
vector tier — with the tier degraded, atonement collapses to Leviticus
(that collapse is what motivated ADR-0014). Re-run with entity_lookup_mode
recorded before treating any single-run verdict here as unconditional.

The 2026-07-19/20 universal_atonement investigation established that
"atonement" is lexically ambiguous in this corpus: the ceremonial sense
(Day of Atonement ritual, sin-offerings — dense in Leviticus/Numbers)
outranks the soteriological sense on pure embedding similarity, AND the
entity lookup returns ceremonial entities ('day of atonement') that
boost toward the same place. Genesis-Numbers + Gospels is exceptionally
rich in ceremonial material and poor in the epistolary doctrine where
Gill argues these positions.

This sweep asks whether the pattern generalizes, and — critically —
PARTITIONS each term by cause, because two very different diseases
present with the same symptom:

  CASE A (ranking problem): doctrinal Gill material EXISTS in the
    indexed volumes but ceremonial chunks outrank it. Fixable at the
    retrieval/generation layer now.

  CASE B (corpus gap): no doctrinal material exists to find. Retrieval
    is faithfully returning the best available match. The honest fix is
    the informative refusal + ingesting Romans/Hebrews. Tuning
    retrieval would only re-rank an empty set.

Method per term:
  1. NORMAL query — the plain doctrinal question. Record the ceremonial
     hijack: how many of top-12 are Leviticus/Numbers ritual chunks.
  2. DOCTRINAL PROBE — a deliberately doctrine-phrased query and/or a
     verse-anchored lookup where doctrinal treatment is expected
     (e.g. JOHN 17:17 for sanctification, MATTHEW 20:28 'ransom for
     many' for redemption). Does doctrinal Gill material surface at
     all?
  3. Partition: doctrinal material found by probe but missed by the
     normal query -> CASE A. Not found by either -> CASE B.

Manifest is held FIXED per condition (passed explicitly) because the
2026-07-20 investigation showed manifest COMPOSITION is the decisive
lever and varying it silently confounds the comparison.
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
os.environ.setdefault("APP_ENV", "e11-probe")

sys.path.insert(0, str(Path("C:/Users/cnogr/git/goat-yard-archive")))
from dotenv import load_dotenv
load_dotenv()
from backend.gill_search import GillSearchEngine  # noqa: E402


CEREMONIAL_BOOKS = ("LEVITICUS", "NUMBERS", "EXODUS")

# term -> (normal query, doctrinal probe query, verse-anchored probe)
TERMS = [
    ("atonement",
     "Did Jesus preach a universal atonement?",
     "for whom did Christ die, the elect or all men",
     "Matthew 20:28"),
    ("redemption",
     "What does Gill say about redemption?",
     "Christ redeemed his people by his blood particular redemption",
     "Matthew 20:28"),
    ("sacrifice",
     "What does Gill say about sacrifice?",
     "Christ offered himself once for sin as a sacrifice",
     "John 1:29"),
    ("propitiation",
     "What does Gill say about propitiation?",
     "Christ is the propitiation for our sins",
     "John 2:2"),
    ("sanctification",
     "What does Gill say about sanctification?",
     "believers are sanctified by the Spirit and the truth",
     "John 17:17"),
    ("cleansing",
     "What does Gill say about cleansing from sin?",
     "the blood of Christ cleanses from all sin",
     "John 13:10"),
]


def ceremonial_count(refs):
    return sum(1 for r in refs if r and r.split()[0] in CEREMONIAL_BOOKS)


def gospel_count(refs):
    return sum(1 for r in refs if r and r.split()[0] in ("JOHN", "LUKE", "MARK", "MATTHEW"))


async def main():
    engine = GillSearchEngine()
    await engine.connect()
    rows = []
    try:
        print("=" * 104)
        print("E-11 CEREMONIAL-HOMONYM SWEEP (partitioned by cause)")
        print("ceremonial books = LEVITICUS/NUMBERS/EXODUS; gospel = JOHN/LUKE/MARK/MATTHEW")
        print("=" * 104)
        for term, normal_q, doctrinal_q, verse_q in TERMS:
            # ADR-0014: get_relevant_entities now returns (names, mode).
            manifest, manifest_mode = await engine.get_relevant_entities(query=normal_q)

            async def refs_for(q, ents):
                r = await engine.search_gill(query=q, entities=ents, limit=12, original_query=q)
                return [c.get("verse_ref") or "" for c in r]

            doct_manifest, _ = await engine.get_relevant_entities(query=doctrinal_q)
            normal_refs = await refs_for(normal_q, manifest)
            doct_refs = await refs_for(doctrinal_q, doct_manifest)
            verse_refs = await refs_for(verse_q, [])

            n_cer, n_gos = ceremonial_count(normal_refs), gospel_count(normal_refs)
            d_cer, d_gos = ceremonial_count(doct_refs), gospel_count(doct_refs)

            # doctrinal material reachable? gospel-book chunks surfacing on the
            # doctrinal probe or the verse anchor is the proxy for "exists".
            doctrinal_reachable = d_gos >= 4 or gospel_count(verse_refs) >= 1
            hijacked = n_cer >= 6
            if hijacked and doctrinal_reachable:
                verdict = "CASE A (ranking - fixable now)"
            elif hijacked and not doctrinal_reachable:
                verdict = "CASE B (corpus gap - needs ingestion)"
            elif not hijacked:
                verdict = "no hijack"
            else:
                verdict = "?"

            print()
            print(f"--- {term.upper()} ---")
            print(f"  manifest ({manifest_mode}): {manifest}")
            print(f"  normal    : cer={n_cer:2} gos={n_gos:2}  {normal_refs[:5]}")
            print(f"  doctrinal : cer={d_cer:2} gos={d_gos:2}  {doct_refs[:5]}")
            print(f"  verse({verse_q}): {verse_refs[:3]}")
            print(f"  => {verdict}")
            rows.append({
                "term": term, "manifest": manifest,
                "normal_cer": n_cer, "normal_gos": n_gos, "normal_refs": normal_refs,
                "doctrinal_cer": d_cer, "doctrinal_gos": d_gos, "doctrinal_refs": doct_refs,
                "verse_refs": verse_refs, "verdict": verdict,
            })

        print()
        print("=" * 104)
        print("SUMMARY")
        print("=" * 104)
        print(f"  {'term':16} {'normal cer/gos':16} {'doctrinal cer/gos':18} verdict")
        print("-" * 104)
        for r in rows:
            print(f"  {r['term']:16} {str(r['normal_cer'])+'/'+str(r['normal_gos']):16} "
                  f"{str(r['doctrinal_cer'])+'/'+str(r['doctrinal_gos']):18} {r['verdict']}")

        out = Path(__file__).parent / "e11_homonym_partition_results.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        print(f"\n  Raw: {out}")
    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
