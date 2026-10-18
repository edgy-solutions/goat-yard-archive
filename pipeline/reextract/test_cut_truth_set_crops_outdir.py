"""cut_truth_set_crops target guard born tested: no run writes over crops that already exist.
Run: python test_cut_truth_set_crops_outdir.py

- No argument is refused, naming the approved folder.
- --out-dir at a folder holding a .png or the manifest is refused.
- The approved set is regenerated only by --out-dir AT the approved folder after it has been emptied on
  purpose, its manifest included.
- Importing the script is refused.

The script runs at module level, so every case runs it as a subprocess. HAD.DATA is redirected to a temporary
data root for each run, so the default target and the approved manifest are sandbox paths. A broken
guard therefore cannot reach the real approved corpus: an accepted run reaches the truth-set read, finds
no truth set in the sandbox, and dies before its first write. That death is also how the two "passes the
guard" tests see acceptance without running the 74-span cut. Separately, the real corpus under the real
HAD.DATA is snapshotted around every run and must be unchanged."""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import hebrew_aperture_diag as HAD

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "cut_truth_set_crops.py"
SET_DIR = "truthset74_crops_0401b636ffa7bf1a"
SET_MAN = "truthset74_cut_0401b636ffa7bf1a.json"
N_TESTS = 9

# Runs the script as __main__ with HAD.DATA pointed at a sandbox: argv = [data_root, *script_args].
RUNNER = (
    "import runpy, sys\n"
    "from pathlib import Path\n"
    "import hebrew_aperture_diag as HAD\n"
    "HAD.DATA = Path(sys.argv[1])\n"
    "script = %r\n"
    "sys.argv = [script] + sys.argv[2:]\n"
    "runpy.run_path(script, run_name='__main__')\n" % str(SCRIPT))
IMPORTER = (
    "import sys\n"
    "from pathlib import Path\n"
    "import hebrew_aperture_diag as HAD\n"
    "HAD.DATA = Path(sys.argv[1])\n"
    "import cut_truth_set_crops\n")


def _snap(d):
    """{relative path: (size, sha256, mtime_ns)} for every file under d. This is what 'nothing written' means."""
    d = Path(d)
    if not d.is_dir():
        return None
    return {str(p.relative_to(d)): (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest(),
                                    p.stat().st_mtime_ns)
            for p in sorted(d.rglob("*")) if p.is_file()}


def _real_corpus():
    """Every cut folder and manifest under the REAL HAD.DATA, whatever set they belong to."""
    return ({str(d): _snap(d) for d in sorted(HAD.DATA.glob("truthset*_crops_*"))},
            {str(m): (m.stat().st_size, m.stat().st_mtime_ns) for m in sorted(HAD.DATA.glob("truthset*_cut_*.json"))})


def _run(code, data_root, *args):
    real_before = _real_corpus()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", code, str(data_root)] + [str(a) for a in args], cwd=str(HERE),
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)
    assert _real_corpus() == real_before, "a run changed the REAL approved crop corpus"
    return r


def _assert_refused(r, watched, before, *needles):
    assert r.returncode == 2, "exit %r, not the refusal's 2; stderr tail: %s" % (r.returncode, r.stderr[-400:])
    assert "Traceback" not in r.stderr, "exited by a crash, not by the refusal: %s" % r.stderr[-400:]
    for n in ("REFUSED:", "Nothing was written") + needles:
        assert n in r.stderr, "%r not in the refusal: %s" % (n, r.stderr[-400:])
    assert _snap(watched) == before, "the refused run changed %s" % watched


def _assert_passed_the_guard(r, watched, before):
    """Accepted, then died at the sandbox's missing truth set. That read comes before the first write."""
    assert "REFUSED" not in r.stderr, "an acceptable target was refused: %s" % r.stderr[-400:]
    assert r.returncode == 1 and "FileNotFoundError" in r.stderr and "truth_set74_" in r.stderr, \
        "did not reach the truth-set read: exit %r, %s" % (r.returncode, r.stderr[-400:])
    assert _snap(watched) == before, "something was written before the truth set was read"


def test_no_argument_is_refused_naming_the_approved_folder():
    with tempfile.TemporaryDirectory() as root:
        (Path(root) / SET_DIR).mkdir()
        (Path(root) / SET_DIR / "p96_n1_A2_spanbox.png").write_bytes(b"approved pixels")
        (Path(root) / SET_MAN).write_text("{}", encoding="utf-8")
        before = _snap(root)
        _assert_refused(_run(RUNNER, root), root, before, "no --out-dir", str(Path(root) / SET_DIR))


def test_no_argument_is_refused_even_when_the_approved_folder_is_empty():
    # Regenerating needs the explicit --out-dir, so an absent or empty default target refuses too.
    with tempfile.TemporaryDirectory() as root:
        before = _snap(root)
        _assert_refused(_run(RUNNER, root), root, before, "no --out-dir")
        assert not (Path(root) / SET_DIR).exists(), "the refused run created the approved folder"


def test_out_dir_at_the_approved_folder_holding_crops_is_refused():
    with tempfile.TemporaryDirectory() as root:
        (Path(root) / SET_DIR).mkdir()
        (Path(root) / SET_DIR / "p96_n1_A2_spanbox.png").write_bytes(b"approved pixels")
        before = _snap(root)
        _assert_refused(_run(RUNNER, root, "--out-dir", Path(root) / SET_DIR), root, before,
                        "(the APPROVED corpus)", "holds 1 crop file(s)")


def test_emptied_approved_folder_with_its_manifest_left_is_refused():
    # The approved manifest lives BESIDE the folder (at OUT), so emptying the folder alone is not enough.
    with tempfile.TemporaryDirectory() as root:
        (Path(root) / SET_DIR).mkdir()
        (Path(root) / SET_MAN).write_text("{}", encoding="utf-8")
        before = _snap(root)
        _assert_refused(_run(RUNNER, root, "--out-dir", Path(root) / SET_DIR), root, before,
                        "(the APPROVED corpus)", SET_MAN)


def test_emptied_approved_folder_passes_the_guard():
    with tempfile.TemporaryDirectory() as root:
        (Path(root) / SET_DIR).mkdir()
        before = _snap(root)
        _assert_passed_the_guard(_run(RUNNER, root, "--out-dir", Path(root) / SET_DIR), root, before)


def test_fresh_out_dir_holding_a_crop_is_refused():
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as td:
        for n in ("p96_n1_A2_spanbox.png", "p96_n1_notecontext.png"):
            (Path(td) / n).write_bytes(b"x")
        before = _snap(td)
        _assert_refused(_run(RUNNER, root, "--out-dir", td), td, before,
                        "holds 2 crop file(s)", "p96_n1_A2_spanbox.png")
        assert _snap(root) == {}, "the refused run wrote into the data root"


def test_fresh_out_dir_holding_only_the_manifest_is_refused():
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as td:
        (Path(td) / SET_MAN).write_text("{}", encoding="utf-8")
        before = _snap(td)
        _assert_refused(_run(RUNNER, root, "--out-dir", td), td, before, SET_MAN)


def test_fresh_empty_out_dir_passes_the_guard():
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as td:
        before = _snap(td)
        _assert_passed_the_guard(_run(RUNNER, root, "--out-dir", td), td, before)
        assert _snap(root) == {}, "the run wrote into the data root"


def test_import_is_refused():
    with tempfile.TemporaryDirectory() as root:
        r = _run(IMPORTER, root)
        assert r.returncode == 1 and "ImportError" in r.stderr and "is a script" in r.stderr, \
            "import was not refused: exit %r, %s" % (r.returncode, r.stderr[-400:])
        assert _snap(root) == {}, "the refused import wrote into the data root"


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
