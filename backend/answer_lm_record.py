"""What model, at what temperature, served by which provider -- recorded per answer call.

Ruling 2 (2026-09-27, Chris): pin GillAnswerLM, with provider/model/temperature recorded per
call, before the next arm runs. This module is the recording half, kept pure so it can be
born-tested without a model call or a server.

Three facts it exists to stop being invisible:

1. The ON path (BAML `GillAnswerLM`) sends `temperature: 0`. The OFF path (`dspy.LM`) sends NO
   temperature at all -- `lm.kwargs["temperature"] is None` and litellm omits the field, so the
   provider's own default applies. Every OFF-vs-ON arm ever run differed in temperature as well
   as in schema, and no artifact recorded it.
2. `deepseek/deepseek-chat` has more than one OpenRouter provider at different quantizations.
   Unpinned, the key routes to DeepInfra (fp4, status -2). Pinned, StreamLake serves it. Ruling 1's
   arms were both unpinned, which is why a flip attributed to the flag could not be attributed at
   all.
3. A pin that is SENT is not a pin that is HONORED. OpenRouter echoes the serving provider in the
   response body, so `pin_honored` is a measurement, not an assumption. Note the case difference:
   the pin says `streamlake`, the response says `StreamLake`.

`provider_served_source` names where the value came from, and says `unavailable:<why>` when it
could not be read. A record that cannot state its source is not evidence; recording None with no
reason is how "we never looked" becomes indistinguishable from "it was not pinned".
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


def as_dict(x: Any) -> Optional[dict]:
    """BAML hands back a dict, a json-able wrapper, or bytes depending on the field. Unwrap all
    three rather than assuming one, because the assumption is version-dependent and silent."""
    if x is None:
        return None
    if isinstance(x, dict):
        return x
    if hasattr(x, "json"):
        try:
            v = x.json()
        except Exception:
            return None
        if isinstance(v, dict):
            return v
        x = v
    if isinstance(x, (str, bytes, bytearray)):
        try:
            v = json.loads(x)
        except Exception:
            return None
        return v if isinstance(v, dict) else None
    return None


def pin_honored(pin: Optional[dict], served: Optional[str]) -> Optional[bool]:
    """True/False, or None when the question is not answerable from what we have.

    None is a third state on purpose: an unpinned call cannot violate a pin, and a call whose
    serving provider could not be read has not been checked. Collapsing either into False would
    manufacture violations; collapsing either into True would hide them.
    """
    if not pin:
        return None
    order = pin.get("order") if isinstance(pin, dict) else None
    if not order or not served:
        return None
    return str(served).strip().lower() in [str(o).strip().lower() for o in order]


def _base(path: str) -> Dict[str, Any]:
    return {"path": path, "client": None, "model_requested": None, "model_returned": None,
            "temperature_on_the_wire": "<not recorded>", "provider_pin": None,
            "provider_served": None, "provider_served_source": "unavailable:not-attempted",
            "pin_honored": None}


def no_call_record(path: str, why: str, pin: Optional[dict]) -> Dict[str, Any]:
    """A record for "we looked and there was no call to read", with the reason attached.

    Distinct from `record_from_*(None, pin)`: that says the entry was missing, this says the
    entry we would have read belongs to something other than this request. Both are
    `unavailable:`, and neither is ever `pin_honored: False`.
    """
    rec = _base(path)
    rec["provider_pin"] = pin
    rec["provider_served_source"] = "unavailable:" + why.lstrip(":")
    return rec


def record_from_baml_call(call: Any, pin: Optional[dict]) -> Dict[str, Any]:
    """From one `baml_py` Collector LLMCall (`collector.last.calls[-1]`)."""
    rec = _base("baml")
    if call is None:
        rec["provider_served_source"] = "unavailable:no-llm-call-recorded"
        rec["provider_pin"] = pin
        return rec
    rec["client"] = getattr(call, "client_name", None)
    req = as_dict(getattr(getattr(call, "http_request", None), "body", None)) or {}
    rec["model_requested"] = req.get("model")
    # Absent means the field was never sent, which is a different fact from 0.0.
    rec["temperature_on_the_wire"] = req.get("temperature", "<absent from request body>")
    rec["provider_pin"] = req.get("provider", pin)
    resp = as_dict(getattr(getattr(call, "http_response", None), "body", None))
    if resp is None:
        rec["provider_served_source"] = "unavailable:no-response-body-on-the-call"
    else:
        rec["model_returned"] = resp.get("model")
        served = resp.get("provider")
        if served is None:
            rec["provider_served_source"] = "unavailable:response-body-has-no-provider-field"
        else:
            rec["provider_served"] = served
            rec["provider_served_source"] = "openrouter_response_body"
    rec["pin_honored"] = pin_honored(rec["provider_pin"], rec["provider_served"])
    return rec


def record_from_dspy_history(entry: Optional[dict], pin: Optional[dict]) -> Dict[str, Any]:
    """From one `dspy.LM.history[-1]` entry.

    The temperature is read from litellm's `_hidden_params["optional_params"]`, the dict actually
    put on the wire -- NOT from `entry["kwargs"]`, where the key is absent whether or not it was
    set. A probe that read the latter reported "<omitted>" for an arm that had sent 0.0.
    """
    rec = _base("dspy")
    if not entry:
        rec["provider_served_source"] = "unavailable:no-dspy-history-entry"
        rec["provider_pin"] = pin
        return rec
    rec["client"] = "dspy.LM"
    rec["model_requested"] = entry.get("model")
    resp = entry.get("response")
    if resp is None:
        # An errored call leaves a history entry with no response. "no response at all" and
        # "a response that carried no provider" are different failures; one label for both
        # would make a dead endpoint read as an OpenRouter field change.
        rec["provider_pin"] = pin
        rec["provider_served_source"] = "unavailable:no-response-on-dspy-history-entry"
        return rec
    hidden = getattr(resp, "_hidden_params", None) or {}
    opt = hidden.get("optional_params")
    if isinstance(opt, dict):
        rec["temperature_on_the_wire"] = opt.get("temperature", "<absent from optional_params>")
        body_pin = (opt.get("extra_body") or {}).get("provider") if isinstance(opt.get("extra_body"), dict) else None
        rec["provider_pin"] = body_pin or pin
    else:
        rec["provider_pin"] = pin
    served = getattr(resp, "provider", None)
    if served is None:
        d = as_dict(resp.model_dump() if hasattr(resp, "model_dump") else None) or {}
        served = d.get("provider")
        rec["model_returned"] = d.get("model")
        rec["provider_served_source"] = ("dspy_response_model_dump" if served is not None
                                         else "unavailable:no-provider-on-dspy-response")
    else:
        rec["model_returned"] = getattr(resp, "model", None)
        rec["provider_served_source"] = "dspy_response_attribute"
    rec["provider_served"] = served
    rec["pin_honored"] = pin_honored(rec["provider_pin"], rec["provider_served"])
    return rec
