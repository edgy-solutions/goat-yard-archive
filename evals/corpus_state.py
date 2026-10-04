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
from typing import Any, Dict, Optional, Tuple

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
                     skipped: bool = False) -> Dict[str, Any]:
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
    provisional = bool(skipped or changed or changed is None)
    note = ("changed_during_run is three-state: None means at least one sample could not be "
            "read, NOT that the corpus held still. A change is a violation (the measurement is "
            "of a moving target); an unread corpus is provisional only (it cannot be cited, but "
            "a metadata read failure does not invalidate answers that were actually scored).")
    if read_fault_uuids:
        note += (" " + str(len(read_fault_uuids)) + " object(s) (" +
                 _named(read_fault_uuids) + ") differ only by a bad read, not a corpus "
                 "change -- this is PROVISIONAL, not a violation; the remedy is a RE-READ, "
                 "never a re-ingest.")
    return {
        "at_start": at_start,
        "at_end": at_end,
        "changed_during_run": changed,
        "comparison_scope": scope,
        "skipped": bool(skipped),
        "provisional": provisional,
        "violations": violations,
        "read_fault_uuids": read_fault_uuids,
        "note": note,
    }


def _brief(st: Dict[str, Any]) -> str:
    if not st.get("available"):
        return "<" + str(st.get("unavailable_reason")) + ">"
    return ("chunks=" + str(st.get("chunk_count"))
            + " text=" + str(st.get("content_sha256"))[:12]
            + " vec=" + str(st.get("vector_sha256"))[:12])
