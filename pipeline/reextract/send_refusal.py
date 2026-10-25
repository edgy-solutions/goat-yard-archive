# -*- coding: utf-8 -*-
"""Law 8: a box that fails a geometry check must never reach a paid arm.

Advisor ruling B(4), 2026-10-25: REFUSE to send a crop whose row carries a ratified `box_fault` or
`partial_in_crop`, and score the span `unscorable:input-refused` instead of as a read.  Refused rows
are excluded from the exact/wrong denominators and reported as `n_refused` beside `n`.  Never counted
wrong, never dropped.

Why this module exists rather than a branch at one call site.  The two flags were recorded at
ratification and read by nothing on the send path -- the third instance of recording-a-flag-is-not-
acting-on-it in this lane, and the reason 3 of the 45 sent crops carried a ratified box fault and all
3 came back wrong on opus bare.  A guard with no consumer is a comment, so the predicate, the
accounting and the plan gate live together and are asserted together.

Two design rules carried from earlier defects in this lane:

  * `populations` is a REQUIRED argument everywhere.  A function that derives its own input fails
    silently -- the counting localizer was never wired up because it could be called without the note
    text, and `n_before` was 0 for 74 of 74 rows.  A caller that has no flags for a span cannot call
    these functions and get `False`; it gets `FlagsUnavailable`.
  * unknown is not clean.  A span absent from the flag mapping raises.  A blank channel is not an
    absent input, and "no record" is the state that most looks like "no fault".

Scope, measured 2026-10-25 and stated because it bounds the wiring: the two flag names exist in the
scoring-45 run's hand-authored populations and in the pass-3 r2 ingest rows (`box_fault`,
`disposition == "signed_partial_in_crop"`).  They do NOT exist in `hebrew_aperture_diag.build_set()`,
which is the population the live sender builds from -- 21 spans, no `box_fault` key, no
`partial_in_crop` key -- nor in `span_box_verdicts_20260906.jsonl`, whose `flags` vocabulary is a
different one (`drop-case`, `non-contiguous`, ...).  So for the live population the flag has no
PRODUCER, not merely no consumer.  `require_flags` is the honest consequence: a sender with no flag
record refuses its whole population, the same shape as the existing `crop_unmeasured` refusal in
`cells()`, rather than sending spans whose faults nobody looked up.

All page numbers in reports built on this module are FILE pages (printed = file - 88).
"""

REFUSAL_CLASS = "unscorable:input-refused"

# The two ratified populations that refuse a send.  Named here once; every consumer imports them, so
# a fourth population cannot be added at one call site and missed at another.
REFUSING_POPULATIONS = ("box_fault", "partial_in_crop")

# The scored classes a READ can carry.  Refused rows carry none of them -- that is the whole point.
READ_CLASSES = ("exact", "nikud_only", "wrong", "abstain")


class FlagsUnavailable(RuntimeError):
    """A span was asked about with no flag record.  Unknown is not clean."""


class RefusalFault(RuntimeError):
    """A refused span reached a paid arm, or a refused span came back with a read.

    Run-level, not item-level: it means the gate did not hold, so the run's numbers describe a
    population nobody authorised.  Errors-out-of-the-denominator is not enough here."""


def refusal_reason(span_id, populations):
    """The populations that refuse this span, as a sorted tuple; empty if it is sendable.

    `populations` is the iterable of population names for THIS span and is required.  Pass an empty
    collection to say "measured, no refusing flag"; pass None and you get FlagsUnavailable, because a
    caller who has not looked is not a caller who has looked and found nothing."""
    if populations is None:
        raise FlagsUnavailable(
            "%s: no flag record. Unknown is not clean -- look the span's populations up, or refuse "
            "the whole population. (law 8, ruling B(4))" % span_id)
    names = set(populations)
    return tuple(sorted(p for p in REFUSING_POPULATIONS if p in names))


def refuses(span_id, populations):
    """True when this span must not be sent.  See `refusal_reason` for the required argument."""
    return bool(refusal_reason(span_id, populations))


def require_flags(span_ids, populations_by_span):
    """Every span must have a flag record before any of them is sent.

    Refusing the whole population is deliberate and follows the `crop_unmeasured` precedent in
    `cells()`: a partial lookup sends the spans nobody checked and reports a clean run."""
    missing = sorted(s for s in span_ids if populations_by_span.get(s) is None)
    if missing:
        raise FlagsUnavailable(
            "refusing to build a send population: %d of %d span(s) have no box_fault / "
            "partial_in_crop record: %s. An unlooked-up fault is not an absent one (law 8)."
            % (len(missing), len(list(span_ids)), ", ".join(missing)))


def partition(span_ids, populations_by_span):
    """(sendable, refused) where refused is {span_id: (reasons,)}.  Raises if any span lacks flags."""
    ids = list(span_ids)
    require_flags(ids, populations_by_span)
    refused = {}
    sendable = []
    for sid in ids:
        why = refusal_reason(sid, populations_by_span[sid])
        if why:
            refused[sid] = why
        else:
            sendable.append(sid)
    return sendable, refused


def gate_not_sent(sent_span_ids, refused):
    """Law 8's clause, asserted on the payloads actually built: never reaches a paid arm.

    A gate must be able to see the failure it watches, so this is checked against the constructed
    requests -- not against the plan that was supposed to exclude them."""
    leaked = sorted(set(sent_span_ids) & set(refused))
    if leaked:
        raise RefusalFault(
            "GATE law-8: %d refused span(s) reached a built payload: %s. Refusal is a send-path "
            "property; it did not hold." % (len(leaked), ", ".join(leaked)))


def tally(class_by_span, refused):
    """Counts with the refusal out of the exact/wrong denominators and reported beside them.

    `class_by_span` maps span_id -> one of READ_CLASSES, for the spans that WERE read.  `refused` is
    the mapping from `partition`.  Returns n, n_refused, the per-class counts over n, and the refused
    ids with their reasons.

    Three things are asserted rather than documented, because the memo's warning is that the refusal
    is not free -- it RAISES the measured exact rate on the sent population:
      * nothing refused carries a read class (if it does, it was sent: RefusalFault);
      * the per-class counts sum to n, so no row is quietly dropped;
      * n + n_refused is the whole population, so the refusal is visible as its own class."""
    overlap = sorted(set(class_by_span) & set(refused))
    if overlap:
        raise RefusalFault(
            "%d refused span(s) came back with a read class: %s. Either the gate leaked or the "
            "refusal was applied after the spend." % (len(overlap), ", ".join(overlap)))
    bad = sorted(s for s, c in class_by_span.items() if c not in READ_CLASSES)
    if bad:
        raise ValueError("unknown read class on %s: %s"
                         % (", ".join(bad), sorted({class_by_span[s] for s in bad})))
    counts = {c: sum(1 for v in class_by_span.values() if v == c) for c in READ_CLASSES}
    n = len(class_by_span)
    assert sum(counts.values()) == n, "class counts do not sum to n -- a row was dropped"
    out = {"n": n, "n_refused": len(refused), "n_population": n + len(refused),
           "refusal_class": REFUSAL_CLASS,
           "refused": {k: list(v) for k, v in sorted(refused.items())}}
    out.update(counts)
    out["exact_rate_on_sent"] = (float(counts["exact"]) / n) if n else None
    # Stated, not computed away: the denominator this rate is taken over EXCLUDES the refused rows,
    # which is why the rate is not comparable to a pre-refusal number on the same set.
    out["denominator_note"] = ("exact/wrong rates are over the %d SENT spans; the %d refused "
                               "span(s) are reported separately as %s and are counted neither "
                               "exact nor wrong" % (n, len(refused), REFUSAL_CLASS))
    return out


# ----------------------------------------------------------------------------- the flag record on disk
# The send path needs the two flags per span BEFORE it builds a payload, and `build_set()` does not
# carry them (see the scope note at the top of this file).  So they live in a sidecar, one JSON object
# mapping span_id -> the populations that span is in, with provenance per span.  A sidecar rather than
# an edit to a frozen manifest: a ratification fact lives BESIDE the record it describes, never inside
# it, and `requested-vs-realized` is the other reason -- this file records what was looked up, with
# who looked.
SIDECAR_NAME = "span_send_flags.json"


def load_span_flags(path):
    """span_id -> [population names].  Absent file is NOT an empty mapping; it raises.

    The distinction this enforces is the one the lane keeps paying for: a missing channel reads as a
    clean one.  A sender with no sidecar must refuse its whole population, not send it unflagged."""
    import io as _io
    import json as _json
    import os as _os
    if not _os.path.exists(path):
        raise FlagsUnavailable(
            "no send-flag sidecar at %s -- refusing to build a send population. Law 8 forbids a "
            "paid call on a box whose geometry was not checked, and an absent flag file is not a "
            "clean one. Produce %s (span_id -> populations, from the ratification record) first."
            % (path, SIDECAR_NAME))
    o = _json.load(_io.open(path, encoding="utf-8"))
    flags = o.get("flags_by_span")
    if not isinstance(flags, dict):
        raise FlagsUnavailable("%s has no `flags_by_span` object" % path)
    out = {}
    for sid, v in flags.items():
        if v is None:
            continue                                   # an explicit unknown stays unknown: see below
        names = v.get("populations") if isinstance(v, dict) else v
        if names is None:
            continue
        unknown = sorted(set(names) - set(KNOWN_POPULATIONS))
        if unknown:
            raise ValueError("%s: %s names population(s) outside the known vocabulary: %s"
                             % (path, sid, unknown))
        out[sid] = sorted(names)
    return out


# Every population name the scoring runs record.  A name outside this list is a typo or a new fact,
# and either way the loader must not silently treat it as non-refusing.
KNOWN_POPULATIONS = ("box_fault", "partial_in_crop", "editorial_insertion", "corrected_heavy",
                     "sic", "multi_word")


# ------------------------------------------------------------------------------- the one entry point
from collections import namedtuple as _nt


class SendPlan(_nt("SendPlan", ["sendable", "refused", "report"])):
    """What a sender may send (`sendable`, a tuple), what it may not (`refused`, id -> reasons), and
    the accounting (`report`, with n and n_refused side by side)."""
    __slots__ = ()

    def refused_records(self):
        """Per refused span, the record a scorer writes.  It never reached the wire."""
        for sid, why in sorted(self.refused.items()):
            yield {"span_id": sid, "class_primary": REFUSAL_CLASS, "refused": list(why),
                   "reached_wire": False}


def refuse_at_send(span_ids, populations_by_span, *, on_refused):
    """The one law-8 entry point for every sender: call it before building any payload.

    Partitions `span_ids` by `populations_by_span` (span_id -> population names, e.g. from
    `load_span_flags`; REQUIRED, a span with no record raises FlagsUnavailable), then checks the
    sendable list against every span the mapping knows to be faulty, derived a second, different way
    (a gate whose input is derived like the thing it checks cannot witness it).

    `on_refused` is REQUIRED and keyword-only:
      "fail"   -- for a sender working from an approved sheet: narrowing it silently would leave an
                  approval that no longer describes what was sent, so any refused span raises
                  RefusalFault ("rebuild the contact sheet without them").
      "record" -- for a scorer that must emit `unscorable:input-refused` rows: returns the plan and
                  the caller writes `plan.refused_records()`.
    Anything else raises ValueError.  `report["n_refused"]` always sits beside `report["n"]`, and
    n + n_refused == n_population is asserted."""
    if on_refused not in ("fail", "record"):
        raise ValueError("on_refused must be 'fail' or 'record', got %r" % (on_refused,))
    ids = list(span_ids)
    sendable, refused = partition(ids, populations_by_span)
    gate_not_sent(sendable, partition(
        sorted(k for k, v in populations_by_span.items() if v is not None), populations_by_span)[1])
    report = {"n": len(sendable), "n_refused": len(refused), "n_population": len(ids),
              "refusal_class": REFUSAL_CLASS,
              "refused": {k: list(v) for k, v in sorted(refused.items())}}
    assert report["n"] + report["n_refused"] == report["n_population"], \
        "n + n_refused is not the population -- a span was dropped"
    if on_refused == "fail" and refused:
        import json as _json
        raise RefusalFault(
            "refusing to spend: %d of %d span(s) on this sheet carry a ratified geometry fault and "
            "are scored `%s`, never read: %s. Law 8 -- rebuild the contact sheet without them."
            % (len(refused), len(ids), REFUSAL_CLASS,
               _json.dumps({k: list(v) for k, v in sorted(refused.items())}, ensure_ascii=False)))
    return SendPlan(sendable=tuple(sendable), refused=dict(refused), report=report)
