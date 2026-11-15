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

try:
    import yaml
except ImportError:  # named as a precondition in __main__, never skipped
    yaml = None

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


def _flag_lines(out):
    """Every rendered GILL_STRUCTURED_ANSWER line, whichever ConfigMap it is in.

    Deliberately not scoped to one ConfigMap: if a second object ever starts
    rendering this key, the callers below fail loudly instead of asserting
    about the first one they happen to find."""
    return [l.strip() for l in out.splitlines()
            if l.strip().startswith("GILL_STRUCTURED_ANSWER:")]


def test_values_frontend_is_still_pinned_by_digest():
    """Production carries a pin too, and until now nothing checked it.

    values-test.yaml had pin assertions from the day it was pinned; prod did
    not, so the prod pin added for 0.3.3 (ruling, Chris 2026-11-01) could have
    been dropped back to a floating tag with a green suite. A guard on one
    environment and not the other is the asymmetry, not the coverage."""
    _, out, _ = _render(values="values-frontend.yaml")
    pinned = [l for l in _image_lines(out) if l.startswith('image: "%s@' % API_REPO)]
    assert pinned, _image_lines(out)
    assert PINNED_TEST_DIGEST in pinned[0], pinned


def test_values_frontend_ui_is_still_pinned_by_digest():
    """Same guard for the prod ui image. This digest's build provenance is
    unverified (it is recorded as-running from gya-test), which is a reason to
    label it honestly in the values file -- not a reason to leave it floating
    on a tag that can be re-pointed under the release."""
    _, out, _ = _render(values="values-frontend.yaml")
    pinned = [l for l in _image_lines(out) if l.startswith('image: "%s@' % UI_REPO)]
    assert pinned, _image_lines(out)
    assert PINNED_TEST_UI_DIGEST in pinned[0], pinned


def test_prod_ships_the_pairing_the_gate_actually_scored():
    """Prod and gya-test must render the SAME two digests.

    Ruling 2026-11-01 item 2 ships "the gya-test pairing" -- the evidence for
    the flag flip is a gate run against that exact pair of images. Bumping one
    side and not the other would put prod on a pairing no gate has scored while
    every other check in this file still passed, because each of those checks
    only ever looks at one file. The claim being guarded is the correspondence,
    so it needs its own assertion."""
    _, prod, _ = _render(values="values-frontend.yaml")
    _, test, _ = _render(values="values-test.yaml")
    for repo in (API_REPO, UI_REPO):
        p = [l for l in _image_lines(prod) if l.startswith('image: "%s@' % repo)]
        t = [l for l in _image_lines(test) if l.startswith('image: "%s@' % repo)]
        assert p and t, (repo, p, t)
        assert p[0] == t[0], (repo, "prod=%s test=%s" % (p[0], t[0]))


def test_values_frontend_ships_the_flag_on():
    """The flip itself, asserted on the RENDER rather than on the values file.

    A file-scoped read cannot see the merge: values.yaml defaults this key to
    "0" and values-frontend.yaml overlays it, so grepping either file alone
    answers a different question than "what does prod deploy". Only the render
    knows. (Written after predicting this key would be ABSENT from the
    before-render and finding it already there at "0" -- the miss that
    motivates asserting here.)"""
    _, out, _ = _render(values="values-frontend.yaml")
    flags = _flag_lines(out)
    assert flags == ['GILL_STRUCTURED_ANSWER: "1"'], flags


def test_values_yaml_default_stays_off():
    """The chart DEFAULT stays "0": a fresh install without the prod overlay
    must not silently inherit the flip. Prod is on because values-frontend.yaml
    says so, not because the default moved under everyone."""
    _, out, _ = _render(values="values.yaml")
    flags = _flag_lines(out)
    assert flags == ['GILL_STRUCTURED_ANSWER: "0"'], flags



# ---- the minio deploy shape (ruling 13 item 5) --------------------------
#
# 529484f and a674cd2 carried three fixes into prod's values-frontend.yaml for
# 0.3.2, and release-0.3.3 was branched without them. The 2026-11-15 drift gate
# caught ONE of the three -- requests.memory 4Gi live against 16Gi rendered --
# and the object count caught a second as 19 rendered against 18. It could not
# see the third at all: `strategy` is not among drift_hash.py's compared keys,
# so a RollingUpdate regression on a one-replica ReadWriteOnce volume would have
# reached the upgrade and hung it with no gate line anywhere. These checks sit
# at the earliest point their inputs exist, which is the render, not the cluster.

MINIO_MEMORY = "4Gi"          # subchart default is 16Gi; worker5 cannot fit it
MINIO_STRATEGY = "Recreate"   # one replica on a RWO local-path volume


def _docs(out):
    return [d for d in yaml.safe_load_all(out) if isinstance(d, dict)]


def _kinds(docs):
    return sorted("%s/%s" % (d.get("kind"), d.get("metadata", {}).get("name"))
                  for d in docs)


def _minio_deployment(docs):
    """The minio Deployment, or an AssertionError naming its absence.

    A guard whose subject did not render would pass on nothing, so the absence
    is a failure of the guard rather than a vacuous success.
    """
    found = [d for d in docs
             if d.get("kind") == "Deployment"
             and d.get("metadata", {}).get("name", "").endswith("-minio")]
    assert len(found) == 1, (
        "expected exactly one minio Deployment in the render, found %d -- these "
        "guards assert a property OF that object and cannot pass without it"
        % len(found))
    return found[0]


def _minio_container(dep):
    cs = dep["spec"]["template"]["spec"]["containers"]
    found = [c for c in cs if c.get("name", "").endswith("minio")]
    assert len(found) == 1, [c.get("name") for c in cs]
    return found[0]


def test_values_frontend_minio_requests_4gi():
    _, out, _ = _render(values="values-frontend.yaml")
    c = _minio_container(_minio_deployment(_docs(out)))
    got = c.get("resources", {}).get("requests", {}).get("memory")
    assert got == MINIO_MEMORY, (
        "minio requests.memory rendered %r, expected %r. The subchart default is "
        "16Gi and k3s-worker5 has 20968Mi allocatable against 10016Mi of "
        "requests, so 16Gi leaves the pod Pending on Insufficient memory -- the "
        "pod is pinned to that node by the local-path PV, not by the dmz label."
        % (got, MINIO_MEMORY))


def test_values_frontend_minio_strategy_is_recreate():
    _, out, _ = _render(values="values-frontend.yaml")
    got = _minio_deployment(_docs(out))["spec"].get("strategy", {}).get("type")
    assert got == MINIO_STRATEGY, (
        "minio strategy.type rendered %r, expected %r. RollingUpdate with "
        "maxUnavailable 0 asks a second pod to go Ready before the first is "
        "removed, which one replica on a 50Gi ReadWriteOnce local-path volume "
        "cannot do. THE DRIFT GATE CANNOT SEE THIS KEY: `strategy` is not in "
        "drift_hash.py's compared set, so this check is the only thing between a "
        "branch that lacks the override and an upgrade that hangs."
        % (got, MINIO_STRATEGY))


def test_values_frontend_renders_no_minio_hook_job():
    _, out, _ = _render(values="values-frontend.yaml")
    jobs = [d for d in _docs(out) if d.get("kind") == "Job"]
    assert jobs == [], (
        "the minio post-install/post-upgrade hook job rendered: %s. It needs "
        "minio.buckets AND minio.users overridden with EMPTY LISTS -- the parent "
        "values.yaml sets buckets and the subchart's own values.yaml ships a "
        "truthy users default, so omitting either leaves the job in the render. "
        "That job is mc-image ImagePullBackOff on prod and it failed the 0.3.2 "
        "upgrade at revision 31."
        % [d.get("metadata", {}).get("name") for d in jobs])


def test_each_minio_guard_can_fail():
    """The mutation control: put the three subchart defaults back and require
    each assertion above to fire. A guard proved only by a green suite is not
    proved -- the suite would be just as green with all three deleted."""
    _, out, _ = _render(values="values-frontend.yaml", sets=(
        "minio.resources.requests.memory=16Gi",
        "minio.deploymentUpdate.type=RollingUpdate",
        "minio.users[0].accessKey=console",
        "minio.users[0].secretKey=console123",
        "minio.users[0].policy=consoleAdmin",
    ))
    docs = _docs(out)
    dep = _minio_deployment(docs)
    got_mem = _minio_container(dep).get("resources", {}).get("requests", {}).get("memory")
    assert got_mem == "16Gi", (
        "control did not restore the 16Gi default (got %r), so the memory guard "
        "is not shown to read the place that moves" % (got_mem,))
    got_strat = dep["spec"].get("strategy", {}).get("type")
    assert got_strat == "RollingUpdate", (
        "control did not restore RollingUpdate (got %r), so the strategy guard "
        "is not shown to read the place that moves" % (got_strat,))
    jobs = [d for d in docs if d.get("kind") == "Job"]
    assert len(jobs) == 1, (
        "control did not produce the hook job (%d found), so the no-Job guard is "
        "not shown to be able to fail" % len(jobs))


def test_values_frontend_renders_the_expected_object_set():
    """A release-branch pin on WHICH objects render, not on how many.

    The 2026-11-15 gate read 19 rendered objects against 0.3.2's 18, and the one
    extra was the hook job. A bare count would have said a number moved; this
    says which object arrived. It is a deliberate pin: a legitimate new object
    updates this list in the same commit that adds it.
    """
    _, out, _ = _render(values="values-frontend.yaml")
    expected = sorted([
        "ConfigMap/gya-frontend-config",
        "ConfigMap/gya-frontend-minio",
        "ConfigMap/litellm-config",
        "Deployment/gya-frontend-api",
        "Deployment/gya-frontend-cloudflared",
        "Deployment/gya-frontend-minio",
        "Deployment/gya-frontend-ui",
        "Deployment/litellm",
        "Ingress/gya-frontend",
        "PersistentVolumeClaim/gya-frontend-minio",
        "Secret/gya-frontend-minio",
        "Secret/gya-frontend-secrets",
        "Service/gya-frontend-api",
        "Service/gya-frontend-minio",
        "Service/gya-frontend-minio-console",
        "Service/gya-frontend-ui",
        "Service/litellm-service",
        "ServiceAccount/minio-sa",
    ])
    got = _kinds(_docs(out))
    assert got == expected, (
        "rendered object set moved.\n  only rendered: %s\n  only expected: %s"
        % (sorted(set(got) - set(expected)), sorted(set(expected) - set(got))))


if __name__ == "__main__":
    if shutil.which("helm") is None:
        print("UNRUN  helm is not on PATH -- these checks did not run")
        sys.exit(2)
    if not os.path.isdir(os.path.join(_CHART, "charts")):
        print("UNRUN  chart dependencies absent -- run `helm dependency build %s`"
              % _CHART)
        sys.exit(2)
    if yaml is None:
        print("UNRUN  PyYAML absent -- the minio shape checks parse the render and did not run")
        sys.exit(2)

    EXPECTED_TEST_COUNT = 22
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
