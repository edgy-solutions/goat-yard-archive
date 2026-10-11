"""Born-test: the provider pin and the temperature are ON THE WIRE for the BAML answer path.

    python backend/test_answer_lm_pin_on_the_wire.py

No model call and no network. `baml` renders the HTTP request it *would* send via
`client.request.<Fn>(...)`, so the pin can be asserted on the actual request body rather than on
the code that is supposed to produce it. This is the difference the ADR-0009 work turned on: a
schema that validates says nothing about what went over the wire.

It also asserts the negative case -- with nothing pinned, no `provider` block appears -- because a
test that only checks the pinned body would pass against an implementation that hard-coded the pin
and could never be turned off.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# A syntactically valid placeholder: ClientRegistry wants an api_key, and nothing here sends a
# request, so a real key is neither needed nor wanted in a test.
os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-v1-testonly-not-a-real-key")

import backend.structured_answer as SA  # noqa: E402

CONTEXT = "[GENESIS_1_1_S00] In the beginning God created the heaven and the earth."


def _body(pin_env):
    """The rendered request body for GenerateGillAnswer with OPENROUTER_PROVIDER_ORDER=pin_env."""
    prev = os.environ.get("OPENROUTER_PROVIDER_ORDER")
    if pin_env is None:
        os.environ.pop("OPENROUTER_PROVIDER_ORDER", None)
    else:
        os.environ["OPENROUTER_PROVIDER_ORDER"] = pin_env
    try:
        client = SA.baml.with_options(client_registry=SA.answer_lm_registry())
        req = client.request.GenerateGillAnswer(
            context=CONTEXT, question="What does Gill say about the beginning?",
            available_books="Genesis")
        body = req.body.json()
        if not isinstance(body, dict):
            body = json.loads(body)
        return body, req
    finally:
        if prev is None:
            os.environ.pop("OPENROUTER_PROVIDER_ORDER", None)
        else:
            os.environ["OPENROUTER_PROVIDER_ORDER"] = prev


def test_pinned_request_carries_the_provider_block():
    body, _ = _body("streamlake")
    assert body.get("provider") == {"order": ["streamlake"], "allow_fallbacks": False}, body.get("provider")


def test_pinned_request_still_carries_model_and_temperature():
    # The registry override replaces the whole client, so the model and temperature from
    # gill_answer.baml have to be restated in it. If they were dropped, the call would still
    # succeed against some other default and the arm would be measuring an unnamed model.
    body, _ = _body("streamlake")
    assert body.get("model") == SA.ANSWER_LM_MODEL, body.get("model")
    assert body.get("temperature") == SA.ANSWER_LM_TEMPERATURE, body.get("temperature")
    assert body.get("temperature") == 0.0


def test_the_url_is_still_openrouter():
    _, req = _body("streamlake")
    assert "openrouter.ai" in str(req.url), req.url


def test_unpinned_request_has_NO_provider_block():
    # The companion assertion. An implementation that baked the pin into gill_answer.baml would
    # pass the test above and make "unpinned" unrepresentable -- and a run could then claim an
    # unpinned baseline it never had.
    body, _ = _body(None)
    assert "provider" not in body, body.get("provider")
    assert body.get("temperature") == 0.0, "the .baml client still sets temperature when unpinned"


def test_registry_is_None_when_nothing_is_pinned():
    prev = os.environ.pop("OPENROUTER_PROVIDER_ORDER", None)
    try:
        assert SA.answer_lm_registry() is None
    finally:
        if prev is not None:
            os.environ["OPENROUTER_PROVIDER_ORDER"] = prev


def test_the_prompt_actually_contains_the_context():
    # A request rendered from the wrong arguments would satisfy every assertion above while
    # measuring a call the system never makes.
    body, _ = _body("streamlake")
    blob = json.dumps(body)
    assert "GENESIS_1_1_S00" in blob, blob[:400]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS  " + name)
        except KeyboardInterrupt:
            raise
        # SystemExit is NOT an Exception, so `except Exception` let a test that reaches sys.exit
        # end the WHOLE run silently -- no summary line, which reads as a shorter suite. Witnessed
        # 2026-10-11 in evals/test_gate_paired.py (argparse exits 2 on an unrecognized flag).
        except BaseException:
            failed += 1
            print("  FAIL  " + name)
            traceback.print_exc()
    print("")
    print(str(len(tests) - failed) + "/" + str(len(tests)) + " passed")
    sys.exit(1 if failed else 0)
