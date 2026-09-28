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


def test_a_bad_also_path_leaves_NO_destination_directory():
    # Born-test for the ordering bug (2026-09-27, Lane A): the old publish() copied the whole
    # run directory to dest FIRST, and only then walked --also -- so a bad --also path left a
    # half-published dest on disk. Against the unfixed code (copy loop before the --also loop)
    # this fails: dest exists and contains summary.json/q1.json by the time the SystemExit fires.
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}})
        out = os.path.join(root, "out")
        try:
            PR.publish(src, "r1", out, ["nope.log"], False)
        except SystemExit:
            pass
        else:
            raise AssertionError("a missing --also path must be refused")
        assert not os.path.isdir(os.path.join(out, "r1")), \
            "a half-published run directory was left on disk"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_good_also_path_really_does_publish_its_basename_into_the_manifest():
    # Companion assertion for the test above: without this, an implementation that raises on
    # ANY --also (even a valid one) before ever copying would also pass "no destination left
    # behind on a bad also" trivially, because it would never publish anything at all.
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


def test_plan_refusal_leaves_an_existing_published_destination_byte_for_byte_untouched():
    # A pre-existing dest that plan() refuses to touch (no --replace) must not be rmtree'd,
    # re-created, or partially overwritten by a later, unrelated call in the same process.
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}})
        out = os.path.join(root, "out")
        PR.publish(src, "r1", out, [], False)
        dest = os.path.join(out, "r1")
        sentinel = os.path.join(dest, "PUBLISHED.json")
        original_bytes = io.open(sentinel, "rb").read()
        try:
            PR.publish(src, "r1", out, [], False)
        except SystemExit as e:
            assert "already published" in str(e), str(e)
        else:
            raise AssertionError("a second publish without --replace must be refused")
        assert io.open(sentinel, "rb").read() == original_bytes, \
            "an existing published destination was modified by a refused publish"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_relative_also_resolves_against_the_current_working_directory():
    root = tempfile.mkdtemp()
    cwd_before = os.getcwd()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}})
        cwd_dir = tempfile.mkdtemp()
        io.open(os.path.join(cwd_dir, "here.log"), "w", encoding="utf-8").write("from cwd")
        os.chdir(cwd_dir)
        dest = PR.publish(src, "r1", os.path.join(root, "out"), ["here.log"], False)
        assert os.path.isfile(os.path.join(dest, "here.log"))
        assert io.open(os.path.join(dest, "here.log"), encoding="utf-8").read() == "from cwd"
    finally:
        os.chdir(cwd_before)
        shutil.rmtree(root, ignore_errors=True)


def test_relative_also_resolves_against_the_run_dirs_parent():
    # Back-compat: this is how the existing published runs were made, before the cwd fallback
    # was added. It must keep working even though it is no longer the ONLY base tried.
    root = tempfile.mkdtemp()
    cwd_before = os.getcwd()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}})
        io.open(os.path.join(root, "beside.log"), "w", encoding="utf-8").write("beside run dir")
        elsewhere = tempfile.mkdtemp()
        os.chdir(elsewhere)  # cwd has no beside.log; only the run dir's parent does
        dest = PR.publish(src, "r1", os.path.join(root, "out"), ["beside.log"], False)
        assert os.path.isfile(os.path.join(dest, "beside.log"))
    finally:
        os.chdir(cwd_before)
        shutil.rmtree(root, ignore_errors=True)


def test_ambiguous_relative_also_between_cwd_and_run_parent_is_refused():
    # Same basename, different bytes, under both candidate bases -> refuse rather than guess.
    root = tempfile.mkdtemp()
    cwd_before = os.getcwd()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}})
        io.open(os.path.join(root, "dup.log"), "w", encoding="utf-8").write("from run parent")
        cwd_dir = tempfile.mkdtemp()
        io.open(os.path.join(cwd_dir, "dup.log"), "w", encoding="utf-8").write("from cwd, different")
        os.chdir(cwd_dir)
        out = os.path.join(root, "out")
        try:
            PR.publish(src, "r1", out, ["dup.log"], False)
        except SystemExit as e:
            assert "ambiguous" in str(e), str(e)
        else:
            raise AssertionError("two different files at the same relative name must not silently pick one")
        assert not os.path.isdir(os.path.join(out, "r1")), "nothing should have been copied"
    finally:
        os.chdir(cwd_before)
        shutil.rmtree(root, ignore_errors=True)


def test_basename_collision_between_two_also_paths_is_refused():
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}})
        sub = os.path.join(root, "sub")
        os.makedirs(sub)
        io.open(os.path.join(root, "dup.log"), "w", encoding="utf-8").write("one")
        io.open(os.path.join(sub, "dup.log"), "w", encoding="utf-8").write("two")
        out = os.path.join(root, "out")
        also = [os.path.join(root, "dup.log"), os.path.join(sub, "dup.log")]
        try:
            PR.publish(src, "r1", out, also, False)
        except SystemExit as e:
            assert "collision" in str(e), str(e)
            assert "dup.log" in str(e), str(e)
        else:
            raise AssertionError("two --also files sharing a basename must not silently overwrite one another")
        assert not os.path.isdir(os.path.join(out, "r1")), "nothing should have been copied"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_basename_collision_between_also_and_a_run_dir_file_is_refused():
    root = tempfile.mkdtemp()
    try:
        # _run() writes q1.json into the run dir by default; collide an --also with it.
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}}, ("q1.json",))
        also_src = os.path.join(root, "elsewhere_q1.json")
        io.open(also_src, "w", encoding="utf-8").write('{"x": 99}')
        also_dir = os.path.join(root, "also_dir")
        os.makedirs(also_dir)
        colliding = os.path.join(also_dir, "q1.json")
        io.open(colliding, "w", encoding="utf-8").write('{"x": 99}')
        out = os.path.join(root, "out")
        try:
            PR.publish(src, "r1", out, [colliding], False)
        except SystemExit as e:
            assert "collision" in str(e), str(e)
            assert "q1.json" in str(e), str(e)
        else:
            raise AssertionError("an --also basename colliding with a run_dir file must be refused")
        assert not os.path.isdir(os.path.join(out, "r1")), "nothing should have been copied"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_summary_json_creates_no_destination_directory():
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", None, ("q1.json",))
        out = os.path.join(root, "out")
        try:
            PR.publish(src, "r1", out, [], False)
        except SystemExit:
            pass
        else:
            raise AssertionError("a run with no summary.json must be refused")
        assert not os.path.isdir(out), "no destination tree should exist at all"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_already_published_without_replace_is_refused_with_replace_it_succeeds():
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
            raise AssertionError("a second publish without --replace must be refused")
        dest = PR.publish(src, "r1", out, [], True)
        assert os.path.isfile(os.path.join(dest, "PUBLISHED.json"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_verify_mismatch_and_missing_do_not_share_a_label():
    # A mutated file and a deleted file are different failures with different remedies; a
    # verify() that lumped them into one bucket would hide which one happened.
    root = tempfile.mkdtemp()
    try:
        src = _run(root, "r1", {"integrity": {"git": CLEAN_GIT}}, ("q1.json", "report.md"))
        dest = PR.publish(src, "r1", os.path.join(root, "out"), [], False)
        io.open(os.path.join(dest, "q1.json"), "w", encoding="utf-8").write('{"x": 2}')
        os.unlink(os.path.join(dest, "report.md"))
        r = PR.verify(dest)
        assert [row[0] for row in r["mismatch"]] == ["q1.json"], r
        assert r["missing"] == ["report.md"], r
        assert "report.md" not in [row[0] for row in r["mismatch"]], r
        assert "q1.json" not in r["missing"], r
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
