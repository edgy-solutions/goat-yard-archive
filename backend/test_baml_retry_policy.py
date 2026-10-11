"""Born-tests for the BoundedTransport retry policy in baml_src/main.baml.

    python backend/test_baml_retry_policy.py

The policy is a deterministic property of a text file, so an assertion owns it
rather than a reviewer's memory. Two things it watches:

  * the BOUND. "retry" without a ceiling is the same defect under a new name,
    so the four numbers are pinned here, not just the policy's existence;
  * the GENERATE step. baml_client/ is committed and the runtime parses the
    INLINED copy of main.baml, not main.baml itself. Editing the source and
    forgetting `baml-cli generate` (AGENTS.md step 3) leaves a source file
    that says "retry" and a shipped client that does not retry, with nothing
    in the diff to say so. The inlined copy is checked for the same bound.

It asserts nothing about whether the bound is OBSERVED. In 0.3.2 it is not:
no attempt counter reaches stage_health, so a call that burned all four
attempts and then failed looks exactly like one that failed on its first try.
See the comment above the policy in main.baml.
"""
from __future__ import annotations

import ast
import io
import os
import re
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC_DIR = os.path.join(_ROOT, "baml_src")
_MAIN_BAML = os.path.join(_SRC_DIR, "main.baml")
_INLINED = os.path.join(_ROOT, "baml_client", "inlinedbaml.py")

# The bound, as one table. Every assertion below reads it from here, so the
# suite cannot drift from the value it claims to pin.
EXPECTED_POLICY = {
    "name": "BoundedTransport",
    "strategy": "exponential_backoff",
    "max_retries": "3",
    "delay_ms": "200",
    "multiplier": "2",
    "max_delay_ms": "2000",
}

assert os.path.exists(_MAIN_BAML), _MAIN_BAML
assert os.path.exists(_INLINED), _INLINED
_MAIN_TEXT = io.open(_MAIN_BAML, encoding="utf-8").read()


def _strip_comments(text):
    """Drop // comments. The policy's own rationale comment names every token
    this suite looks for, so a probe over the raw text could be satisfied by
    the explanation of the thing instead of the thing."""
    return "\n".join(line.split("//")[0] for line in text.splitlines())


def _blocks(text, kind):
    """{name: body} for every `<kind> [<..>] <name> .. {` block, brace-counted
    so that a nested `strategy { .. }` does not end the block early. The
    `[^{}]*` before the brace is for `function Foo(a: string) -> Bar {`, whose
    signature sits between the name and the body: a pattern that demanded the
    brace right after the name matched no function at all, and the liveness
    assertion in the caller is what said so."""
    found = {}
    pat = re.compile(r"^%s(?:<[^>]*>)?\s+([A-Za-z_][A-Za-z0-9_]*)\b[^{}]*\{" % kind, re.M)
    for m in pat.finditer(text):
        i, depth = m.end() - 1, 0
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        found[m.group(1)] = text[m.end():i]
    return found


def _policy_of(client_body):
    m = re.search(r"\bretry_policy\s+([A-Za-z_][A-Za-z0-9_]*)", client_body)
    return m.group(1) if m else None


def _inlined_main():
    """The copy of main.baml that the generated client actually ships."""
    text = io.open(_INLINED, encoding="utf-8").read()
    m = re.search(r'"main\.baml":\s*("(?:[^"\\]|\\.)*")', text)
    assert m, "no main.baml entry in baml_client/inlinedbaml.py"
    return ast.literal_eval(m.group(1))


def test_the_policy_is_DEFINED_with_the_exact_bound():
    pols = _blocks(_strip_comments(_MAIN_TEXT), "retry_policy")
    assert pols, "no retry_policy is defined in main.baml at all"
    body = pols.get(EXPECTED_POLICY["name"])
    assert body is not None, sorted(pols)
    for key in ("max_retries", "delay_ms", "multiplier", "max_delay_ms"):
        got = re.search(r"\b%s\s+(\S+)" % key, body)
        assert got and got.group(1) == EXPECTED_POLICY[key], (
            key, EXPECTED_POLICY[key], got and got.group(1))
    assert re.search(r"\btype\s+%s\b" % EXPECTED_POLICY["strategy"], body), body


def test_the_bound_is_FINITE_and_small_for_EVERY_policy_in_the_source():
    # The ceiling is the point. A later policy with no max_retries, or a large
    # one, is the unbounded-retry defect back under a new name, so this reads
    # every policy rather than the one named above.
    pols = _blocks(_strip_comments(_MAIN_TEXT), "retry_policy")
    assert pols, "liveness: this probe matched no policies, so it asserted nothing"
    for name, body in sorted(pols.items()):
        m = re.search(r"\bmax_retries\s+(\d+)", body)
        assert m, "%s declares no max_retries, so its retries are unbounded" % name
        assert 1 <= int(m.group(1)) <= 5, (name, m.group(1))


def test_LOCAL_ROUTER_carries_the_policy_INSIDE_its_own_block():
    # `"BoundedTransport" in text` would pass on the definition alone. The
    # claim is that the client the backend calls through uses it.
    clients = _blocks(_strip_comments(_MAIN_TEXT), "client")
    assert "LocalRouter" in clients, sorted(clients)
    assert _policy_of(clients["LocalRouter"]) == EXPECTED_POLICY["name"], (
        _policy_of(clients["LocalRouter"]))


def test_EVERY_retry_policy_a_client_NAMES_is_actually_defined():
    stripped = _strip_comments(_MAIN_TEXT)
    defined = set(_blocks(stripped, "retry_policy"))
    named = {c: _policy_of(b) for c, b in _blocks(stripped, "client").items()
             if _policy_of(b)}
    assert named, "liveness: no client names a retry_policy"
    dangling = {c: p for c, p in named.items() if p not in defined}
    assert not dangling, (dangling, sorted(defined))


def test_the_BACKENDs_OWN_baml_functions_resolve_to_a_RETRYING_client():
    # Derived, not a literal list: find the functions backend/*.py calls as
    # b.<Name>(), look up each one's `client`, require that client to carry a
    # defined policy. A function moved to a client with no policy fails here
    # even though nothing in main.baml changed.
    called = set()
    for fn in sorted(f for f in os.listdir(_HERE)
                     if f.endswith(".py") and not f.startswith("test_")):
        text = io.open(os.path.join(_HERE, fn), encoding="utf-8").read()
        called.update(re.findall(r"\bb\.([A-Z][A-Za-z0-9_]*)\s*\(", text))
    assert called, "liveness: found no b.<Function>() calls in backend/"

    src = ""
    for f in sorted(os.listdir(_SRC_DIR)):
        if f.endswith(".baml"):
            src += io.open(os.path.join(_SRC_DIR, f), encoding="utf-8").read() + "\n"
    stripped = _strip_comments(src)
    policies = set(_blocks(stripped, "retry_policy"))
    retrying = {c for c, b in _blocks(stripped, "client").items()
                if _policy_of(b) in policies}
    funcs = _blocks(stripped, "function")

    resolved, unretried = {}, {}
    for name in sorted(called):
        body = funcs.get(name)
        if body is None:
            continue  # not a baml_src function (a dspy helper, a stub): not this claim
        m = re.search(r"\bclient\s+([A-Za-z_][A-Za-z0-9_]*)", body)
        assert m, "baml function %s binds no client" % name
        resolved[name] = m.group(1)
        if m.group(1) not in retrying:
            unretried[name] = m.group(1)
    assert resolved, ("liveness: none of the called functions were found in baml_src, "
                      "so this asserted nothing", sorted(called))
    assert not unretried, (
        "these functions the backend calls route through a client with no bounded "
        "retry policy: %r" % unretried)


def test_the_GENERATED_client_was_REGENERATED_after_the_source_edit():
    # The runtime parses the inlined copy, so this is the assertion that
    # actually speaks about shipped behaviour.
    inlined = _strip_comments(_inlined_main())
    body = _blocks(inlined, "retry_policy").get(EXPECTED_POLICY["name"])
    assert body is not None, (
        "baml_client/inlinedbaml.py has no %s: main.baml was edited without running "
        "`baml-cli generate` (AGENTS.md step 3), so the shipped client does not retry"
        % EXPECTED_POLICY["name"])
    m = re.search(r"\bmax_retries\s+(\d+)", body)
    assert m and m.group(1) == EXPECTED_POLICY["max_retries"], m and m.group(1)
    clients = _blocks(inlined, "client")
    assert _policy_of(clients.get("LocalRouter", "")) == EXPECTED_POLICY["name"], (
        "the inlined LocalRouter does not carry the policy")


if __name__ == "__main__":
    EXPECTED_TEST_COUNT = 6
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
        # SystemExit is NOT an Exception: `except Exception` lets a test that
        # reaches sys.exit end the whole run with no summary line, which reads
        # as a shorter suite (witnessed 2026-10-11 in evals/test_gate_paired.py).
        except BaseException:
            failed += 1
            print("  FAIL  %s" % name)
            traceback.print_exc()
    print("")
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
