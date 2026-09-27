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
check("carve-out set is n=19 scorable", nf == 19, str(nf))
check("the carve-out adds exactly 9 scorable spans", nf - nb == 9, str(nf - nb))
check("every added span is on a SEALED page",
      all(s["sealed"] for s in full if s["span_id"] not in {b["span_id"] for b in base}))
check("A2 is n=18 (p657:n0 has no ratified span box)",
      sum(1 for s in full if not s["unscorable"] and s["span_box"]) == 18,
      str(sum(1 for s in full if not s["unscorable"] and s["span_box"])))
check("the default set still refuses sealed pages",
      all(not s["sealed"] for s in base))

print("\n(5) every sealed span has BOTH human-ratified boxes (no aperture is invented)")
for s in [x for x in full if x["sealed"]]:
    check(f"{s['span_id']} has a ratified note box and span box",
          bool(s["note_box"]) and bool(s["span_box"]))

print()
if fails:
    print(f"FAIL: {len(fails)} assertion(s)")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"PASS: {len(D.SEALED_TRUTH)} sealed truths trace to the signature; n=19 scorable, A2 n=18.")
sys.exit(0)
