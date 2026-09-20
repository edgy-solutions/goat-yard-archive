"""Born-test fixture assertion: marker LETTERS, not just count/structure (Chris, 2026-09-20).

    python test_born_fixtures.py [run.jsonl]

*** THIS TEST IS EXPECTED-RED. DO NOT "FIX" IT BY WEAKENING THE ASSERTION. ***

The ratified reset records STAND. The run is what is on trial. Both fixtures fail today because the
band-aperture read gets the marker letters wrong while getting the note count right — which is precisely
the failure the count-authority chain cannot see on its own.

  p90  ratified `c | a,b,c,d`          run reads `c,b,d,c,d`
  p403 ratified `x,y,z,a,b | c,d,e,f,a` run reads `a,b,c,d,e,f,g,h,i,j`

p403 is the louder of the two: a clean textbook a..j is what a sequence GUESS looks like, not a read.

WHAT TURNS IT GREEN: the per-note crop path — per-note column-bounded rectangles feeding a marker-glyph
sub-crop per note, replacing the whole-band read. Read stability (p129/p393/p660 reproduce letter for
letter) says re-reading at the band aperture will not move these. If this test goes green for any other
reason, that reason needs explaining before it is believed.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_assert as FA

DEFAULT_RUN = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/born_test_baml.jsonl")
FIXTURES = [90, 403]
EXPECTED_RED = {90, 403}          # known-failing today; see module docstring


def main(run=DEFAULT_RUN):
    run = Path(run)
    if not run.exists():
        print(f"SKIP: no run jsonl at {run}")
        return 0
    records, offset = FA.load_records()
    print(f"born-test fixture assertion vs ratified marker_resets_observed.json")
    print(f"  run: {run.name}   file_page = printed_page + {offset}\n")

    results, hard_fail = [], []
    for pg in FIXTURES:
        obs = FA.letters_from_run(run, pg)
        if obs is None:
            print(f"p{pg}: NOT IN RUN — skipped"); continue
        r = FA.check_page(pg, obs, records)
        results.append(r)
        if r["ok"] is None:
            print(f"p{pg}: UNASSERTABLE — {r['why']}"); continue
        tag = "PASS" if r["ok"] else ("FAIL (expected-red)" if pg in EXPECTED_RED else "FAIL *** NEW ***")
        print(f"p{pg} (printed {r['printed_page']}, {r['book']}, ratified confidence={r['confidence']}): {tag}")
        print(f"     ratified : {r['letters_read']}")
        print(f"     expected : {','.join(r['expected_flat'])}   series={[len(s) for s in r['expected_series']]}")
        print(f"     observed : {','.join(r['observed_flat'])}   series={[len(s) for s in r['observed_series']]}")
        print(f"     count_ok={r['count_ok']} ({r['observed_n']}/{r['expected_n']})  "
              f"letters_ok={r['letters_ok']}  series_ok={r['series_ok']}")
        for m in r["mismatches"]:
            print(f"       k={m['k']}: expected '{m['expected']}' observed '{m['observed']}'")
        print()
        if not r["ok"] and pg not in EXPECTED_RED:
            hard_fail.append(pg)

    failing = [r["page"] for r in results if r["ok"] is False]
    passing = [r["page"] for r in results if r["ok"] is True]
    print(f"--- letters FAIL: {failing or 'none'}   PASS: {passing or 'none'} ---")
    if set(failing) == EXPECTED_RED and not hard_fail:
        print("STATUS: EXPECTED-RED, unchanged. The per-note crop path is what turns this green.")
        print("        (Red here is the correct state today — do not weaken the assertion.)")
        return 1
    if hard_fail:
        print(f"STATUS: NEW FAILURE on {hard_fail} — a fixture regressed beyond the known-red set.")
        return 2
    newly_green = sorted(EXPECTED_RED - set(failing) - {r['page'] for r in results if r['ok'] is None})
    if newly_green:
        print(f"STATUS: {newly_green} now GREEN. Verify the CAUSE before crediting it — read stability")
        print("        says the band aperture cannot produce this, so something else changed.")
    return 0


if __name__ == "__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RUN))
