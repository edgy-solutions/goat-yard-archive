"""cut_truth_set_crops --out-dir born tested: a re-cut into a folder that already holds crops is REFUSED
loudly (exit 2) and writes nothing, either there or in the approved corpus.
Run: python test_cut_truth_set_crops_outdir.py

The script runs at module level, so it is exercised as a subprocess, the way it is actually called. Only
the refusal path is run: an accepted --out-dir starts the full 74-span cut, which needs the private page
images and is Lane B's reproducibility check, not a unit test."""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import hebrew_aperture_diag as HAD

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "cut_truth_set_crops.py"
N_TESTS = 3


def _snap(d):
    """{name: (size, sha256, mtime_ns)} for every file directly in d -- what 'nothing written' means."""
    d = Path(d)
    if not d.is_dir():
        return None
    return {p.name: (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in d.iterdir() if p.is_file()}


def _corpus():
    """Every default cut folder and manifest under HAD.DATA, whatever set they belong to. A refused run
    must not touch the approved corpus either."""
    dirs = sorted(HAD.DATA.glob("truthset*_crops_*"))
    mans = sorted(HAD.DATA.glob("truthset*_cut_*.json"))
    return ({str(d): _snap(d) for d in dirs},
            {str(m): (m.stat().st_size, m.stat().st_mtime_ns) for m in mans})


def _run(out_dir):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "--out-dir", str(out_dir)], cwd=str(HERE),
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)


def _assert_refused(r, out_dir, before, corpus_before):
    assert r.returncode == 2, "exit %r, not the refusal's 2; stderr tail: %s" % (r.returncode, r.stderr[-400:])
    assert "REFUSED: --out-dir" in r.stderr and "Nothing was written" in r.stderr, r.stderr[-400:]
    assert "Traceback" not in r.stderr, "exited 2 by a crash, not by the refusal: %s" % r.stderr[-400:]
    assert _snap(out_dir) == before, "the refused run changed the target folder"
    assert _corpus() == corpus_before, "the refused run changed the approved crop corpus"


def test_refuses_when_out_dir_holds_a_crop():
    corpus_before = _corpus()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "p96_n1_A2_spanbox.png").write_bytes(b"not a real crop")
        before = _snap(td)
        _assert_refused(_run(td), td, before, corpus_before)
        assert not list(Path(td).glob("*.json")), "a manifest was written by a refused run"


def test_refuses_when_out_dir_holds_only_the_manifest():
    corpus_before = _corpus()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "truthset74_cut_0401b636ffa7bf1a.json").write_text("{}", encoding="utf-8")
        before = _snap(td)
        _assert_refused(_run(td), td, before, corpus_before)


def test_refusal_names_the_count_and_a_file():
    corpus_before = _corpus()
    with tempfile.TemporaryDirectory() as td:
        for n in ("p96_n1_A2_spanbox.png", "p96_n1_notecontext.png"):
            (Path(td) / n).write_bytes(b"x")
        before = _snap(td)
        r = _run(td)
        _assert_refused(r, td, before, corpus_before)
        assert "holds 2 crop file(s)" in r.stderr and "p96_n1_A2_spanbox.png" in r.stderr, r.stderr[-400:]


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    assert len(fns) == N_TESTS, "found %d tests, expected %d" % (len(fns), N_TESTS)
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed")
    raise SystemExit(1 if f or p != N_TESTS else 0)
