"""Born-tests for the per-call answer-LM record. Offline: no model call, no server, no BAML.

    python backend/test_answer_lm_record.py

Every extractor here is tested in BOTH directions, because each field has a "we did not look"
state and a "we looked and it was wrong" state, and a record that cannot tell them apart is not
evidence. The tests that matter most are the companion assertions:

  * the extractor can actually FIND a provider that IS there (a version that always returned None
    would pass every "unavailable" test below),
  * pin_honored can actually return False when a pin IS violated (a version that always returned
    None would pass every unknowable-case test below),
  * temperature 0.0 is not read as absent (0.0 is falsy; `or` instead of a sentinel default is the
    bug this guards).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer_lm_record as R  # noqa: E402

PIN = {"order": ["streamlake"], "allow_fallbacks": False}


class _Body:
    def __init__(self, v):
        self._v = v

    def json(self):
        return self._v


class _Part:
    def __init__(self, body):
        self.body = body


class _Call:
    def __init__(self, client_name, req, resp):
        self.client_name = client_name
        self.http_request = _Part(req)
        self.http_response = _Part(resp) if resp is not None else None


class _Resp:
    """Stands in for a litellm ModelResponse: attributes plus _hidden_params."""

    def __init__(self, provider=None, model=None, optional_params=None, dump=None):
        if provider is not None:
            self.provider = provider
        self.model = model
        self._hidden_params = {"optional_params": optional_params} if optional_params is not None else {}
        self._dump = dump

    def model_dump(self):
        if self._dump is None:
            raise AssertionError("model_dump should not have been reached")
        return self._dump


# --- as_dict ------------------------------------------------------------------------

def test_as_dict_unwraps_all_three_shapes():
    assert R.as_dict({"a": 1}) == {"a": 1}
    assert R.as_dict(_Body({"a": 1})) == {"a": 1}
    assert R.as_dict('{"a": 1}') == {"a": 1}
    assert R.as_dict(b'{"a": 1}') == {"a": 1}


def test_as_dict_returns_None_rather_than_raising():
    assert R.as_dict(None) is None
    assert R.as_dict("not json") is None
    assert R.as_dict("[1, 2]") is None, "a JSON array is not a body dict"
    assert R.as_dict(object()) is None


# --- pin_honored: three states --------------------------------------------------------

def test_pin_honored_is_case_insensitive():
    # The pin says 'streamlake'; OpenRouter answers 'StreamLake'. A case-sensitive compare
    # reports every honored pin as a violation.
    assert R.pin_honored(PIN, "StreamLake") is True


def test_pin_honored_can_actually_SEE_a_violation():
    # The companion assertion. An implementation that returned None for everything would pass
    # every unknowable-case test below and never report a wrong provider.
    assert R.pin_honored(PIN, "DeepInfra") is False


def test_pin_honored_is_None_when_unknowable_not_False():
    assert R.pin_honored(None, "DeepInfra") is None, "an unpinned call cannot violate a pin"
    assert R.pin_honored(PIN, None) is None, "an unread provider has not been checked"
    assert R.pin_honored({"allow_fallbacks": False}, "StreamLake") is None, "no order = no claim"


# --- the BAML path --------------------------------------------------------------------

def _baml_call(temperature=0.0, provider_in_req=PIN, served="StreamLake"):
    req = {"model": "deepseek/deepseek-chat"}
    if temperature is not None:
        req["temperature"] = temperature
    if provider_in_req is not None:
        req["provider"] = provider_in_req
    resp = {"model": "deepseek/deepseek-chat", "provider": served}
    if served is None:
        resp.pop("provider")
    return _Call("GillAnswerLM", _Body(req), _Body(resp))


def test_baml_record_reads_every_field_off_the_wire():
    r = R.record_from_baml_call(_baml_call(), PIN)
    assert r["path"] == "baml"
    assert r["client"] == "GillAnswerLM"
    assert r["model_requested"] == "deepseek/deepseek-chat"
    assert r["model_returned"] == "deepseek/deepseek-chat"
    assert r["temperature_on_the_wire"] == 0.0
    assert r["provider_pin"] == PIN
    # The companion assertion: the provider IS findable. Everything else about this record
    # could be right while this silently stayed None.
    assert r["provider_served"] == "StreamLake", r
    assert r["provider_served_source"] == "openrouter_response_body"
    assert r["pin_honored"] is True, r


def test_baml_record_reports_a_violated_pin():
    r = R.record_from_baml_call(_baml_call(served="DeepInfra"), PIN)
    assert r["provider_served"] == "DeepInfra"
    assert r["pin_honored"] is False, r


def test_baml_temperature_zero_is_not_read_as_absent():
    # 0.0 is falsy. `req.get("temperature") or sentinel` would report the pinned arm as unset,
    # which is exactly the asymmetry this record exists to make visible.
    r = R.record_from_baml_call(_baml_call(temperature=0.0), PIN)
    assert r["temperature_on_the_wire"] == 0.0
    assert r["temperature_on_the_wire"] is not None


def test_baml_absent_temperature_is_distinct_from_zero():
    r = R.record_from_baml_call(_baml_call(temperature=None), PIN)
    assert r["temperature_on_the_wire"] == "<absent from request body>", r


def test_baml_no_call_at_all_says_why_and_claims_nothing():
    r = R.record_from_baml_call(None, PIN)
    assert r["provider_served"] is None
    assert r["provider_served_source"] == "unavailable:no-llm-call-recorded"
    assert r["pin_honored"] is None, "no call is not a violated pin"
    assert r["provider_pin"] == PIN, "the pin we asked for is still a fact worth recording"


def test_baml_response_without_a_provider_field_names_that():
    r = R.record_from_baml_call(_baml_call(served=None), PIN)
    assert r["provider_served"] is None
    assert r["provider_served_source"] == "unavailable:response-body-has-no-provider-field"
    assert r["pin_honored"] is None


def test_baml_missing_response_body_names_that():
    r = R.record_from_baml_call(_Call("GillAnswerLM", _Body({"model": "m"}), None), PIN)
    assert r["provider_served_source"] == "unavailable:no-response-body-on-the-call", r
    assert r["pin_honored"] is None


def test_baml_prefers_the_pin_on_the_wire_over_the_one_we_intended():
    # If the request body carries a different pin than provider_pin() reports, the wire wins:
    # the record is of what happened, not of what was configured.
    other = {"order": ["deepinfra"], "allow_fallbacks": False}
    r = R.record_from_baml_call(_baml_call(provider_in_req=other, served="DeepInfra"), PIN)
    assert r["provider_pin"] == other, r
    assert r["pin_honored"] is True, "honored against the pin actually sent"


# --- the DSPy path --------------------------------------------------------------------

def test_dspy_record_reads_temperature_from_optional_params():
    # NOT from entry["kwargs"], where the key is absent either way. A probe that read kwargs
    # printed "<omitted>" for an arm that had sent 0.0.
    entry = {"model": "openai/deepseek/deepseek-chat",
             "kwargs": {},
             "response": _Resp(provider="StreamLake", model="deepseek/deepseek-chat",
                               optional_params={"temperature": 0.0,
                                                "extra_body": {"provider": PIN}})}
    r = R.record_from_dspy_history(entry, PIN)
    assert r["path"] == "dspy" and r["client"] == "dspy.LM"
    assert r["model_requested"] == "openai/deepseek/deepseek-chat"
    assert r["temperature_on_the_wire"] == 0.0, r
    assert r["provider_pin"] == PIN
    assert r["provider_served"] == "StreamLake", r
    assert r["provider_served_source"] == "dspy_response_attribute"
    assert r["pin_honored"] is True


def test_dspy_unset_temperature_is_recorded_as_absent_not_as_a_number():
    # This is the live OFF path today: dspy.LM sets temperature None, litellm omits the field,
    # and the provider default applies. The record must say so rather than guess 0 or 1.
    entry = {"model": "openai/deepseek/deepseek-chat",
             "response": _Resp(provider="StreamLake", model="m", optional_params={"max_tokens": 4000})}
    r = R.record_from_dspy_history(entry, PIN)
    assert r["temperature_on_the_wire"] == "<absent from optional_params>", r


def test_dspy_falls_back_to_model_dump_for_the_provider():
    entry = {"model": "m",
             "response": _Resp(provider=None, model="m", optional_params={"temperature": 0.0},
                               dump={"model": "deepseek/deepseek-chat", "provider": "StreamLake"})}
    r = R.record_from_dspy_history(entry, PIN)
    assert r["provider_served"] == "StreamLake", r
    assert r["provider_served_source"] == "dspy_response_model_dump"
    assert r["model_returned"] == "deepseek/deepseek-chat"
    assert r["pin_honored"] is True


def test_dspy_record_reports_a_violated_pin():
    entry = {"model": "m", "response": _Resp(provider="DeepInfra", model="m",
                                             optional_params={"temperature": 0.0})}
    r = R.record_from_dspy_history(entry, PIN)
    assert r["pin_honored"] is False, r


def test_dspy_no_history_entry_says_why():
    for empty in (None, {}):
        r = R.record_from_dspy_history(empty, PIN)
        assert r["provider_served_source"] == "unavailable:no-dspy-history-entry", r
        assert r["pin_honored"] is None
        assert r["provider_pin"] == PIN


def test_dspy_entry_with_no_response_object_says_THAT_not_no_provider():
    # A history entry can exist with no response (an errored call). "no response on the entry"
    # and "a response that carried no provider" are different failures and must not share a label.
    r = R.record_from_dspy_history({"model": "m", "response": None}, PIN)
    assert r["provider_served"] is None
    assert r["provider_served_source"] == "unavailable:no-response-on-dspy-history-entry", r
    assert r["pin_honored"] is None


def test_dspy_unpinned_call_is_not_a_violation():
    entry = {"model": "m", "response": _Resp(provider="DeepInfra", model="m",
                                             optional_params={"temperature": 0.0})}
    r = R.record_from_dspy_history(entry, None)
    assert r["provider_served"] == "DeepInfra", "still recorded -- this is the fp4 provider"
    assert r["provider_pin"] is None
    assert r["pin_honored"] is None, "unpinned is not honored and not violated"


def test_no_call_record_is_unavailable_and_never_a_violation():
    r = R.no_call_record("dspy", "no-dspy-call-during-this-request", PIN)
    assert r["path"] == "dspy"
    assert r["provider_served_source"] == "unavailable:no-dspy-call-during-this-request", r
    assert r["provider_pin"] == PIN
    assert r["pin_honored"] is None, "no call read is not a violated pin"
    assert r["temperature_on_the_wire"] == "<not recorded>", r


# --- the shape both paths must share --------------------------------------------------

def test_both_paths_produce_the_same_keys():
    a = R.record_from_baml_call(_baml_call(), PIN)
    b = R.record_from_dspy_history(
        {"model": "m", "response": _Resp(provider="StreamLake", model="m",
                                         optional_params={"temperature": 0.0})}, PIN)
    assert set(a) == set(b), (sorted(set(a) ^ set(b)),)
    # and so does the empty case, or an aggregator over a mixed set of arms breaks on the
    # records that recorded nothing.
    assert set(R.record_from_baml_call(None, None)) == set(a)
    assert set(R.record_from_dspy_history(None, None)) == set(a)
    assert set(R.no_call_record("dspy", "why", None)) == set(a)


# --- the resolver: which record belongs to ONE answered request -----------------------
# The defect these guard cost a whole scored arm. The ON arm of attempt 4 had one run that
# returned early from the structured path (a correct refusal: the model cited a sentence id that
# was not in the context). That return dropped the record, and the caller INFERRED the path from
# its absence -- "no record attached means DSPy" -- so a real BAML call was written down as an
# unchecked DSPy non-call, the arm became a mixture, and the gate refused all 65 runs.

_DSPY_HIST = {"model": "deepseek/deepseek-chat",
              "response": _Resp(provider="StreamLake", model="deepseek/deepseek-chat",
                                optional_params={"temperature": 0.0})}


def test_the_resolver_returns_the_record_the_path_already_attached():
    attached = {"path": "baml", "provider_served": "StreamLake"}
    got = R.resolve_answer_lm(attached, structured_on=True, history_grew=False,
                              last_entry=None, pin=PIN)
    assert got is attached, got


def test_an_unrecorded_STRUCTURED_answer_is_a_BAML_record_not_a_dspy_one():
    # LOAD-BEARING: this is the exact defect. The old code produced path "dspy" here.
    got = R.resolve_answer_lm(None, structured_on=True, history_grew=False,
                              last_entry=None, pin=PIN)
    assert got["path"] == "baml", got
    assert got["provider_served_source"] == "unavailable:structured-path-returned-no-record", got
    assert got["provider_pin"] == PIN, got
    # An unavailable record claims nothing about the pin: it is never False.
    assert got["pin_honored"] is None, got


def test_the_resolver_does_not_read_the_DSPY_history_on_the_structured_path():
    # The inference "falsy means DSPy" must not come back in another form. A history entry that
    # WOULD produce a fully-populated pinned record is offered and must be ignored, because it
    # belongs to some other request -- attributing it here is how a wrong record is manufactured
    # rather than merely missed.
    got = R.resolve_answer_lm(None, structured_on=True, history_grew=True,
                              last_entry=_DSPY_HIST, pin=PIN)
    assert got["path"] == "baml", got
    assert got["model_returned"] is None, got
    assert got["provider_served"] is None, got


def test_the_DSPY_path_still_reads_its_own_history():
    # The companion assertion. Without it, a resolver that always returned an "unavailable"
    # record would pass every other test here.
    got = R.resolve_answer_lm(None, structured_on=False, history_grew=True,
                              last_entry=_DSPY_HIST, pin=PIN)
    assert got["path"] == "dspy", got
    assert got["provider_served"] == "StreamLake", got
    assert got["pin_honored"] is True, got
    assert got["temperature_on_the_wire"] == 0.0, got


def test_the_DSPY_path_with_no_call_in_the_window_says_so_exactly_as_before():
    # The OFF arm is unaffected by the fix: this is the old behaviour, byte for byte.
    got = R.resolve_answer_lm(None, structured_on=False, history_grew=False,
                              last_entry=None, pin=PIN)
    assert got["path"] == "dspy", got
    assert (got["provider_served_source"]
            == "unavailable:no-dspy-call-added-to-history-during-this-request"), got


def test_every_return_in_the_bot_carries_the_record():
    """Source-level, and anchored on a COUNT so it cannot quietly stop checking anything.

    The missing keyword argument was invisible to every behavioural test in this repo because the
    branch that drops it answers correctly -- only the eval's attribution table saw it. A count
    that must match is what makes a fifth return, added later without the record, fail here.
    """
    import re
    src = (Path(__file__).resolve().parent / "bot.py").read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(r"return\s+dspy\.Prediction\(", src)]
    assert len(starts) == 4, ("bot.py has %d `return dspy.Prediction(` sites, not the 4 this test "
                              "was written against -- read them and update the count deliberately"
                              % len(starts))
    missing = []
    for i in starts:
        depth, j = 0, src.index("(", i)
        for j in range(j, len(src)):
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    break
        call = src[i:j + 1]
        if "answer_lm=" not in call:
            missing.append(src[:i].count("\n") + 1)
    assert not missing, ("bot.py returns a Prediction with no answer_lm= at line(s) %s: a branch "
                         "that answers without saying who answered costs the whole arm" % missing)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    EXPECTED_TESTS = 28
    if len(tests) != EXPECTED_TESTS:
        print("COLLECTED %d test(s), EXPECTED %d -- a test was lost or added without updating "
              "the count; a suite that silently shrinks asserts nothing" % (len(tests),
                                                                            EXPECTED_TESTS))
        sys.exit(1)
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS  " + name)
        except Exception:
            failed += 1
            print("  FAIL  " + name)
            traceback.print_exc()
    print("")
    print(str(len(tests) - failed) + "/" + str(len(tests)) + " passed")
    sys.exit(1 if failed else 0)
