"""Born-test: the sealed-page Hebrew truths are DERIVED from the signed sitting, not typed by an agent.

    python test_hebrew_sealed_truth.py

WHY THIS EXISTS. Ruling 2 (2026-09-20) opens sealed pages for the Hebrew aperture harness only, taking the
scorable set from n=10 to n=19. The 9 new truth strings are Hebrew, and an agent retyping Hebrew is the
**plausible-word-substitution** failure this lane measures at 35%: a wrong string that reads fluently and
scores things against itself forever. So the strings in `SEALED_TRUTH` are derived from
`hebrew_sitting_chris_20260906.jsonl` by a rule, and this test checks the rule and the derivation.

THE RULE, AND THE THREE CASES IT COVERS:

    chosen == "correct"                  -> the candidate line's Hebrew span, verbatim
    chosen == "wrong" + Hebrew correction -> the correction string, verbatim
    chosen == "wrong" + empty correction  -> UNSCORABLE (the rule that already excluded p138:n6)

WHAT MAKES IT CHECKABLE. The rule is validated against the FOUR hand-written `candidate-verbatim` entries in
the original `TRUTH` dict — spans a human derived by hand, before this rule existed. If the rule reproduces
those four exactly, it is not inventing readings; if it ever stops, this test fails rather than the corpus
quietly acquiring a truth nobody signed.

n IS AN ASSERTION HERE, not a description. The prerun's arithmetic says the sealed carve-out takes the set
to exactly 19 scorable. That number is only consistent with counting p726:n3 scorable and p596:n2 not, so it
is asserted: if someone later reinterprets either span, this test fails and the report's `n=19` cannot drift
away from what the set actually contains.

SCOPE. This asserts the strings trace to the signature. It does NOT assert Chris would sign them again, and
it cannot adjudicate p726:n3 — whose verdict text ("correct but should have no makers") is about MARKERS,
not about the Hebrew. That reading is flagged in the prerun and in every report; this test only pins what
the code currently claims so the claim cannot move silently."""
import io
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import re
import hebrew_aperture_diag as D
import nikud_gate

fails = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(f"{name}: {detail}")


def N(t):
    return unicodedata.normalize("NFC", (t or "").strip())


sitting = {o["span_id"]: o for o in D._lines(D.DOWN / "hebrew_sitting_chris_20260906.jsonl")
           if "span_id" in o}
agent = {o["span_id"]: o for o in D._lines(D.DOWN / "hebrew_sitting_agent_20260906.jsonl")
         if "span_id" in o}

print("(1) the derivation rule reproduces the HAND-WRITTEN truths (it invents nothing)")
# These four were derived by a human before the rule existed. They are the rule's control group.
for sid in ("p102:n0", "p138:n5", "p219:n0", "p360:n0"):
    hand = D.TRUTH[sid][0]
    got = D._heb_span(sitting[sid]["inputs"]["candidates"][0])
    check(f"{sid} derived == hand-written", N(got) == N(hand), f"derived={got!r} hand={hand!r}")

print("\n(1b) p200:n2 carries NO pointing -- Chris's ruling of 2026-09-27")
# The sitting showed a POINTED candidate that was missing a vav; Chris added the vav and the
# pointing rode along with the string he was editing. He ruled on 2026-09-27 that the points are
# not in the original. The stored truth is therefore strip_nikud(his correction) -- the same
# derivation p253:n2 already uses -- so the table has ONE convention and an `exact` rate is
# measured against one standard. Pinned because the cost of the pointed entry was concrete: 18 of
# 30 arms scored `nikud-only` instead of `exact`, and two audits published the span as having no
# correct candidate from any arm.
_corr = sitting["p200:n2"]["disputed_span_correction"].strip()
_want = D.TRUTH["p200:n2"][0]
check("p200:n2 truth == strip_nikud(the signed correction)",
      N(D.nikud_gate.strip_nikud(_corr)) == N(_want),
      f"strip={D.nikud_gate.strip_nikud(_corr)!r} stored={_want!r}")
check("p200:n2 truth carries no combining marks at all",
      not any(unicodedata.combining(c) for c in _want), repr(_want))
check("p200:n2 keeps the vav Chris added (the consonantal edit he actually made)",
      "\u05d5" in _want.split()[-1], repr(_want))
check("p200:n2 basis records the ruling",
      "ruled-20260927" in D.TRUTH["p200:n2"][1], D.TRUTH["p200:n2"][1])

print("\n(1c) p362:n1 is TWO words -- Chris's ruling of 2026-09-27")
# Same inherited-property failure as p200:n2. The sitting candidate \u05dc\u05d4\u05ea\u05d2\u05dc\u05e2\u05dc\u05d9\u05e0\u05d5 was one lamed
# short AND unspaced; Chris supplied the lamed and the joined words rode along. He ruled on
# 2026-09-27 that there is a space. The stored truth is the agent row of the SAME sitting, which
# recorded the spaced form on 2026-09-06 -- derived from a file, not typed. The ruling is allowed to
# move word division and nothing else, which is what the space-stripped equality asserts.
_chris = sitting["p362:n1"]["disputed_span_correction"].strip()
_agent = agent["p362:n1"]["disputed_span_correction"].strip()
_p362 = D.SEALED_TRUTH["p362:n1"][0]
check("p362:n1 truth == the agent row of the same sitting, verbatim",
      N(_agent) == N(_p362), f"agent={_agent!r} stored={_p362!r}")
check("p362:n1 ruling moved word division ONLY -- not one letter",
      _chris.replace(" ", "") == _p362.replace(" ", ""), f"chris={_chris!r} stored={_p362!r}")
check("p362:n1 truth is two words", len(_p362.split()) == 2, repr(_p362))
check("p362:n1 basis records the ruling",
      "ruled-20260927" in D.SEALED_TRUTH["p362:n1"][1], D.SEALED_TRUTH["p362:n1"][1])

print("\n(1d) Chris's re-sign batch of 2026-09-27: four verdicts on SHAPE, none of them typed")
# The property that matters is not "the table holds these four strings" -- that is what a literal would
# give, and a literal is checked against nothing. It is that each string FALLS OUT of the string the
# sitting recorded, by the rule the verdict names, and that the rule could not have been applied
# ambiguously. p895:n0 is why: it was reported as already re-signed in a committed audit and in two
# sessions of notes while the table still held the ayin form, and the derivation is what caught it.
_BATCH = {
    "p217:n2": ("mem", "pe", "the candidate was affirmed verbatim and the third glyph was never looked at"),
    "p423:n3": ("bet", "gimel", "signed from the re-cut crop -- the first pixels this span has had"),
    "p895:n0": ("ayin", "tsadi", "reported as already applied for a day while the table said otherwise"),
}
for _sid, (_a, _b, _why) in sorted(_BATCH.items()):
    _t = D.SEALED_TRUTH.get(_sid) or D.TRUTH[_sid]
    _frm, _to, _obs = D.GLYPH_RESIGN[_sid]
    _rec = sitting[_sid]
    _corr = (_rec.get("disputed_span_correction") or "").strip()
    _base = _corr if (_rec.get("chosen") == "wrong" and D.HEB.search(_corr)) else D._heb_span(
        _rec["inputs"]["candidates"][0])
    check(f"{_sid} truth == the sitting string with its one {_a} replaced by {_b} ({_why})",
          N(_t[0]) == N(D._resign(_base, _frm, _to)), f"{_t[0]!r} from {_base!r}")
    check(f"{_sid} the substitution was unambiguous: exactly one {_a} in the base",
          _base.count(_frm) == 1, f"{_base.count(_frm)} occurrence(s)")
    check(f"{_sid} basis records the re-sign and its date", "resign" in _t[1] and "20260927" in _t[1], _t[1])
    check(f"{_sid} the shape observation is recorded, not just the substitution",
          len(_obs) > 80 and ("not a mem" in _obs or "stem" in _obs or "one line" in _obs), _obs[:60])
# The rule must refuse when it cannot be applied. Asserted in the direction of the MISTAKE: a string
# with two of the letter, and a depointing applied to something that was never pointed.
try:
    D._resign("\u05de\u05de", "\u05de", "\u05e4")
    check("_resign refuses an ambiguous substitution", False, "it returned instead of raising")
except AssertionError as _e:
    check("_resign refuses an ambiguous substitution (two candidates, no 'the')", "exactly one" in str(_e))
try:
    D._depoint("\u05e9\u05d0\u05e8")
    check("_depoint refuses a string that carries no points", False, "it returned instead of raising")
except AssertionError as _e:
    check("_depoint refuses a string that carries no points (wrong span)", "no points" in str(_e))

print("\n(1e) p726:n3 is BARE -- Chris's verdict from the 4x crop, 2026-09-27")
_p726 = D.SEALED_TRUTH["p726:n3"][0]
_p726_base = D._heb_span(sitting["p726:n3"]["inputs"]["candidates"][0])
check("p726:n3 truth == strip_nikud(the pointed candidate he affirmed)",
      N(_p726) == N(nikud_gate.strip_nikud(_p726_base)), f"{_p726!r} from {_p726_base!r}")
check("the base really was pointed, so the ruling changed something",
      _p726_base != nikud_gate.strip_nikud(_p726_base))
check("p726:n3 carries no combining marks at all",
      not re.search(r"[\u0591-\u05c7]", _p726), " ".join(hex(ord(c))[2:] for c in _p726))
check("the ruling moved POINTS only -- not one consonant",
      nikud_gate.strip_nikud(_p726_base) == _p726, f"{_p726!r}")
check("p726:n3 basis records the ruling", "ruled-20260927" in D.SEALED_TRUTH["p726:n3"][1],
      D.SEALED_TRUTH["p726:n3"][1])
# What this closes, asserted rather than asserted-in-prose: the book-wide claim the prompt makes on
# every span, and this span's scorability, which used to rest on an interpretation of mine.
check("NO signed truth in either table carries points any more -- the prompt's book-wide "
      "'Gill's Hebrew is unpointed' assertion has no counter-example in the signed set",
      not [s for s, (t, _b) in list(D.TRUTH.items()) + list(D.SEALED_TRUTH.items())
           if isinstance(t, str) and re.search(r"[\u0591-\u05c7]", t)],
      [s for s, (t, _b) in list(D.TRUTH.items()) + list(D.SEALED_TRUTH.items())
       if isinstance(t, str) and re.search(r"[\u0591-\u05c7]", t)])
check("p726:n3 no longer takes the marker-defect path, so n no longer rests on reading a prose verdict",
      "marker-defect" not in D.SEALED_TRUTH["p726:n3"][1])

print("\n(2) every sealed truth traces to the signature by the stated rule")
D._assert_derivation(sitting, agent)   # raises on any mismatch
check(f"_assert_derivation passes over all {len(D.SEALED_TRUTH)} sealed truths", True)
for sid, (want, basis) in sorted(D.SEALED_TRUTH.items()):
    rec = sitting.get(sid)
    check(f"{sid} is in the signed sitting", rec is not None)
    if not rec:
        continue
    corr = (rec.get("disputed_span_correction") or "").strip()
    chosen = rec.get("chosen")
    if sid in D.GLYPH_RESIGN or sid in D.DEPOINTED_POST_SITTING:
        # A span re-signed on 2026-09-27. The dispatch below is by sitting-row SHAPE, and a re-signed
        # span still HAS its old shape -- p217:n2's row still says chosen == "correct" -- so without
        # this branch it walks into the pin for the reading Chris overturned. Section 1d/1e carry the
        # per-span derivation; here we only assert that the licence is declared and that the truth is
        # not the raw sitting string any more.
        base = corr if (chosen == "wrong" and D.HEB.search(corr)) else D._heb_span(
            rec["inputs"]["candidates"][0])
        want2 = D._resign(base, *D.GLYPH_RESIGN[sid][:2]) if sid in D.GLYPH_RESIGN else D._depoint(base)
        check(f"{sid} re-signed 2026-09-27: truth == the stated rule applied to the sitting string",
              N(want) == N(want2), f"{want!r} vs {want2!r}")
        check(f"{sid} basis declares the ruling and its date",
              "ruled-20260927" in basis, basis)
        check(f"{sid} truth differs from the raw sitting string (the verdict changed something)",
              N(want) != N(base), f"{want!r} vs {base!r}")
        continue
    if chosen == "correct":
        check(f"{sid} basis says candidate-verbatim", basis.startswith("signed-correct"), basis)
        check(f"{sid} == the candidate's Hebrew",
              N(want) == N(D._heb_span(rec["inputs"]["candidates"][0])))
    elif D.HEB.search(corr):
        check(f"{sid} basis says correction", "correction" in basis, basis)
        if sid in D.RULED_POST_SITTING:
            # Ruled after the sitting closed (p362:n1). The row is still derived, not typed -- section
            # 1c pins it to the agent row and asserts the ruling moved no letter. Here we only assert
            # that it did not silently diverge from what the signer wrote.
            check(f"{sid} ruled post-sitting: consonants match the signed correction",
                  want.replace(" ", "") == corr.replace(" ", ""), f"{want!r} vs {corr!r}")
            check(f"{sid} basis names the ruling", "ruled-" in basis, basis)
        else:
            check(f"{sid} == the signed correction, verbatim", N(want) == N(corr), f"{want!r} vs {corr!r}")
    elif sid in D.SUPPLIED_POST_SITTING:
        # Signed `wrong` with an EMPTY correction, then filled by a post-sitting ruling (p596:n2 since
        # 2026-09-27). This branch exists because such a span looks identical, from the sitting row
        # alone, to the p726:n3 case below and to the UNSCORABLE state it used to be in. What separates
        # it is a SECOND file row, so that is what gets asserted -- not the basis text, which I wrote.
        check(f"{sid} basis names the supplied ruling", "supplied-20260927" in basis, basis)
        check(f"{sid} the sitting row really is empty (a fill, not an overwrite)",
              not D.HEB.search(corr), corr)
        _ar = (agent.get(sid) or {}).get("disputed_span_correction", "")
        check(f"{sid} == the agent row of the same sitting, VERBATIM", N(want) == N(_ar.strip()),
              f"{want!r} vs {_ar!r}")
        # Verbatim, not modulo spaces: nothing rode along from an earlier edit, so unlike p362:n1 there
        # is no licence to differ by word division either.
        check(f"{sid} is not merely space-equal to the agent row", want.strip() == _ar.strip(),
              f"{want!r} vs {_ar!r}")
    else:
        # p726:n3: signed `wrong`, correction text carries no Hebrew, and NO post-sitting ruling. The
        # only span allowed here, and it must declare the interpretation in its basis rather than
        # passing as an ordinary derivation.
        check(f"{sid} declares the marker-defect interpretation in its basis",
              basis == "signed-wrong:marker-defect-not-hebrew-defect", basis)
        check(f"{sid} is the only span taking that path", sid == "p726:n3", sid)

print("\n(3) a signed `wrong` with an empty correction is never GUESSED")
# CHANGED 2026-09-27. p138:n6 and p596:n2 were the two members of the UNSCORABLE tables and Chris
# signed both (sequence item 5), so both tables are now empty. The assertion that must not be lost is
# not "these two spans are unscorable" -- that was a fact about a date. It is the RULE: a span whose
# signer wrote `wrong` and left the correction blank gets a truth string ONLY from a licensed
# post-sitting ruling backed by a second file row. Anything else is a guess wearing a signature.
check("both UNSCORABLE tables are empty", not D.UNSCORABLE and not D.SEALED_UNSCORABLE,
      (D.UNSCORABLE, D.SEALED_UNSCORABLE))
# The correction field holds THREE states and only one of them licenses a fill. Written out because
# the first version of this check tested "carries no Hebrew", which lumps the prose rows in with the
# empty ones -- and the guard in hebrew_aperture_diag had the same defect until this assertion caught
# it. A signer who wrote "not hebrew" HAS given a verdict; a signer who wrote nothing has not.
_wrong = [sid for sid in {**D.TRUTH, **D.SEALED_TRUTH}
          if sitting.get(sid) and sitting[sid].get("chosen") == "wrong"]
_corrof = lambda sid: (sitting[sid].get("disputed_span_correction") or "").strip()
_blank = sorted(sid for sid in _wrong if not _corrof(sid))
_prose = sorted(sid for sid in _wrong if _corrof(sid) and not D.HEB.search(_corrof(sid)))
check("exactly two spans have a GENUINELY EMPTY correction, and they are the supplied pair",
      _blank == ["p138:n6", "p596:n2"], _blank)
check("the blank pair is exactly the SUPPLIED pair",
      _blank == sorted(D.SUPPLIED_POST_SITTING), (_blank, sorted(D.SUPPLIED_POST_SITTING)))
check("three spans carry an English instruction instead of a Hebrew string",
      _prose == ["p253:n2", "p726:n3", "p900:n4"], _prose)
check("no prose-instruction span is licensed as SUPPLIED (that would be an overwrite)",
      not (set(_prose) & set(D.SUPPLIED_POST_SITTING)), sorted(set(_prose) & set(D.SUPPLIED_POST_SITTING)))
for sid in ("p138:n6", "p596:n2"):
    check(f"{sid} carries a SUPPLIED licence", sid in D.SUPPLIED_POST_SITTING)
    check(f"{sid} is registered as ruled post-sitting", sid in D.RULED_POST_SITTING)
    check(f"{sid} has an agent row to derive from",
          bool((agent.get(sid) or {}).get("disputed_span_correction", "").strip()))
    check(f"{sid} really is signed wrong with no Hebrew correction",
          sitting[sid].get("chosen") == "wrong" and not D.HEB.search(
              (sitting[sid].get("disputed_span_correction") or "")))
# p726:n3 is the counter-example that keeps the rule honest: empty correction, NO supplied licence, and
# it gets its truth from the candidate under a declared interpretation instead. If it ever drifts into
# SUPPLIED, the licence has become a way to type anything.
check("p726:n3 is NOT supplied -- it takes the declared-interpretation path",
      "p726:n3" not in D.SUPPLIED_POST_SITTING)

print("\n(4) n is what the reports claim it is")
base = D.build_set()
full = D.build_set(include_sealed=True)
nb = sum(1 for s in base if not s["unscorable"])
nf = sum(1 for s in full if not s["unscorable"])
# COUNTS ARE PINNED BY MEMBERSHIP, NOT BY TOTAL, and that is not pedantry -- it is a bug this suite
# already let through once. On 2026-09-27 two spans entered the scorable set (p138:n6, p596:n2 signed)
# while two left it (p423:n3, p726:n3 blank-crop faulted), so `len(cells()) == 18` stayed TRUE across a
# change of membership in both directions and the assertion reported nothing. A count is a parity
# proxy; the set is the claim.
#
# History of these numbers, so a later reader can tell a ruling from a drift:
#   19 -> 17  2026-09-27  p423:n3 + p726:n3 leave: sent to all 30 arms as pure white images, so no arm
#                         was ever shown them and none can be graded on them (crop-fault gate).
#   17 -> 19  2026-09-27  p138:n6 + p596:n2 arrive: Chris signed both, sequence item 5.
#   19 -> 20  2026-09-27  p423:n3 + p726:n3 come BACK. Lane A's dc573ca persists each column's paste
#                         origin, so the strip->native map no longer re-infers it from the strip's own
#                         ink. Same ratified boxes, same crop sizes, different pixels: the crops had
#                         been cut from the wrong place on the page and landed in white margin. Their
#                         exclusion was our arithmetic, never their geometry.
#   20 -> 19  2026-09-27  p900:n4 leaves. Cause, in one line: its A2 span box maps 2 rows past the
#                         bottom of its own strip (out-of-strip:beyond=bottom2), a geometry fault.
# Both moves are membership, not drift, and both are named -- a count that changes by zero across a
# two-in two-out swap is the failure mode these sets exist to prevent, and it has now happened twice.
_BASE_SCORABLE = {"p102:n0", "p124:n4", "p138:n5", "p138:n6", "p200:n2", "p219:n0", "p253:n2",
                  "p360:n0", "p657:n0", "p895:n0"}
_FULL_SCORABLE = _BASE_SCORABLE | {"p217:n2", "p293:n0", "p362:n1", "p423:n3", "p427:n4", "p491:n1",
                                   "p596:n2", "p726:n3", "p897:n4", "p912:n2"}
check("default scorable set is exactly the unsealed signed spans",
      {s["span_id"] for s in base if not s["unscorable"]} == _BASE_SCORABLE,
      sorted({s["span_id"] for s in base if not s["unscorable"]} ^ _BASE_SCORABLE))
check(f"default set is n={len(_BASE_SCORABLE)} scorable (sealed pages untouched)",
      nb == len(_BASE_SCORABLE), str(nb))
check("carve-out scorable set is exactly the signed corpus minus the one crop-faulted span",
      {s["span_id"] for s in full if not s["unscorable"]} == _FULL_SCORABLE,
      sorted({s["span_id"] for s in full if not s["unscorable"]} ^ _FULL_SCORABLE))
check(f"carve-out set is n={len(_FULL_SCORABLE)} scorable "
      f"({len(D.TRUTH) + len(D.SEALED_TRUTH) - len(_FULL_SCORABLE)} lost to the crop-fault gate)",
      nf == len(_FULL_SCORABLE), str(nf))
check("the one span the crop-fault gate removes is p900:n4, on a geometry fault",
      {sid for sid in {**D.TRUTH, **D.SEALED_TRUTH}} - _FULL_SCORABLE == {"p900:n4"},
      sorted({sid for sid in {**D.TRUTH, **D.SEALED_TRUTH}} - _FULL_SCORABLE))
check(f"the carve-out adds exactly {len(_FULL_SCORABLE) - len(_BASE_SCORABLE)} scorable spans",
      nf - nb == len(_FULL_SCORABLE) - len(_BASE_SCORABLE), str(nf - nb))
check("every added span is on a SEALED page",
      all(s["sealed"] for s in full if s["span_id"] not in {b["span_id"] for b in base}))
_A2 = {s["span_id"] for s in full if not s["unscorable"] and s["span_box"]}
check("A2 sendable set is the carve-out set minus p657:n0, which has no span box",
      _A2 == _FULL_SCORABLE - {"p657:n0"}, sorted(_A2 ^ (_FULL_SCORABLE - {"p657:n0"})))
check(f"A2 is n={len(_FULL_SCORABLE) - 1} (p657:n0 has no span box; p900:n4 is crop-faulted)",
      len(_A2) == len(_FULL_SCORABLE) - 1, str(len(_A2)))
check("the default set still refuses sealed pages",
      all(not s["sealed"] for s in base))

print("\n(5) every sealed span has BOTH human-ratified boxes (no aperture is invented)")
for s in [x for x in full if x["sealed"]]:
    check(f"{s['span_id']} has a ratified note box and span box",
          bool(s["note_box"]) and bool(s["span_box"]))


print("\n(6) the CROP FAULT GATE refuses what was never shown to a model")
# The two spans below were read by 30 arms and every one of those reads is void: the image was one
# uniform white value. This section is the born-test for that never recurring silently.
from PIL import Image                                                        # noqa: E402
from pathlib import Path as _Path                                            # noqa: E402
_HERE = _Path(__file__).parent
_full = {s["span_id"]: s for s in D.build_set(include_sealed=True)}


def _gate_err(src):
    """The fault the gated encoder raises, or None when it encoded. Used so a born-test asserts on
    the REFUSAL rather than on whether an exception type was spelled correctly."""
    try:
        D.b64_gated(src)
        return None
    except D.CropRefused as e:
        return e.fault
# Rewritten 27 Sept. p423:n3 and p726:n3 were held out here for a blank A2 crop; Lane A's mapping fix
# recovered both, so the crop-fault holdout is now a different span for a different reason. Pinned as a
# SET so the membership cannot turn over again without this failing -- which is exactly what it just did.
_CROPFAULT = {sid for sid, s in _full.items() if (s["unscorable"] or "").startswith("crop-fault:")}
check("exactly one span is held out by an A2 crop fault, and it is p900:n4",
      _CROPFAULT == {"p900:n4"}, sorted(_CROPFAULT))
check("p900:n4's cause is geometric: its A2 box maps 2 rows below its strip",
      "out-of-strip" in (_full["p900:n4"]["unscorable"] or ""), _full["p900:n4"]["unscorable"])
for sid in ("p423:n3", "p726:n3"):
    check(f"{sid} is no longer held out: the blank crop was our mapping, not its box",
          not _full[sid]["unscorable"], _full[sid]["unscorable"])
    # The blank crop is still the truth about what was SENT, and that record must survive the fix --
    # otherwise the 35 reads taken off a white rectangle silently become valid evidence again.
    check(f"{sid}'s as-sent crop is still recorded blank in the frozen archive",
          "blank" in (D.sent_faults().get(sid) or ""), D.sent_faults().get(sid))
check("a uniform image is refused",
      D.crop_fault(Image.new("L", (60, 40), 255), [{"box": [0, 0, 60, 40]}], (3584, 5400))
      == "blank:uniform=255")
check("a rect off the page edge is refused, never clamped",
      (D.crop_fault(Image.new("L", (60, 40), 255), [{"box": [3500, 0, 3600, 40]}], (3584, 5400))
       or "").startswith("out-of-bounds"))
check("a real inked crop passes",
      D.crop_fault(Image.open(D.CROPDIR / "p912_n2_A2_spanbox.png"),
                   [{"box": [449, 4645, 649, 4702]}], (3584, 5400)) is None)

print("\n(7) box faults are not misreads, and a loop is not a reading")
# contains: the box held MORE than the signature (p124:n4). clipped: it held LESS (p912:n2).
check("signed inside a fuller transcription is `contains`",
      D.classify("\u05dc\u05db\u05df quasi \u05dc\u05d0 \u05db\u05df",
                 "\u05dc\u05d0 \u05db\u05df") == "contains")
check("a partial read of a two-word signature is `clipped`",
      D.classify("\u05d1\u05d9\u05e9\u05e8\u05d0\u05dc",
                 "\u05d1\u05d9\u05e9\u05e8\u05d0\u05dc \u05d1\u05d9\u05e2\u05e7\u05d1")
      == "clipped")
check("neither is `wrong`",
      "wrong" not in {D.classify("\u05dc\u05db\u05df quasi \u05dc\u05d0 \u05db\u05df",
                                 "\u05dc\u05d0 \u05db\u05df"),
                      D.classify("\u05d1\u05d9\u05e9\u05e8\u05d0\u05dc",
                                 "\u05d1\u05d9\u05e9\u05e8\u05d0\u05dc "
                                 "\u05d1\u05d9\u05e2\u05e7\u05d1")})
# The two real degenerate outputs this class was built from.
check("the p596:n2 repetition loop is `degenerate`",
      D.classify("See Buxtorf. in voce " * 40, "\u05e1\u05e0\u05d4") == "degenerate")
check("the p423:n3 est-loop is `degenerate`",
      D.classify("est." * 80, "\u05d5\u05ea\u05d2\u05e2 \u05dc\u05e8\u05d1\u05dc\u05d9\u05d5")
      == "degenerate")
check("a degenerate Latin loop does NOT score exact against a NOT_HEBREW truth",
      D.classify("est." * 80, D.NOT_HEBREW) == "degenerate")
check("an ordinary short read is never degenerate",
      D.repetition_ratio("\u05dc\u05d0 \u05db\u05df") < D.DEGENERATE_AT)
check("glm-ocr is dropped from scoring", "glm-ocr:bf16" in D.DROPPED_ARMS)

print("\n(9) ITEM 2 -- the guard stands in front of the wire, not beside it")
# The gate existed and the arms did not call it. Each of the four arms had its own base64 step reading
# PNGs straight off disk, so the check in crops() protected the crop BUILD and nothing downstream --
# and a faulted crop is written to disk deliberately, as the evidence of what was sent. So the blank
# PNGs sat there to be picked up by anything that globbed the folder, and they were.
#
# The fix puts the gate at the ENCODE, because an arm cannot reach the wire without encoding. These
# checks are structural: they read the arm sources. A behavioural check that one arm refuses one crop
# would say nothing about the arm that forgot.
import re as _re                                                             # noqa: E402
_ARMS = ("hebrew_frontier_or.py", "hebrew_local_arms.py", "hebrew_aperture_frontier.py",
         "hebrew_recrop.py")
for _a in _ARMS:
    _src = io.open(_HERE / _a, encoding="utf-8").read()
    check(f"{_a} encodes images only through the gate", "b64_gated" in _src, _a)
    # A raw b64encode of image bytes anywhere in an arm is a bypass. base64 of a KEY or a text payload
    # is not, so the check is scoped to the image verbs that were actually there before.
    _bypass = [m for m in _re.findall(r"base64\.b64encode\([^\n]*", _src)
               if any(k in m for k in ("read_bytes", "getvalue", "BytesIO", "img", "crop", "im."))]
    check(f"{_a} has no ungated image encode left", not _bypass, _bypass)

check("the gated encoder refuses a uniform image",
      isinstance(_gate_err(Image.new("L", (80, 40), 255)), str))
check("the gated encoder passes a real crop",
      _gate_err(D.CROPDIR / "p912_n2_A2_spanbox.png") is None)
check("a missing file is refused rather than crashing",
      (_gate_err(D.CROPDIR / "definitely_not_here.png") or "").startswith("missing"))

# Chris 2026-09-27: refuse a crop whose mapped rect leaves the page OR THE STRIP.
check("a box that leaves the strip is refused",
      (D.crop_fault(Image.open(D.CROPDIR / "p912_n2_A2_spanbox.png"), [],
                    (3584, 5400), [10, 10, 100, 340], (1841, 330)) or "").startswith("out-of-strip"))
check("a box inside the strip is not refused for strip reasons",
      not (D.crop_fault(Image.open(D.CROPDIR / "p912_n2_A2_spanbox.png"), [],
                        (3584, 5400), [10, 10, 100, 300], (1841, 330)) or "")
      .startswith("out-of-strip"))
# The strip fault must NOT claim a loss. Measured: the strip box is mapped, not cut, so nothing is
# clamped -- p900:n4 A2 asks 2 rows past a 330-row strip and still gets a full 64-row crop carrying
# 0.2020 ink. An earlier version of this fault string said "lost=428px" and that was false.
_sf = D.crop_fault(Image.open(D.CROPDIR / "p912_n2_A2_spanbox.png"), [], (3584, 5400),
                   [139, 268, 353, 332], (1841, 330))
check("the strip fault reports reach, and claims no pixel loss",
      "beyond=bottom2" in _sf and "lost" not in _sf, _sf)
check("a page clamp DOES report the pixels it costs",
      "lost=19372px/17.1%" in (D.crop_fault(None, [{"box": [1960, 4713, 3918, 4771]}],
                                            (3584, 5400)) or ""),
      D.crop_fault(None, [{"box": [1960, 4713, 3918, 4771]}], (3584, 5400)))
check("clamp_loss is zero for a box that fits", D.clamp_loss([0, 0, 10, 10], (100, 100)) == (0, 0.0))

# A refusal is not a call error: it never reached the wire and it cost nothing. Folding the two
# together would blame the endpoint for our geometry and feed a dead-item rule with live items.
for _a, _tok in (("hebrew_frontier_or.py", "crop_refused"),
                 ("hebrew_local_arms.py", "REFUSED:")):
    _src = io.open(_HERE / _a, encoding="utf-8").read()
    check(f"{_a} records a refusal apart from a call error", _tok in _src, _a)
    check(f"{_a} catches CropRefused before the broad handler",
          _src.index("CropRefused") < _src.rindex("except Exception"), _a)

# The near-uniform threshold sits in the empty band measured across all 740 PNGs: nothing in the
# corpus lies between 0.0 and 0.02555 ink.
check("the near-uniform threshold is below every real crop in the corpus",
      0 < D.NEAR_UNIFORM_INK < 0.02555, D.NEAR_UNIFORM_INK)

print("\n(10) ITEM 2 -- the census counts every folder, and says what it cannot judge")
import crop_census as CC                                                     # noqa: E402
_per, _bad, (_nall, _nempty, _nnoline, _nunread) = CC.report(write=False)
print(f"      {_nall} PNGs in {len(_per)} folders: {_nempty} EMPTY, {_nnoline} no-line, "
      f"{_nunread} unreadable")
check("the census covers the whole tree, not one folder", len(_per) >= 5 and _nall >= 700,
      (len(_per), _nall))
# By FOLDER, not by a global count. A single total cannot say the thing that matters here, and it
# proved it: the count went 4 -> 5 -> 4 across the re-cut while meaning something different each time.
# The live folder must hold NO blank crop -- that is what the mapping fix bought. The archive must hold
# exactly 4 forever -- that is the evidence of what was sent, and it is not allowed to improve.
_EMPTY = [r for r in _bad if r["kind"] == "empty"]
_LIVE_BLANK = [r["name"] for r in _EMPTY if r["folder"].endswith("hebrew_aperture_crops_20260920")]
_SENT_BLANK = sorted(r["name"] for r in _EMPTY if "AS_SENT" in r["folder"])
check("no blank crop survives in the live aperture folder after the re-cut", _LIVE_BLANK == [],
      _LIVE_BLANK)
check("the frozen archive still holds exactly the 4 blank crops that were sent",
      _SENT_BLANK == ["p423_n3_A1_notebox.png", "p423_n3_A2_spanbox.png",
                      "p726_n3_A1_notebox.png", "p726_n3_A2_spanbox.png"], _SENT_BLANK)
check("every blank in the tree is accounted for by those two folders", len(_EMPTY) == len(_SENT_BLANK),
      sorted(r["folder"] + "/" + r["name"] for r in _EMPTY))
check("every blank sits in an aperture crop folder",
      all("hebrew_aperture_crops" in r["folder"] for r in _EMPTY))
check("the no-line case is reported separately and is not counted as blank",
      _nnoline == 1 and all(r["ink"] > D.NEAR_UNIFORM_INK for r in _bad if r["kind"] == "noline"))
check("nothing in the tree is unreadable", _nunread == 0, _nunread)

print("\n(11) ITEM 4 -- the four classes, each pinned to the read that forced it")
# Every string below is the ACTUAL recorded read, and each is checked to exist in the corpus before
# it is classified. A born-test that asserts `classify(literal) == cls` proves the function maps a
# string I typed; it says nothing about whether that string was ever produced. Both halves, or the
# test passes on nothing.
import hebrew_bind as B                                                      # noqa: E402
_ALL = B.reads("A2_spanbox")
def _recorded(span_id, starts, model=None):
    """Every FULL recorded A2 read of this span that begins with `starts`, longest first.

    It returns stored strings rather than comparing to one, and the caller classifies what comes back.
    Two bugs were caught by getting this wrong, in the two opposite directions a locator can fail:

      * embedding a complete literal -- my p596 copy was a 70-character prefix of a much longer
        repetition loop, printed while looking at the data. The check was right; the copy was short.
      * locating by prefix and classifying the FIRST hit -- `openai/gpt-5.6-sol` answered p912:n2 with
        both words in REVERSED order ('bisrael
biyaaqov'), which shares the prefix and is scored
        `wrong`. One loose match silently replaced the case under test.

    So: return the whole matching set and let the caller require that SOME stored read carries the
    class. There is no second copy of the data to get wrong, and no single row can stand in for the
    population.

    B.reads() drops DROPPED_ARMS, so rows are fetched unfiltered here -- the degenerate class exists
    BECAUSE of glm-ocr, and a test for it cannot use a feed that removes it."""
    import json as _json
    _out = []
    for _lane, _fn in B.READ_FILES:
        _p = D.DATA / _fn
        if not _p.exists():
            continue
        for _ln in io.open(_p, encoding="utf-8"):
            _ln = _ln.strip()
            if not _ln:
                continue
            _o = _json.loads(_ln)
            if _o.get("span_id") != span_id or _o.get("aperture") != "A2_spanbox":
                continue
            if model and _o.get("model") != model:
                continue
            _g = _o.get("gated") or ""
            if _g.startswith(starts):
                _out.append(_g)
    return sorted(set(_out), key=len, reverse=True)


# THE THIRD STATE, now with no corpus instance. Chris's batch depointed the last pointed signature,
# so `nikud-only` cannot be demonstrated from a recorded read any more -- measured: zero reads in the
# whole corpus classify that way. The class still has to be guarded, because the carve-out it encodes
# is a ruling: adding points to the standard does not make an unpointed read wrong, and neither does the
# reverse. So it is pinned by a CONSTRUCTED pair, built from the pointed candidate the sitting recorded
# against the bare truth Chris signed, and labelled constructed so nobody reads it as a measurement.
_pointed = D._heb_span(sitting["p726:n3"]["inputs"]["candidates"][0])
check("nikud-only is still reachable: the pointed candidate against the bare signature "
      "(CONSTRUCTED pair -- zero corpus reads classify this way since the batch)",
      D.classify(_pointed, D.SEALED_TRUTH["p726:n3"][0]) == "nikud-only",
      D.classify(_pointed, D.SEALED_TRUTH["p726:n3"][0]))
check("and it is not reachable from any recorded read, which is why the pair above is constructed",
      not [1 for _o in D._lines(D.OUT)
           if _o.get("aperture") == "A2_spanbox" and (_o.get("gated") or "")
           and _o.get("span_id") in _full
           and D.classify(_o["gated"], _full[_o["span_id"]]["truth"]) == "nikud-only"])

_CASES = [
    # span      model                read as recorded                       class        why
    ("p124:n4", None, "\u05dc\u05d0 \u05db\u05df \u05d9\u05d4\u05d9\u05d4 \u05dc\u05da", "contains",
     "the box held MORE than the signature, so obeying the prompt returns the neighbours too"),
    ("p912:n2", None, "\u05d1\u05d9\u05e9\u05e8\u05d0\u05dc", "clipped",
     "the box held LESS than the signature, so only one of two words could be returned"),
    ("p596:n2", "glm-ocr:bf16",
     "* See Buxtorf. in voce \u05e0\u05d5\u05e1.\n* See Buxtorf. in voce \u05e0\u05d5\u05e1.\n* See Buxtorf.",
     "degenerate", "a repetition loop is not a reading and cannot be graded as one"),
    ("p726:n3", "qwen3.5:122b", "\u05e9\u05d0\u05e8 \u05d0\u05d1\u05d9\u05da", "exact",
     "the same read that was nikud-only against the pointed signature is EXACT against the bare one, "
     "which is what Chris's verdict of 2026-09-27 means: the arm was reading the page correctly and "
     "the standard was wrong"),
]
for _sid, _model, _read, _want, _why in _CASES:
    _got = _recorded(_sid, _read, _model)
    check(f"{_sid} -- the {_want} read is really in the corpus", bool(_got),
          (_sid, _model, _read[:30]))
    if not _got:
        continue
    _truth = _full[_sid]["truth"]
    _cls = [D.classify(_g, _truth) for _g in _got]
    check(f"{_sid} -- classify calls it {_want}: {_why}", _want in _cls,
          (_sid, sorted(set(_cls)), _want, _truth))

# Nikud stripped on BOTH sides, which is the half that is easy to get half-right. The p726 case only
# exercises pointed-truth vs unpointed-read; the mirror must behave the same or the class is
# direction-dependent, and a signature that happens to be unpointed would then score a pointed read
# as wrong.
_UNP, _PTD = "\u05e9\u05d0\u05e8 \u05d0\u05d1\u05d9\u05da", "\u05e9\u05b0\u05bc\u05d0\u05b8\u05e8 \u05d0\u05b8\u05d1\u05b4\u05d9\u05da\u05b0"
check("nikud is stripped on the READ side", D.classify(_UNP, _PTD) == "nikud-only")
check("nikud is stripped on the TRUTH side too", D.classify(_PTD, _UNP) == "nikud-only")
check("nikud-only is its own class, not folded into exact",
      D.classify(_PTD, _PTD) == "exact" and D.classify(_UNP, _PTD) != "exact")

# contains and clipped are opposite directions and must not collapse into one another, because they
# indict opposite box faults: too wide versus too narrow.
check("contains and clipped are not the same class",
      D.classify("\u05d0\u05d1 \u05d2\u05d3", "\u05d0\u05d1") == "contains"
      and D.classify("\u05d0\u05d1", "\u05d0\u05d1 \u05d2\u05d3") == "clipped")
# Neither is a misread, so neither may be scored as one.
check("neither direction is scored as wrong",
      "wrong" not in (D.classify("\u05d0\u05d1 \u05d2\u05d3", "\u05d0\u05d1"),
                      D.classify("\u05d0\u05d1", "\u05d0\u05d1 \u05d2\u05d3")))
# degenerate is tested before the not-Hebrew branch on purpose: p900:n4's glm-ocr loop is LATIN, and
# a truth of NOT_HEBREW would otherwise score that loop `exact`.
check("a Latin repetition loop against a NOT-HEBREW truth is degenerate, not exact",
      D.classify("est. est. est. est. est. est. est. est. est. est. est. est. est.",
                 D.NOT_HEBREW) == "degenerate")

print("\n(12) ITEM 3 -- the binding test refuses to confirm what it cannot see")
# The whole point of item 3's design: reads arrive with a context strip, so a recovered signature is
# evidence about the strip and is NOT counted. Asserted here as well as in hebrew_bind's own
# selftest, because this is the claim the sealed-truth suite must not lose.
_brows, _bcounts, _bbroken = B.bind_report()
print(f"      binding verdicts: {_bcounts}")
check("no span is ever called bound", "bound" not in _bcounts, _bcounts)
check("p912:n2 is detected broken by the sound signal only",
      next(r for r in _brows if r["span_id"] == "p912:n2")["verdict"] == "broken:box-too-small")
check("the two faulted crops supply no binding evidence",
      all(next(r for r in _brows if r["span_id"] == s)["verdict"] == "no-evidence"
          for s in ("p423:n3", "p726:n3")))
# WAS (3, 18). The number moved because the STANDARD was wrong, not the boxes: the old check counted
# ink runs at 12% of peak, and pointed Hebrew is made of thin runs -- a nikud row below the baseline, an
# ascender, a neighbour's descender inside the 12px pad. It reported 15 of 18 sound boxes as multi-line,
# and those 15 were the queue held for Lane A's presplit fix. Corrected against two thresholds each
# taken from an empty band in the measurements (MIN_BAND_PX 20: runs are 1-14px or 30-38px, nothing
# between; MAX_BAND_PX 50: every band is 30-38px except p362:n1 at 67), the debt was one box -- and that
# one was ruled a pass on 2026-09-27, on the page rather than on the measurement. See decision 4 below.
# Derived from the measured set, never typed: `(one, tot) == (17, 18)` stayed true across a two-span
# membership change in BOTH directions once already, which is the third time a count passed while the
# set moved underneath it. The population is 20 since Lane A's dc573ca recovered p423:n3 and p726:n3.
_MEAS = {r["span_id"] for r in B.G.box_quality(True) if r["lines"] is not None}
check(f"the one-band debt is {len(_MEAS) - B.G.one_band_report()[0]} of {len(_MEAS)} -- reported",
      B.G.one_band_report()[1] == len(_MEAS), B.G.one_band_report()[:2])
check("the measurable population is the 20 spans with a ratified box, p657:n0 alone excluded",
      len(_MEAS) == 20 and "p657:n0" not in _MEAS, sorted(_MEAS))

# ---- Chris's decision 4 of 2026-09-27: the debt went to zero and NOT ONE PIXEL MOVED ----------------
# "p362:n1: box stands; the band test needs a pass condition for 'merged at row 0, span intact below.'
# No rerun." A violator count that falls to zero because the standard gained a clause is indistinguishable
# -- from the count alone -- from one that falls to zero because the boxes were fixed. This block is where
# that difference is on the record. First: the box did not change, so the change is in the rule and can be
# nowhere else.
check("p362:n1's box is untouched by the ruling -- it is the STANDARD that moved",
      _full["p362:n1"]["span_box"] == [471, 125, 799, 192]
      and _full["p362:n1"]["sealed"] is True, _full["p362:n1"]["span_box"])
_p362im = B.G.cut(362, _full["p362:n1"]["span_box"], D.PAD,
                  _full["p362:n1"]["column_bands"])[0]
_v362, _i362 = B.G.band_geometry(_p362im)
check("and it passes as merged-top-edge, not as one-band -- the crop is still unusual and says so",
      _v362 == "merged-top-edge" and B.G._one_band(_p362im), (_v362, _i362))
# WHY, in measured terms rather than by appeal to the ruling: the 67px band is two things. Chris read the
# page and said descenders from the line above; the pixels agree, and the fragment is 12px, which is in
# the thin population MIN_BAND_PX exists to reject. It is not a line of type.
check("the 67px band is a 33px corpus-normal band plus a 12px fragment of the line above",
      (_i362["band_px"], _i362["clear_top"]) == (67, 0)
      and _i362["split_px"] == 33 and _i362["split_band"] == [32, 64]
      and _i362["top_fragment_px"] == 12
      and _i362["top_fragment_px"] < B.G.MIN_BAND_PX <= _i362["split_px"] <= B.G.MAX_BAND_PX,
      {k: _i362.get(k) for k in ("band_px", "split_px", "split_band", "top_fragment_px")})

# THE BRANCH MUST BE UNREACHABLE FOR THE FAILURE IT RESEMBLES. A box that CONTAINS two lines and a box
# that CLIPS one both produce a single over-thick band; the pass condition is allowed to exist only
# because it separates them. Exercised on real pixels in the failing direction -- the same ratified box
# grown upward, so the line above moves from clipped to enclosed -- and not on a synthetic profile, which
# would only be testing my idea of the page.
_grown = {}
for _g in (20, 35, 50, 70):
    _b = list(_full["p362:n1"]["span_box"])
    _b[1] -= _g
    _grown[_g] = B.G.band_geometry(B.G.cut(362, _b, D.PAD, _full["p362:n1"]["column_bands"])[0])[0]
check("growing that box upward is REFUSED at every step: clipping a line is a pass, holding one is not",
      all(v in ("merged", "multi-band") for v in _grown.values()), _grown)

# SPLIT_FRAC IS NOT LOAD-BEARING. The verdict is invariant across every threshold from 0.16 to 0.39 --
# below that the two lines fuse, at 0.40 the span's own line starts breaking up -- and 0.28 is the middle
# of that plateau. Asserted over the whole interval, because a number chosen from the centre of a plateau
# is only defensible for as long as the plateau is still there.
# Measured on `text_bands`, which is the surface the probe consumes -- NOT on band_geometry(im, f).
# `frac` is the primary profile's threshold, so passing 0.20 to band_geometry makes the crop one-band
# outright and the probe is never reached: the first version of this check came back "one-band" for all
# 24 values and would have been satisfied by a build containing no probe at all.
_plateau = {f: B.G.text_bands(_p362im, f / 100.0) for f in range(16, 40)}
check("across the whole 0.16-0.39 plateau the split yields ONE corpus-height band clear of row 0",
      all(len(v) == 1 and v[0][0] > 0
          and B.G.MIN_BAND_PX <= v[0][1] - v[0][0] + 1 <= B.G.MAX_BAND_PX
          for v in _plateau.values())
      and 16 <= B.G.SPLIT_FRAC * 100 <= 39,
      {f: v for f, v in _plateau.items() if not (len(v) == 1 and v[0][0] > 0)})
check("and it is a real threshold effect: at BAND_FRAC the two lines fuse into one 67px band at row 0",
      B.G.text_bands(_p362im, B.G.BAND_FRAC) == [(0, 66)]
      and B.G.text_bands(_p362im, 0.40) == [],
      (B.G.text_bands(_p362im, B.G.BAND_FRAC), B.G.text_bands(_p362im, 0.40)))

# THE OTHER HALF OF THE EXERCISE: the new rule run over everything that already passed. The probe lives
# inside the `px > MAX_BAND_PX` branch, so by construction no passing crop can reach it -- and the way
# that claim earns its keep is by being measured rather than deduced from the control flow.
_verdicts = {s["span_id"]: B.G.band_geometry(
                 B.G.cut(s["page"], s["span_box"], D.PAD, s["column_bands"])[0])[0]
             for s in D.build_set(include_sealed=True) if s.get("span_box")}
check("exactly ONE span is merged-top-edge and the other 19 are one-band: nothing else moved",
      sorted(_verdicts.values()).count("one-band") == 19
      and [k for k, v in _verdicts.items() if v == "merged-top-edge"] == ["p362:n1"]
      and len(_verdicts) == 20,
      {k: v for k, v in _verdicts.items() if v != "one-band"})
check("so the debt is 0 of 20 with no violators, by a ruling on the rule and no change to any box",
      B.G.one_band_report(include_sealed=True) == (20, 20, []),
      B.G.one_band_report(include_sealed=True))
# A tally against a wrong standard is faithful and worthless. The corrected rule was kept honest by the
# one thing that could refuse it: an already-ratified box. Chris's 2026-09-27 re-ratified p423:n3 crop
# was 35px tall around a 35px band, touching both edges -- an edge-clearance clause in the accept gate
# would have thrown it out, which is why that clause was not added.
#
# THAT BOX IS NOW RETIRED (ruling 2026-09-28): it was drawn one note too low, on `T. Hicros. Nedarim`,
# a row with no Hebrew in it. The edge-clearance clause would indeed have rejected it -- for being
# tight, when what was wrong with it was the row. A rule that gets the right answer from a property
# unrelated to the fault has not been vindicated, so the clause stays out and this stays a caution.
# The counterexample, though, is gone: no ratified box in the corpus touches both edges any more, and
# the claim is unexercised rather than disproved. Asserted as the vacuity it is, below.
_rerat = B.G.rerat_load()[0]["p423:n3"]["_crop"]
check("the corrected band rule accepts the ratified p423:n3 box",
      B.G.band_geometry(_rerat)[0] == "one-band", B.G.band_geometry(_rerat))
_rg = B.G.band_geometry(_rerat)[1]
check("the superseding box is the live mapping of the ORIGINAL ratified strip box, not a redraw",
      B.G.rerat_load()[0]["p423:n3"]["new_box"] == [1674, 4655, 1960, 4715],
      B.G.rerat_load()[0]["p423:n3"]["new_box"])
check("and it clears both edges, so the edge-touching counterexample has NO instance left",
      _rg["clear_top"] > 0 and _rg["clear_bottom"] > 0, _rg)
check("no ratified span box touches both edges now -- the claim is unexercised, not refuted",
      [s["span_id"] for s in D.build_set(include_sealed=True) if s.get("span_box")
       and (lambda g: g["clear_top"] == 0 and g["clear_bottom"] == 0)(
           B.G.band_geometry(B.G.cut(s["page"], s["span_box"], D.PAD, s["column_bands"])[0])[1])] == [],
      "a box that touches both edges would appear here")
check("the retired box is named in the store with what was wrong with it, not merely replaced",
      B.G.rerat_load()[0]["p423:n3"]["old_box_state"] == "wrong-row-no-hebrew",
      B.G.rerat_load()[0]["p423:n3"].get("old_box_state"))
# The contains bucket, split by output shape. Under the PRE-BATCH truth table it was 22 reads, 9 of
# them not a box fault in any sense and 2 of those broken parses that a substring test CREDITS -- a free
# pass for the failure the typed contract exists to catch. Chris's batch moved the strings the substring
# test runs against, so the population moved with them; the 22 stays in this sentence because it is what
# was measured, and the assertion below derives today's figure instead of restating it.
#
# Pinned so item 7's re-tally knows what it is absorbing; classify is untouched.
_cc = B.contains_counts()
_cp = B.contains_population()
# Derived two ways that can disagree: the shapes must total the contains reads counted independently
# off the same corpus, and no read may be filed under two different shapes. The first catches a read
# that fell through every branch; the second catches a branch that is not exclusive. A set-equality on
# the (span, read) pairs would NOT work here and was tried: the population legitimately repeats a pair
# when two arms return the same string, so uniqueness is not the invariant -- exclusivity is.
import hebrew_frontier_or as _F                                              # noqa: E402
_MUTE_KEYS = set(_F.stale_reads())
_full_b = {x["span_id"]: x for x in D.build_set(include_sealed=True)}
_n_contains = sum(1 for _r in B.reads("A2_spanbox")
                  if (_full_b.get(_r["span_id"]) or {}).get("truth")
                  and D.classify(_r.get("gated") or "",
                                 _full_b[_r["span_id"]]["truth"]) == "contains")
_kinds_of = {}
for _k, _v in _cp.items():
    for _r in _v:
        _kinds_of.setdefault(_r, set()).add(_k)
check("the shapes total the contains reads counted independently -- none fell through every branch",
      sum(_cc.values()) == _n_contains, "%d by shape vs %d by classify" % (sum(_cc.values()), _n_contains))
check("and no read is filed under two shapes -- the branches are exclusive, not merely exhaustive",
      not [r for r, ks in _kinds_of.items() if len(ks) > 1],
      [(r[0], sorted(ks)) for r, ks in _kinds_of.items() if len(ks) > 1])
check("the contains population moved with the batch, and the move is reported rather than pinned",
      sum(_cc.values()) != 22,
      "%d today against 22 under the pre-batch table -- item 7 step 5 owns the re-tally"
      % sum(_cc.values()))
# REPORTED, NOT PINNED. 9-of-22 was the pre-batch table; the 104-call send of 2026-09-27 moved the
# population and the check above already says the move is the re-tally's to own. The claim that holds
# independent of the count is that extra-material is not the whole of it -- a box fault does not
# explain every contains read, which is the finding the number was serving.
check("extra-material does not explain every contains read (count reported; item 7 step 5 re-tallies)",
      0 < sum(v for k, v in _cc.items() if k != "extra-material") < sum(_cc.values()),
      "%d of %d not a box fault, was 9 of 22 pre-batch: %s"
      % (sum(v for k, v in _cc.items() if k != "extra-material"), sum(_cc.values()), _cc))
# `hebrew_bind.reads()` returns every read in every lane artifact and does NOT apply the crop-hash void
# rule, so a read taken on a re-cut crop could enter this tally -- a model's opinion of a rectangle that
# no longer exists, counted as evidence. Measured, not assumed: today the overlap is empty. Stated as a
# vacuity so that the day it is not, this says so rather than the tally absorbing it silently.
_retired = [_r for _r in B.reads("A2_spanbox")
            if _F.read_key(_r) in _MUTE_KEYS
            and (_full_b.get(_r["span_id"]) or {}).get("truth")
            and D.classify(_r.get("gated") or "", _full_b[_r["span_id"]]["truth"]) == "contains"]
check("no contains read sits on a crop that was re-cut after it (EMPTY today, and bind does not filter)",
      not _retired, [(r["span_id"], r["model"]) for r in _retired])
check("two contains reads are broken parses credited by the substring test",
      _cc.get("envelope-leak") == 2, _cc)

print("\n(N) Chris's p217 ruling of 2026-09-27, and the door it came through")
# THE RULING. "p217:n2: ratified box x0 = 0, no other change, no rerun." The ratified note box began at
# x = -2, outside the page. The CROP was never wrong -- this lane clamps max(0, x0 - pad) and Lane A's
# mapper adds a canvas-slop clamp -- and Chris's point was that two clamps agreeing is not a
# ratification. So the box is corrected, no pixel moves, and nothing is re-sent.
_NB = D.DATA / "note_box_truth_20260906_FINAL.jsonl"
_nbrecs = [o for o in D._lines(_NB) if "page" in o]
_p217 = [o for o in _nbrecs if o["page"] == 217]
check("page 217 has an ORIGINAL and a SUPERSEDING record, both readable",
      len(_p217) == 2, len(_p217))
check("the loader resolves p217 to the later record (last-wins, which is what makes the door work)",
      {s["span_id"]: s for s in D.build_set(include_sealed=True)}["p217:n2"]["note_box"]
      == [0, 109, 1955, 213])
if len(_p217) == 2:
    _o, _n = _p217
    # DERIVED, NOT RETYPED. The superseding record was built from the original in memory with one
    # coordinate replaced. If the other five notes had been retyped, my transcription would have become
    # an assertion about Chris's ratification; this check is what keeps it a copy.
    _diff = [(i, j) for i in range(min(len(_o["notes"]), len(_n["notes"])))
             for j in range(4)
             if _o["notes"][i]["strip_box"][j] != _n["notes"][i]["strip_box"][j]]
    check("exactly ONE coordinate differs, and it is note 2's x0: -2 -> 0",
          _diff == [(2, 0)] and _o["notes"][2]["strip_box"][0] == -2
          and _n["notes"][2]["strip_box"][0] == 0, _diff)
    check("every other field of every note is unchanged -- 'no other change' means x1 stays 1955 too",
          [{k: v for k, v in nn.items() if k != "strip_box"} for nn in _o["notes"]]
          == [{k: v for k, v in nn.items() if k != "strip_box"} for nn in _n["notes"]]
          and _n["notes"][2]["strip_box"][2] == 1955)
    check("the page's own geometry is untouched: strip size, bands, counts",
          all(_o[k] == _n[k] for k in ("strip_size", "column_bands", "mode", "n_extractor",
                                       "n_detected", "n_ratified")))
    check("the record names the ruling, the change, and that no pixel moved",
          _n["provenance"]["supersedes"]["changed"] == [{"note": 2, "field": "strip_box[0]",
                                                         "from": -2, "to": 0}]
          and _n["provenance"]["pixels_changed"] is False
          and "2026-09-27" in _n["provenance"]["ruling"])
check("and the A1 fault table is now EMPTY -- the -2 was its last entry",
      D.crop_faults("A1_notebox") == {}, D.crop_faults("A1_notebox"))
check("while p900:n4 remains the one A2 fault, so the gate did not go quiet for the wrong reason",
      set(D.crop_faults("A2_spanbox")) == {"p900:n4"}, D.crop_faults("A2_spanbox"))

print("\n(N+1) the append-only door cannot glue a record onto a signed line")
# This store ended WITHOUT a trailing newline, and a plain "a"-mode write put the p217 correction onto
# the end of the last ratified page record. The whole store then failed to parse, because the loader
# raises on the first bad line. Loud, repairable, and it must not be reachable again.
check("the store ends with a newline, so the next append lands on its own line",
      _NB.read_bytes().endswith(b"\n"))
_tmp = D.CROPDIR / "_append_probe.jsonl"
try:
    io.open(_tmp, "w", encoding="utf-8", newline="").write('{"a": 1}')      # no terminator, on purpose
    D.append_jsonl(_tmp, {"a": 2})
    check("append_jsonl on a store with no trailing newline yields TWO records, not one glued line",
          [o["a"] for o in D._lines(_tmp)] == [1, 2], D._lines(_tmp))
    io.open(_tmp, "w", encoding="utf-8", newline="").write('{"a": 1}\r\n')
    D.append_jsonl(_tmp, {"a": 2})
    check("and it keeps the store's own CRLF rather than normalising 34 signed lines to append a 35th",
          _tmp.read_bytes().count(b"\r\n") == 2 and [o["a"] for o in D._lines(_tmp)] == [1, 2],
          _tmp.read_bytes()[:40])
finally:
    if _tmp.exists():
        _tmp.unlink()

print()
if fails:
    print(f"FAIL: {len(fails)} assertion(s)")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"PASS: {len(D.SEALED_TRUTH)} sealed truths trace to the signature; n={nf} scorable, "
      f"A2 n={len(_A2)} "
      f"({', '.join(sorted(_CROPFAULT)) or 'none'} held out by the crop-fault gate, "
      f"p657:n0 by having no span box).")
sys.exit(0)
