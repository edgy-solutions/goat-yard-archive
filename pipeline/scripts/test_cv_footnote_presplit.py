"""Born-tests for the ADDITIVE body_regions extension to `presplit()` in cv_footnote_presplit.py.
The strip image and the four original info keys (xdiv, rules, mode, fn_gutter) must stay byte- and
value-identical to the pre-change code; only new keys (page, coord, body_regions) are appended.
Convention follows pipeline/reextract/test_assembler.py: plain asserts, dependency-free runner,
`python test_cv_footnote_presplit.py` prints "<n> passed, <m> failed" and exits nonzero on failure.
Cases needing a file that is absent print a SKIP line naming the file and do not count as a pass."""
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cv_footnote_presplit as ps

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_REL = "pipeline/scripts/cv_footnote_presplit.py"

IMG_DIR = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
PAGE100 = IMG_DIR / "page100_image1.png"
PAGE403 = IMG_DIR / "page403_image1.png"
PAGE546 = IMG_DIR / "page546_image1.png"

# Pinned sha256 of the NEW code's page100 strip (upscale=2), so the check still works once the
# git-HEAD baseline this was pinned against is no longer available as a comparison point.
PAGE100_STRIP_SHA256 = "96d5dd1a56d80cc0f01ce51e3f15012f92f968c04386ecb1cfae7124be104db4"
PAGE100_STRIP_SIZE = (3814, 1020)


class Skip(Exception):
    """Raised by a test to mean 'not assertable here', never counted as a pass or a fail."""


def _require(path):
    if not path.exists():
        raise Skip(f"missing fixture file: {path}")
    return path


# The pre-body_regions blob of cv_footnote_presplit.py. Pinned as a blob id, NOT read from
# HEAD: the moment the body_regions change is committed, HEAD *is* the new file and a
# HEAD-based baseline compares the new code against itself and passes for free. A blob id
# keeps this an actual before/after comparison for as long as the object survives in the
# repo; when it does not, the pinned sha256 below is the surviving guard.
BASELINE_BLOB = "a238cae0b20667952f2a3022bd7f18e5d32ddc61"


def _load_baseline_module():
    """git cat-file blob <pre-change blob> -> temp file OUTSIDE the repo -> import under a
    distinct name. Returns (module, None), or (None, reason) if the object is unavailable."""
    try:
        out = subprocess.run(
            ["git", "cat-file", "blob", BASELINE_BLOB],
            cwd=str(REPO_ROOT), capture_output=True, timeout=30,
        )
    except Exception as e:
        return None, f"git unavailable: {e}"
    if out.returncode != 0:
        return None, f"git cat-file blob {BASELINE_BLOB[:12]} failed: {out.stderr.decode(errors='replace')[:200]}"
    src = out.stdout.decode("utf-8")
    tmpdir = tempfile.mkdtemp(prefix="cvfp_baseline_")   # system temp dir, outside the repo
    baseline_path = os.path.join(tmpdir, "cv_footnote_presplit_baseline.py")
    with open(baseline_path, "w", encoding="utf-8") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location("cv_footnote_presplit_baseline", baseline_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, None


# ---------------------------------------------------------------------------
# Synthetic page builders (no private data — these run anywhere)
# ---------------------------------------------------------------------------

def _save_tmp_png(arr):
    im = Image.fromarray(arr, mode="L")
    fd, path = tempfile.mkstemp(suffix=".png", prefix="cvfp_synth_")
    os.close(fd)
    im.save(path)
    return path


def _make_two_column_page(W=1600, H=2000, rule_left_y_frac=0.70, rule_right_y_frac=0.75):
    """White page, a light gutter near centre (so find_vertical_divider locks onto it), a few dark
    text blobs in the body band of each column (kept < the hrule run-floor and above y=0.45H so they
    can't be mistaken for a rule), and two horizontal dark rules at DIFFERENT rows, one per column."""
    arr = np.full((H, W), 255, dtype=np.uint8)
    band0, band1 = int(H * 0.15), int(H * 0.40)          # strictly below the 0.45H rule-scan floor
    for y in range(band0, band1, 40):
        arr[y:y + 15, int(W * 0.10):int(W * 0.30)] = 0    # left column text blob (width < floor)
        arr[y:y + 15, int(W * 0.65):int(W * 0.85)] = 0    # right column text blob
    ry_l = int(H * rule_left_y_frac)
    ry_r = int(H * rule_right_y_frac)
    assert ry_l != ry_r, "test fixture bug: rule rows must differ"
    arr[ry_l:ry_l + 4, int(W * 0.02):int(W * 0.48)] = 0    # left column's own rule
    arr[ry_r:ry_r + 4, int(W * 0.52):int(W * 0.98)] = 0    # right column's own rule
    return _save_tmp_png(arr), W, H, ry_l, ry_r


def _make_blank_page(W=1600, H=2000):
    """Pure white page: no vertical gutter signal beyond an arbitrary argmin tie, and crucially NO
    horizontal dark run anywhere -> find_hrule returns None for both columns."""
    arr = np.full((H, W), 255, dtype=np.uint8)
    return _save_tmp_png(arr), W, H


# ---------------------------------------------------------------------------
# 1. Strip byte-identity
# ---------------------------------------------------------------------------

def test_strip_byte_identity_pinned_sha256():
    _require(PAGE100)
    strip, _info = ps.presplit(str(PAGE100), upscale=2)
    assert strip is not None
    assert tuple(strip.size) == PAGE100_STRIP_SIZE
    got = hashlib.sha256(strip.tobytes()).hexdigest()
    assert got == PAGE100_STRIP_SHA256, f"strip bytes changed: {got} != pinned {PAGE100_STRIP_SHA256}"


def test_strip_byte_identity_against_git_head_baseline():
    _require(PAGE100)
    baseline_mod, reason = _load_baseline_module()
    if baseline_mod is None:
        print(f"  SKIP (pinned pre-change baseline unavailable: {reason})")
        raise Skip(reason)
    base_strip, _base_info = baseline_mod.presplit(str(PAGE100), upscale=2)
    new_strip, _new_info = ps.presplit(str(PAGE100), upscale=2)
    assert base_strip is not None and new_strip is not None
    assert new_strip.size == base_strip.size
    assert new_strip.tobytes() == base_strip.tobytes()


# ---------------------------------------------------------------------------
# 2. Existing info keys unchanged (names, order, values) for a real page
# ---------------------------------------------------------------------------

def test_existing_info_keys_unchanged_for_real_page():
    _require(PAGE100)
    baseline_mod, reason = _load_baseline_module()
    if baseline_mod is None:
        print(f"  SKIP (pinned pre-change baseline unavailable: {reason})")
        raise Skip(reason)
    _base_strip, base_info = baseline_mod.presplit(str(PAGE100), upscale=2)
    _new_strip, new_info = ps.presplit(str(PAGE100), upscale=2)

    original_keys = ["xdiv", "rules", "mode", "fn_gutter"]
    assert list(base_info.keys()) == original_keys, f"baseline key set/order surprising: {list(base_info.keys())}"
    # the four original keys keep their exact names, order, AND values
    assert list(new_info.keys())[:4] == original_keys
    for k in original_keys:
        assert new_info[k] == base_info[k], f"{k} changed: {new_info[k]} != baseline {base_info[k]}"
    # new keys are appended after, in the specified order
    assert list(new_info.keys())[4:] == ["page", "coord", "body_regions"]


# ---------------------------------------------------------------------------
# 3 & 4. Synthetic two-column page: body_regions shape + the never-into-the-footnote invariant
# ---------------------------------------------------------------------------

def test_synthetic_two_column_body_regions():
    path, W, H, ry_l, ry_r = _make_two_column_page()
    try:
        strip, info = ps.presplit(path, upscale=1)
        assert "body_regions" in info
        regions = info["body_regions"]
        assert len(regions) == 2
        left, right = regions[0], regions[1]
        assert left["col"] == "left" and right["col"] == "right"

        for col, r in (("left", left), ("right", right)):
            x0, y0, x1, y1 = r["box"]
            for v in (x0, y0, x1, y1):
                assert isinstance(v, int), f"{col} box has non-int {v!r}"
            assert 0 <= x0 < x1 <= W
            assert 0 <= y0 < y1 <= H

        assert left["box"][2] == right["box"][0] == info["xdiv"]
        assert left["box"][0] == 0
        assert right["box"][2] == W

        assert left["rule_y"] == ry_l and left["y1_source"] == "rule"
        assert left["box"][3] == ry_l
        assert right["rule_y"] == ry_r and right["y1_source"] == "rule"
        assert right["box"][3] == ry_r
    finally:
        os.remove(path)


def test_body_region_never_reaches_into_footnote_strip():
    path, W, H, ry_l, ry_r = _make_two_column_page()
    try:
        _strip, info = ps.presplit(path, upscale=1)
        for r in info["body_regions"]:
            rule_y = r["rule_y"]
            y1 = r["box"][3]
            if rule_y is not None:
                assert y1 <= rule_y, f"{r['col']} body y1={y1} reaches past its rule at {rule_y}"
    finally:
        os.remove(path)


# ---------------------------------------------------------------------------
# 5. No-rule case: body_regions still present and well-formed on the (None, info) path
# ---------------------------------------------------------------------------

def test_no_rule_page_still_yields_body_regions():
    path, W, H = _make_blank_page()
    try:
        strip, info = ps.presplit(path, upscale=1)
        assert strip is None
        assert info["rules"] == [None, None]
        assert "body_regions" in info
        regions = info["body_regions"]
        assert len(regions) == 2
        for r in regions:
            assert r["rule_y"] is None
            assert r["y1_source"] == "page_bottom_no_rule"
            assert r["box"][3] == H
        assert regions[0]["col"] == "left" and regions[1]["col"] == "right"
        assert info["page"] == [W, H]
        assert info["coord"] == "native_px_x0y0x1y1_topleft_exclusive"
    finally:
        os.remove(path)


# ---------------------------------------------------------------------------
# 6. full_width mode: body_regions still two rule-derived entries
# ---------------------------------------------------------------------------

def test_full_width_page_still_yields_two_body_regions():
    if not PAGE546.exists():
        print(f"  SKIP (missing fixture file: {PAGE546})")
        raise Skip(f"missing fixture file: {PAGE546}")
    strip, info = ps.presplit(str(PAGE546), upscale=1)
    assert info["mode"] == "full_width"
    regions = info["body_regions"]
    assert len(regions) == 2
    assert regions[0]["col"] == "left" and regions[1]["col"] == "right"
    for r in regions:
        assert r["y1_source"] == "rule"
        assert r["rule_y"] is not None
        assert r["box"][3] == r["rule_y"]


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
