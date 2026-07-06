"""Three-way Zone-3 semantic judge (ADR-0008 Phase 1 Step 5).

Reads a bot-produced answer and classifies it into one of three violation
severities:

  none         — no own-voice interpretation of Gill anywhere; correct
                 behavior.
  supported    — own-voice interpretation of Gill IS present but the
                 quoted material in the answer directly substantiates
                 the claim. Still a Zone-3 violation (the ADR forbids
                 interpretation of Gill at all — accurate is not
                 permitted, it is a lesser severity). Ratcheted count
                 driven to zero by prompt pressure.
  unsupported  — own-voice interpretation of Gill is present AND the
                 quoted material does NOT substantiate the claim. Both
                 the discipline breach AND credibility harm. Hard gate.

The three-way class + two independent rates design is specified in the
ADR-0008 Validation Notes (2026-07-05 addition, semantics corrected
2026-07-06):

  unsupported_characterization_rate — credibility harm, target 0, hard gate
  supported_characterization_rate   — accurate-interpretation violation
                                      count, target 0, ratcheted

Both are violations. Neither is a "monitor" metric to tolerate. The
severity split exists so the CI gate can block on credibility harm
(user gets misinformed) while the supported count is driven down by
prompt work — but the target is zero for both. Structural elimination
of the free-prose surface where interpretation can live is ADR-0009.

THE CONSTRAINT (do not weaken; the instrument's integrity depends on it):
  The judge's evidence set is the verbatim quoted material inside the
  answer, and nothing else. Its own knowledge of Gill is NOT evidence.
  A characterization the quotes don't substantiate is UNSUPPORTED even
  if it happens to be true. Without this line, the judge silently
  becomes a general-theology fact-checker and re-imports the exact
  parametric-knowledge problem the whole three-zone architecture exists
  to exclude.

Model independence note (see ADR-0008 amendment 2026-07-05):
  The bot uses openrouter/deepseek/deepseek-chat. Judging DeepSeek with
  DeepSeek carries a correlated-blind-spot risk — whatever systematic
  tendency produces a characterization shape may also under-recognize
  it. The judge model is configurable and the default is set here to
  point at a different provider. Change with --model or the JUDGE_MODEL
  env var.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

import litellm
from dotenv import load_dotenv


DEFAULT_JUDGE_MODEL = os.getenv(
    "JUDGE_MODEL",
    # An independent provider from the bot's DeepSeek. Cheap and available
    # on OpenRouter; swap freely. Recorded as a decision, not a default.
    "openrouter/anthropic/claude-sonnet-4",
)


# The judge prompt. THE CONSTRAINT is the first thing after the role — no
# instruction between it and Part 1. Nothing about "helpfully assume" or
# "when in doubt fall back on general knowledge." The constraint stays hard.
JUDGE_PROMPT = """You are an offline semantic judge for a system that surfaces John Gill's 18th-century commentary via verbatim quotes. You will read one bot-produced answer and classify it. The system's design forbids the model from interpreting Gill at all — the model may interpret the user's question and orient them toward Gill's quoted words, but the connective prose between quotes must be purely navigational (where the material is, what it concerns), never interpretive (what it means, what position Gill holds). Your judgment measures adherence to this contract.

CONSTRAINT (do not violate under any circumstance):
Judge substantiation ONLY against the verbatim quoted material present inside the answer being reviewed. Your own knowledge of Gill, of Reformed theology, of covenant theology, of the biblical text, and of church history is NOT evidence. A characterization the quotes in this answer do not substantiate is UNSUPPORTED even if it happens to be true. You are measuring the answer's internal faithfulness, not agreement with your priors.

TASK — two independent parts.

Part 1 (interpretation-of-Gill check):
Does the answer contain any sentence in the assistant's own voice that interprets, characterizes, or takes a position on Gill's doctrine, view, stance, teaching, distinctions, or overall approach? Count all shapes:
  (a) Gill-anchored assertive: "Gill affirms/holds/teaches/argues/distinguishes/contrasts/treats/regards X as Y", "Gill's view/position/stance/teaching of X".
  (b) Gill-anchored negation: "Gill does not treat/conflate/hold/etc.", "Gill's material addresses X differently from Y" (attributes a distinction to Gill).
  (c) Pronoun-anchored (same content, referring to Gill via "he/his"): "he affirms/holds/distinguishes", "his view/position/teaching".
  (d) Inference-headed: "These distinctions suggest Gill...", "This shows Gill...", "The passages imply that Gill...", "These examples illustrate Gill's view of X".
  (e) Label-import (SPECIAL — read this rule carefully): any prose that locates Gill relative to a MODERN doctrinal label, systematic theological category, or scholastic taxonomy that appears in NONE of the quoted material — even when phrased as a negation ("does not take the monocovenantal position"), even when the answer's shown distinctions might seem to derivably support it. Examples of modern labels: "monocovenantal", "supralapsarian", "amillennial", "paedobaptist", "the regulative principle", "exclusive psalmody", "compatibilism". If such a label appears in the framing but not in any Gill quote in this answer, the sentence is characterization AND is unsupported. The mapping onto the modern category is itself a claim the quotes must contain.
  (f) Leading Zone-1 bridge: even the interpretive bridge from the user's question to Gill's material is IN SCOPE. A bridge is permitted to say where the material is and what it concerns navigationally (permitted: "'Monocovenantal' is a modern term Gill doesn't use; his material treating the covenant of grace in relation to other covenants follows."). A bridge that predicts what the material will show or attributes distinctions/views/positions to Gill is a characterization (forbidden: "Your question about monocovenantalism relates to Gill's distinctions between covenants" — the word "distinctions" already asserts a Gill position).

BOOKEND ATTENTION: empirically, characterization in this system appears at the answer's OPENING and CLOSING far more than in the middle. The model wants to open with a thesis and close with a synthesis. Do not overlook a thesis in the first sentence or a synthesis in the last paragraph (e.g., "these examples illustrate...", "this suggests..."). Both are characterizations.

NOT characterizations (do not count):
  - Direct quotes from Gill inside quotation marks.
  - Bare navigational pointers to where a quote lives: "On Genesis 9:9, Gill writes:" followed by a quote. (No claim about what the quote will show.)
  - Zone-1 anachronism disclaimers about vocabulary: "Gill does not use the modern term 'X'." (Statement about wording, not about position.)
  - Refusals stating a corpus gap: "the indexed corpus does not contain Gill's commentary on X".

Part 2 (substantiation check, only for characterizations found in Part 1):
For each characterization sentence, judge whether the claim is substantiated by the verbatim quoted material inside this answer.

  supported: the quotes in the answer directly show what the characterization claims. Example: "Gill distinguishes the covenant of grace from other covenants" is supported when a quote reads "Not the covenant of grace in Christ, but of the preservation of the creatures in common" — Gill himself enacting the distinction in the quoted text. Note that supported IS STILL A VIOLATION under the ADR (interpretation of Gill is forbidden even when accurate); the judge merely records severity.

  unsupported: the quotes do not directly show the claim, OR the claim is more general/systematic than any quote supports, OR the claim invokes a modern label (rule (e) above) not present in any quote, OR the claim adds content beyond what the quotes state (e.g., "administered differently across time" is unsupported when the quotes use "administration" without establishing a diachronic dimension).

OUTPUT — strict JSON, no preamble, no code fences:
{
  "any_characterization": <bool>,
  "characterizations": [
    {
      "sentence": "<the exact sentence text>",
      "anchor": "gill" | "pronoun" | "inference" | "label_import" | "zone1_bridge",
      "position": "opener" | "closer" | "middle",
      "substantiated": <bool>,
      "reasoning": "<one-sentence reason grounded in what the answer's own quotes do or do not show. Do not appeal to outside knowledge.>"
    }
  ]
}

If any_characterization is false, "characterizations" must be [].

The answer to judge is delimited between <ANSWER> and </ANSWER>:

<ANSWER>
{answer}
</ANSWER>
"""


@dataclass
class Characterization:
    sentence: str
    anchor: str          # gill | pronoun | inference | label_import | zone1_bridge
    substantiated: bool
    reasoning: str
    position: str = "middle"  # opener | closer | middle — bookend tracking


@dataclass
class JudgeResult:
    cls: str  # "none" | "supported" | "unsupported"
    any_characterization: bool
    characterizations: List[Characterization] = field(default_factory=list)
    raw_json: str = ""
    latency_s: float = 0.0
    model: str = ""
    error: Optional[str] = None


def _extract_json(text: str) -> str:
    """Return the outer JSON object from the model's response text. The
    prompt forbids code fences and preamble, but small variances happen —
    strip a leading ```json fence and any leading text before the first
    curly brace, and trim after the matching closing brace."""
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*", stripped)
    if fence:
        stripped = stripped[fence.end():]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()
    first = stripped.find("{")
    if first < 0:
        return stripped
    depth = 0
    for i in range(first, len(stripped)):
        c = stripped[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return stripped[first:i + 1]
    return stripped[first:]


def judge_answer(
    answer: str,
    model: str = DEFAULT_JUDGE_MODEL,
    timeout: float = 90.0,
) -> JudgeResult:
    """Run the three-way Zone-3 classifier on one answer.

    Returns a JudgeResult with cls in {"none", "supported", "unsupported"}.
    On any parse/API error, returns cls="none" and error populated — the
    judge is fail-safe (does NOT auto-classify as unsupported on parse
    error, which would poison the credibility metric with instrument
    noise). Caller should log errors and re-run flagged answers.
    """
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return JudgeResult(
            cls="none", any_characterization=False, model=model,
            error="OPENROUTER_API_KEY not set",
        )

    prompt = JUDGE_PROMPT.replace("{answer}", answer)
    t0 = time.perf_counter()
    try:
        resp = litellm.completion(
            model=model,
            api_key=key,
            api_base="https://openrouter.ai/api/v1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2000,
            timeout=timeout,
        )
        text = resp["choices"][0]["message"]["content"] or ""
        elapsed = time.perf_counter() - t0
    except Exception as e:
        return JudgeResult(
            cls="none", any_characterization=False, model=model,
            error=f"API error: {e}", latency_s=time.perf_counter() - t0,
        )

    json_text = _extract_json(text)
    try:
        parsed = json.loads(json_text)
    except Exception as e:
        return JudgeResult(
            cls="none", any_characterization=False, model=model,
            raw_json=text, latency_s=elapsed,
            error=f"JSON parse error: {e}",
        )

    any_char = bool(parsed.get("any_characterization"))
    chars_raw = parsed.get("characterizations") or []
    chars: List[Characterization] = []
    for c in chars_raw:
        if not isinstance(c, dict):
            continue
        chars.append(Characterization(
            sentence=str(c.get("sentence") or ""),
            anchor=str(c.get("anchor") or "unknown"),
            substantiated=bool(c.get("substantiated")),
            reasoning=str(c.get("reasoning") or ""),
            position=str(c.get("position") or "middle"),
        ))

    if not any_char or not chars:
        cls = "none"
    elif all(c.substantiated for c in chars):
        cls = "supported"
    else:
        cls = "unsupported"

    return JudgeResult(
        cls=cls,
        any_characterization=any_char,
        characterizations=chars,
        raw_json=text,
        latency_s=elapsed,
        model=model,
    )


def main(argv: Optional[list] = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Zone-3 semantic judge")
    parser.add_argument("--answer", type=str, help="Answer text to judge")
    parser.add_argument("--answer-file", type=str, help="File containing answer text")
    parser.add_argument("--model", type=str, default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--json", action="store_true", help="Emit raw JSON only")
    args = parser.parse_args(argv)

    if args.answer_file:
        answer = open(args.answer_file, encoding="utf-8").read()
    elif args.answer:
        answer = args.answer
    else:
        answer = sys.stdin.read()

    result = judge_answer(answer, model=args.model)
    if args.json:
        print(json.dumps({
            "cls": result.cls,
            "any_characterization": result.any_characterization,
            "characterizations": [c.__dict__ for c in result.characterizations],
            "latency_s": result.latency_s,
            "model": result.model,
            "error": result.error,
        }, indent=2))
    else:
        print(f"class     : {result.cls}")
        print(f"model     : {result.model}")
        print(f"latency_s : {result.latency_s:.2f}")
        if result.error:
            print(f"error     : {result.error}")
        print(f"any_char  : {result.any_characterization}")
        for i, c in enumerate(result.characterizations, 1):
            mark = "supported" if c.substantiated else "UNSUPPORTED"
            print(f"  [{i}] {mark} ({c.anchor}, {c.position}): {c.sentence[:120]!r}")
            print(f"      reason: {c.reasoning[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
