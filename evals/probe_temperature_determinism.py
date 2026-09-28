"""Does the OFF (DSPy) path sample, and would temperature 0 stop it?

    python evals/probe_temperature_determinism.py

WHY THIS EXISTS. Measured 2026-09-27 while implementing ruling 2's per-call recording:

    dspy.LM(...).kwargs == {'temperature': None, 'max_tokens': None, ...}

The OFF path sends NO temperature. litellm omits the field, so DeepSeek's own default applies.
The ON path's BAML client sends `temperature: 0` (gill_answer.baml, verified on the rendered
request body). So every OFF-vs-ON arm ever run differed in temperature as well as in schema, and
nothing recorded it.

That also makes unset temperature a candidate cause of the instrument noise this lane has been
chasing: 36-43% FLAKY, and 11 of 28 stability-class changes between two OFF arms differing in
nothing. It is only a CANDIDATE. A fix can work while the reason given for it is false, so this
probe measures the mechanism directly instead of inferring it from the floor.

PREDICTION, recorded before the first run of this file (locked by committing it before running):
  P1. temperature unset  -> the 3 completions are NOT all identical.
  P2. temperature 0.0    -> the 3 completions ARE all identical.
  P3. The pin is honored in all 6 calls (provider served == StreamLake).
  If P1 holds and P2 fails, temperature is not the lever and the noise is provider-side
  non-determinism; that outcome is as useful as the other and must not be reported as a failure
  of the probe.

WHAT THIS DOES NOT MEASURE. LM-level determinism is not harness-level stability: a question's
PASS/FAIL also moves with retrieval, the quote verifier, and the content gates. Identical
completions here would bound the sampling contribution, not prove the floor's cause.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PIN = {"order": ["streamlake"], "allow_fallbacks": False}
N = 3
PROMPT = (
    "Using ONLY this extract, answer in at most 60 words, quoting the extract verbatim once.\n"
    "[GENESIS_1_1_S00] In the beginning God created the heaven and the earth; that is, the "
    "matter of which all things were made, and which was without form and void.\n"
    "Question: What does Gill say the beginning refers to?"
)


def arm(temperature, api_key):
    import dspy
    kwargs = dict(model="openai/deepseek/deepseek-chat", api_key=api_key,
                  api_base="https://openrouter.ai/api/v1",
                  extra_body={"usage": {"include": True}, "provider": PIN})
    if temperature is not None:
        kwargs["temperature"] = temperature
    lm = dspy.LM(**kwargs)
    outs, served, sent_temp = [], [], []
    for _ in range(N):
        text = lm(PROMPT)[0]
        outs.append(text)
        r = lm.history[-1].get("response")
        served.append(getattr(r, "provider", None))
        sent_temp.append((lm.history[-1].get("kwargs") or {}).get("temperature", "<omitted>"))
    digests = [hashlib.sha256(o.encode("utf-8")).hexdigest()[:16] for o in outs]
    return {"temperature_requested": temperature,
            "temperature_in_call_kwargs": sent_temp,
            "provider_served": served,
            "digests": digests,
            "all_identical": len(set(digests)) == 1,
            "distinct_outputs": len(set(digests)),
            "lengths": [len(o) for o in outs],
            "first_output": outs[0][:400]}


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        # A probe that quietly runs against no credentials would report "0 distinct outputs".
        sys.exit("probe: OPENROUTER_API_KEY is absent. Refusing to report determinism measured "
                 "over zero successful calls.")
    out = {"n_per_arm": N, "pin": PIN, "prompt_sha16": hashlib.sha256(PROMPT.encode()).hexdigest()[:16],
           "arms": {}}
    for label, temp in (("unset", None), ("zero", 0.0)):
        print(f"arm {label}: {N} calls ...")
        out["arms"][label] = arm(temp, key)
        a = out["arms"][label]
        print(f"  distinct outputs: {a['distinct_outputs']}/{N}   identical: {a['all_identical']}")
        print(f"  temperature in call kwargs: {a['temperature_in_call_kwargs']}")
        print(f"  provider served: {a['provider_served']}")
    p1 = out["arms"]["unset"]["all_identical"] is False
    p2 = out["arms"]["zero"]["all_identical"] is True
    served = [s for a in out["arms"].values() for s in a["provider_served"]]
    p3 = all((s or "").lower() == "streamlake" for s in served)
    out["predictions"] = {
        "P1 unset is NOT deterministic": p1,
        "P2 zero IS deterministic": p2,
        "P3 pin honored in all calls": p3,
    }
    print("")
    for k, v in out["predictions"].items():
        print(f"  {'HELD     ' if v else 'FALSIFIED'} {k}")
    dest = Path(__file__).resolve().parents[1] / "evals" / "output" / "probe_temperature_determinism.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
