"""ADR-0009 structured answer path — schema call, structural gates, prose renderer.

Behind the `GILL_STRUCTURED_ANSWER` flag. Default OFF: `backend/bot.py` takes the
DSPy path and this module is never entered.

Three jobs, in order:

1. `generate()` — one BAML call returning a typed `GillAnswer`.
2. `check_structure()` — DETERMINISTIC structural gates. Everything checked here is a
   property of the object, not a judgement about the prose: exactly-one-of
   phrases/refusal, exactly-one-of gill_quote/scripture_quote, informative refusals
   carry adjacent material, flat refusals carry none, every sentence_id is one the
   context actually supplied. Code owns these; no model is consulted about them.
3. `render()` — the typed object back to the prose shape `main.py`, the quote verifier,
   and `evals/run_eval.py` already consume: framing, then `"quote" [SID]`, matching
   `bot.QUOTE_WITH_CITE_RE`. The structured object rides alongside for the ADR-0008
   voice-marked UI; nothing downstream is forced to use it yet.

Two rules this module exists to make structural rather than hoped-for:

  - `zone3_notes` is NEVER rendered. It is logged. That is the whole contract.
  - The FLAT refusal wording is a deterministic string owned here, not something the
    model is trusted to reproduce. `evals/run_eval.py:is_refusal()` keys on that exact
    wording, so on the DSPy path a flat refusal only scores as a refusal when the model
    happens to echo the sentence verbatim. Here `mode == "flat"` makes it certain.
    (Deterministic property, so code owns it.)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from baml_py import ClientRegistry, Collector

from baml_client.sync_client import b as baml
from baml_client.types import GillAnswer, GillRefusal, Zone2Phrase

try:
    from .answer_lm_record import record_from_baml_call
    from .degradation import provider_pin
except ImportError:  # run as a script / imported flat, same as bot.py does
    from answer_lm_record import record_from_baml_call  # type: ignore
    from degradation import provider_pin  # type: ignore

# The canonical flat refusal. Must stay character-identical to the string in
# bot.py's No-Free-Lunch fallback and to REFUSAL_MARKERS in evals/run_eval.py.
FLAT_REFUSAL_TEMPLATE = (
    "I regret that the provided extracts from the Doctor's writings "
    "do not appear to address this specific inquiry. Could it be that "
    "you are looking for something not in the library ({available_books})?"
)

_SID_RE = re.compile(r"[A-Z0-9_]+_S\d+")


def structured_enabled() -> bool:
    """Read the flag per call, not at import.

    Per-call so a single running backend can serve the before-and-after eval without a
    restart, and so flipping it in production is a config change rather than a deploy.
    """
    return os.getenv("GILL_STRUCTURED_ANSWER", "").strip().lower() in ("1", "true", "yes", "on")


def _norm_sid(raw: str) -> str:
    """'[MATTHEW_26_28_S01]' / 'matthew_26_28_s01' -> '[MATTHEW_26_28_S01]'."""
    m = _SID_RE.search((raw or "").upper())
    return f"[{m.group(0)}]" if m else ""


# The model and temperature GillAnswerLM is declared with in baml_src/gill_answer.baml. Repeated
# here because a runtime ClientRegistry entry REPLACES the declared client wholesale: omit a field
# and it is not inherited, it is gone. Kept identical on purpose -- this pass adds a pin, it does
# not change the model or the sampling.
ANSWER_LM_MODEL = "deepseek/deepseek-chat"
ANSWER_LM_TEMPERATURE = 0.0
ANSWER_LM_BASE_URL = "https://openrouter.ai/api/v1"


def answer_lm_registry() -> Optional[ClientRegistry]:
    """GillAnswerLM with the OpenRouter provider pin applied, or None when nothing is pinned.

    Ruling 2: pin GillAnswerLM. The pin CANNOT live in gill_answer.baml, because
    `degradation.provider_pin()` reads OPENROUTER_PROVIDER_ORDER at call time while a .baml
    options block is static -- a literal there would be a second source of truth able to disagree
    silently with the pin the DSPy path is using in the same process. One source, read per call.

    `add_llm_client` under the SAME NAME overrides that client only; no `set_primary`, so no other
    BAML function in this codebase is touched. Verified on the rendered request body: the pin
    reaches `provider` in the JSON sent to OpenRouter without set_primary.

    Returns None when unpinned, so an unpinned run behaves exactly as before rather than being
    rerouted through a registry for no reason.
    """
    pin = provider_pin()
    if not pin:
        return None
    cr = ClientRegistry()
    cr.add_llm_client(name="GillAnswerLM", provider="openai", options={
        "base_url": ANSWER_LM_BASE_URL,
        "api_key": os.getenv("OPENROUTER_API_KEY"),
        "model": ANSWER_LM_MODEL,
        "temperature": ANSWER_LM_TEMPERATURE,
        "provider": pin,
    })
    return cr


def generate(context: str, question: str, available_books: str) -> Tuple[GillAnswer, Dict[str, Any]]:
    """The one BAML call, plus a per-call record of what actually served it.

    Returns a tuple rather than setting module state: two concurrent requests through one process
    would race on a module-level "last call", and the record would then be attributed to the wrong
    answer. The caller already holds the answer; it can hold the record beside it.
    """
    pin = provider_pin()
    collector = Collector(name="gill_answer")
    client = baml.with_options(collector=collector, client_registry=answer_lm_registry())
    ans = client.GenerateGillAnswer(
        context=context, question=question, available_books=available_books
    )
    last = getattr(collector, "last", None)
    calls = getattr(last, "calls", None) or []
    return ans, record_from_baml_call(calls[-1] if calls else None, pin)


# --------------------------------------------------------------------------
# Structural gates
# --------------------------------------------------------------------------

def _check_phrase(p: Zone2Phrase, idx: int, where: str, valid_sids: set) -> List[str]:
    v: List[str] = []
    has_gill = bool((p.gill_quote or "").strip())
    has_scripture = bool((p.scripture_quote or "").strip())
    if has_gill and has_scripture:
        v.append(f"{where}[{idx}]: both gill_quote and scripture_quote populated")
    if not has_gill and not has_scripture:
        v.append(f"{where}[{idx}]: neither gill_quote nor scripture_quote populated")
    sid = _norm_sid(p.sentence_id)
    if not sid:
        v.append(f"{where}[{idx}]: sentence_id {p.sentence_id!r} is not a Sentence ID")
    elif valid_sids and sid not in valid_sids:
        # Not in the context = fabricated or guessed. The DSPy path can only catch this
        # after the fact by regex-scraping prose; here it is a field comparison.
        v.append(f"{where}[{idx}]: sentence_id {sid} was not in the retrieved context")
    return v


def check_structure(ans: GillAnswer, valid_sids: Optional[set] = None) -> List[str]:
    """Return a list of structural violations. Empty list == structurally sound.

    A violation is a FLAG, not a crash: the caller renders anyway and records the flag,
    because a structurally odd answer that still quotes Gill correctly is better for the
    reader than an error screen. What the flags buy is that the oddity is visible.
    """
    valid_sids = valid_sids or set()
    v: List[str] = []

    has_phrases = bool(ans.phrases)
    has_refusal = ans.refusal is not None
    if has_phrases and has_refusal:
        v.append("both phrases and refusal populated (exactly one is allowed)")
    if not has_phrases and not has_refusal:
        v.append("neither phrases nor refusal populated")

    for i, p in enumerate(ans.phrases or []):
        v.extend(_check_phrase(p, i, "phrases", valid_sids))

    r: Optional[GillRefusal] = ans.refusal
    if r is not None:
        mode = (r.mode or "").strip().lower()
        if mode not in ("flat", "informative"):
            v.append(f"refusal.mode {r.mode!r} is neither 'flat' nor 'informative'")
        if not (r.gap_statement or "").strip():
            v.append("refusal.gap_statement is empty")
        adj = r.adjacent_phrases or []
        if mode == "informative" and not adj:
            v.append("refusal.mode='informative' with no adjacent_phrases")
        if mode == "flat" and adj:
            v.append(f"refusal.mode='flat' with {len(adj)} adjacent_phrases")
        for i, p in enumerate(adj):
            v.extend(_check_phrase(p, i, "refusal.adjacent_phrases", valid_sids))
            # The 2026-07-12 refusal-path fix, now a field check rather than a prose
            # heuristic: adjacent material must be Gill's own commentary, never the
            # Scripture verse he is about to comment on.
            if (p.scripture_quote or "").strip() and not (p.gill_quote or "").strip():
                v.append(
                    f"refusal.adjacent_phrases[{i}]: Scripture surfaced as adjacent "
                    "material (GILL-ONLY constraint)"
                )
    return v


# --------------------------------------------------------------------------
# Renderer
# --------------------------------------------------------------------------

def _render_phrase(p: Zone2Phrase) -> str:
    quote = (p.gill_quote or p.scripture_quote or "").strip()
    # The model is told not to include the wrapping quote marks; strip them if it did
    # anyway, so the rendered text never doubles them.
    if len(quote) >= 2 and quote[0] in '"“”' and quote[-1] in '"“”':
        quote = quote[1:-1].strip()
    framing = (p.framing or "").strip()
    sid = _norm_sid(p.sentence_id) or p.sentence_id
    if not quote:
        return framing
    body = f'"{quote}" {sid}'
    return f"{framing} {body}".strip() if framing else body


def render(ans: GillAnswer, available_books: str) -> Tuple[str, List[str], Dict[str, Any]]:
    """Typed answer -> (prose, citations, meta).

    `meta` carries what the structured path knows and the prose cannot express:
    the zone3 sinkhole, the refusal mode, and the structural flags.
    """
    parts: List[str] = []
    citations: List[str] = []

    def emit(phrases: List[Zone2Phrase]) -> None:
        for p in phrases:
            parts.append(_render_phrase(p))
            sid = _norm_sid(p.sentence_id)
            # Only Gill quotes claim a Gill citation. A Scripture quote is rendered with
            # its SID for the reader's navigation but does not enter the citation list,
            # so it can never stand in for having quoted Gill. That substitution is the
            # Garden of Eden failure.
            if sid and (p.gill_quote or "").strip() and sid not in citations:
                citations.append(sid)

    r = ans.refusal
    if r is not None and (r.mode or "").strip().lower() == "flat":
        # Deterministic wording, code-owned. The model's gap_statement is logged, not shown.
        prose = FLAT_REFUSAL_TEMPLATE.format(available_books=available_books)
        return prose, [], {
            "refusal_mode": "flat",
            "model_gap_statement": (r.gap_statement or "").strip(),
            "zone3_notes": ans.zone3_notes or "",
            "zone1_interpretation": ans.zone1_interpretation or "",
        }

    if (ans.zone1_interpretation or "").strip():
        parts.append(ans.zone1_interpretation.strip())

    if r is not None:
        parts.append((r.gap_statement or "").strip())
        emit(r.adjacent_phrases or [])
        mode = (r.mode or "").strip().lower() or "informative"
    else:
        emit(ans.phrases or [])
        mode = ""

    prose = "\n\n".join(p for p in parts if p)
    return prose, citations, {
        "refusal_mode": mode,
        "model_gap_statement": (r.gap_statement or "").strip() if r else "",
        "zone3_notes": ans.zone3_notes or "",
        "zone1_interpretation": ans.zone1_interpretation or "",
    }


def to_payload(ans: GillAnswer) -> Dict[str, Any]:
    """The structured object as plain dicts, for the trace and the future gutter UI.

    `zone3_notes` is deliberately present here — this payload goes to logs and traces,
    never to the rendered answer. Anything rendering this to a user must drop that key.
    """
    def ph(p: Zone2Phrase) -> Dict[str, Any]:
        return {
            "framing": p.framing,
            "gill_quote": p.gill_quote,
            "scripture_quote": p.scripture_quote,
            "sentence_id": _norm_sid(p.sentence_id) or p.sentence_id,
        }

    out: Dict[str, Any] = {
        "reasoning": ans.reasoning,
        "zone1_interpretation": ans.zone1_interpretation,
        "phrases": [ph(p) for p in (ans.phrases or [])],
        "zone3_notes": ans.zone3_notes,
        "refusal": None,
    }
    if ans.refusal is not None:
        out["refusal"] = {
            "mode": ans.refusal.mode,
            "gap_statement": ans.refusal.gap_statement,
            "adjacent_phrases": [ph(p) for p in (ans.refusal.adjacent_phrases or [])],
        }
    return out
