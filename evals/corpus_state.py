"""The corpus half of run integrity: WHICH corpus a run measured, asked of the corpus itself.

`integrity.git` records the code that ran. Nothing recorded the DATA it ran against, and on
2026-09-27 that gap ate a measurement: nf1 and pf1 differ by 9 questions out of 28 with the same
commit, the same pin, the same model and the same cache setting, and the shift cannot be attributed
because neither artifact says what was in Weaviate at the time. The corpus is a shared remote
instance that any lane, any ingest and any re-vectorisation can move, and the config hash cannot
see it. So: ask the instance, at run start and at run end, and record the answer.

Two hashes, not one, because the two failure modes are independent:

  * `content_sha256` moves when the TEXT changes -- a re-extraction, a repair, a dropped chunk.
  * `vector_sha256` moves when the EMBEDDINGS change while every byte of text stays identical.
    A re-vectorisation with a different model rewrites retrieval order under a corpus that looks
    untouched, which is the most plausible unattributed cause of a pass-rate shift and the one a
    text-only fingerprint is blind to.

Asymmetric treatment, deliberately, following `answer_lm_record.pin_honored`:

  * a corpus that CHANGED mid-run is a VIOLATION. The measurement is of a moving target and the
    run must fail loudly.
  * a corpus that could not be READ is PROVISIONAL, not a violation. Retrieval reaches Weaviate
    over gRPC on one host while this fingerprint reads REST on another, so a metadata network
    hiccup must not turn a completed run into a nonzero exit. An unstamped run simply cannot be
    cited, which is the cheapest wrong answer available here.
  * whether the corpus changed is a THREE-state question. If either sample is missing, the answer
    is None -- unknowable -- never False. Reporting an unread corpus as unchanged is how a run
    claims a stability it never checked.

Cost, measured against 192.168.1.54 on 2026-09-27 with 7294 chunks: 79.8s for text+vectors
(7294/7294 vectors hashed), roughly 15s text-only. Twice per run, against runs that take tens of
minutes. The estimate from a single page latency was 27.6s, which was wrong by 2.9x: cursor paging
slows as the cursor advances, so quote the measured number and not the extrapolation.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

# Same convention as answer_lm_record: a reason string that begins with this prefix means "we did
# not find out", and is never confused with a finding.
UNAVAILABLE = "unavailable:"

# The fields that decide corpus identity. `chunk_count` is redundant with `counts` and kept because
# a human reads it first.
IDENTITY_FIELDS = ("counts", "chunk_count", "content_sha256", "vector_sha256")
TEXT_ONLY_FIELDS = ("counts", "chunk_count", "content_sha256")

KEYS = ("available", "unavailable_reason", "weaviate_url", "include_vectors", "counts",
        "chunk_count", "content_sha256", "vector_sha256", "n_hashed", "n_vectors_hashed",
        "seconds", "per_object", "per_object_complete", "dim_histogram", "vector_dim",
        "dim_anomalies", "read_faults")


def normalize_corpus_url(raw: str) -> str:
    """A bare host or host:port, as fingerprint_rest wants it for http://{ip}/v1/...

    WEAVIATE_URL is written three ways across this repo -- `192.168.1.54:80`, `http://192.168.1.54:80`
    and a bare host -- and pasting a scheme into the f-string yields http://http://... which fails
    as a DNS error and reads like an unreachable corpus.
    """
    u = (raw or "").strip()
    if "://" in u:
        u = u.split("://", 1)[1]
    return u.rstrip("/").split("/")[0]


def resolve_corpus_url(env: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], Optional[str]]:
    """(host_port, None) or (None, typed reason).

    There is NO localhost default, unlike corpus_fingerprint.fingerprint_instance. Defaulting to
    localhost when the variable is unset does not fail -- it succeeds against the wrong instance, or
    against nothing, and stamps the run with a fingerprint of a corpus no question was asked of.
    """
    e = os.environ if env is None else env
    raw = e.get("WEAVIATE_URL")
    if not raw:
        return None, UNAVAILABLE + "WEAVIATE_URL-is-not-set"
    u = normalize_corpus_url(raw)
    if not u:
        return None, UNAVAILABLE + "WEAVIATE_URL-is-empty-after-normalising"
    return u, None


def unavailable_state(reason: str, url: Optional[str] = None,
                      include_vectors: bool = True) -> Dict[str, Any]:
    """A state record that claims nothing and says why. Same KEYS as a successful one, so an
    aggregator over a mixed set of arms does not break on the arms that recorded nothing."""
    if not reason.startswith(UNAVAILABLE):
        reason = UNAVAILABLE + reason
    return {"available": False, "unavailable_reason": reason, "weaviate_url": url,
            "include_vectors": include_vectors, "counts": None, "chunk_count": None,
            "content_sha256": None, "vector_sha256": None, "n_hashed": None,
            "n_vectors_hashed": None, "seconds": None, "per_object": None,
            "per_object_complete": False, "dim_histogram": None, "vector_dim": None,
            "dim_anomalies": None, "read_faults": None}


def corpus_state(url: Optional[str] = None, include_vectors: bool = True,
                 _fingerprint=None) -> Dict[str, Any]:
    """Fingerprint the live corpus, READ-ONLY, or return a typed unavailable record.

    `_fingerprint(url, include_vectors) -> dict` is injectable so the run block and the whole
    integrity path can be born-tested without a Weaviate instance.
    """
    if url is None:
        url, reason = resolve_corpus_url()
        if reason:
            return unavailable_state(reason, None, include_vectors)
    fp_fn = _fingerprint or _live_fingerprint
    t0 = time.perf_counter()
    try:
        fp = fp_fn(url, include_vectors)
    except Exception as exc:
        st = unavailable_state(UNAVAILABLE + "read-failed:" + type(exc).__name__, url, include_vectors)
        st["unavailable_reason"] = st["unavailable_reason"] + ": " + str(exc)[:160]
        return st
    st = {"available": True, "unavailable_reason": None, "weaviate_url": url,
          "include_vectors": bool(include_vectors), "seconds": round(time.perf_counter() - t0, 1)}
    for k in ("counts", "chunk_count", "content_sha256", "vector_sha256", "n_hashed",
              "n_vectors_hashed", "per_object", "per_object_complete", "dim_histogram",
              "vector_dim", "dim_anomalies", "read_faults"):
        st[k] = fp.get(k)
    # Page-level re-fetching in fingerprint_rest already tried to repair a dim anomaly; if one is
    # STILL here, every attempt failed. The remedy is a re-read, not a re-ingest, and this sample
    # cannot be trusted enough to compare against anything.
    if st.get("dim_anomalies"):
        n = len(st["dim_anomalies"])
        return unavailable_state(f"read-fault:vector-dim-anomaly:{n}", url, include_vectors)
    # Ruling (2026-10-04): the sampler reads every vector twice and this REFUSES on a mismatch.
    # An unstable read makes the sample unusable in a way no later check can repair -- the stored
    # digest is over bytes that do not reproduce, so every comparison against it is meaningless
    # and the arms that carried it reported a corpus change that never happened. Refusing here
    # costs a run; not refusing costs the measurement, silently.
    #
    # The faults are carried onto the refusal record. `read_faults` is already in KEYS, so the
    # shape every aggregator relies on is unchanged, and dropping the evidence to report only a
    # count would discard the one description of the mechanism this path ever produces.
    unstable = [f for f in (st.get("read_faults") or []) if f.get("kind") == "vector_unstable"]
    if unstable:
        uu = sorted({str(f.get("uuid")) for f in unstable if f.get("uuid")})
        stu = unavailable_state(
            "read-fault:vector-unstable:" + str(len(unstable)) + ": two reads of the same "
            "object disagreed at sampling time, so this sample cannot be reproduced and nothing "
            "may be compared against it; uuid(s) " + _named(uu), url, include_vectors)
        stu["read_faults"] = st.get("read_faults")
        return stu
    # A fingerprint over zero objects has a well-defined hash and means the corpus is EMPTY or the
    # class name is wrong. Either way it is not a corpus a run can be scored against.
    if not st.get("chunk_count"):
        return unavailable_state(UNAVAILABLE + "corpus-read-returned-no-chunks", url, include_vectors)
    if include_vectors and not st.get("n_vectors_hashed"):
        # Text hashed, vectors did not: a named-vector schema change, or include=vector ignored.
        # Recording a vector fingerprint of None while still claiming include_vectors would let a
        # re-vectorisation slip through the comparison below unnoticed.
        st["unavailable_reason"] = UNAVAILABLE + "vectors-requested-but-none-were-returned"
        st["include_vectors"] = False
    return st


def _live_fingerprint(url: str, include_vectors: bool) -> Dict[str, Any]:
    """The real read. Imported lazily so this module is importable with no httpx and no network."""
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parent.parent / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    import corpus_fingerprint as CF
    import fingerprint_rest as FR
    faults: list = []
    fp = CF.fingerprint(FR.stream_chunks(url, include_vector=include_vectors, faults=faults),
                        FR.counts(url), ingestion_sha=os.getenv("INGESTION_SHA"))
    fp["read_faults"] = faults
    return fp


REREAD_KEYS = ("available", "unavailable_reason", "weaviate_url", "include_vectors",
               "requested", "per_object", "read_faults", "seconds")


def reread_state(uuids, url: Optional[str] = None, include_vectors: bool = True,
                 _reread=None) -> Dict[str, Any]:
    """Re-read the NAMED read-faulted objects after the run, READ-ONLY, and digest them exactly
    the way the two samples were digested -- by handing fingerprint_rest's own 3-tuples to
    corpus_fingerprint.fingerprint(). Not one line of digest arithmetic is restated here, because a
    re-read computed differently would mismatch the stored sample on the arithmetic and look like
    the very corruption it is trying to rule out.

    `_reread(url, uuids, include_vectors) -> {uuid: {text, vec, dim, last_update_ms}}` is
    injectable for born-tests, same pattern as `corpus_state`'s `_fingerprint`.
    """
    uuids = list(uuids or [])
    if url is None:
        url, reason = resolve_corpus_url()
        if reason:
            return {"available": False, "unavailable_reason": reason, "weaviate_url": None,
                    "include_vectors": include_vectors, "requested": uuids,
                    "per_object": None, "read_faults": None, "seconds": None}
    fn = _reread or _live_reread
    t0 = time.perf_counter()
    faults: list = []
    try:
        per_object = fn(url, uuids, include_vectors)
    except Exception as exc:
        return {"available": False,
                "unavailable_reason": (UNAVAILABLE + "reread-failed:" + type(exc).__name__
                                       + ": " + str(exc)[:160]),
                "weaviate_url": url, "include_vectors": include_vectors, "requested": uuids,
                "per_object": None, "read_faults": None, "seconds": None}
    if isinstance(per_object, tuple):          # (per_object, faults) from the live reader
        per_object, faults = per_object
    return {"available": True, "unavailable_reason": None, "weaviate_url": url,
            "include_vectors": bool(include_vectors), "requested": uuids,
            "per_object": dict(per_object or {}), "read_faults": list(faults or []),
            "seconds": round(time.perf_counter() - t0, 1)}


def _live_reread(url: str, uuids, include_vectors: bool):
    """The real by-uuid read. Lazily imported for the same reason as `_live_fingerprint`."""
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parent.parent / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    import corpus_fingerprint as CF
    import fingerprint_rest as FR
    faults: list = []
    fp = CF.fingerprint(FR.fetch_objects(url, uuids, include_vector=include_vectors,
                                         faults=faults),
                        {}, ingestion_sha=os.getenv("INGESTION_SHA"))
    return fp.get("per_object") or {}, faults


# The fields a re-read must reproduce for an object to count as unchanged. `last_update_ms` is
# included on purpose: if it moved between the end sample and the re-read, something WROTE, which
# is the opposite of the finding this check exists to confirm.
REREAD_COMPARE_FIELDS = ("text", "vec", "dim", "last_update_ms")
# ...and the digest subset, which is what gets compared. `last_update_ms` is not compared as a
# field; it is the DISCRIMINATOR that says whether a digest difference was a write or a bad read,
# and `difference_kind` reads it directly. Both tuples are reported so a reader can see that
# nothing in REREAD_COMPARE_FIELDS goes unexamined.
REREAD_DIGEST_FIELDS = tuple(f for f in REREAD_COMPARE_FIELDS if f != "last_update_ms")


def reread_verdict(at_start: Dict[str, Any], read_fault_uuids, reread) -> Dict[str, Any]:
    """Did a post-run re-read confirm that the read-faulted objects never actually changed?

    `confirms` is True ONLY when every named uuid came back and matched the AT_START sample on
    every field in REREAD_COMPARE_FIELDS. Matching the END sample would prove nothing -- the end
    sample is the one suspected of being misread.

    Every other outcome is a typed non-confirmation, and each is kept distinct because they are
    distinct findings: no re-read was attempted, the re-read itself could not be read, there is no
    baseline to compare against, an object did not come back, or an object came back DIFFERENT.

    That last one is TWO findings, not one, and conflating them was a defect. A digest that moved
    while `last_update_ms` held still is a bad read in one of the two reads -- nothing was written
    -- while a digest that moved alongside its timestamp is a real write. The rule that tells them
    apart already existed for the start/end axis; this function used to attribute every difference
    to a write, and so put two clean arms on the record as "evidence of a real write" when the
    live timestamps proved no write had happened
    (docs/audits/RESULT_off_vs_on_rerun3_laneA_20261004.md).

    Both kinds are NON-CONFIRMING on byte-identity, so `confirms` stays False for both: a
    digest-only difference means the start sample's own digest for those objects was computed over
    bytes that could not be reproduced, and reporting that as a confirmation would overstate it.

    They differ on the question the GATE asks, which is whether the corpus was WRITTEN during the
    run, and that is what `excludes_write` carries. Ruling of 2026-10-04, superseding the earlier
    reading recorded here: a digest-only difference at a static last_update_ms is NOT provisional.
    Nothing was written, so the arm can be cited; the unreliable read is a recorded fact about
    named uuids, not a reason to withhold a measurement it did not touch. A difference whose
    timestamp MOVED still refuses, because that is a write.

    Two fields because there are two questions. Collapsing them would rebuild the original defect
    pointing the other way -- a verdict that says "confirmed" about bytes it could not reproduce.
    """
    base = {"confirms": False, "excludes_write": False, "status": None, "checked": list(read_fault_uuids or []),
            "matched": [], "differing": [], "differing_write": [], "differing_digest_only": [],
            "missing": [], "detail": None}
    if not base["checked"]:
        base["status"] = "not-needed"
        base["detail"] = "no read-faulted objects to re-read"
        return base
    if reread is None:
        base["status"] = "not-attempted"
        base["detail"] = ("no post-run re-read was performed, so the read fault is unconfirmed "
                          "and this arm stays provisional")
        return base
    if not reread.get("available"):
        base["status"] = "unavailable"
        base["detail"] = ("the re-read itself could not be performed: "
                          + str(reread.get("unavailable_reason")))
        return base
    start_po = at_start.get("per_object")
    if not start_po:
        base["status"] = "no-baseline"
        base["detail"] = ("the start sample carries no per_object map, so there is nothing for a "
                          "re-read to match against")
        return base
    got = reread.get("per_object") or {}
    for u in base["checked"]:
        if u not in got:
            base["missing"].append(u)
            continue
        a, c = start_po.get(u) or {}, got[u] or {}
        kind = _difference_kind(a, c, REREAD_DIGEST_FIELDS)
        if kind == "same":
            base["matched"].append(u)
            continue
        base["differing"].append(u)
        # "stamp-only" belongs with "write": on THIS axis a timestamp that moved between the end
        # sample and the re-read means something wrote, whether or not the digests show it.
        if kind == "digest-only":
            base["differing_digest_only"].append(u)
        else:
            base["differing_write"].append(u)
    if base["differing_write"]:
        # A real write dominates a mixed verdict: it is the stronger finding and the reason the
        # check exists. The digest-only uuids are still named so neither group is hidden.
        base["status"] = "differs-write"
        base["detail"] = (str(len(base["differing_write"])) + " re-read object(s) differ from the "
                          "start sample AND their last_update_ms moved ("
                          + _named(base["differing_write"]) + ") -- that is evidence of a real "
                          "write, not a bad read; this arm stays provisional"
                          + (("; a further " + str(len(base["differing_digest_only"]))
                              + " differ by digest only ("
                              + _named(base["differing_digest_only"]) + ")")
                             if base["differing_digest_only"] else ""))
    elif base["differing_digest_only"]:
        base["status"] = "differs-digest-only"
        base["detail"] = (str(len(base["differing_digest_only"])) + " re-read object(s) differ "
                          "from the start sample by digest ONLY, at an identical last_update_ms ("
                          + _named(base["differing_digest_only"]) + ") -- so NOTHING was written: "
                          "one of the two reads is bad, and since the re-read is the later one the "
                          "start sample's digest for those objects is the suspect. No write "
                          "occurred, so this does NOT make the arm provisional; the objects that "
                          "could not be re-read identically are recorded by uuid as a caveat")
        base["excludes_write"] = True
    elif base["missing"]:
        base["status"] = "missing"
        base["detail"] = (str(len(base["missing"])) + " object(s) could not be re-read ("
                          + _named(base["missing"]) + "), so nothing was confirmed")
    else:
        base["status"] = "confirmed"
        base["confirms"] = True
        base["excludes_write"] = True
        base["detail"] = ("all " + str(len(base["matched"])) + " read-faulted object(s) were "
                          "re-read after the run and match the start sample on "
                          + "+".join(REREAD_COMPARE_FIELDS))
    return base


def provisional_console_lines(block: Dict[str, Any]) -> List[str]:
    """The human-readable WHY for a corpus axis that did not resolve, as lines to print.

    A pure function because this text was inline in `run_eval` main, where no test could reach
    it -- and it was wrong there. It printed the two samples' `unavailable_reason` and nothing
    else, so a run whose samples BOTH read fine and whose post-run re-read did not confirm
    printed the words "Corpus state was NOT established at both ends:  / " with two empty
    reasons. Both arms of the attempt-5 pair printed exactly that
    (docs/audits/RESULT_off_vs_on_rerun3_laneA_20261004.md): the operator was told the samples
    could not be read when the real reason was a re-read verdict with its own typed status.

    Every reason the block carries is named, and if it carries none that is said out loud rather
    than printed as an empty string.
    """
    reread = block.get("reread") or {}
    unavailable = [str(side.get("unavailable_reason")) for side in
                   (block.get("at_start") or {}, block.get("at_end") or {})
                   if not side.get("available")]
    out = []
    if block.get("provisional"):
        out.append("*** THIS RUN IS PROVISIONAL ON THE CORPUS AXIS ***")
    else:
        out.append("Corpus: the comparison is INCOMPLETE, but this arm is not provisional.")
    if unavailable:
        out.append("    Corpus state was NOT established at both ends: " + " / ".join(unavailable))
    if reread.get("status") and reread["status"] != "not-needed":
        out.append("    post-run re-read: " + str(reread["status"]) + " -- "
                   + str(reread.get("detail")))
    if not unavailable and not reread.get("status"):
        out.append("    The reason is not in the record, which is its own defect: see"
                   " summary.integrity.corpus.")
    if block.get("caveats") and not block.get("provisional"):
        # An arm can be NOT provisional and still carry a finding the operator must see, and
        # "not provisional" must never read as "nothing happened". The caveat TEXT is not
        # repeated here: run_eval prints every caveat from one loop that covers all branches, so
        # emitting it again would double every line. This says it is there and how many.
        out.append("    " + str(len(block["caveats"])) + " CAVEAT(s) below name the affected"
                   " object(s) by uuid; the arm is citable, the read fault is not thereby "
                   "retracted.")
    out.append("    It is not a violation: the answers that were scored were really scored.")
    if block.get("provisional"):
        out.append("    It may withdraw an earlier claim but asserts nothing new, and cannot be")
        out.append("    cited in an ADR or a tier change.")
    return out


def _classify_change(fp_a: Dict[str, Any], fp_b: Dict[str, Any]) -> Dict[str, Any]:
    """Lazy-imported wrapper over corpus_fingerprint.classify_change (same import pattern as
    `_live_fingerprint`), shared by `corpus_changed` and `corpus_run_block`."""
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parent.parent / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    import corpus_fingerprint as CF
    return CF.classify_change(fp_a, fp_b)


def _difference_kind(oa: Dict[str, Any], ob: Dict[str, Any], fields) -> str:
    """Lazy-imported wrapper over corpus_fingerprint.difference_kind. The read-vs-write rule is
    imported rather than restated: `reread_verdict` having its own copy of it is precisely the
    defect this wrapper exists to remove."""
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parent.parent / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    import corpus_fingerprint as CF
    return CF.difference_kind(oa, ob, fields=fields)


def _named(uuids: list, limit: int = 10) -> str:
    """Up to `limit` uuids, then a count of those not named. A reason a human reads must not be
    7294 uuids long, and truncating it without saying so would be its own quiet loss."""
    more = len(uuids) - limit
    return ", ".join(uuids[:limit]) + (f" (+{more} more)" if more > 0 else "")


def _attributable_classification(at_start: Dict[str, Any], at_end: Dict[str, Any]):
    """`classify_change` over two samples, or None when either side carries no `per_object` map or
    the map is incomplete. ONE place decides whether a difference is attributable, so the verdict
    (`corpus_changed`) and the naming (`corpus_run_block`) can never disagree about it."""
    if at_start.get("per_object") is None or at_end.get("per_object") is None:
        return None
    cls = _classify_change(at_start, at_end)
    return cls if cls.get("attributable") else None


def _attributed_reason(cls: Dict[str, Any]) -> str:
    """'CORPUS CHANGED: <uuid>:<category>, ...' naming up to 10 uuids and the category each falls
    in -- added, removed or rewritten -- instead of only a corpus-wide fold that names nothing."""
    rows = sorted([(u, "added") for u in cls["added"]] +
                  [(u, "removed") for u in cls["removed"]] +
                  [(u, "rewritten") for u in cls["rewritten"]])
    named = ", ".join(f"{u}:{cat}" for u, cat in rows[:10])
    more = len(rows) - 10
    return ("CORPUS CHANGED: " + str(len(cls["added"])) + " added, " + str(len(cls["removed"]))
            + " removed, " + str(len(cls["rewritten"])) + " rewritten; " + named
            + (f" (+{more} more)" if more > 0 else ""))


def corpus_changed(at_start: Dict[str, Any], at_end: Dict[str, Any]) -> Tuple[Optional[bool], str]:
    """(changed, scope). changed is True, False, or None for unknowable. Never False on a guess.

    When both samples carry a complete `per_object` map, the verdict is attributed to named
    objects via `classify_change` instead of only a corpus-wide fold: a real add/remove/rewrite is
    True, a digest that moved while last_update_ms held still is a bad READ (None, not a change),
    and otherwise it falls through to the fold comparison below."""
    if not (at_start.get("available") and at_end.get("available")):
        return None, "not-compared: at least one sample is unavailable"
    fields = IDENTITY_FIELDS
    scope = "text+vectors"
    if not (at_start.get("include_vectors") and at_end.get("include_vectors")):
        fields = TEXT_ONLY_FIELDS
        scope = ("text-only: vector hashing was not in force for both samples, so a "
                 "re-vectorisation during this run would NOT have been detected")

    cls = _attributable_classification(at_start, at_end)
    if cls is not None:
        if cls["real_change"]:
            return True, _attributed_reason(cls)
        if cls["read_fault"]:
            n = len(cls["read_fault"])
            return None, (
                f"not-compared: {n} objects differ only by digest while their "
                f"last_update_ms is identical, which is a bad read, not a corpus change; "
                + _named(cls["read_fault"]))
        return False, scope
    if at_start.get("per_object") is not None and at_end.get("per_object") is not None:
        # either side's per_object was incomplete -- say so, and fall back to the fold below.
        scope = scope + " (per_object incomplete on at least one side; not attributable, " \
                         "falling back to the fold comparison)"

    for f in fields:
        if at_start.get(f) != at_end.get(f):
            return True, scope
    return False, scope


def corpus_run_block(at_start: Dict[str, Any], at_end: Dict[str, Any],
                     skipped: bool = False,
                     reread: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The `integrity.corpus` block, shaped like `integrity.git` and for the same reason: a function
    so the comparison can be born-tested. Asserting that the SOURCE mentions changed_during_run
    proves nothing about whether it is ever True."""
    changed, scope = corpus_changed(at_start, at_end)
    violations = []
    read_fault_uuids: list = []
    if changed:
        violations.append(
            "CORPUS CHANGED MID-RUN: the Weaviate instance this run was scored against was mutated "
            "while questions were being asked. Start " + _brief(at_start) + " -> end " +
            _brief(at_end) + ". The arm measured a moving target and is not comparable to anything, "
            "including itself. Find out who ingested, then rerun from the top.")
    elif changed is None:
        cls = _attributable_classification(at_start, at_end)
        if cls is not None:
            read_fault_uuids = cls["read_fault"]
    # `provisional` is narrowed to ATTRIBUTABLE change (ruling, 2026-10-04). A difference that
    # classify_change attributes to a BAD READ -- digest moved, last_update_ms did not -- no longer
    # makes an arm uncitable BY ITSELF, because the transport produces that on nearly every run and
    # a permanent uncitable flag is an instrument that has stopped discriminating.
    #
    # The condition that makes this a narrowing and not a loosening: the named objects must be
    # RE-READ after the run and still match the AT_START sample. That turns "we failed to read two
    # objects" into "we failed once, re-read, and they had not changed", which is verified rather
    # than hopeful. No re-read, a failed re-read, an object that did not come back, or a re-read
    # whose last_update_ms MOVED (that is a write) -> still provisional.
    #
    # What does NOT make it provisional, per the ruling of 2026-10-04: a re-read differing by
    # DIGEST ALONE at a static last_update_ms. That is a bad read in one of the two reads and no
    # write at all, so the arm is citable and the misread uuids go on the record as a caveat. The
    # gate therefore turns on `excludes_write` ("was a write ruled out?") rather than `confirms`
    # ("were the bytes reproduced?"): different questions, and only the first is what the claim
    # "the corpus did not change during this run" actually needs.
    rr = reread_verdict(at_start, read_fault_uuids, reread)
    read_fault_only = changed is None and bool(read_fault_uuids)
    reread_confirmed = bool(read_fault_only and rr["confirms"])
    reread_excludes_write = bool(read_fault_only and rr["excludes_write"])
    provisional = bool(skipped or changed is True
                       or (changed is None and not reread_excludes_write))
    caveats: list = []
    note = ("changed_during_run is three-state: None means at least one sample could not be "
            "read, NOT that the corpus held still. A change is a violation (the measurement is "
            "of a moving target); an unread corpus is provisional only (it cannot be cited, but "
            "a metadata read failure does not invalidate answers that were actually scored).")
    if read_fault_uuids:
        note += (" " + str(len(read_fault_uuids)) + " object(s) (" +
                 _named(read_fault_uuids) + ") differ only by a bad read, not a corpus "
                 "change; the remedy is a RE-READ, never a re-ingest.")
        note += " Re-read verdict: " + str(rr["status"]) + " -- " + str(rr["detail"]) + "."
    if reread_confirmed:
        # A caveat, not a violation and not silence. The arm is citable AND the reader is told
        # exactly which objects were misread and on what evidence that was decided.
        caveats.append(
            "READ-FAULT CAVEAT: " + str(len(read_fault_uuids)) + " object(s) (" +
            _named(read_fault_uuids) + ") were misread during this run -- their digests moved "
            "while last_update_ms held still. They were re-read after the run and match the "
            "start sample, so nothing was written and this arm is citable. The corpus comparison "
            "for these objects rests on the re-read, not on the end sample.")
    elif reread_excludes_write:
        # Citable -- and the reason it is citable is itself a defect that must not go unsaid. The
        # uuids are named HERE because a flag nobody is shown is not a disclosure: this caveat is
        # the only place a reader of the summary learns which objects the instrument misread.
        caveats.append(
            "READ-FAULT CAVEAT (digest-only): " + str(len(rr["differing_digest_only"])) +
            " object(s) (" + _named(rr["differing_digest_only"]) + ") were re-read after the run "
            "and came back with a DIFFERENT digest at an unchanged last_update_ms. No write "
            "happened, so this arm is citable -- but two reads of the same unchanged object "
            "disagree, which means the vector read itself is unreliable and the start sample is "
            "the suspect. Any claim resting on those objects' BYTES is unsupported; the claim "
            "that the corpus did not change during the run is not.")
    return {
        "at_start": at_start,
        "at_end": at_end,
        "changed_during_run": changed,
        "comparison_scope": scope,
        "skipped": bool(skipped),
        "provisional": provisional,
        "violations": violations,
        "read_fault_uuids": read_fault_uuids,
        "reread": rr,
        "reread_confirmed": reread_confirmed,
        "reread_excludes_write": reread_excludes_write,
        "caveats": caveats,
        "note": note,
    }


def _brief(st: Dict[str, Any]) -> str:
    if not st.get("available"):
        return "<" + str(st.get("unavailable_reason")) + ">"
    return ("chunks=" + str(st.get("chunk_count"))
            + " text=" + str(st.get("content_sha256"))[:12]
            + " vec=" + str(st.get("vector_sha256"))[:12])
