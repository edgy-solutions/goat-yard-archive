# -*- coding: utf-8 -*-
u"""Born tests for signature_reversal (ruling A(2) 2026-10-25).

pytest is not installed in this venv: run it directly.

    PYTHONIOENCODING=utf-8 ../../../goat-yard-archive/.venv/Scripts/python.exe \
        test_signature_reversal.py

The load-bearing test is the one on p442:n0.  That span is the ONLY instance a human has
adjudicated, and a detector that cannot see its own founding case is a probe that passes on nothing.
It is asserted from the committed run record, not from a string typed in here.

The second load-bearing test is the opposite failure: `read == signature` must NOT be flagged.  For a
3-consonant signature a correct read sits at Hamming distance 2 from the reverse by construction, and
31 of the 34 reads at that distance in this population are correct reads.  A detector that scored a
distance band would have reported a reversal epidemic.

The assertion COUNT is asserted: in a hand-rolled suite an exception ends the run silently, and this
lane has lost 40 assertions that way twice.

All page numbers are FILE pages (printed = file - 88).
"""
import io
import json
import os
import sys

import confusable_vocab as V
import hebrew_aperture_diag as diag
import signature_reversal as R

N = 0
FAILED = []


def chk(cond, msg):
    global N
    N += 1
    if not cond:
        FAILED.append(msg)


D, K, B, R_, Y, L, FK, FN, V_, T, SH, TS = (u"ד", u"ך", u"ב", u"ר", u"י",
                                            u"ל", u"ך", u"ן", u"ו", u"ת",
                                            u"ש", u"צ")

# --------------------------------------------------------------- normalisation: what gets dropped
chk(R.consonants(u"טֹבֹת") == [u"ט", B, T],
    "nikud is stripped, consonants kept in stored order")
chk(R.consonants(u"ברא - לעשות")
    == [B, R_, u"א", L, u"ע", SH, V_, T],
    "a separator (the hyphen in the p102:n0 signature) is dropped: it has no glyph order")
chk(R.consonants(u"[ל][א][ ][ה]חסיר")
    == [L, u"א", u"ה", u"ח", u"ס", Y, R_],
    "bracket notation of an out-of-crop signature contributes its letters, not its brackets")
chk(R.consonants(u"") == [] and R.consonants(None) == [], "empty and None are empty, not an error")
chk(R.words(u"ברא - לעשות") == [[B, R_, u"א"],
                                                                        [L, u"ע", SH, V_, T]],
    "words() splits on the separator")
chk(R.reverse_per_word(u"ברא לע")
    != R.reverse_all(R.consonants(u"ברא לע")),
    "for a multi-word signature the two reversal bases DIFFER, so they are reported separately")
chk(R.reverse_per_word(u"רבך") == R.reverse_all(R.consonants(u"רבך")),
    "for a single-word signature the two bases coincide")

# -------------------------------------------------------- THE founding case: p442:n0, from the record
# signed רבך; pixels and both bare reads דבר; ruling A(1): signed in visual left-to-right order,
# dalet taken as final kaf.
SIG442, READ442 = u"רבך", u"דבר"
rec = R.examine(SIG442, READ442)
chk(rec["flag"] == "reversed_one_swap",
    "p442:n0 is flagged reversed_one_swap -- the ONE adjudicated instance.  got %r" % rec["flag"])
chk(rec["dist_to_reverse"] == 1 and rec["dist_to_signature"] == 2,
    "the reverse is STRICTLY the better explanation (1 vs 2), which is why it is not ambiguous: %s"
    % ((rec["dist_to_reverse"], rec["dist_to_signature"]),))
chk(rec["swap"]["pair"] == u"dalet/final-kaf", "the swap is named dalet/final-kaf")
chk(rec["swap"]["reading_position"] == 1,
    "the swapped glyph is the FIRST glyph read (Hebrew is stored in logical order): got %s"
    % rec["swap"]["reading_position"])
chk(rec["swap"]["position_in_signature"] == 2,
    "and it sits at stored index 2 of the signed string -- the tile number a glyph card must carry: "
    "got %s" % rec["swap"]["position_in_signature"])
chk(rec["registers"] == ["ADJUDICATED_IN_AUDIT"],
    "the hit reports WHICH register licensed it, so a weaker grounding cannot pass unnoticed: %s"
    % rec["registers"])
chk(V.registers(D, FK) != [],
    "the rule as literally written ('one swap from the confusable list') needs dalet/final-kaf IN "
    "the list; without ruling A(1)'s entry this detector fires on nothing at all")

# ------------------------------------------------------- trap 1: a correct read is not a suspect
for s in (u"טבת", u"כהן", u"שרצ", u"מצא"):
    r = R.examine(s, s)
    chk(r["flag"] == "read_equals_signature",
        u"read == signature is excluded by cause, never scored as a reversal (%s): got %r"
        % (s, r["flag"]))
    chk(r["dist_to_reverse"] == 2,
        u"and it really does sit at distance 2 from the reverse (%s) -- which is the whole trap" % s)

# ------------------------------------------------------- trap 2: the reverse must be strictly better
amb = R.examine(u"בן", u"בו")      # p628:n2: d(fwd)=1, d(rev)=2
chk(amb["flag"] == "ambiguous_basis",
    "a read no closer to the reverse than to the signature is NOT a reversal suspect; p628:n2 "
    "(signed בן, read בו) is a one-glyph misread and is excluded: got %r" % amb["flag"])
chk(amb["dist_to_signature"] == 1 and amb["dist_to_reverse"] == 2,
    "both distances are recorded, so the exclusion can be audited instead of trusted")

# ----------------------------------------------------------------------- palindrome: vacuous test
pal = R.examine(u"בב", u"בר")
chk(pal["flag"] == "palindrome_signature",
    "when reverse(signature) == signature the test cannot discriminate and says so: got %r"
    % pal["flag"])
chk(R.examine(u"ב", u"ר")["flag"] == "palindrome_signature",
    "a one-glyph signature is its own reverse: the test is vacuous, not passing")

# ------------------------------------------------------------------------- exact and length cases
chk(R.examine(u"רבך", u"ךבר")["flag"] == "reversed_exact",
    "read == reverse(signature) exactly is the first limb of the ruling")
chk(R.examine(u"רבך", u"ךב")["flag"] == "length_mismatch",
    "a shorter read admits no positional comparison and is excluded by name, not by silence")
chk(R.examine(u"רבך", u"")["flag"] == "empty_read", "an empty read is named")

# -------------------------------------------------------- an unlisted pair is NOT a ruling-A(2) hit
unl = R.examine(u"לי", u"יך")      # p910:n3: reverse יל, read יך, swap ל/ך
chk(unl["flag"] == "reversed_one_swap_unlisted",
    "p910:n3 has the reversal SHAPE with a pair the vocabulary does not carry (lamed/final-kaf), so "
    "it is reported separately and is not counted as a hit: got %r" % unl["flag"])
chk(unl["registers"] == [],
    "an unlisted hit carries NO register, which is the fact that keeps it out of the count")
chk(V.registers(L, FK) == [], "lamed/final-kaf really is absent from every register")

# ------------------------------------------------------------- no path from this module to an edit
chk(not hasattr(R, "fix_signature") and not hasattr(R, "resign"),
    "there is no function here that rewrites a signature: a hit opens a glyph card, it never edits")
chk(set(R.VERDICTS) & set(R.EXCLUSIONS) == set(),
    "a verdict name and an exclusion name can never collide, so a count cannot double-book")

# ------------------------------------------------------------------- the scan itself, over the record
hits, unlisted, counts, meta = R.scan()
chk(meta["n_compared"] > 0,
    "the scan compared something: a scan that tests nothing passes on nothing (n_compared=%s)"
    % meta["n_compared"])
# The ruling names the population "45 + 19" = 64.  Measured, it is 65, and the arithmetic is
# asserted here rather than coerced, because a population is a claim too: the 45 of the scored run,
# plus the 21 signed in code (TRUTH + SEALED_TRUTH), of which p657:n0 is also one of the 45.
# The ruling's 19 are the subset of those 21 that the 19-span run scored; p900:n4 is signed and was
# never in that run, and p657:n0 was signed the same day.  All 21 are scanned: including them costs
# nothing and excluding a signed span from a scan of signatures would need a reason.
RULING19 = set(["p102:n0", "p124:n4", "p138:n5", "p138:n6", "p200:n2", "p217:n2", "p219:n0",
                "p253:n2", "p293:n0", "p360:n0", "p362:n1", "p423:n3", "p427:n4", "p491:n1",
                "p596:n2", "p726:n3", "p895:n0", "p897:n4", "p912:n2"])
CODE_SIGNED = set(diag.TRUTH) | set(diag.SEALED_TRUTH)
chk(len(CODE_SIGNED) == 21, "21 spans are signed in code, not the 19 the ruling names: got %d"
    % len(CODE_SIGNED))
chk(RULING19 < CODE_SIGNED and sorted(CODE_SIGNED - RULING19) == ["p657:n0", "p900:n4"],
    "the ruling's 19 are a strict subset of the 21, and the two extras are named: %s"
    % sorted(CODE_SIGNED - RULING19))
chk(meta["n_signed_spans"] == 65,
    "45 + 21 - 1 overlap (p657:n0) = 65 signed spans scanned: got %d" % meta["n_signed_spans"])
chk(meta["n_spans_with_a_read"] == 65,
    "every signed span has at least one recorded read, so no span is silently untested: got %d"
    % meta["n_spans_with_a_read"])
known = set(R.VERDICTS) | set(R.EXCLUSIONS) | set(["no_match", "span_not_signed"])
chk(set(counts) <= known, "every outcome is a NAMED outcome: unexpected %s" % (set(counts) - known,))
chk(counts.get("read_equals_signature", 0) > counts.get("reversed_one_swap", 0),
    "most reads of a signed span match it; if that were not so the scan would be measuring "
    "something other than reversal")
h442 = [r for r in hits if r["span_id"] == "p442:n0"]
chk(len(h442) >= 2,
    "the scan finds p442:n0 on at least two arms, as ruling A(1) reports (both arms read דבר): "
    "got %d" % len(h442))
chk(all(r["registers"] for r in hits), "every HIT carries at least one register")
chk(all(r["page_printed"] == r["page_file"] - 88 for r in hits + unlisted),
    "the printed page is derived, never typed: printed = file - 88")

# -------- the 45-span signatures used here are the committed ones, not a copy that can drift
rec45 = json.load(io.open(os.path.join(R.DATA, R.SCORE45), encoding="utf-8"))
sig45 = dict((r["span_id"], r["signature"]) for r in rec45["rows"])
built = R.signed_spans()
chk(all(built[s][0] == sig45[s] for s in sig45),
    "every 45-span signature is taken from the committed SCORE45 record verbatim")
_both = dict(diag.TRUTH)
_both.update(diag.SEALED_TRUTH)
_v = _both["p657:n0"]
chk(R.consonants(sig45["p657:n0"]) == R.consonants(_v[0] if isinstance(_v, (tuple, list)) else _v),
    "the one span signed in BOTH sources carries the same signature in both; a disagreement there "
    "would be a finding in its own right, not a tie to break silently")
chk(built["p442:n0"][0] == SIG442,
    "and the record's p442:n0 signature is the רבך that ruling A(1) adjudicated -- so the test "
    "above is pinned to the record, not to my typing: got %r" % built["p442:n0"][0])

# ------------------------------------------------------------------------------------------ report
EXPECTED = 47
print("signature_reversal: %d checks, %d failed" % (N, len(FAILED)))
for m in FAILED:
    print("  FAIL  %s" % m)
if N != EXPECTED:
    print("SUITE DID NOT RUN TO COMPLETION: %d checks, expected %d. An exception in a hand-rolled "
          "suite ends it silently; a short count is a failure, not a smaller pass." % (N, EXPECTED))
    sys.exit(2)
sys.exit(1 if FAILED else 0)
