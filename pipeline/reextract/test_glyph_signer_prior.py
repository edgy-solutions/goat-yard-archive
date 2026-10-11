"""Born-test, in both directions: a re-opened row with a prior `corrected` tile PRESENTS the correction.
ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

The same node assertion file (test_glyph_signer_prior.js, which asserts in the tile's OWN element) is run
against a round-2 page rendered on JS_PASS4, which must PASS, and on JS_PASS3 (via --test-console pass3),
which must FAIL -- otherwise the test is not testing what it claims. Also covers the overlay gate
(resign_overlay.py): an uncovered disagreement refuses, a stray ruling refuses, a bad verdict refuses.
Run: python test_glyph_signer_prior.py
These tests need the audits directory (the pinned signed exports); they fail loudly, never skip, without it.
"""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hebrew_aperture_diag as HAD                      # noqa: E402
import resign_overlay as RO                             # noqa: E402

ADJ = HAD.DATA / "ADJUDICATION_pass3_r1_588879f2f4a2cee8.json"
CUR = HAD.DATA / "glyphsign_0401b636ffa7bf1a_pass3_3span_signed_51c0e7ba.jsonl"
PRI = HAD.DATA / "glyphsign_0401b636ffa7bf1a_pass2_26span_signed_3285d39a.jsonl"
JSDOM_DIRS = [os.environ.get("NODE_PATH", ""), "C:/Users/cnogr/git/airbyte/airbyte-webapp/node_modules",
              "C:/Users/cnogr/git/cortex-ui/node_modules"]


def _node_env():
    for p in JSDOM_DIRS:
        if p and os.path.isdir(os.path.join(p, "jsdom")):
            e = dict(os.environ)
            e["NODE_PATH"] = p
            e["PYTHONIOENCODING"] = "utf-8"
            return e
    raise AssertionError("jsdom not found in %r -- the born-test cannot run, and a gate that cannot run "
                         "is not passing" % (JSDOM_DIRS,))


def _build(extra, out):
    e = _node_env()
    p = subprocess.run([sys.executable, os.path.join(HERE, "glyph_signer.py"), "--pass3", "--pass3-round", "2",
                        "--out-dir", out] + extra, capture_output=True, env=e)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-600:]
    return [os.path.join(out, f) for f in os.listdir(out) if f.endswith(".html")][0]


def _run_node(page):
    return subprocess.run(["node", os.path.join(HERE, "test_glyph_signer_prior.js"), page],
                          capture_output=True, env=_node_env())


def test_born_prior_corrected_is_presented_pass4_passes_pass3_fails():
    with tempfile.TemporaryDirectory() as d4, tempfile.TemporaryDirectory() as d3:
        r4 = _run_node(_build([], d4))
        out4 = r4.stdout.decode("utf-8", "replace")
        r3 = _run_node(_build(["--test-console", "pass3"], d3))
        out3 = r3.stdout.decode("utf-8", "replace")
    assert r4.returncode == 0 and "RESULT PASS" in out4, out4
    assert re.search(r"OK   tile 4's own text says 'prior: corrected' \+ resh", out4)
    # the gate must be able to SEE the failure: the older console hides the correction
    assert r3.returncode != 0 and "RESULT FAIL" in out3, out3
    assert re.search(r"FAIL tile 4's own text says 'prior: corrected' \+ resh", out3), out3
    assert re.search(r"FAIL all five verdict buttons are inert until unlocked", out3), out3


class _Raises:
    def __init__(self, match):
        self.match = match

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        assert et is RO.OverlayRefusal, "expected an OverlayRefusal matching %r, got %r" % (self.match, et)
        assert re.search(self.match, str(ev)), "refusal %r does not match %r" % (str(ev), self.match)
        return True


def _fixtures():
    assert ADJ.exists() and CUR.exists() and PRI.exists(), "audits directory data missing"
    diff = RO.compute_diff(CUR, PRI)
    return diff, json.loads(ADJ.read_text(encoding="utf-8"))


def test_overlay_gate_refuses_uncovered_stray_and_malformed():
    diff, adj = _fixtures()
    assert RO.check_coverage(diff, adj) == 10
    a = copy.deepcopy(adj)
    a["rulings"].pop(3)
    with _Raises("NO ruling"):
        RO.check_coverage(diff, a)
    a = copy.deepcopy(adj)
    a["rulings"].append({"span_id": "p1:n0", "what": "tile", "tile_i": 0, "verdict": "take",
                         "authority": "x", "basis": "y"})
    with _Raises("match no disagreement"):
        RO.check_coverage(diff, a)
    a = copy.deepcopy(adj)
    a["rulings"][0]["verdict"] = "maybe"
    with _Raises("not one of"):
        RO.check_coverage(diff, a)
    a = copy.deepcopy(adj)
    a["rulings"][0]["authority"] = ""
    with _Raises("authority"):
        RO.check_coverage(diff, a)
    a = copy.deepcopy(adj)
    a["diff_sha16"] = "0" * 16
    with _Raises("rules on diff"):
        RO.check_coverage(diff, a)


def test_overlay_restores_only_the_keep_and_marks_it():
    diff, adj = _fixtures()
    lines = [l for l in CUR.read_text(encoding="utf-8").splitlines() if l.strip()]
    prior = [json.loads(l) for l in PRI.read_text(encoding="utf-8").splitlines() if l.strip()]
    text, tally = RO.overlay_text(lines, prior, adj, "restored from pass 2 by ruling: keep")
    assert tally == {"keep": 1, "take": 9, "neither": 0}
    rows = {json.loads(l)["span_id"]: json.loads(l) for l in text.splitlines()}
    cur = {json.loads(l)["span_id"]: json.loads(l) for l in lines}
    t4 = [t for t in rows["p493:n3"]["tiles"] if t["i"] == 4][0]
    assert t4["verdict"] == "corrected" and t4["chose"] == "\u05e8" and t4["restored_from"]
    # every tile except that one is exactly the current reading
    for sid, r in rows.items():
        for t, c in zip(r["tiles"], cur[sid]["tiles"]):
            if (sid, t["i"]) != ("p493:n3", 4):
                assert t == c


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    assert len(fns) == 3, "expected 3 tests, found %d" % len(fns)
    p = f = 0
    for fn in fns:
        try:
            fn()
            p += 1
            print("  PASS %s" % fn.__name__)
        except Exception:
            f += 1
            print("  FAIL %s" % fn.__name__)
            traceback.print_exc()
    print("%d passed, %d failed" % (p, f))
    raise SystemExit(1 if f else 0)
