# -*- coding: utf-8 -*-
r"""sitting_provenance -- HOW a signing sitting was conducted, recorded BESIDE the signed file.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

WHY THIS FILE EXISTS. The signer's export has no channel for how the sitting was conducted. Every row
of every sitting carries the same constant `signed_in: "glyph signer, in the browser"`, and nothing
else in the row says who or what was in the room, whether anything was read aloud, or whether the
verdicts were given blind. So a sitting where a model read each crop aloud to the human and a sitting
where the human read the pixels unaided produce byte-identical provenance fields. That is a channel
the format does not have, and an absent channel is not an empty one: without a record, silence reads
as "nothing influenced the signer", which is a claim nobody made.

Advisor ruling 2026-11-15, item 1, about the return `..._signed_50d419a4.jsonl`:

    Record on all five rows: signed_with_advisor_reading = true (a Claude model read each crop aloud
    to Chris during the sitting). No row from this sitting is truth on its own.

THE RECORD IS A STANDOFF, NEVER AN EDIT. The signed file's NAME IS ITS CONTENT ADDRESS: writing the
flag into its rows would rename the thing the flag is about, and the record of a human's yes must be
named by what it describes. So the flag lives in a sidecar named by the signed file's sha16 and by its
own hash, and `ingest_pass2.admit_resigned` is the consumer: it refuses to admit a row of a sitting
under a ruling unless this record is supplied, and refuses outright while the record says no row is
truth on its own. The refusal is the ruling ACTING, not a flag recorded and left for somebody to read.

WHAT THIS FILE DOES NOT DO. It does not decide anything about a sitting. Every fact in the record
comes from a ruling, quoted and attributed; the only things derived here are the file's hash and its
span ids, read from the file itself. It writes a record for a NAMED file and refuses to write one for
a sitting whose facts it was not given -- a provenance record invented for an old sitting would be a
fabrication of exactly the kind the sidecar exists to prevent. It says nothing about whether any
reading in the file is right.

    python sitting_provenance.py --write-50d419a4      # the 2026-11-15 sitting, from the ruling
    python sitting_provenance.py --selftest
"""
import hashlib
import io
import json
import os
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from write_scope import assert_inside                                     # noqa: E402

AUDITS = pathlib.Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")

# Ruling 5 of this lane: the hash is over UTF-8 BYTES and the rule says so. This record holds no
# non-ASCII character, so ensure_ascii makes no difference to its bytes -- the rule is still stated
# in full, because a hash rule that is only true of the records written so far is not a rule.
HASH_RULE = ("sha256 over json.dumps(record minus record_sha16 and record_sha16_rule, indent=1, "
             "sort_keys=True, ensure_ascii=False).encode('utf-8'), first 16 hex")


class SittingProvenanceError(Exception):
    pass


def record_sha16(body):
    """The hash of a record BODY (the record without its own hash and hash rule)."""
    body = {k: v for k, v in body.items() if k not in ("record_sha16", "record_sha16_rule")}
    raw = json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def file_facts(path):
    """The two things about a signed file this record may DERIVE rather than be told: its hash and
    the span ids it holds, in file order. Refuses an empty file: a sitting with no rows is not a
    sitting, and a record covering nothing would validate against every row by vacuity."""
    raw = io.open(path, "rb").read()
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
    if not rows:
        raise SittingProvenanceError("%s holds no rows" % os.path.basename(path))
    ids = [r["span_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise SittingProvenanceError("%s names a span twice: %s" % (os.path.basename(path), ids))
    return hashlib.sha256(raw).hexdigest()[:16], ids


def build(path, signed_with_advisor_reading, reading_channel, no_row_is_truth_on_its_own,
          what_would_lift_it, ruled_by, recorded_on, does_not_assert):
    """Assemble a record for ONE signed file. The flag is stated per row AND for the sitting, because
    the ruling is about rows and a later reader asks about rows; both are required to be real
    booleans, since a provenance field that may be absent is the silence this file exists to end."""
    if not isinstance(signed_with_advisor_reading, bool):
        raise SittingProvenanceError("signed_with_advisor_reading must be a bool, got %r"
                                     % (signed_with_advisor_reading,))
    if not isinstance(no_row_is_truth_on_its_own, bool):
        raise SittingProvenanceError("no_row_is_truth_on_its_own must be a bool, got %r"
                                     % (no_row_is_truth_on_its_own,))
    if signed_with_advisor_reading and not str(reading_channel or "").strip():
        raise SittingProvenanceError("a sitting with a reading must name what did the reading")
    if no_row_is_truth_on_its_own and not str(what_would_lift_it or "").strip():
        raise SittingProvenanceError(
            "a record that withholds truth standing must name what would lift it; a refusal that "
            "names no way out is a dead end, not a gate")
    sha, ids = file_facts(path)
    body = {
        "kind": "sitting_provenance",
        "describes_file": os.path.basename(path),
        "describes_file_sha16": sha,
        "rows": {sid: {"signed_with_advisor_reading": signed_with_advisor_reading} for sid in ids},
        "row_order_in_file": ids,
        "signed_with_advisor_reading": signed_with_advisor_reading,
        "reading_channel": reading_channel,
        "no_row_is_truth_on_its_own": no_row_is_truth_on_its_own,
        "what_would_lift_it": what_would_lift_it,
        "ruled_by": ruled_by,
        "recorded_on": recorded_on,
        "does_not_assert": does_not_assert,
        "why_a_sidecar": "the signed file's name is its content address; writing this flag into its "
                         "rows would rename the thing the flag is about",
        "channel_absent_from_the_format": "the export's only provenance field is the constant "
                                          "signed_in='glyph signer, in the browser'; it is identical "
                                          "for a sitting with a model reading and one without",
    }
    body["record_sha16_rule"] = HASH_RULE
    body["record_sha16"] = record_sha16(body)
    return body


# ---------------------------------------------------------------------------- the 2026-11-15 sitting
SIGNED_50D419A4 = AUDITS / "glyphsign_0401b636ffa7bf1a_resign_5span_signed_50d419a4.jsonl"


def build_50d419a4():
    """Every fact here is quoted from advisor ruling 2026-11-15, items 1 and 2. Nothing is inferred."""
    return build(
        SIGNED_50D419A4,
        signed_with_advisor_reading=True,
        reading_channel="a Claude model read each crop aloud to Chris during the sitting (advisor "
                        "ruling 2026-11-15 item 1)",
        no_row_is_truth_on_its_own=True,
        what_would_lift_it="a second sitting: the rows re-signed after the pointing, on cards with "
                           "exemplars, blind to these verdicts and with no model reading shown or "
                           "consulted (advisor ruling 2026-11-15 item 2). Agreement with this file "
                           "confirms a row; a changed tile goes to a keep/take/neither card. The "
                           "confirming sitting must be a DIFFERENT file: a sitting cannot confirm "
                           "itself.",
        ruled_by="advisor ruling 2026-11-15, items 1 and 2",
        recorded_on="2026-11-15",
        does_not_assert=[
            "that any reading in the file is right or wrong -- the six tile changes this return made "
            "over identical pixels are unadjudicated (RESIGNDIFF_A_vs_pass1_4span.json, diff_sha16 "
            "14d3d6a00f4d949c)",
            "that the model's reading was wrong; the objection is to the CHANNEL, not to its content",
            "anything about any other sitting. This record covers one file, named by its hash.",
            "that a model reading is recorded for any earlier sitting. It is not, and this file "
            "refuses to invent one: for every sitting before this ruling the question was never "
            "asked, and 'unknown' is where it stands.",
        ])


def write_50d419a4():
    rec = build_50d419a4()
    dest = AUDITS / ("SITTINGPROV_%s_%s.json" % (rec["describes_file_sha16"], rec["record_sha16"]))
    final = json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")
    assert_inside(dest, "a sitting-provenance record belongs beside the file it describes")
    if dest.exists() and io.open(dest, "rb").read() != final:
        raise SittingProvenanceError(
            "%s exists with different bytes. The name holds the record's own hash, so this cannot "
            "happen from a change of content -- investigate before overwriting." % dest.name)
    io.open(str(dest), "wb").write(final)
    return dest, rec


# ---------------------------------------------------------------------------------------- selftest
def selftest():
    n = [0]

    def ck(cond, msg):
        n[0] += 1
        if not cond:
            raise AssertionError("check %d: %s" % (n[0], msg))

    rec = build_50d419a4()
    ck(rec["kind"] == "sitting_provenance", "kind")
    ck(rec["describes_file_sha16"] == "50d419a4e1cafbc4",
       "the file's hash is 50d419a4e1cafbc4, got %s" % rec["describes_file_sha16"])
    ck(len(rec["rows"]) == 5 and set(rec["rows"]) == {"p254:n1", "p442:n0", "p628:n2", "p798:n0",
                                                      "p831:n2"},
       "the five rows of the sitting, derived from the file, got %s" % sorted(rec["rows"]))
    ck(all(v["signed_with_advisor_reading"] is True for v in rec["rows"].values()),
       "the flag is True on every row, as ruled")
    ck(rec["no_row_is_truth_on_its_own"] is True, "no row is truth on its own")
    ck(rec["what_would_lift_it"].strip(), "the record names what would lift it")
    ck("cannot confirm itself" in rec["what_would_lift_it"],
       "what lifts it says the confirming sitting must be a different file")
    ck(rec["record_sha16"] == record_sha16(rec), "the record hashes to its own stated hash")
    ck(rec["record_sha16_rule"] == HASH_RULE and "ensure_ascii=False" in rec["record_sha16_rule"],
       "the rule is stated on the record")

    # the hash covers every field: move one character of one row's flag and the hash must move
    tampered = json.loads(json.dumps(rec))
    tampered["rows"]["p254:n1"]["signed_with_advisor_reading"] = False
    ck(record_sha16(tampered) != rec["record_sha16"], "the hash must cover the per-row flags")
    tampered = json.loads(json.dumps(rec))
    tampered["describes_file_sha16"] = "0" * 16
    ck(record_sha16(tampered) != rec["record_sha16"], "the hash must cover the file it describes")

    # the builder refuses what it must refuse
    for kw, why in (
            ({"signed_with_advisor_reading": "yes"}, "a non-bool flag"),
            ({"no_row_is_truth_on_its_own": None}, "a non-bool truth standing"),
            ({"signed_with_advisor_reading": True, "reading_channel": "  "},
             "a reading with nothing named as the reader"),
            ({"no_row_is_truth_on_its_own": True, "what_would_lift_it": ""},
             "withheld truth with no way out named")):
        base = dict(signed_with_advisor_reading=True, reading_channel="x",
                    no_row_is_truth_on_its_own=True, what_would_lift_it="y",
                    ruled_by="r", recorded_on="d", does_not_assert=[])
        base.update(kw)
        try:
            build(SIGNED_50D419A4, **base)
            ck(False, "the builder accepted %s" % why)
        except SittingProvenanceError:
            ck(True, "refused %s" % why)

    # an empty file is not a sitting: a record over no rows would validate against every row
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        empty = f.name
    try:
        try:
            file_facts(empty)
            ck(False, "file_facts accepted an empty file")
        except SittingProvenanceError:
            ck(True, "refused an empty file")
    finally:
        os.unlink(empty)

    # The count check counts ITSELF, the convention the resign selftest already uses: a check
    # that did not run is as invisible as a check that passed, so the total is pinned.
    ck(n[0] + 1 == EXPECTED_CHECKS, "ran %d checks including this one, expected %d"
       % (n[0] + 1, EXPECTED_CHECKS))
    return n[0]


EXPECTED_CHECKS = 17


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        print("sitting_provenance selftest: %d/%d checks pass" % (selftest(), EXPECTED_CHECKS))
    elif "--write-50d419a4" in sys.argv:
        dest, rec = write_50d419a4()
        print("wrote %s" % dest)
        print("  describes      %s  sha16 %s" % (rec["describes_file"], rec["describes_file_sha16"]))
        print("  rows           %s" % ", ".join(rec["row_order_in_file"]))
        print("  advisor reading %r on every row" % rec["signed_with_advisor_reading"])
        print("  truth standing  no row from this sitting is truth on its own")
        print("  record_sha16   %s" % rec["record_sha16"])
    else:
        sys.exit(__doc__.strip().split("\n")[-3].strip())
