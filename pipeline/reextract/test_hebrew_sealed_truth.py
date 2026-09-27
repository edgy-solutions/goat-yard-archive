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
import hebrew_aperture_diag as D

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

print("\n(2) every sealed truth traces to the signature by the stated rule")
D._assert_derivation(sitting, agent)   # raises on any mismatch
check("_assert_derivation passes over all 9 sealed truths", True)
for sid, (want, basis) in sorted(D.SEALED_TRUTH.items()):
    rec = sitting.get(sid)
    check(f"{sid} is in the signed sitting", rec is not None)
    if not rec:
        continue
    corr = (rec.get("disputed_span_correction") or "").strip()
    chosen = rec.get("chosen")
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
    else:
        # p726:n3: signed `wrong`, correction text carries no Hebrew. The ONLY span allowed here, and it
        # must declare the interpretation in its basis rather than passing as an ordinary derivation.
        check(f"{sid} declares the marker-defect interpretation in its basis",
              basis == "signed-wrong:marker-defect-not-hebrew-defect", basis)
        check(f"{sid} is the only span taking that path", sid == "p726:n3", sid)

print("\n(3) a signed `wrong` with an empty correction is UNSCORABLE, never guessed")
for sid in ("p138:n6", "p596:n2"):
    rec = sitting.get(sid)
    unsc = {**D.UNSCORABLE, **D.SEALED_UNSCORABLE}
    check(f"{sid} is UNSCORABLE", sid in unsc)
    check(f"{sid} has no truth string", sid not in D.TRUTH and sid not in D.SEALED_TRUTH)
    if rec:
        check(f"{sid} really is signed wrong with no Hebrew correction",
              rec.get("chosen") == "wrong" and not D.HEB.search(
                  (rec.get("disputed_span_correction") or "")))

print("\n(4) n is what the reports claim it is")
base = D.build_set()
full = D.build_set(include_sealed=True)
nb = sum(1 for s in base if not s["unscorable"])
nf = sum(1 for s in full if not s["unscorable"])
check("default set is n=10 scorable (sealed pages untouched)", nb == 10, str(nb))
# 19 -> 17 and 18 -> 16 on 2026-09-27, and the two that left are not a retune: p423:n3 and p726:n3
# were sent to all 30 arms as pure white images, so no arm was ever shown them and no arm can be
# graded on them. The numbers below move only when the CROP FAULT GATE says they may.
check("carve-out set is n=17 scorable (2 lost to the crop-fault gate)", nf == 17, str(nf))
check("the carve-out adds exactly 7 scorable spans", nf - nb == 7, str(nf - nb))
check("every added span is on a SEALED page",
      all(s["sealed"] for s in full if s["span_id"] not in {b["span_id"] for b in base}))
check("A2 is n=16 (p657:n0 has no span box; 2 blank crops are unscorable)",
      sum(1 for s in full if not s["unscorable"] and s["span_box"]) == 16,
      str(sum(1 for s in full if not s["unscorable"] and s["span_box"])))
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
for sid in ("p423:n3", "p726:n3"):
    u = _full[sid]["unscorable"] or ""
    check(f"{sid} is UNSCORABLE by crop fault, not by signature", u.startswith("crop-fault:"), u)
    check(f"{sid} names the fault as blank", "blank" in u, u)
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
check("the blank-crop count across all artifact folders is 4", _nempty == 4,
      sorted(r["name"] for r in _bad if r["kind"] == "empty"))
check("every blank sits in the aperture crop folder",
      all("hebrew_aperture_crops" in r["folder"] for r in _bad if r["kind"] == "empty"))
check("the no-line case is reported separately and is not counted as blank",
      _nnoline == 1 and all(r["ink"] > D.NEAR_UNIFORM_INK for r in _bad if r["kind"] == "noline"))
check("nothing in the tree is unreadable", _nunread == 0, _nunread)

print()
if fails:
    print(f"FAIL: {len(fails)} assertion(s)")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"PASS: {len(D.SEALED_TRUTH)} sealed truths trace to the signature; n=17 scorable, A2 n=16 "
      f"(p423:n3 and p726:n3 held out by the crop-fault gate).")
sys.exit(0)
