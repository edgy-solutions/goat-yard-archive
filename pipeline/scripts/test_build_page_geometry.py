"""Born-tests for build_page_geometry.py.
Convention follows pipeline/scripts/test_cv_footnote_presplit.py: plain asserts, dependency-free
runner, `python test_build_page_geometry.py` prints "<n> passed, <m> failed, <s> skipped" and
exits nonzero on failure. Cases needing a file that is absent print a SKIP line and do not count
as a pass. NONE of these tests touch the real private output path -- they all write to the
system temp dir.
"""
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_page_geometry as bpg

IMG_DIR = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
PAGE100 = IMG_DIR / "page100_image1.png"


class Skip(Exception):
    """Raised by a test to mean 'not assertable here', never counted as a pass or a fail."""


def _require(path):
    if not path.exists():
        raise Skip(f"missing fixture file: {path}")
    return path


def _tmp_out(name="page_geometry.jsonl"):
    tmpdir = tempfile.mkdtemp(prefix="bpg_test_")
    return Path(tmpdir) / name


def _no_rule_info(W=1600, H=2000):
    """Shape of `info` as presplit() returns it on the (None, info) no-rule early-return path:
    both rules None, no fn_gutter key at all (never computed), body_regions both page_bottom."""
    return {
        "xdiv": 800,
        "rules": [None, None],
        "mode": "two_column",
        "page": [W, H],
        "coord": "native_px_x0y0x1y1_topleft_exclusive",
        "body_regions": [
            {"col": "left", "box": [0, 0, 800, H], "rule_y": None, "y1_source": "page_bottom_no_rule"},
            {"col": "right", "box": [800, 0, W, H], "rule_y": None, "y1_source": "page_bottom_no_rule"},
        ],
    }


# ---------------------------------------------------------------------------
# 1. Output-path refusal
# ---------------------------------------------------------------------------

def test_refuses_output_inside_goatyard_laneA():
    try:
        bpg.validate_out_path("C:/Users/cnogr/git/goatyard-laneA/pipeline/scripts/leak.jsonl")
        assert False, "expected OutputPathRefused"
    except bpg.OutputPathRefused:
        pass


def test_refuses_output_inside_goat_yard_archive():
    try:
        bpg.validate_out_path("C:/Users/cnogr/git/goat-yard-archive/some/nested/path/leak.jsonl")
        assert False, "expected OutputPathRefused"
    except bpg.OutputPathRefused:
        pass


def test_refuses_output_at_forbidden_root_exactly():
    try:
        bpg.validate_out_path("C:/Users/cnogr/git/goat-yard-archive")
        assert False, "expected OutputPathRefused"
    except bpg.OutputPathRefused:
        pass


def test_guard_covers_the_repo_this_file_runs_from():
    """Hardcoded machine paths rot. The script's own repo root is derived at import, so a
    clone under another name, or a second worktree, is refused without editing the list."""
    self_root = Path(bpg.__file__).resolve().parents[2]
    assert any(bpg._is_within(self_root, r.resolve()) for r in bpg.FORBIDDEN_OUTPUT_ROOTS)
    try:
        bpg.validate_out_path(str(self_root / "some" / "where" / "out.jsonl"))
    except bpg.OutputPathRefused:
        pass
    else:
        raise AssertionError("output inside the running repo was not refused")


def test_accepts_temp_path():
    out = _tmp_out()
    resolved = bpg.validate_out_path(str(out))
    assert resolved == out.resolve()


# ---------------------------------------------------------------------------
# 2. Record shape: exact key set + order, printed_page arithmetic
# ---------------------------------------------------------------------------

def test_record_key_order_real_page():
    _require(PAGE100)
    from cv_footnote_presplit import presplit
    strip, info = presplit(str(PAGE100), upscale=2)
    config = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
    record = bpg.build_record(1, 100, "page100_image1.png", info, strip, "best_effort", config)
    expected_keys = [
        "volume", "file_page", "printed_page", "image", "page", "coord", "xdiv",
        "rules", "mode", "fn_gutter", "body_regions", "tier", "flags", "config",
    ]
    assert list(record.keys()) == expected_keys, list(record.keys())
    assert record["printed_page"] == record["file_page"] - 88
    assert record["printed_page"] == 12
    assert record["volume"] == 1
    assert record["tier"] == "best_effort"


# ---------------------------------------------------------------------------
# 3. Config hash determinism + sensitivity
# ---------------------------------------------------------------------------

def test_config_hash_deterministic():
    c1 = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
    c2 = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
    assert c1["hash"] == c2["hash"]
    assert len(c1["hash"]) == 16
    int(c1["hash"], 16)  # must be valid hex


def test_config_hash_sensitive_to_git_dirty():
    c_clean = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
    c_dirty = bpg.build_config(2, 0.30, "deadbeef", "abc1234", True)
    assert c_clean["hash"] != c_dirty["hash"]


def test_config_hash_sensitive_to_upscale():
    c1 = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
    c2 = bpg.build_config(3, 0.30, "deadbeef", "abc1234", False)
    assert c1["hash"] != c2["hash"]


def test_config_key_order():
    c = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
    assert list(c.keys()) == ["presplit", "module_sha256", "git_head", "git_dirty", "hash"]
    assert list(c["presplit"].keys()) == ["upscale", "full_width_depth"]


# ---------------------------------------------------------------------------
# 4. presplit() raises -> record with flags=["error"], pass does not abort
# ---------------------------------------------------------------------------

def test_presplit_exception_yields_error_record():
    _require(PAGE100)

    def _boom(path, upscale=2, full_width_depth=0.30):
        raise ValueError("synthetic boom for born-test")

    orig = bpg.presplit
    bpg.presplit = _boom
    try:
        config = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
        record, missing = bpg.process_page(1, 100, PAGE100, "page100_image1.png", "best_effort", config)
    finally:
        bpg.presplit = orig

    assert missing is False
    assert record is not None
    assert record["flags"] == ["error"]
    assert record["error"]["type"] == "ValueError"
    assert "synthetic boom" in record["error"]["message"]
    assert record["file_page"] == 100
    assert record["printed_page"] == 12


def test_run_does_not_abort_on_presplit_exception():
    """Full main() over two pages where one always raises: the run still writes a record for
    both and exits 0 (nonzero only when ZERO records were written)."""
    _require(PAGE100)

    def _boom(path, upscale=2, full_width_depth=0.30):
        raise RuntimeError("synthetic boom")

    orig = bpg.presplit
    bpg.presplit = _boom
    out = _tmp_out()
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bpg.main(["--volume-dir", str(IMG_DIR), "--out", str(out), "--pages", "100"])
    finally:
        bpg.presplit = orig

    assert rc == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["flags"] == ["error"]


# ---------------------------------------------------------------------------
# 5. No-rule page: carries no_rule + y1_unknown, is NOT skipped
# ---------------------------------------------------------------------------

def test_no_rule_page_not_skipped():
    info = _no_rule_info()
    config = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
    record = bpg.build_record(1, 999, "page999_image1.png", info, None, "best_effort", config)
    assert record is not None
    assert "no_rule" in record["flags"]
    assert "y1_unknown" in record["flags"]
    assert "no_strip" in record["flags"]
    assert record["fn_gutter"] is None
    assert record["mode"] == "two_column"
    assert "full_width" not in record["flags"]


def test_no_rule_via_process_page_monkeypatched():
    info = _no_rule_info()

    def _fake_presplit(path, upscale=2, full_width_depth=0.30):
        return None, info

    orig = bpg.presplit
    bpg.presplit = _fake_presplit
    tmpdir = tempfile.mkdtemp(prefix="bpg_norule_")
    fake_image = Path(tmpdir) / "page999_image1.png"
    fake_image.write_bytes(b"not a real png, presplit is monkeypatched")
    try:
        config = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
        record, missing = bpg.process_page(1, 999, fake_image, "page999_image1.png", "best_effort", config)
    finally:
        bpg.presplit = orig

    assert missing is False
    assert record is not None
    assert "no_rule" in record["flags"]
    assert "y1_unknown" in record["flags"]


# ---------------------------------------------------------------------------
# 6. Absent image file: no record, but census counts + names it
# ---------------------------------------------------------------------------

def test_absent_image_no_record():
    fake_dir = Path(tempfile.mkdtemp(prefix="bpg_absent_"))
    config = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
    record, missing = bpg.process_page(1, 12345, fake_dir / "page12345_image1.png",
                                        "page12345_image1.png", "best_effort", config)
    assert record is None
    assert missing is True


def test_absent_image_counted_in_census_and_run_still_succeeds():
    _require(PAGE100)
    out = _tmp_out()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = bpg.main(["--volume-dir", str(IMG_DIR), "--out", str(out), "--pages", "100", "999999"])
    stdout = buf.getvalue()
    assert rc == 0
    assert "MISSING: page999999_image1.png" in stdout
    assert "missing: 1" in stdout
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # only page100's record -- the missing page produced NO record
    rec = json.loads(lines[0])
    assert rec["file_page"] == 100


# ---------------------------------------------------------------------------
# 7. image path stored relative, not absolute
# ---------------------------------------------------------------------------

def test_image_field_is_relative():
    _require(PAGE100)
    from cv_footnote_presplit import presplit
    strip, info = presplit(str(PAGE100), upscale=2)
    config = bpg.build_config(2, 0.30, "deadbeef", "abc1234", False)
    record = bpg.build_record(1, 100, "page100_image1.png", info, strip, "best_effort", config)
    assert record["image"] == "page100_image1.png"
    assert not Path(record["image"]).is_absolute()
    assert "/" not in record["image"] and "\\" not in record["image"]


# ---------------------------------------------------------------------------
# Zero-records-written exit code
# ---------------------------------------------------------------------------

def test_zero_records_written_exits_nonzero():
    out = _tmp_out()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = bpg.main(["--volume-dir", str(IMG_DIR), "--out", str(out), "--pages", "88888888"])
    assert rc != 0


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = s = 0
    for fn in fns:
        try:
            fn()
            p += 1
            print(f"  PASS {fn.__name__}")
        except Skip as e:
            s += 1
            print(f"  SKIP {fn.__name__}: {e}")
        except Exception:
            f += 1
            print(f"  FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{p} passed, {f} failed, {s} skipped")
    raise SystemExit(1 if f else 0)
