# -*- coding: utf-8 -*-
"""Prove the band, report, re-ratification and readiness checks live by mutating what they MEASURE.

These are passing checks, so breaking the check proves nothing: each mutation below breaks the
PRODUCER -- the report, the box-quality table, the accepted re-ratification map, the population rule,
the pinned literal in the signer -- and the harness records which named check noticed. A mutation
nothing notices is a check that is not there, and the two listed as EXPECTED MISS are noticed by
nobody on purpose, with the reason: a miss that is understood is a finding, a miss that is quiet is
a hole.

Two things this harness is NOT:
  - It is not a pass/fail on the suite. WATCH is a list of which check SHOULD notice, which is a
    claim of its own: the 2026-11-25 round found the floor mutant caught by the suite (23 reds) and
    missed by the watched check, and that gap was the finding, not the catch.
  - It cannot exercise a check whose subject is DATA. The chain check reads
    hebrew_box_reratify.jsonl, and mutating signed data to test a harness is not on the table. Two
    checks here are tripwires for data that does not exist yet (the third band verdict, the forked
    chain); they are listed and left unmutated rather than faked.

Both files are mutated IN PLACE (the module reads page images relative to its own directory, and the
drift check reads the signer as text). Pristine bytes are saved and restored, and the restore is
verified byte-for-byte for each file.
"""
import hashlib
import io
import os
import subprocess
import sys

# Derived, not transcribed: this file lives beside the two modules it mutates, and it runs
# the suite with the interpreter that is running IT. A harness holding an absolute path to
# a worktree mutates whatever sits at that path, which need not be the tree it was invoked
# in -- and this one restores from bytes it read at import, so the wrong tree would be
# restored from the wrong pristine.
D = os.path.dirname(os.path.abspath(__file__))
CARD = os.path.join(D, "hebrew_glyph_card.py")
SIGNER = os.path.join(D, "glyph_signer.py")
PY = sys.executable


def read(p):
    return io.open(p, encoding="utf-8", newline="").read()


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


PRIST = {CARD: read(CARD), SIGNER: read(SIGNER)}
SHAS = dict((k, sha(v)) for k, v in PRIST.items())

MUTANTS = [
    # ---- section 7: the band claim, and the chain the map is supposed to hold
    (CARD, "the line floor moves, so a 33px band is no longer corpus-normal",
     "MIN_BAND_PX = 20     #", "MIN_BAND_PX = 34     #"),
    (CARD, "the accepted map takes the FIRST link of the chain instead of the head",
     '''                good[r["span_id"]] = r''',
     '''                good.setdefault(r["span_id"], r)'''),
    # ---- section 8: the report and the table it reads
    (CARD, "the report stops naming the clipped boxes",
     '''    out.append("  merged-top-edge (a pass; the box clips the line above): %s"
               % (", ".join(sorted(r["span_id"] for r in rows
                                   if r["band"] == "merged-top-edge")) or "none"))''',
     '''    out.append("  merged-top-edge (a pass; the box clips the line above): %d"
               % len([r for r in rows if r["band"] == "merged-top-edge"]))'''),
    (CARD, "the report drops the band column from each row",
     '''                      r["band"] or "-", r["fault"] or ""))''',
     '''                      "", r["fault"] or ""))'''),
    (CARD, "the one-band total is off by one",
     "    return len(rows) - len(bad), len(rows), bad",
     "    return len(rows) - len(bad), len(rows) + 1, bad"),
    (CARD, "the report's loose set gains a span the table does not call loose",
     "    return len(rows) - len(bad), len(rows), bad",
     '    return len(rows) - len(bad), len(rows), bad + ["p999:n9"]'),
    # ---- section 18: the population, the table, the report, the pin
    (CARD, "the population forgets the spans carrying a recorded need",
     '''    return sorted(set(r["span_id"] for r in _A.AUDIT) | set(NEEDS))''',
     '''    return sorted(set(r["span_id"] for r in _A.AUDIT))'''),
    (CARD, "the table drops the spans that have only a card",
     '''    for sid in sorted(pop | cards, key=lambda s: (int(s.split(":")[0][1:]), s)):''',
     '''    for sid in sorted(pop, key=lambda s: (int(s.split(":")[0][1:]), s)):'''),
    (CARD, "surface_only is computed the wrong way round",
     '''            surface_only=bool(surface and sid not in pop),''',
     '''            surface_only=bool(surface and sid in pop),'''),
    (CARD, "the readiness report counts the ready-and-unpinned spans instead of naming them",
     '''        out.append("  ready and NOT pinned (a human decision, not a defect to patch here): %s"
                   % (", ".join(sorted(set(ready) - set(pin))) or "none"))''',
     '''        out.append("  ready and NOT pinned (a human decision, not a defect to patch here): %d"
                   % len(set(ready) - set(pin)))'''),
    (CARD, "the pinned literal can no longer be parsed out of the signer",
     '''    m = _re.search(r"RUN_N\\s*==\\s*(\\d+)\\s*and\\s*sorted\\(RUN_SPAN_IDS\\)\\s*==\\s*\\[([^\\]]*)\\]",''',
     '''    m = _re.search(r"RUN_M\\s*==\\s*(\\d+)\\s*and\\s*sorted\\(RUN_SPAN_IDS\\)\\s*==\\s*\\[([^\\]]*)\\]",'''),
    (SIGNER, "the signer's domain rule drifts away from the card module's",
     '''    _audited = sorted(set(r["span_id"] for r in AUDIT.AUDIT) | set(_GC.NEEDS))''',
     '''    _audited = sorted(set(list(r["span_id"] for r in AUDIT.AUDIT) + list(_GC.NEEDS)))'''),
    # ---- the two expected misses, listed on purpose, each with the module saying why
    (CARD, "EXPECTED MISS: ready ignores the surface clause (vacuous today, and section 18 says so)",
     '''            ready=bool(ok and surface)))''',
     '''            ready=bool(ok)))'''),
    (CARD, "one_band forced true -- caught at the SOURCE (s.17 call graph), not by the data",
     '''                         one_band=bool(im is not None and not fault and _one_band(im))))''',
     '''                         one_band=True))'''),
]

WATCH = [
    # section 7
    "every re-ratification on file is accepted",
    "every re-ratified box holds exactly one text band",
    "the re-ratified population is NOT EMPTY",
    "every span's re-ratifications form a CHAIN",
    "the accepted map holds the HEAD of each chain",
    # section 8
    "the one-band report's arithmetic closes",
    "the loose set reads the same from the report and from the table",
    "every box the report counts as one-band is one of the two shapes",
    "no readable span box on this set holds a third verdict",
    "the box-quality report NAMES every span whose box clips",
    "the report carries the band verdict on each span's own row",
    # section 18
    "the AUDIT and the build set are disjoint",
    "every span in both the readiness population and the build set",
    "the population covers every audited span",
    "the table speaks about the population UNION",
    "a span with a surface and no place in the population is reported as surface_only",
    "ready is exactly 'has a surface and signable'",
    "the needs clause is holding rows back",
    "the surface clause is vacuous on this set today",
    "the table is not unanimous in either direction",
    "the signer's pinned re-sign population still parses",
    "every span the signer pins is in the table",
    "the report NAMES every span ready under the rule",
    "glyph_signer still derives its domain with the same expression",
    # section 17: the call-graph guards. Added 2026-11-25 after this harness reported the
    # one_band=True mutant as an expected miss while section 17 was going red at it unwatched.
    "the LINE-CROP path keeps the old gate",
    "no threshold moved",
]


def run():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.Popen([PY, "-X", "utf8", "hebrew_glyph_card.py", "selftest"],
                         cwd=D, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    out = p.communicate()[0].decode("utf-8", "replace")
    red = [c for c in WATCH
           if any(l.strip().startswith("FAIL") and c in l for l in out.splitlines())]
    # EVERY red, not only the watched ones: the floor mutant was caught by the suite and missed by
    # the watch list, and a harness that only reports its own list cannot see that happen.
    allred = [l.strip()[6:].split("   ")[0].strip()
              for l in out.splitlines() if l.strip().startswith("FAIL")]
    return red, allred, ("Traceback (most recent call last)" in out), out


try:
    base_red, base_all, base_crash, base_out = run()
    print("pristine: watched reds %s; all reds %d %s; crashed=%s  %s"
          % (base_red, len(base_all), base_all, base_crash,
             base_out.strip().splitlines()[-1]))
    assert not base_red and not base_crash, "the pristine module does not pass its own checks"
    base = set(base_all)
    caught, expected_miss, surprises = 0, 0, []
    for path, name, old, new in MUTANTS:
        assert PRIST[path].count(old) == 1, ("anchor %r hits %d in %s"
                                             % (old[:50], PRIST[path].count(old),
                                                os.path.basename(path)))
        io.open(path, "w", encoding="utf-8", newline="\n").write(PRIST[path].replace(old, new, 1))
        red, allred, crash, out = run()
        io.open(path, "w", encoding="utf-8", newline="\n").write(PRIST[path])
        other = sorted(set(allred) - base)
        hit = bool(red) or crash
        want_miss = name.startswith("EXPECTED MISS")
        if want_miss:
            expected_miss += 1
            tag = "MISS-OK" if not hit else "CAUGHT!"
            if hit:
                surprises.append((name, red))
        else:
            caught += bool(hit)
            tag = "OK" if hit else "MISS"
        print("%-8s %-62s -> %s%s" % (tag, name[:62], ", ".join(red) or "nothing",
                                      " (+crash)" if crash else ""))
        if not hit and other:
            print("         ...but %d unwatched check(s) went red: %s"
                  % (len(other), "; ".join(o[:70] for o in other[:4])))
        elif hit and len(other) > len(red):
            print("         (%d red(s) in all, so the suite noticed more widely than the watch "
                  "list)" % len(other))
finally:
    for p_ in (CARD, SIGNER):
        io.open(p_, "w", encoding="utf-8", newline="\n").write(PRIST[p_])
        print("restored %-20s %s == %s  %s" % (os.path.basename(p_), sha(read(p_)), SHAS[p_],
                                               "yes" if sha(read(p_)) == SHAS[p_]
                                               else "NO -- FIX BY HAND"))

real = len(MUTANTS) - expected_miss
print("%d of %d real mutants caught by a watched check; %d expected misses, %d of them surprised"
      % (caught, real, expected_miss, len(surprises)))
print("NOT MUTATED, and listed for it: the chain check's subject is signed data "
      "(hebrew_box_reratify.jsonl) and the third-verdict check's subject is a box shape that does "
      "not exist on this set. Both are tripwires for data, not measurements of it.")
sys.exit(0 if caught == real else 1)
