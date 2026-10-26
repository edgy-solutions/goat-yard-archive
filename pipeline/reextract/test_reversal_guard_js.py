# -*- coding: utf-8 -*-
u"""Born-test for the reversal guard: the JS port against the Python original, under node.

The guard in the signing console and `signature_reversal.examine` are ONE RULE ON TWO AXES.  This
test is the only thing that makes that true: node runs the generated JS, Python runs `examine`, and
every field of every record has to match on every case.  Node never calls Python and Python never
calls node, so an agreement here is a witness and not a construction.

The case population is deliberately three kinds, because each can hide what the others show:

  1. EVERY real pair this lane holds -- each of the 74 frozen spans' signature against its candidate,
     and every recorded read in `signature_reversal.recorded_reads()`.  Real strings carry nikud,
     final forms, multiple words and the lengths that actually occur.
  2. The named cases from `test_signature_reversal.py` -- the founding instance `p442:n0`, the
     ambiguous `p628:n2`, the unlisted-pair `p910:n3`.  If the port ever disagrees on those three,
     the ruling that rests on them is resting on nothing.
  3. A GENERATED cross-product over a small alphabet, every string of length 1..3 against every
     other of the same or different length.  Real data contains no palindromes, no empty reads and
     almost no length mismatches, so three of `examine`'s six exclusions are unreachable from (1)
     and (2) alone -- and an exclusion branch that no case reaches is a branch this test says
     nothing about.  The suite asserts every flag in the vocabulary was REACHED, so a port that
     never returns one cannot pass.

The suite asserts its own check COUNT: a raise in a hand-rolled suite ends the run silently, and
this lane has lost 40 assertions that way twice.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
"""
import io
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import reversal_guard_js as G                                            # noqa: E402
import signature_reversal as R                                           # noqa: E402
import confusable_vocab as V                                             # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

#: The alphabet the cross-product is built over.  Five letters chosen for what they make REACHABLE,
#: not for coverage of the alef-bet: a confusable pair the vocabulary carries (dalet/resh), a pair it
#: does not (lamed/final-kaf), and a final form, so `reversed_one_swap`, `..._unlisted` and the
#: final-form path all occur.  Plus a space, so `reverse_per_word` differs from `reverse_all`.
ALPHABET = [u"ד", u"ר", u"ל", u"ך", u"ב"]       # dalet resh lamed final-kaf bet

#: Cases written out by hand because each one is a RULING's instance, not a sample.
NAMED = [
    (u"רבך", u"דבר", "p442:n0 -- signed, pixels; the founding case"),
    (u"בן", u"בו", "p628:n2 -- no closer to the reverse than to the signature"),
    (u"לי", u"יך", "p910:n3 -- the reversal shape with an unlisted pair"),
]

N = 0
FAILED = []


def ok(cond, msg):
    global N
    N += 1
    if cond:
        print("  ok    %s" % msg)
    else:
        print("  FAIL  %s" % msg)
        FAILED.append(msg)


# ------------------------------------------------------------------- the node side
_HARNESS = u"""
const fs = require("fs");
__GUARD__
const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = cases.map(function(c){
  const r = rgExamine(c[0], c[1]);
  r.refuses = rgRefuses(r.flag);
  r.warns = rgWarns(r.flag);
  return r;
});
fs.writeFileSync(process.argv[3], JSON.stringify(out), "utf8");
"""


def run_node(cases, tmp):
    u"""Run the GENERATED guard under node over `cases`, returning one record per case."""
    js = os.path.join(tmp, "harness.js")
    cin = os.path.join(tmp, "cases.json")
    cout = os.path.join(tmp, "out.json")
    io.open(js, "w", encoding="utf-8", newline="\n").write(
        _HARNESS.replace("__GUARD__", G.GUARD_JS))
    io.open(cin, "w", encoding="utf-8", newline="\n").write(
        json.dumps(cases, ensure_ascii=False))
    # No `--` separator: node puts it in argv, so argv[2] would be the separator, not the file.
    p = subprocess.Popen(["node", js, cin, cout],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    so, se = p.communicate()
    if p.returncode != 0:
        raise RuntimeError("node failed rc=%d: %s" % (p.returncode, se.decode("utf-8", "replace")))
    return json.loads(io.open(cout, encoding="utf-8").read())


# ------------------------------------------------------------------- the case population
def real_pairs():
    u"""Every pair this lane actually holds.  Returns [(sig, read, why)]."""
    sigs = {sid: val[0] for sid, val in R.signed_spans().items()}
    out = []
    for sid, sig in sorted(sigs.items()):
        # A signature against itself is the `read_equals_signature` exclusion, which is the branch
        # every correct read lands in and therefore the one a port must not get wrong.
        out.append((sig, sig, "%s signature against itself" % sid))
        out.append((sig, u"".join(reversed(sig)), "%s signature against its own reverse" % sid))
    for sid, src, arm, cell, txt in R.recorded_reads():
        if sid not in sigs:
            continue        # a read of a span nobody signed has no signature to test against
        out.append((sigs[sid], txt, "%s %s/%s recorded read (%s)" % (sid, arm, cell, src)))
    return out


def cross_pairs():
    u"""Every string of length 1..3 over ALPHABET (and the two-word forms) against every other."""
    strs = [u""]
    for n in (1, 2, 3):
        for t in itertools.product(ALPHABET, repeat=n):
            strs.append(u"".join(t))
    # two-word forms, so reverse_per_word can differ from reverse_all at all
    for a in ALPHABET[:3]:
        for b in ALPHABET[:3]:
            strs.append(a + u" " + b)
            strs.append(a + a + u" " + b + b)
    out = []
    for a in strs:
        for b in strs:
            out.append((a, b, "cross %r/%r" % (a, b)))
    # `reversed_per_word_exact` needs a signature of three or more words-worth of letters read with
    # word ORDER kept and letters reversed inside each word, and it needs the per-word form to be
    # strictly closer to the read than the span-wide reverse is.  Nothing in the block above is long
    # enough, so that verdict was UNREACHED until these cases were added -- which is the whole point
    # of asserting coverage rather than counting cases.  The reads are DERIVED by calling the Python
    # helpers, never typed: a case built by hand would be a case about my arithmetic.
    for n in (3, 4, 5):
        for t in itertools.product(ALPHABET[:4], repeat=n):
            for cut in range(1, n):
                sig = u"".join(t[:cut]) + u" " + u"".join(t[cut:])
                out.append((sig, u"".join(R.reverse_per_word(sig)), "per-word %r" % (sig,)))
                out.append((sig, u"".join(reversed(R.consonants(sig))), "span-wide %r" % (sig,)))
    return out


FIELDS = ("signature_cons", "read_cons", "reverse_cons", "reverse_per_word_cons", "n_cons",
          "dist_to_signature", "dist_to_reverse", "swap", "registers", "flag")


def compare(cases, whys, label):
    u"""One node run against one Python run over the same cases.  Returns the flags reached."""
    tmp = tempfile.mkdtemp(prefix="rgjs_")
    try:
        got = run_node([[a, b] for a, b in cases], tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok(len(got) == len(cases), "%s: node returned one record per case (%d)" % (label, len(cases)))
    bad = []
    flags = {}
    for (a, b), why, g in zip(cases, whys, got):
        want = R.examine(a, b)
        flags[want["flag"]] = flags.get(want["flag"], 0) + 1
        for f in FIELDS:
            wv, gv = want[f], g.get(f)
            if f == "swap" and wv is not None and gv is not None:
                # a dict: compare key by key so a missing key is named, not hidden by ordering
                if sorted(wv) != sorted(gv) or any(wv[k] != gv[k] for k in wv):
                    bad.append((why, f, wv, gv))
                continue
            if wv != gv:
                bad.append((why, f, wv, gv))
        # the two consequences, which only exist on the JS side
        if g.get("refuses") != (want["flag"] in G.REFUSING_FLAGS):
            bad.append((why, "refuses", want["flag"] in G.REFUSING_FLAGS, g.get("refuses")))
        if g.get("warns") != (want["flag"] in G.WARNING_FLAGS):
            bad.append((why, "warns", want["flag"] in G.WARNING_FLAGS, g.get("warns")))
    ok(not bad, "%s: every field of every record agrees with Python (%d cases)%s"
       % (label, len(cases),
          "" if not bad else " -- first 3 of %d: %s" % (len(bad), bad[:3])))
    return flags


def main():
    print("ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).")

    # ---- node is present, and the harness really runs the guard (not a stub that returns nothing)
    tmp = tempfile.mkdtemp(prefix="rgjs_")
    try:
        probe = run_node([[u"דבר", u"רבד"]], tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok(probe and probe[0]["flag"] == "reversed_exact",
       "node runs the generated guard: an exactly-reversed pair comes back `reversed_exact`")
    ok(probe[0]["refuses"] is True, "and the console would REFUSE the save on it")

    # ---- the generator's own invariants
    ok(set(G.REFUSING_FLAGS) | set(G.WARNING_FLAGS) == set(R.VERDICTS),
       "every verdict in signature_reversal.VERDICTS has a consequence in the console")
    ok(not (set(G.REFUSING_FLAGS) & set(G.WARNING_FLAGS)),
       "no verdict both refuses and warns -- a flag with two consequences has none")
    ok(len(G.REGISTERS) == len(V.ALL_WITNESSED) == 19,
       "the emitted vocabulary is every pair confusable_vocab witnesses (19)")
    for k in sorted(V.ALL_WITNESSED):
        if G.REGISTERS[k] != list(V.registers(k[0], k[1])):
            ok(False, "emitted registers for %r differ from confusable_vocab" % (k,))
            break
    else:
        ok(True, "every emitted register list equals confusable_vocab.registers for that pair")
    ok(G.PAIR_NAMES[V.key(u"ד", u"ר")] is not None,
       "dalet/resh carries a name, so a swap record can say which pair it is")
    ok(G.guard_id()[0] > 1000 and len(G.guard_id()[1]) == 16,
       "the guard blob has an id (recorded, not pinned: the vocabulary may grow)")

    # ---- (1) and (2): every real pair, plus the three named rulings
    rp = real_pairs()
    ok(len(rp) >= 74, "the real-pair population covers at least the 74 signatures (%d pairs)" % len(rp))
    named = [(a, b) for a, b, _w in NAMED]
    f_real = compare([(a, b) for a, b, _w in rp] + named,
                     [w for _a, _b, w in rp] + [w for _a, _b, w in NAMED], "real+named")

    # The founding case, asserted by NAME and not only by agreement: if the port and the Python both
    # said the wrong thing here, the comparison above would be silent.
    p442 = R.examine(NAMED[0][0], NAMED[0][1])
    ok(p442["flag"] == "reversed_one_swap",
       "p442:n0 is `reversed_one_swap` -- so the REFUSAL alone would not have caught it")
    ok(p442["flag"] in G.WARNING_FLAGS and p442["flag"] not in G.REFUSING_FLAGS,
       "p442:n0 WARNS and does not refuse, which is the limit this build names")
    ok(R.examine(NAMED[1][0], NAMED[1][1])["flag"] == "ambiguous_basis",
       "p628:n2 is `ambiguous_basis`, not a reversal: no closer to the reverse than to the signature")
    ok(R.examine(NAMED[2][0], NAMED[2][1])["flag"] == "reversed_one_swap_unlisted",
       "p910:n3 is the reversal shape with a pair no register carries")

    # ---- (3) the cross-product, which is what reaches the exclusion branches
    cp = cross_pairs()
    f_cross = compare([(a, b) for a, b, _w in cp], [w for _a, _b, w in cp], "cross-product")

    # ---- every flag the predicate can return was REACHED by some case.  A branch no case reaches is
    # a branch this test says nothing about, and three exclusions are unreachable from real data.
    reached = set(f_real) | set(f_cross)
    expect = set(R.EXCLUSIONS) | set(R.VERDICTS) | {None}
    missing = sorted(x for x in expect if x not in reached and x is not None)
    ok(not missing, "every flag and exclusion was reached by some case%s"
       % ("" if not missing else " -- never reached: %s" % ", ".join(missing)))
    ok(None in reached, "and so was the no-flag outcome (a read that is neither, which must be silent)")
    ok(f_cross.get("palindrome_signature", 0) > 0 and f_cross.get("empty_read", 0) > 0
       and f_cross.get("length_mismatch", 0) > 0,
       "the three exclusions real data cannot reach were reached by the cross-product")

    # ---- a mutation: the comparison must be able to FAIL.  A green suite that cannot go red is a
    # claim about nothing, and this lane has shipped a verifier that agreed by construction.
    broken = G.GUARD_JS.replace('rec.flag="reversed_exact"', 'rec.flag="reversed_WRONG"')
    ok(broken != G.GUARD_JS, "the mutant guard differs from the real one")
    tmp = tempfile.mkdtemp(prefix="rgjs_")
    try:
        real_js = G.GUARD_JS
        G.GUARD_JS = broken
        mut = run_node([[u"דבר", u"רבד"]], tmp)
    finally:
        G.GUARD_JS = real_js
        shutil.rmtree(tmp, ignore_errors=True)
    ok(mut[0]["flag"] == "reversed_WRONG" and mut[0]["refuses"] is False,
       "a one-word mutation to the guard changes the flag AND drops the refusal -- so the "
       "agreement check above is live, and the refusal is not independent of the port")


def run():
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        FAILED.append("UNEXPECTED EXCEPTION: %r" % (e,))
    print("reversal_guard_js: %d checks, %d failed" % (N, len(FAILED)))
    rc = 0
    if FAILED:
        for m in FAILED:
            print("  - %s" % m)
        rc = 1
    if N != EXPECTED_CHECKS:
        print("CHECK COUNT %d != EXPECTED_CHECKS %d -- a check was lost, added, or never reached"
              % (N, EXPECTED_CHECKS))
        rc = 1
    return rc


EXPECTED_CHECKS = 22


if __name__ == "__main__":
    sys.exit(run())
