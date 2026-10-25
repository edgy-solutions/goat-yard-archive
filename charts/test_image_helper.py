"""Born-tests for the `goat-yard-archive.image` chart helper.

    python charts/test_image_helper.py

The helper lets a deployment be pinned to an exact artefact: it emits
`repository@<digest>` when `image.digest` is set and `repository:<tag>`
otherwise. These tests exist because the no-digest path is the one every
existing deploy already rides -- adding a branch to it has to be proved inert
before the new branch is worth anything.

This suite shells out to `helm template`. If helm is not on PATH, or the chart's
dependencies have not been fetched, it exits UNRUN (status 2) rather than
reporting a pass: a check that cannot run has not passed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_CHART = os.path.join(_HERE, "goat-yard-archive")

API_REPO = "ghcr.io/edgy-solutions/goat-yard-archive/backend"
UI_REPO = "ghcr.io/edgy-solutions/goat-yard-archive/frontend"
DIGEST = "sha256:ac37c84fed147f96fb14c276a8fb51869d6b6d765257959e578bc6366d0c7d8e"
# What gya-test is pinned to as committed (release 0.3.3, smoked 2026-10-18).
PINNED_TEST_DIGEST = "sha256:2fce1e3467d5f53e4f0700cdd51530db86cc85c8ef7231f091c6e69509b11433"
# What gya-test is ACTUALLY serving for the ui, read 2026-10-25. This one is
# as-running rather than a smoked release artefact, and the pin says so; the
# test below is still the same check -- that it has not drifted back to a tag.
PINNED_TEST_UI_DIGEST = "sha256:f386254ee465b77ceee57b3f11ad8f1742e8f6d671e1fa71452aa819c1996da4"

VALUES_FILES = ["values.yaml", "values-test.yaml",
                "values-frontend.yaml", "values-backend.yaml"]

# The no-digest precondition, stated rather than borrowed. _render() renders a
# real environment file, and values-test.yaml now legitimately pins a digest
# (release 0.3.3). A test of the no-digest BRANCH must establish that branch
# itself: a check whose precondition comes from a deployable config file is not
# testing the helper, it is testing the config -- and it silently stopped
# testing anything the day that config changed.
NO_DIGEST = ["api.image.digest=", "ui.image.digest="]


def _render(values="values-test.yaml", sets=(), expect_ok=True):
    """Run `helm template` and return (rc, stdout, stderr)."""
    cmd = ["helm", "template", "rel", _CHART, "-f", os.path.join(_CHART, values)]
    for s in sets:
        cmd += ["--set", s]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if expect_ok and p.returncode != 0:
        raise AssertionError("helm template failed unexpectedly:\n%s" % p.stderr)
    return p.returncode, p.stdout, p.stderr


def _image_lines(out):
    return [l.strip() for l in out.splitlines() if l.strip().startswith("image:")]


def test_no_digest_renders_repository_colon_tag():
    _, out, _ = _render(sets=NO_DIGEST)
    assert ('image: "%s:latest"' % API_REPO) in out, _image_lines(out)


def test_ui_also_routes_through_the_helper():
    """Not just the backend: the frontend image is pinnable too."""
    _, out, _ = _render(sets=NO_DIGEST)
    assert any(l.startswith('image: "%s:' % UI_REPO) for l in _image_lines(out)), \
        _image_lines(out)


def test_digest_renders_repository_at_digest():
    _, out, _ = _render(sets=["api.image.digest=" + DIGEST])
    assert ('image: "%s@%s"' % (API_REPO, DIGEST)) in out, _image_lines(out)


def test_digest_does_not_leak_into_the_other_image():
    """Pinning the api must not pin the ui to the api's digest."""
    _, out, _ = _render(sets=["api.image.digest=" + DIGEST])
    ui_lines = [l for l in out.splitlines() if UI_REPO in l]
    assert ui_lines, "no ui image line rendered -- this check would pass on nothing"
    for line in ui_lines:
        assert DIGEST not in line, "ui image picked up the api digest: %s" % line


def test_digest_wins_over_tag():
    """A leftover tag must not be able to defeat an explicit pin."""
    _, out, _ = _render(sets=["api.image.digest=" + DIGEST,
                              "api.image.tag=NOT-THE-PINNED-ONE"])
    assert ('image: "%s@%s"' % (API_REPO, DIGEST)) in out
    assert "NOT-THE-PINNED-ONE" not in out


def test_malformed_digest_fails_loud():
    rc, _, err = _render(sets=["api.image.digest=ac37c84f"], expect_ok=False)
    assert rc != 0, "a digest with no sha256: prefix rendered anyway"
    assert "must be a full digest" in err, err


def test_missing_tag_and_digest_fails_loud():
    rc, _, err = _render(sets=NO_DIGEST + ["api.image.tag="], expect_ok=False)
    assert rc != 0, "an image with neither tag nor digest rendered anyway"
    assert "image.tag is required" in err, err


def test_missing_repository_fails_loud():
    rc, _, err = _render(sets=["api.image.repository="], expect_ok=False)
    assert rc != 0, "an image with no repository rendered anyway"
    assert "image.repository is required" in err, err


def test_every_committed_values_file_still_renders():
    """The inert half: all four shipped values files must render cleanly with
    no digest set, since that is what every current deploy does."""
    for v in VALUES_FILES:
        rc, out, err = _render(values=v, expect_ok=False)
        assert rc == 0, "%s no longer renders: %s" % (v, err)
        assert _image_lines(out), "%s rendered no image lines at all" % v


def test_no_rendered_image_reference_is_malformed():
    """Across every values file: each image line is repo:tag or repo@sha256:,
    never both separators and never a dangling one."""
    for v in VALUES_FILES:
        _, out, _ = _render(values=v)
        for line in _image_lines(out):
            ref = line.split("image:", 1)[1].strip().strip('"')
            assert not ref.endswith(":") and not ref.endswith("@"), (v, line)
            if "@" in ref:
                assert ref.split("@", 1)[1].startswith("sha256:"), (v, line)


def test_values_test_is_still_pinned_by_digest():
    """The gya-test pin is itself a check. values-test.yaml must render the
    smoked 0.3.3 artefact as repository@digest; if someone drops the digest the
    file goes back to floating on `:latest`, which is no longer a deploy target
    (ruling, Chris 2026-10-18), and that must fail here rather than at deploy."""
    _, out, _ = _render(values="values-test.yaml")
    pinned = [l for l in _image_lines(out) if l.startswith('image: "%s@' % API_REPO)]
    assert pinned, _image_lines(out)
    assert PINNED_TEST_DIGEST in pinned[0], pinned


def test_values_test_ui_is_still_pinned_by_digest():
    """Same check for the ui image, which was the half left floating. The
    digest here is as-running, not a smoked artefact -- but a recorded
    as-running digest still beats a tag that moves under the release, which
    is the whole reason `:latest` is no longer a deploy target."""
    _, out, _ = _render(values="values-test.yaml")
    pinned = [l for l in _image_lines(out) if l.startswith('image: "%s@' % UI_REPO)]
    assert pinned, _image_lines(out)
    assert PINNED_TEST_UI_DIGEST in pinned[0], pinned


if __name__ == "__main__":
    if shutil.which("helm") is None:
        print("UNRUN  helm is not on PATH -- these checks did not run")
        sys.exit(2)
    if not os.path.isdir(os.path.join(_CHART, "charts")):
        print("UNRUN  chart dependencies absent -- run `helm dependency build %s`"
              % _CHART)
        sys.exit(2)

    EXPECTED_TEST_COUNT = 12
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    if len(tests) != EXPECTED_TEST_COUNT:
        print("FAIL  expected %d tests, collected %d -- a test silently disappeared"
              % (EXPECTED_TEST_COUNT, len(tests)))
        sys.exit(1)

    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  ok    %s" % name)
        except KeyboardInterrupt:
            raise
        except BaseException:
            failed += 1
            print("  FAIL  %s" % name)
            traceback.print_exc()
    print("")
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
