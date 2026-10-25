# -*- coding: utf-8 -*-
u"""Born tests for confusable_vocab (ruling B(5)).

pytest is not installed in this venv: run it directly.

    PYTHONIOENCODING=utf-8 ../../../goat-yard-archive/.venv/Scripts/python.exe test_confusable_vocab.py

The counts are NOT typed in twice.  They are RE-DERIVED here from the committed record
CANONICAL45_reader_e63ecc2eab1aa479.json and compared to the module's table, so a count that drifts
from its source fails.  A test that restated the numbers would only test my typing.

The assertion COUNT is itself asserted: in a hand-rolled suite an exception ENDS the run silently,
and this lane has lost 40 assertions that way twice.

All page numbers are FILE pages (printed = file - 88).
"""
import io
import json
import os
import re
import sys
import unicodedata

import confusable_vocab as V
import hebrew_aperture_diag as diag

N = 0
FAILED = []


def chk(cond, msg):
    global N
    N += 1
    if not cond:
        FAILED.append(msg)


NIK = re.compile(u"[֑-ׇ]")


def cons(s):
    return NIK.sub(u"", unicodedata.normalize("NFC", s or u""))


# ----------------------------------------------------------------- re-derive from the committed record
REC = os.path.join(str(diag.DATA), "CANONICAL45_reader_e63ecc2eab1aa479.json")
chk(os.path.exists(REC), "the committed canonical record is present (a probe that misses passes on "
                         "nothing): %s" % REC)

if os.path.exists(REC):
    rows = json.load(io.open(REC, encoding="utf-8"))["rows"]
    chk(len(rows) == 18, "the record carries 18 reader rows (got %d)" % len(rows))

    derived = {}
    equal_len, unequal = 0, 0
    for r in rows:
        p, q = cons(r["printed"]), cons(r["read"])
        if len(p) != len(q):
            unequal += 1
            continue
        equal_len += 1
        for x, y in zip(p, q):
            if x != y:
                k = V.key(x, y)
                derived[k] = derived.get(k, 0) + 1

    chk(equal_len == 14, "14 rows have equal consonant counts and admit a positional pair (got %d)"
        % equal_len)
    chk(unequal == 4, "4 rows differ in length and contribute NO pair -- an insertion or deletion "
                      "has no differing position (got %d)" % unequal)
    chk(sum(derived.values()) == 18, "18 substitution positions over those rows (got %d)"
        % sum(derived.values()))

    # the table must equal the derivation, key for key
    tbl = dict((k, v[0]) for k, v in V.OBSERVED_IN_READS.items())
    chk(tbl == derived,
        "OBSERVED_IN_READS equals the derivation from the record. table=%s derived=%s"
        % (sorted(tbl.items()), sorted(derived.items())))
    chk(len(derived) == 13, "13 distinct observed pairs (got %d)" % len(derived))

    # the letter table must be derivable from the pair table, not independently typed
    letters = {}
    for k, (n, _nm) in V.OBSERVED_IN_READS.items():
        for ch in k:
            letters[ch] = letters.get(ch, 0) + n
    for ch, (n, nm) in V.IMPLICATED_LETTER_COUNTS.items():
        chk(letters.get(ch) == n,
            "IMPLICATED_LETTER_COUNTS[%s] (%s) = %d matches the pair table's %s"
            % (ch, nm, n, letters.get(ch)))

# ------------------------------------------------- the ruling's pair that the data does not contain
VAV, RESH = u"ו", u"ר"
chk(V.observed_count(VAV, RESH) == 0, "vav/resh has ZERO observed instances")
chk(V.registers(VAV, RESH) == [], "vav/resh is in NO witnessed register")
chk(V.key(VAV, RESH) in V.NOT_OBSERVED, "vav/resh is recorded as an explicit null, not dropped")
chk(V.key(VAV, RESH) not in V.ALL_WITNESSED,
    "a zero-count entry must NOT leak into ALL_WITNESSED -- that is how a null gets cited as "
    "measured")
chk("ruling B(5)" in V.NOT_OBSERVED[V.key(VAV, RESH)][1],
    "the null entry says which ruling named it, so the provenance travels with it")

# --------------------------------------------------------------------- registers do not get merged
chk(not (set(V.SIGNED_GLYPH_CARD) & set(V.ARGUED_SAME_DEFECT)),
    "a pair is signed OR argued, never silently both")
chk(not (set(V.ADJUDICATED_IN_AUDIT) & (set(V.SIGNED_GLYPH_CARD) | set(V.ARGUED_SAME_DEFECT))),
    "an audit-adjudicated pair does not also sit in the signed or argued register -- the three "
    "evidence registers are pairwise disjoint, so a pair cannot borrow a grounding it lacks")
chk(len(V.SIGNED_GLYPH_CARD) == 3, "3 pairs were signed on glyph cards")
chk(len(V.ARGUED_SAME_DEFECT) == 5, "5 pairs sit in the run's list by argument, unsigned")
AYIN, TSADI = u"ע", u"צ"
chk(V.registers(AYIN, TSADI) == ["SIGNED_GLYPH_CARD"], "ayin/tsadi is signed only")
DALET = u"ד"
chk(V.registers(DALET, RESH) == ["ARGUED_SAME_DEFECT", "OBSERVED_IN_READS"],
    "dalet/resh is argued AND observed, and both registers are reported: %s"
    % V.registers(DALET, RESH))
chk(V.registers(DALET, RESH)[0] == "ARGUED_SAME_DEFECT",
    "registers are returned strongest first, so a caller reading [0] is not misled")
HE, HET = u"ה", u"ח"
chk(V.registers(HE, HET) == ["ARGUED_SAME_DEFECT", "OBSERVED_IN_READS"], "he/het argued + observed")
# the three keys that were copied in UNSORTED and were therefore unreachable: pinned so a future
# copy from classify45_evidence.CONFUSABLE (which stores sets, where order is free) cannot reintroduce it
KAF, FKAF, BET = u"כ", u"ך", u"ב"
chk(V.registers(KAF, BET) == ["ARGUED_SAME_DEFECT"], "kaf/bet is REACHABLE (was an unsorted key)")
chk(V.registers(FKAF, BET) == ["ARGUED_SAME_DEFECT"],
    "final-kaf/bet is REACHABLE (was an unsorted key)")
chk(V.registers(VAV, u"י") == ["ARGUED_SAME_DEFECT", "OBSERVED_IN_READS"],
    "vav/yod is REACHABLE in both registers (was an unsorted key)")

# ---------------------------------------------- ruling A(1): dalet/final-kaf, the reversal pair
# Without this entry the ruling-A(2) rule ("one swap from the confusable list") fires on NOTHING --
# not even on p442:n0, the case that produced the ruling.  So its reachability is load-bearing.
FKAF_ = u"ך"
chk(len(V.ADJUDICATED_IN_AUDIT) == 1, "one pair was adjudicated in the audit, not more")
chk(V.registers(DALET, FKAF_) == ["ADJUDICATED_IN_AUDIT"],
    "dalet/final-kaf is REACHABLE and reports its own register only: %s"
    % V.registers(DALET, FKAF_))
chk(V.key(DALET, FKAF_) in V.ALL_WITNESSED,
    "dalet/final-kaf is in ALL_WITNESSED, so signature_reversal can find it")
chk(V.name(DALET, FKAF_) == u"dalet/final-kaf", "the pair has a human name")
_src = io.open("confusable_vocab.py", encoding="utf-8").read()
chk("left-to-right" in _src and "A(1)" in _src,
    "the register records the RULING and the CAUSE on record (a reading-order fault, not an optical "
    "confusion), because the cause is what decides whether a consumer may use it")

# ------------------------------------------------------------------------------- the key invariant
for d in (V.SIGNED_GLYPH_CARD, V.ADJUDICATED_IN_AUDIT, V.ARGUED_SAME_DEFECT,
          V.OBSERVED_IN_READS, V.NOT_OBSERVED):
    for k in d:
        chk(len(k) == 2 and list(k) == sorted(k),
            "every key is two letters in sorted order, so lookup cannot depend on argument order: "
            "%r" % k)
chk(V.key(u"ו", u"ז") == V.key(u"ז", u"ו"), "key() is order-independent")

# -------------------------------------------------------------- no decision is exposed, by design
chk(not any(n.lower().startswith(("is_", "should_", "suspect"))
            for n in dir(V) if callable(getattr(V, n, None))),
    "the module exposes no predicate that returns a verdict: ruling B(5) says record only, no "
    "threshold")
chk(isinstance(V.observed_count(VAV, u"ז"), int) and V.observed_count(VAV, u"ז") == 2,
    "vav/zayin counts 2 -- the pair that found p233:n4")
chk(V.name(VAV, u"ז") == u"vav/zayin", "name() resolves a witnessed pair")
chk(V.name(u"א", u"ט") is None, "name() is None for an unknown pair")
chk(V.observed_count(u"א", u"ט") == 0, "an unknown pair counts 0, and 0 is not a verdict")

# ------------------------------------------------------------------------------------------ report
EXPECTED = 61
print("confusable_vocab: %d checks, %d failed" % (N, len(FAILED)))
for m in FAILED:
    print("  FAIL  %s" % m)
if N != EXPECTED:
    print("SUITE DID NOT RUN TO COMPLETION: %d checks, expected %d. An exception in a hand-rolled "
          "suite ends it silently; a short count is a failure, not a smaller pass." % (N, EXPECTED))
    sys.exit(2)
sys.exit(1 if FAILED else 0)
