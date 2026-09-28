"""Born-tests for publish_run. Offline; builds run directories on disk from literals.

    python evals/test_publish_run.py

What is under test is mostly the REFUSALS. A publisher that silently copies whatever it finds
turns a half-written run into something that looks like evidence, and a publisher that
overwrites a published run id turns two measurements into one.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_run as PR  # noqa: E402

CLEAN_GIT = {"at_start": {"head": "a" * 40, "dirty": False, "dirty_paths": 0},
             "at_end": {"head": "a" * 40, "dirty": False, "dirty_paths": 0},
             "changed_during_run": False, "provisional": False}


def _run(root, name, summary=None, extra_files=("q1.json",)):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    if summary is not None:
        io.open(os.path.join(d, "summary.json"), "w", encoding="utf-8").write(json.dumps(summary))
    for f in extra_files:
        io.open(os.path.join(d, f), "w", encoding="utf-8").write('{"x": 1}')
    return d


def test_publishes_files_and_records_a_sha_per_file():
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}}, ("q1.json", "report.md"))
        dest = PR.publish(src, "r1", os.path.join(root, "out"), [], False)
        m = json.load(io.open(os.path.join(dest, "PUBLISHED.json"), encoding="utf-8"))
        assert set(m["files"]) == {"summary.json", "q1.json", "report.md"}, m["files"]
        assert all(len(v) == 64 for v in m["files"].values()), m["files"]
        assert m["integrity_git"]["provisional"] is False, m["integrity_git"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_run_with_no_summary_is_refused():
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", None, ("q1.json",))
        try:
            PR.publish(src, "r1", os.path.join(root, "out"), [], False)
        except SystemExit as e:
            assert "no summary.json" in str(e), str(e)
        else:
            raise AssertionError("fragments of a run must not publish as evidence")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_republishing_a_run_id_is_refused_without_replace():
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}})
        out = os.path.join(root, "out")
        PR.publish(src, "r1", out, [], False)
        try:
            PR.publish(src, "r1", out, [], False)
        except SystemExit as e:
            assert "already published" in str(e), str(e)
        else:
            raise AssertionError("two measurements must not silently become one run id")
        PR.publish(src, "r1", out, [], True)  # explicit --replace is allowed
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_named_also_file_that_does_not_exist_is_an_error_not_a_skip():
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}})
        try:
            PR.publish(src, "r1", os.path.join(root, "out"), ["nope.log"], False)
        except SystemExit as e:
            assert "does not exist" in str(e), str(e)
        else:
            raise AssertionError("a named-and-missing file is an error")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_an_also_file_beside_the_run_dir_is_published():
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}})
        io.open(os.path.join(root, "r1.log"), "w", encoding="utf-8").write("log text")
        dest = PR.publish(src, "r1", os.path.join(root, "out"), ["r1.log"], False)
        assert os.path.isfile(os.path.join(dest, "r1.log"))
        m = json.load(io.open(os.path.join(dest, "PUBLISHED.json"), encoding="utf-8"))
        assert "r1.log" in m["files"], m["files"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_missing_integrity_block_is_UNKNOWN_and_never_clean():
    # The pre-b7d82dc runs. "No information" and "was clean" are different facts.
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"questions": 28})
        dest = PR.publish(src, "r1", os.path.join(root, "out"), [], False)
        m = json.load(io.open(os.path.join(dest, "PUBLISHED.json"), encoding="utf-8"))
        assert "unavailable" in m["integrity_git"], m["integrity_git"]
        assert "UNKNOWN" in m["integrity_git"]["unavailable"], m["integrity_git"]
        assert m["integrity_git"].get("provisional") is None, "absent must not read as not-provisional"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_provisional_run_publishes_and_says_so():
    # Publishing is not a certification. A dirty run is evidence of what happened; the manifest
    # carries the fact that it cannot be cited.
    root = tempfile.mkdtemp()
    try:
        dirty = json.loads(json.dumps(CLEAN_GIT))
        dirty["at_start"]["dirty"] = True
        dirty["at_start"]["dirty_paths"] = 3
        dirty["provisional"] = True
        src = _run(root, "r1", {"integrity": {"git": dirty}})
        dest = PR.publish(src, "r1", os.path.join(root, "out"), [], False)
        m = json.load(io.open(os.path.join(dest, "PUBLISHED.json"), encoding="utf-8"))
        assert m["integrity_git"]["provisional"] is True, m["integrity_git"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_verify_passes_on_an_untouched_published_run():
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}}, ("q1.json", "report.md"))
        dest = PR.publish(src, "r1", os.path.join(root, "out"), [], False)
        r = PR.verify(dest)
        assert r["verified"] is True and r["ok"] == r["checked"] == 3, r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_verify_can_actually_SEE_an_altered_byte():
    # The companion assertion. A verifier that always returns verified=True would pass the test
    # above, and that is exactly the failure that shipped: the first published pair's hashes did
    # not match the committed blobs (autocrlf=input), and nothing noticed until a hash was
    # compared by hand.
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}}, ("q1.json",))
        dest = PR.publish(src, "r1", os.path.join(root, "out"), [], False)
        io.open(os.path.join(dest, "q1.json"), "w", encoding="utf-8").write('{"x": 2}')
        r = PR.verify(dest)
        assert r["verified"] is False, r
        assert [row[0] for row in r["mismatch"]] == ["q1.json"], r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_verify_reports_a_deleted_file_as_MISSING_not_as_a_mismatch():
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}}, ("q1.json",))
        dest = PR.publish(src, "r1", os.path.join(root, "out"), [], False)
        os.unlink(os.path.join(dest, "q1.json"))
        r = PR.verify(dest)
        assert r["missing"] == ["q1.json"] and r["mismatch"] == [], r
        assert r["verified"] is False, r
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_verify_refuses_a_directory_with_no_manifest():
    root = tempfile.mkdtemp()
    try:
        d = os.path.join(root, "nope")
        os.makedirs(d)
        try:
            PR.verify(d)
        except SystemExit as e:
            assert "no PUBLISHED.json" in str(e), str(e)
        else:
            raise AssertionError("an unpublished directory must not verify")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print("")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
