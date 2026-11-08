"""Born test: KJV USFM verse counts vs Golden Chain versification (lock 545b69e6)."""
import hashlib
import os
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from book_codes import USFM_TO_OSIS, UsfmCountError, count_usfm_dir, count_usfm_text  # noqa: E402

GC_VERSIFICATION_COMMIT = "dba4257359a0e3ca19e3b3dea088ea9dbeb29461"
GC_VERSIFICATION_PATH = "goldenchain/versification.py"
GC_VERSIFICATION_SHA256 = "3ee4533405fcd84f950b8a886acd88a6bca4fa4cfa59bcf301fef712724a4b4a"
GC_PIN_STATUS = "ratified"  # ratified by Chris on A2's three-way agreement, 2026-11-08 (lock 545b69e6 addendum)
GOLDEN_CHAIN_REPO = os.environ.get("GOLDEN_CHAIN_REPO", "C:/Users/cnogr/git/golden-chain")
KJV_USFM_DIR = os.environ.get("GOATYARD_KJV_USFM_DIR", "C:/Users/cnogr/git/dr-voluminous/bibles/eng-kjv2006_usfm")


def load_pinned_versification(repo, commit, path, sha256):
    if not Path(repo).is_dir():
        raise AssertionError(f"golden-chain repo missing: {repo}")
    r = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True)
    if r.returncode != 0:
        raise AssertionError(f"git show {commit}:{path} failed: {r.stderr.decode(errors='replace')}")
    got = hashlib.sha256(r.stdout).hexdigest()
    if got != sha256:
        raise AssertionError(f"versification sha256 mismatch: pinned {sha256} actual {got}")
    mod = types.ModuleType("gc_versification")
    exec(compile(r.stdout.decode("utf-8"), f"{commit}:{path}", "exec"), mod.__dict__)
    return mod


def _V():
    return load_pinned_versification(GOLDEN_CHAIN_REPO, GC_VERSIFICATION_COMMIT,
                                     GC_VERSIFICATION_PATH, GC_VERSIFICATION_SHA256)


def _counts():
    if not Path(KJV_USFM_DIR).is_dir():
        raise AssertionError(f"KJV USFM dir missing: {KJV_USFM_DIR}")
    return count_usfm_dir(KJV_USFM_DIR)


def test_table_is_a_66_entry_bijection_onto_versification_books():
    V = _V()
    assert len(USFM_TO_OSIS) == 66, len(USFM_TO_OSIS)
    assert len(set(USFM_TO_OSIS.values())) == 66
    assert tuple(USFM_TO_OSIS.values()) == tuple(V.BOOKS), "order/values differ from V.BOOKS"


def test_every_usfm_id_is_mapped_and_files_are_one_per_book():
    c = _counts()
    ids, mapped = set(c), set(USFM_TO_OSIS)
    assert len(c) == 66 and ids == mapped, (
        f"{len(c)} ids; extra in files: {sorted(ids - mapped)}; missing from files: {sorted(mapped - ids)}")


def test_per_book_chapter_and_verse_totals_equal():
    V, c = _V(), _counts()
    bad = []
    for usfm, osis in USFM_TO_OSIS.items():
        u = c[usfm]
        g = V.CHAPTERS[osis]
        if len(u) != len(g) or sum(u) != sum(g):
            bad.append(f"{usfm}({osis}): usfm chapters {len(u)} verses {sum(u)} vs gc chapters {len(g)} verses {sum(g)}")
    assert not bad, f"{len(bad)} book mismatches:\n" + "\n".join(bad)


def test_totals_66_1189_31102_both_sides():
    V, c = _V(), _counts()
    u = (len(c), sum(len(v) for v in c.values()), sum(sum(v) for v in c.values()))
    g = (len(V.CHAPTERS), sum(len(v) for v in V.CHAPTERS.values()), sum(sum(v) for v in V.CHAPTERS.values()))
    assert u == (66, 1189, 31102) and g == (66, 1189, 31102), f"usfm {u} gc {g} expected (66, 1189, 31102)"


def test_per_chapter_counts_descriptive():
    V, c = _V(), _counts()
    mism, n = [], 0
    for usfm, osis in USFM_TO_OSIS.items():
        u, g = c[usfm], V.CHAPTERS[osis]
        if len(u) != len(g):
            continue
        for i, (a, b) in enumerate(zip(u, g), 1):
            n += 1
            if a != b:
                mism.append((usfm, i, a, b))
    print(f"    per-chapter: compared {n} chapters, {len(mism)} mismatches")
    for m in mism:
        print(f"      {m[0]} {m[1]}: usfm {m[2]} gc {m[3]}")
    assert n == 1189, n


def test_pin_refuses_wrong_sha256():
    try:
        load_pinned_versification(GOLDEN_CHAIN_REPO, GC_VERSIFICATION_COMMIT, GC_VERSIFICATION_PATH, "0" * 64)
    except AssertionError:
        return
    raise AssertionError("wrong sha256 was accepted")


def test_pin_status_is_recorded():
    assert GC_PIN_STATUS in {"candidate_unratified", "ratified"}, GC_PIN_STATUS


def _raises(text):
    try:
        count_usfm_text(text, "synthetic")
    except UsfmCountError:
        return
    raise AssertionError(f"no UsfmCountError for {text!r}")


def test_verse_gap_raises():
    _raises("\\id GEN\n\\c 1\n\\v 1 a \\v 3 b")


def test_duplicate_verse_raises():
    _raises("\\id GEN\n\\c 1\n\\v 1 a \\v 1 b")


def test_bridge_raises():
    _raises("\\id GEN\n\\c 1\n\\v 1 a \\v 2 b \\v 3-4 c")


def test_missing_id_raises():
    _raises("\\c 1\n\\v 1 a")


def test_chapter_gap_raises():
    _raises("\\id GEN\n\\c 1\n\\v 1 a\n\\c 3\n\\v 1 b")


def test_positive_two_chapters():
    t = "\\id RUT\n\\c 1\n\\p\n\\v 1 a \\v 2 b\n\\c 2\n\\v 1 c \\v 2 d \\v 3 e\n"
    assert count_usfm_text(t) == ("RUT", (2, 3))


def test_va_vp_cl_not_counted():
    t = "\\id RUT\n\\c 1\n\\cl Chapter 1\n\\v 1 a \\va 2 \\v 2 b \\vp 2 \\ca 5\\ca* \\cp 9\n"
    assert count_usfm_text(t) == ("RUT", (2,))


EXPECTED_TESTS = 14


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed (EXPECTED {EXPECTED_TESTS})")
    if p + f != EXPECTED_TESTS:
        print(f"FAIL: ran {p + f} tests, expected {EXPECTED_TESTS}"); f += 1
    raise SystemExit(1 if f else 0)
