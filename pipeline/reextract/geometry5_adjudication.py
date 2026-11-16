# -*- coding: utf-8 -*-
u"""Chris's verdicts on the GEOMETRY5 sheet `3f6b0357a850548e`, as a STANDOFF record.

Lane B writes this record, because Lane B built the sheet. The verdicts first reached the Lane A2
session; A2 saved them verbatim and declined to transcribe them, which is right -- each lane writes
its own records -- and Chris confirmed that on 2026-11-15. A2's observations travel here as
`consumer_observations`, marked as a consumer's reading and NOT as verdicts.

**Standoff, never an edit.** `wrong_line_check_0401b636ffa7bf1a.json` is what the checker measured
and the sheet is content-addressed by a digest over what it describes. Rewriting a box inside either
would destroy the thing a later reader needs most: the ability to see that the pipeline stored one
position and a human looking at the pixels said another, and which of the two is grounded in what.
So the adjudication lives beside the measurement and a consumer joins them on `span_id`.

PROVENANCE IS THE WEAK POINT, AND IT IS WEAKER HERE THAN USUAL. Every verdict below is TRANSCRIBED
by me, from a relay of Chris's words that passed through a second session before reaching this one.
It is not a measurement and it is not my judgment. Each row carries `basis` as Chris's own sentence,
untrimmed, so the typed fields can be checked against what he actually said rather than against what
I concluded from it. A fact he did not state is `None`, never inferred -- he said the blue witness
tick was on the Hebrew's line for p107:n3 and said nothing about the other four, so those four record
no claim about the witness at all.

TWO THINGS THAT ARE NOT LINE COUNTS, and the reason the vocabulary is typed rather than numeric:

  `no_hebrew_on_crop` (p256:n3). "No Hebrew on crop" is not an offset of zero and not an offset of
  any size. No line on that crop can be the Hebrew, so a distance to it does not exist. A schema
  that forced this into a number would have recorded a measurement where there is none -- the same
  defect as a system with no "empty" channel turning an honest observation into a fabrication. The
  class carries no `lines_from_hebrew` at all, and a check enforces that.

  `not_adjudicated` (p92:n1). The sheet's own control, which Chris was not shown for adjudication.
  It is a ROW here, not an absence, because a span missing from a record of verdicts reads as a span
  that passed. p92:n1 is the span whose crop was found sitting three lines off while a byte-identity
  comparison reported 74/74, so it is the last one whose silence should look like a pass.

THE OFFSETS RUN BOTH WAYS: one line above on two cards, two lines below on two. There is no single
shift to correct, and `no_single_shift` asserts it rather than leaving it in prose. Chris's reading
is that each box is placed wrong for its own reason, which fits a wrong note region better than an
arithmetic slip; that reading is recorded as his, in his words, and this record does not add to it.

THE SHEET THESE ANSWER IS PROVISIONAL. It was built with both trees dirty (`provisional: true` in
its own manifest), so by the clean-run rule it cannot be cited in an ADR or a tier change -- and
neither can this record, for a rate or a tier. What the verdicts ARE good for is unchanged: Chris
looked at pixels, and the pixels are pinned here by the sha16 of each marked crop he saw. The
dirtiness is a fact about the artifact's identity, not about his eyes, and `citable_for` says so
instead of leaving a reader to work it out.

HASH RULE (ruling 5): sha256 over the UTF-8 bytes of the record serialised with
`ensure_ascii=False, sort_keys=True, indent=1`, with the `self_sha16` field absent.

All page numbers are FILE pages (printed = file - 88).
"""
import hashlib
import io
import json
import os
import sys

from clean_run import git_state, provisional
import hebrew_aperture_diag as diag

DATA = str(diag.DATA)
SHEET_DIGEST = "3f6b0357a850548e"
MANIFEST = "GEOMETRY5_sheet_%s.json" % SHEET_DIGEST
SHEET = "GEOMETRY5_sheet_%s.html" % SHEET_DIGEST
RELAY = r"C:\tmp\a2\RELAY_chris_geometry5_verdicts_20261115.md"
#: The archived copy, beside the record in the private data repo. `C:\tmp` is outside both repos
#: and will not outlive the machine; a record whose central claim is "these are his words verbatim"
#: must keep the document those words came from, or the claim is unfalsifiable the first time the
#: temp directory is cleared.
RELAY_ARCHIVED = "RELAY_chris_geometry5_verdicts_20261115.md"


def relay_lines(path=None):
    """The verbatim block's lines, in order, from the archived relay. Raises if it is not there.

    The block is the one fenced section of the relay: Chris's five sentences and nothing else. The
    prose around it is A2's, and a comparison that let prose in would pass on a paraphrase."""
    p = path or os.path.join(DATA, RELAY_ARCHIVED)
    txt = io.open(p, encoding="utf-8").read()
    parts = txt.split("```")
    if len(parts) < 3:
        raise ValueError("%s holds no fenced verbatim block" % p)
    return [l.strip() for l in parts[1].split("\n") if l.strip()]

#: Verdict vocabulary, typed by WHAT IS BEING ASSERTED rather than by a number.
#:
#:   box_off_by_lines   the stored box is on printed type, but N lines away from the Hebrew. Carries
#:                      a SIGNED `lines_from_hebrew`.
#:   box_on_hebrew      the stored box is on the Hebrew. Declared, unused in this sitting, and kept
#:                      because a vocabulary with no way to say "correct" cannot record a pass.
#:   no_hebrew_on_crop  no line on the crop can be the Hebrew. Not an offset of any size; carries no
#:                      line count, by rule.
#:   not_adjudicated    not put in front of him. Claims nothing.
VERDICTS = ("box_off_by_lines", "box_on_hebrew", "no_hebrew_on_crop", "not_adjudicated")

#: Sign rule for `lines_from_hebrew`, stated once and checked against Chris's own words below:
#: NEGATIVE means the stored box is ABOVE the Hebrew, POSITIVE means it is BELOW. The words "above"
#: and "below" in each `basis` are what the sign is derived from, and `check` re-derives it from the
#: basis text rather than trusting the integer -- a sign flip is the one transcription error that
#: would read as a clean measurement.
SIGN_RULE = ("negative = the stored box is ABOVE the Hebrew; positive = BELOW. Derived from the "
             "words 'above' and 'below' in Chris's own basis, and re-checked against them.")

#: Chris's verdicts, 2026-11-15, relayed via the Lane A2 session. `basis` is his sentence verbatim.
AUDIT = [
    {"span_id": "p107:n3", "verdict": "box_off_by_lines", "lines_from_hebrew": -1,
     "basis_is_his_words": True,
     "basis": u'p107:n3 \u2014 red box 1 line above the Hebrew. Box is on roman type '
              u'("Paradise Lost.", note x); the Hebrew is in note y. Blue tick is on the '
              u"Hebrew's line.",
     # The only span for which he stated anything about the blue witness tick. For this one the
     # witness and the eye AGREE and the stored box is the outlier -- so here the witness could have
     # caught it. That is a fact about one span and is not generalised to the other four.
     "witness_agrees_with_eye": True,
     # His own ruling to A2, recorded as his: p107:n3 is a confirmed instance of the
     # two-printed-notes-in-one-note_line_region debt. He also names the two notes: the box is on
     # note x, the Hebrew is in note y.
     "confirms_debt": "two printed notes inside one note_line_region (A2's debt); Chris named this "
                      "span as a confirmed instance on 2026-11-15",
     "box_is_on": u'roman type, "Paradise Lost." in note x; the Hebrew is in note y'},
    {"span_id": "p133:n1", "verdict": "box_off_by_lines", "lines_from_hebrew": -1,
     "basis_is_his_words": True,
     "basis": u"p133:n1 - red box 1 line above the Hebrew",
     "witness_agrees_with_eye": None, "confirms_debt": None, "box_is_on": None},
    {"span_id": "p144:n0", "verdict": "box_off_by_lines", "lines_from_hebrew": 2,
     "basis_is_his_words": True,
     "basis": u"p144:n0 - red box 2 lines below the hebrew",
     "witness_agrees_with_eye": None, "confirms_debt": None, "box_is_on": None},
    # No line count, by rule: there is no Hebrew on the crop to be a distance from.
    {"span_id": "p256:n3", "verdict": "no_hebrew_on_crop",
     "basis_is_his_words": True,
     "basis": u"p256:n3 - no hebrew on crop",
     "witness_agrees_with_eye": None, "confirms_debt": None, "box_is_on": None},
    {"span_id": "p306:n1", "verdict": "box_off_by_lines", "lines_from_hebrew": 2,
     "basis_is_his_words": True,
     "basis": u"p306:n1 - red box 2 lines below the hebrew",
     "witness_agrees_with_eye": None, "confirms_debt": None, "box_is_on": None},
    # The sheet's control. A row, not an absence -- see the module docstring.
    {"span_id": "p92:n1", "verdict": "not_adjudicated",
     "basis_is_his_words": False,
     "basis": u"the sheet's control (`control_not_adjudicated`); not put in front of Chris in this "
              u"sitting, so nothing here is a claim about it. It is the span whose crop was found "
              u"three lines off while a byte-identity comparison reported 74/74.",
     "witness_agrees_with_eye": None, "confirms_debt": None, "box_is_on": None},
]

#: A2's reading of the same five verdicts, carried as a CONSUMER's observations. Chris forwarded
#: these to Lane B as findings worth having; they are not verdicts and they do not join as rows.
CONSUMER_OBSERVATIONS = [
    {"from": "Lane A2", "session": "20133971-29e4-4c59-a118-64dc3d8ff470",
     "observation": u"p256:n3's 'no hebrew on crop' is not a placement offset; no line on the crop "
                    u"can be the Hebrew, so the verdict needs its own field, not a line count.",
     "acted_on": u"yes: `no_hebrew_on_crop` is its own class and carries no `lines_from_hebrew`, "
                 u"enforced by a check."},
    {"from": "Lane A2", "session": "20133971-29e4-4c59-a118-64dc3d8ff470",
     "observation": u"The offsets are mixed: 1 line above (x2) and 2 lines below (x2). As a group "
                    u"the five do not show one vertical displacement.",
     "acted_on": u"yes: `no_single_shift` is asserted from the signed values, not left in prose."},
    {"from": "Lane A2", "session": "20133971-29e4-4c59-a118-64dc3d8ff470",
     "observation": u"p306:n1 is the sheet's rate-exclusion (page-level contamination); excluding "
                    u"it is the sheet's rule, not the relay's.",
     "acted_on": u"yes: its verdict is recorded like the others and `excluded_from_rate` is carried "
                 u"from the sheet's own manifest, with tallies reported both ways."},
    {"from": "Lane A2", "session": "20133971-29e4-4c59-a118-64dc3d8ff470",
     "observation": u"p107:n3 is the case on the A2 handoff as a note_line_region covering TWO "
                    u"printed notes; the verdict says the box sits on note x and the Hebrew is in "
                    u"note y.",
     "acted_on": u"recorded on the row as `confirms_debt`, attributed to Chris's own ruling of "
                 u"2026-11-15 rather than to this inference."},
]


def digest(obj):
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _sign_from_basis(basis):
    """Re-derive the sign from Chris's words. Returns -1, +1 or None.

    The integer in a row and the sentence it came from are two statements of one fact, and a flipped
    sign is the transcription error that would read as a clean measurement -- "2 lines below" typed
    as -2 is a well-formed row describing the opposite of what he saw. So the sign is checked against
    the words, not trusted. `None` where the words say neither, which is itself a finding.
    """
    b = basis.lower()
    above, below = "above" in b, "below" in b
    if above == below:          # both or neither: the basis does not settle it
        return None
    return -1 if above else 1


#: The number of checks that must run to the end for anything to be written. Read by `check`'s
#: completion gate and recorded in the artifact, so the two cannot drift: a run at any other count
#: refuses and leaves nothing behind. Deliberately NOT asserted inside `ck` -- comparing this
#: constant with itself would be a verifier asking the producer, and would move the number it checks.
# 26 -> 32: six for provenance. The record claimed Chris's words verbatim and named the relay in
# prose without ever opening it, and a transcription lost a character of his span id.
CHECKS_EXPECTED = 32


def build():
    start = {"laneB": git_state(os.path.dirname(os.path.abspath(__file__))), "drv": git_state(DATA)}
    mp = os.path.join(DATA, MANIFEST)
    man = json.load(io.open(mp, encoding="utf-8"))
    with io.open(os.path.join(DATA, SHEET), "rb") as fh:
        sheet_sha = hashlib.sha256(fh.read()).hexdigest()[:16]
    # HIS WORDS, FROM THE DOCUMENT THEY ARE IN. Read before the rows are built, so a missing or
    # malformed archive stops the record being written rather than producing one whose provenance
    # claim is untestable.
    relay_path = os.path.join(DATA, RELAY_ARCHIVED)
    with io.open(relay_path, "rb") as fh:
        relay_sha = hashlib.sha256(fh.read()).hexdigest()[:16]
    quoted = relay_lines()
    rows = []
    for r in AUDIT:
        r = dict(r)
        pf = int(r["span_id"].split(":")[0][1:])
        r["page_file"], r["page_printed"] = pf, pf - 88
        card = man["cards"].get(r["span_id"], {})
        # The verdict is about the MARKED crop -- the one carrying the red box and the blue tick --
        # so that is the artifact it is pinned to. A verdict pinned to a filename would survive the
        # pixels changing under it.
        r["marked_sha16"] = card.get("marked_sha16")
        r["plain_sha16"] = card.get("plain_sha16")
        r["realized_crop_origin"] = card.get("realized_crop_origin")
        r["realized_crop_extent"] = card.get("realized_crop_extent")
        r["excluded_from_rate"] = r["span_id"] in man["excluded_from_rate"]
        r["in_adjudication_population"] = r["span_id"] in man["adjudication_population"]
        r["sign_from_basis"] = _sign_from_basis(r["basis"])
        rows.append(r)
    adj = [r for r in rows if r["verdict"] != "not_adjudicated"]
    offs = [r["lines_from_hebrew"] for r in adj if r["verdict"] == "box_off_by_lines"]
    end = {"laneB": git_state(os.path.dirname(os.path.abspath(__file__))), "drv": git_state(DATA)}
    prov = (provisional(start["laneB"], end["laneB"]) or provisional(start["drv"], end["drv"])
            or bool(man.get("provisional")))
    rec = {
        "kind": "geometry5_adjudication",
        "lane": "Lane B",
        "session": "50612c81",
        "date": "2026-11-15",
        "of": MANIFEST,
        "of_digest": SHEET_DIGEST,
        # The sheet's BYTES, re-hashed here, not copied from the manifest. A record that quoted the
        # manifest's own figure would agree with it by construction.
        "of_sheet_sha256_16": sheet_sha,
        "manifest_says_sheet_sha256_16": man["sheet_sha256_16"],
        "page_convention": "all page numbers are FILE pages (printed = file - 88)",
        "standoff": ("the measurement is not edited; this record sits beside it and a consumer "
                     "joins on span_id. Where the stored box and Chris's eye disagree, BOTH stand, "
                     "each with its own grounding."),
        "provenance": ("transcribed by Lane B from a relay of Chris's words that passed through the "
                       "Lane A2 session (%s). Not a measurement and not Lane B's judgment. Every "
                       "row carries Chris's sentence verbatim as `basis`; a fact he did not state "
                       "is None, never inferred." % RELAY),
        "verdict_vocabulary": {
            "box_off_by_lines": "stored box is on printed type, N lines from the Hebrew; carries a "
                                "signed lines_from_hebrew",
            "box_on_hebrew": "stored box is on the Hebrew. Declared and unused in this sitting: a "
                             "vocabulary with no way to say 'correct' cannot record a pass",
            "no_hebrew_on_crop": "no line on the crop can be the Hebrew. NOT an offset of any "
                                 "size; carries no line count, by rule",
            "not_adjudicated": "not put in front of him; claims nothing"},
        "relay": {
            "archived": RELAY_ARCHIVED,
            "sha256_16": relay_sha,
            "source_path_at_build": RELAY,
            "verbatim_lines": quoted,
            "means": ("the document Chris's words reached Lane B in, archived beside this record "
                      "and hashed here. Every row flagged `basis_is_his_words` is byte-identical "
                      "to one of these lines, and every line is claimed by a row -- checked both "
                      "ways, because a verdict dropped in transcription is invisible to a per-row "
                      "comparison. The transcription of p107:n3 lost the leading 'p' of its span "
                      "id and nothing could see it until this comparison existed."),
        },
        "sign_rule": SIGN_RULE,
        "hash_rule": ("sha256[:16] over the UTF-8 bytes of this record serialised with "
                      "ensure_ascii=False, sort_keys=True, indent=1, with the self_sha16 field "
                      "absent. To verify: parse, remove self_sha16, re-serialise with those "
                      "options, hash. Checked at write time."),
        "rows": rows,
        "consumer_observations": CONSUMER_OBSERVATIONS,
        "consumer_observations_are": ("Lane A2's reading of the same verdicts, forwarded by Chris "
                                      "as findings worth having. NOT verdicts, and they do not "
                                      "join as rows."),
        # Both ways, always. A single headline rate over a population with an exclusion in it is the
        # shape of defect this project has been bitten by before.
        "tallies": dict((v, len([r for r in rows if r["verdict"] == v])) for v in VERDICTS),
        "tallies_excluding_rate_exclusions":
            dict((v, len([r for r in rows if r["verdict"] == v and not r["excluded_from_rate"]]))
                 for v in VERDICTS),
        "no_single_shift": {
            "offsets": sorted(offs),
            "distinct_signs": sorted(set(1 if x > 0 else -1 for x in offs)),
            "holds": len(set(1 if x > 0 else -1 for x in offs)) > 1,
            "means": ("the five do not share one vertical displacement, so no single shift "
                      "corrects them. Chris's reading -- recorded as his -- is that each box is "
                      "placed wrong for its own reason, which fits a wrong note region better than "
                      "an arithmetic slip. This record does not add to that reading.")},
        "git_start": start,
        "git_end": end,
        "provisional": prov,
        "provisional_because": (
            "the GEOMETRY5 sheet's own manifest records provisional: %s (built with both trees "
            "dirty); this record's own run was %s" % (
                bool(man.get("provisional")),
                "clean" if not (provisional(start["laneB"], end["laneB"])
                                or provisional(start["drv"], end["drv"])) else "not clean")),
        "citable_for": ("the verdicts themselves, each pinned to the sha16 of the marked crop Chris "
                        "looked at. NOT for a fault rate and NOT for a tier change: the sheet it "
                        "answers is provisional by the clean-run rule. The dirtiness is a fact "
                        "about the artifact's identity, not about his eyes."),
        "checks": {
            "count": CHECKS_EXPECTED,
            "meaning": ("this record exists only because exactly this many checks ran to the end "
                        "and none failed. A run that reaches a different count prints SUITE DID "
                        "NOT RUN TO COMPLETION and writes nothing, so the number is not a claim "
                        "about the run -- it is the condition the run had to meet to produce the "
                        "file you are reading. Without it, a reader cannot tell a 26-check pass "
                        "from a 3-check one, and an unpersisted measurement is a comment."),
            "harness": ("the guards are proven live by mutation, not by green; the harness is a "
                        "scratch script, so its result lives in the commit message, not here"),
        },
        "spend": "none; no model call, no outbound request",
    }
    rec["self_sha16"] = digest(rec)
    return rec, man


def check(rec, man):
    n, fail = [0], []

    def ck(cond, msg):
        n[0] += 1
        if not cond:
            fail.append(msg)

    rows = rec["rows"]
    # FIRST, and before anything indexes the manifest. A row naming a span the manifest does not
    # hold used to raise KeyError three checks later, which ABORTS the suite rather than failing it:
    # every check after the raise went unevaluated and no count was printed to say so. The two
    # mutations that drop a span were DEAD for exactly that reason.
    _unknown = sorted(r["span_id"] for r in rows if r["span_id"] not in man["cards"])
    ck(not _unknown,
       "every row names a span the sheet's manifest actually holds: unknown %s" % (_unknown,))
    ck(all(r["verdict"] in VERDICTS for r in rows), "every verdict is in the vocabulary")
    ck(len(set(r["span_id"] for r in rows)) == len(rows),
       "one verdict per span: a duplicate would let two verdicts about one span both stand")
    ck(all(r["page_printed"] == r["page_file"] - 88 for r in rows),
       "the printed page is derived, never typed")
    ck(all(r["basis"] for r in rows), "every row carries a basis, including the unadjudicated one")

    # ------------------------------------------------- THE BASIS IS HIS SENTENCE, OR IT IS NOT HIS
    _his = [r for r in rows if r.get("basis_is_his_words")]
    _ours = [r for r in rows if not r.get("basis_is_his_words")]
    _quoted = rec["relay"]["verbatim_lines"]
    ck(all("basis_is_his_words" in r for r in rows),
       "every row says whose sentence its basis is, rather than leaving it to the verdict")
    ck([r["span_id"] for r in _ours] == ["p92:n1"]
       and all(r["verdict"] == "not_adjudicated" for r in _ours),
       "the only basis that is not his is the control's, which is Lane B's own description")
    _unquoted = [r["span_id"] for r in _his if r["basis"] not in _quoted]
    ck(not _unquoted,
       "every his-words basis is byte-identical to a line of the relay: %s" % _unquoted)
    # THE OTHER DIRECTION. A row can only be wrong about a line it has; a line with no row is a
    # verdict dropped in transcription, and nothing in a per-row comparison can see one.
    _unclaimed = [l for l in _quoted if l not in [r["basis"] for r in _his]]
    ck(not _unclaimed,
       "every line of the relay's verbatim block is claimed by a row: %s" % _unclaimed)
    ck(len(_his) == len(_quoted) == 5,
       "five sentences, five rows that quote them (%d, %d)" % (len(_his), len(_quoted)))
    # The archive is the thing being compared against, so its bytes are checked too: a record that
    # verified itself against a file it had rewritten would agree by construction.
    _ap = os.path.join(DATA, rec["relay"]["archived"])
    _live_relay = None
    if os.path.exists(_ap):
        with io.open(_ap, "rb") as _fh:
            _live_relay = hashlib.sha256(_fh.read()).hexdigest()[:16]
    ck(_live_relay == rec["relay"]["sha256_16"],
       "the archived relay on disk is the one this record was built from (%s vs %s)"
       % (_live_relay, rec["relay"]["sha256_16"]))
    # ---- the typed classes assert what they claim and nothing else
    ck(all("lines_from_hebrew" not in r for r in rows if r["verdict"] == "no_hebrew_on_crop"),
       "a no_hebrew_on_crop row carries NO line count: there is no Hebrew to be a distance from, "
       "and a zero or any other number would be a measurement where there is none")
    ck(all(isinstance(r.get("lines_from_hebrew"), int) and r["lines_from_hebrew"] != 0
           for r in rows if r["verdict"] == "box_off_by_lines"),
       "every box_off_by_lines row carries a non-zero signed integer: an offset of zero is the "
       "box_on_hebrew class, not this one")
    # ---- the sign is checked against Chris's words, not trusted
    ck(all(r["sign_from_basis"] is not None for r in rows if r["verdict"] == "box_off_by_lines"),
       "every offset row's basis says 'above' or 'below', so the sign has a witness in his words")
    ck(all((r["lines_from_hebrew"] > 0) == (r["sign_from_basis"] > 0)
           for r in rows if r["verdict"] == "box_off_by_lines"),
       "every recorded sign agrees with the direction word in Chris's own sentence: a flipped sign "
       "is the one transcription error that reads as a clean measurement")
    # ---- nothing is inferred
    ck(all(r["witness_agrees_with_eye"] is None for r in rows if r["span_id"] != "p107:n3"),
       "the blue witness tick is claimed ONLY for p107:n3, the one span he spoke about it on")
    ck([r["span_id"] for r in rows if r["witness_agrees_with_eye"] is not None] == ["p107:n3"],
       "and it IS claimed there, so the clause above is not satisfied by claiming nothing anywhere")
    ck(all(r["witness_agrees_with_eye"] is None and r["confirms_debt"] is None
           for r in rows if r["verdict"] == "not_adjudicated"),
       "an unadjudicated row claims nothing at all")
    # ---- the population is the sheet's, not this record's
    ck(sorted(r["span_id"] for r in rows if r["in_adjudication_population"])
       == sorted(man["adjudication_population"]),
       "every span the sheet put up for adjudication has a verdict here: %s"
       % (sorted(set(man["adjudication_population"])
                 - set(r["span_id"] for r in rows)),))
    ck([r["span_id"] for r in rows if not r["in_adjudication_population"]]
       == [man["control_not_adjudicated"]],
       "the only row outside that population is the sheet's own control, and it IS present -- a "
       "control missing from a record of verdicts reads as a control that passed")
    ck(all(r["excluded_from_rate"] == (r["span_id"] in man["excluded_from_rate"]) for r in rows),
       "the rate exclusion is carried from the sheet's manifest, not decided here")
    ck(sum(rec["tallies"].values()) == len(rows)
       and sum(rec["tallies_excluding_rate_exclusions"].values()) == len(rows) - 1,
       "both tallies account for every row, and they differ by exactly the one excluded span")
    # ---- the pixels
    ck(all(r["marked_sha16"] and len(r["marked_sha16"]) == 16 for r in rows),
       "every row is pinned to the sha16 of the MARKED crop, the artifact Chris actually looked at")
    ck(len(set(r["marked_sha16"] for r in rows)) == len(rows),
       "no two rows are pinned to the same crop bytes")
    ck(all(r["marked_sha16"] == man["cards"].get(r["span_id"], {}).get("marked_sha16")
           for r in rows),
       "each pin matches the manifest's own record of that crop")
    # MEASURED HERE, not taken from `build`. Comparing build's figure with the manifest's was a
    # verifier asking the producer: a build that read both from the manifest agreed with itself by
    # construction, and the mutation that did that wrote a record. This re-reads the sheet.
    with io.open(os.path.join(DATA, SHEET), "rb") as _fh:
        _live = hashlib.sha256(_fh.read()).hexdigest()[:16]
    ck(rec["of_sheet_sha256_16"] == _live == rec["manifest_says_sheet_sha256_16"],
       "the sheet on disk still hashes to what its manifest says, and to what this record claims, "
       "with the hash re-measured here rather than taken from the builder: %s vs %s vs %s"
       % (rec["of_sheet_sha256_16"], _live, rec["manifest_says_sheet_sha256_16"]))
    # ---- the group claim
    ck(rec["no_single_shift"]["holds"] and len(rec["no_single_shift"]["distinct_signs"]) == 2,
       "the offsets run both ways, so no single shift corrects them -- asserted, not left in prose")
    # ---- provenance and citability
    ck(rec["provisional"] is True and "provisional: True" in rec["provisional_because"],
       "the record states that the sheet it answers is provisional")
    ck("NOT for a fault rate" in rec["citable_for"],
       "and states what that forbids, rather than leaving a reader to work it out")
    ck(rec["consumer_observations_are"].count("NOT verdicts") == 1
       and all(o["from"] != "Chris" for o in rec["consumer_observations"]),
       "A2's notes are marked as a consumer's observations and none is attributed to Chris")
    ck(all(o.get("acted_on") for o in rec["consumer_observations"]),
       "every consumer observation records what was done about it: a note filed and not acted on "
       "is the recording-a-flag defect")
    ck(rec["self_sha16"] == digest(dict((k, v) for k, v in rec.items() if k != "self_sha16")),
       "the digest is over the record without its own digest field")
    EXPECTED = CHECKS_EXPECTED
    print("geometry5_adjudication: %d checks, %d failed" % (n[0], len(fail)))
    for m in fail:
        print("  FAIL  %s" % m)
    if n[0] != EXPECTED:
        print("SUITE DID NOT RUN TO COMPLETION: %d checks, expected %d." % (n[0], EXPECTED))
        return 2
    return 1 if fail else 0


def main():
    rec, man = build()
    rc = check(rec, man)
    if rc:
        print("REFUSED: nothing written.")
        return rc
    # Named by what it describes: the sheet's digest, as the manifest's `answer_record_would_be`
    # says. Staged and renamed only once the round-trip passes -- a build that refuses must leave
    # nothing behind.
    name = "GEOMETRY5_adjudication_%s.json" % SHEET_DIGEST
    final = os.path.join(DATA, name)
    stage = final + ".staging"
    body = json.dumps(rec, ensure_ascii=False, sort_keys=True, indent=1)
    with io.open(stage, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    back = json.load(io.open(stage, encoding="utf-8"))
    ok = (back["self_sha16"] == digest(dict((k, v) for k, v in back.items()
                                            if k != "self_sha16"))
          and back == rec)
    if not ok:
        os.unlink(stage)
        print("REFUSED: the written bytes do not round-trip to the record. Nothing left behind.")
        return 2
    if os.path.exists(final):
        os.unlink(final)
    os.rename(stage, final)
    print("wrote %s" % final)
    print("  self_sha16 %s   rows %d   tallies %s" % (rec["self_sha16"], len(rec["rows"]),
                                                      rec["tallies"]))
    print("  provisional %s -- %s" % (rec["provisional"], rec["citable_for"][:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
