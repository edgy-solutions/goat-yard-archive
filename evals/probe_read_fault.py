# AS-RUN, 2026-10-04. This is the exact code that produced the numbers in
# docs/audits/READFAULT_mechanism_reproduction_laneA_20261004.md, committed so those numbers are
# checkable. Do NOT edit it in place: a changed probe no longer matches the recorded result, so a
# new version gets a new name.
#
# THREE DEFECTS IN THIS PROBE, found while reading its output and named in the report:
#   1. The unstable counter fires whenever len(vals) != K, so a page where ONE read failed to
#      PARSE flags all 20 of its objects even when the surviving reads agree. 372 of the 380
#      records it reported are this artifact; the real number of disagreements is 8. Separate
#      "a read was lost" from "two reads disagreed" before trusting the headline.
#   2. A two-read tie (2 surviving reads, 2 distinct digests) has majority 1 and no outlier, so
#      no disagreement shape is computed for it. 2 of the 8 real faults are unshaped.
#   3. Raw bodies are not retained on a fault, so block alignment -- the most discriminating
#      test available -- cannot be run from its output. page_stats is not serialised either.
#
# It writes its outputs NEXT TO ITSELF and hardcodes an absolute path for the backend import, so
# run it from a scratch copy, never from the repo tree.

"""Ruling 1c: locate the read-corruption mechanism with a reproduction.

READ-ONLY against the TEST corpus (192.168.1.54:80). Production (192.168.1.52) is never
addressed. No writes, no deletes, GET only.

Method: page the corpus exactly as the sampler does (limit=20&include=vector) and fetch each page
THREE times. Three rather than two because two reads that disagree cannot say which one is wrong,
and the claim already on the record -- "the start sample's digest is the suspect" -- is precisely
a claim about which read is the outlier. For every uuid whose rounded vector digest is not
identical across all three reads, record the shape of the disagreement and the majority structure.

Recorded per page so the mechanism has somewhere to show itself: the response body size of each
fetch, the elapsed time, the object count, and the HTTP content-length. If corruption tracks body
size we will see it; if it tracks a particular page or uuid we will see that instead.

PREDICTIONS, written before the run:
  P1  at least one uuid disagrees across a full-corpus pass (4 were observed across two arms)
  P2  the disagreement is 'elements' with a CONTIGUOUS run of differing indices, not scattered
      singletons -- that is the block-reassembly signature already documented for the visible
      half of this defect (READFAULT_corpus_vector_sha_false_positive_20261004.md)
  P3  2 of the 3 reads agree and 1 is the outlier, rather than all three differing
  P4  faulting pages are NOT distinguishable by body size from clean ones at limit=20, because
      every page at that limit is about the same size (~1.1 MB)
  P5  the rate is low: order 1 in 100 pages
"""
import io, json, os, sys, time

sys.path.insert(0, "C:/Users/cnogr/git/goatyard-laneA/backend")
import httpx
import corpus_fingerprint as CF
import fingerprint_rest as FR

IP = "192.168.1.54:80"
assert not IP.startswith("192.168.1.52"), "production is never addressed"
K = 3
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_1c_faults.json")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_1c_progress.log")


def fetch(url):
    t0 = time.perf_counter()
    r = httpx.get(url, timeout=120)
    dt = time.perf_counter() - t0
    body = r.text
    try:
        j = r.json()
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e), "bytes": len(body), "seconds": dt,
                "content_length": r.headers.get("content-length")}
    return {"json": j, "bytes": len(body), "seconds": dt,
            "content_length": r.headers.get("content-length")}


after = None
pages = 0
objects = 0
unstable = []
page_stats = []
log = io.open(LOG, "w", encoding="utf-8")
while True:
    url = "http://%s/v1/objects?class=CommentaryChunk&limit=20&include=vector" % IP
    if after:
        url += "&after=%s" % after
    reads = [fetch(url) for _ in range(K)]
    errs = [r for r in reads if "error" in r]
    first = next((r for r in reads if "json" in r), None)
    if first is None:
        log.write("page %d: ALL %d reads failed to parse: %s\n"
                  % (pages, K, [r["error"] for r in reads]))
        break
    objs = first["json"].get("objects", [])
    if not objs:
        break
    pages += 1
    objects += len(objs)
    page_stats.append({"page": pages, "after": after, "n": len(objs),
                       "bytes": [r["bytes"] for r in reads],
                       "seconds": [round(r["seconds"], 2) for r in reads],
                       "errors": [r.get("error") for r in reads if "error" in r]})

    # per-uuid digest across the K reads that parsed
    digests = {}
    vectors = {}
    for i, r in enumerate(reads):
        if "json" not in r:
            continue
        for o in r["json"].get("objects", []):
            uid = o.get("id")
            v = FR._extract_vector(o)
            digests.setdefault(uid, {})[i] = CF._vec_digest(v)
            vectors.setdefault(uid, {})[i] = v
    for uid, per_read in digests.items():
        vals = list(per_read.values())
        if len(set(vals)) == 1 and len(vals) == K:
            continue
        counts = {}
        for d in vals:
            counts[d] = counts.get(d, 0) + 1
        majority = max(counts.values())
        outlier_reads = [i for i, d in per_read.items() if counts[d] != majority]
        shape = None
        if outlier_reads:
            good = next(i for i, d in per_read.items() if counts[d] == majority)
            shape = FR.vector_disagreement(vectors[uid].get(good), vectors[uid].get(
                outlier_reads[0], FR._ABSENT))
        rec = {"uuid": uid, "page": pages, "after": after, "reads_seen": len(vals),
               "distinct_digests": len(counts), "majority": majority,
               "outlier_reads": outlier_reads, "shape": shape,
               "page_bytes": [r["bytes"] for r in reads]}
        unstable.append(rec)
        log.write("UNSTABLE %s\n" % json.dumps(rec)[:600])
        log.flush()
    if errs:
        log.write("page %d: %d of %d reads failed to parse\n" % (pages, len(errs), K))
    if pages % 25 == 0:
        log.write("...%d pages, %d objects, %d unstable so far\n" % (pages, objects, len(unstable)))
        log.flush()
    after = objs[-1]["id"]

summary = {"ip": IP, "reads_per_page": K, "pages": pages, "objects": objects,
           "n_unstable": len(unstable), "unstable": unstable,
           "page_bytes_min": min((min(p["bytes"]) for p in page_stats), default=None),
           "page_bytes_max": max((max(p["bytes"]) for p in page_stats), default=None),
           "pages_with_parse_errors": sum(1 for p in page_stats if p["errors"])}
io.open(OUT, "w", encoding="utf-8").write(json.dumps(summary, indent=1))
log.write("\nDONE pages=%d objects=%d unstable=%d\n" % (pages, objects, len(unstable)))
log.close()
print(json.dumps({k: v for k, v in summary.items() if k != "unstable"}, indent=1))
print("faults -> %s" % OUT)
