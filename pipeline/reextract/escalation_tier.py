"""Stage-3 FRONTIER ESCALATION TIER — escalate the ADJUDICATION, never the perception.
Validated 2026-08-09 (8/8 on the two final-letter floor spans). Governance (see HANDOFF):
- PRECONDITION / intake gate: escalate ONLY spans whose note contains ADJUDICATING MATERIAL (a Latin
  gloss / citation adjacent to the Hebrew). No material -> honest review-queue, NO panel (philology
  without a text to reason from is prior-voting at higher price).
- FAITHFULNESS is a permanent prompt clause: reproduce the PRINTED form, do NOT normalize to the
  dictionary. Divergence from print is a DEFECT, not a fix.
- Unanimity is a confidence signal ONLY over shared EVIDENCE (the gloss), never shared priors.
- Output is a PROPOSAL with provenance class `adjudicated-by-frontier-with-bilingual-context`
  (!= `Chris-verified-against-scan`), and its OWN cost (usage.cost for OpenRouter-billed models +
  tokens for BYOK models whose cost reads $0). Auto-accept threshold = the trust dial (default: only
  unanimous).
"""
import os, re, json
import httpx

HEB = re.compile(r"[֐-׿]")
LATIN = re.compile(r"[A-Za-zÀ-ÿæœ]{3,}")
PANEL = ["anthropic/claude-opus-5", "google/gemini-3.6-flash", "deepseek/deepseek-v4-pro"]

_PROMPT = (
    "You verify OCR of a 1766 Hebrew-lexicographer commentary footnote. The Hebrew is UNPOINTED and may "
    "be a non-standard/abbreviated 1766 spelling — reproduce what was PRINTED; do NOT normalize to the "
    "modern dictionary form. OCR read the Hebrew as \"{base}\" but likely DROPPED its FINAL letter (worn "
    "type). Determine the single most likely FINAL LETTER dropped, using the Latin gloss to adjudicate "
    "grammatical form (number/gender/person). Return the base reading with that final letter appended "
    "(unchanged if none dropped).\nFootnote: {note}\n"
    "Reply ONLY JSON: {{\"corrected_hebrew\":\"...\",\"dropped_final_letter\":\"...\",\"reasoning\":\"one sentence citing the Latin\"}}")

def has_adjudicating_material(note_text, hebrew_span):
    """Intake gate: is there Latin/citation material AFTER the Hebrew span to reason from?"""
    i = note_text.find(hebrew_span)
    tail = note_text[i + len(hebrew_span):] if i >= 0 else note_text
    return bool(LATIN.search(tail))

def _call(model, base, note, key):
    r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": model, "temperature": 0,
                         "messages": [{"role": "user", "content": _PROMPT.format(base=base, note=note)}]},
                   timeout=180).json()
    if "error" in r: return {"model": model, "error": str(r["error"])[:120]}
    c = r["choices"][0]["message"]["content"]; c = c[c.find("{"):c.rfind("}") + 1]
    d = json.loads(c); u = r.get("usage", {})
    return {"model": model, "corrected": d.get("corrected_hebrew", ""), "reasoning": d.get("reasoning", ""),
            "cost": u.get("cost", 0.0), "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens")}

def escalate_span(base_hebrew, note_text, key, models=None):
    """Returns a review-queue PROPOSAL. Only call when has_adjudicating_material() is True."""
    models = models or PANEL
    votes = [_call(m, base_hebrew, note_text, key) for m in models]
    ok = [v for v in votes if "corrected" in v]
    corr = [v["corrected"] for v in ok]
    unanimous = len(set(corr)) == 1 and len(corr) == len(models)
    proposal = corr[0] if unanimous else (max(set(corr), key=corr.count) if corr else base_hebrew)
    return {
        "base": base_hebrew, "proposal": proposal, "unanimous": unanimous,
        "provenance": "adjudicated-by-frontier-with-bilingual-context",
        "auto_acceptable": unanimous,                    # trust dial: default only unanimous
        "votes": [{"model": v.get("model"), "corrected": v.get("corrected"), "reasoning": v.get("reasoning")} for v in votes],
        "cost_openrouter": round(sum(v.get("cost", 0.0) for v in ok), 6),
        "tokens": {v["model"]: (v.get("prompt_tokens"), v.get("completion_tokens")) for v in ok},  # for BYOK pricing
    }

def escalate_page_hebrew(notes, key, models=None):
    """For each Hebrew note with adjudicating material, produce a proposal. Notes without material are
    returned as review-queue items with no panel (per the precondition)."""
    out = []
    for n in notes:
        m = HEB.search(n["text"])
        if not m: continue
        span = HEB.search(n["text"]);
        hspan = re.search(r"[֐-׿][֐-׿ ]*", n["text"]).group(0).strip()
        if has_adjudicating_material(n["text"], hspan):
            p = escalate_span(hspan, n["text"], key, models); p["marker"] = n["marker"]; out.append(p)
        else:
            out.append({"marker": n["marker"], "base": hspan, "proposal": None,
                        "provenance": "review-queue-no-adjudicating-material", "unanimous": False, "auto_acceptable": False})
    return out

if __name__ == "__main__":
    import sys
    key = os.environ["OPENROUTER_KEY"]
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    tests = [
        {"marker": "[^13]", "text": "סגר עליה clausit viam illis, Pagninus, præclusit sese illis, Vatablus."},
        {"marker": "[^2]",  "text": "ריח הניח odorem quietis, Pagninus, Montanus, Munster, &c."},
        {"marker": "[^9]",  "text": "וכי"},   # no adjudicating material -> review queue, no panel
    ]
    for p in escalate_page_hebrew(tests, key):
        print(f"{p['marker']}: base={p['base']} -> proposal={p.get('proposal')} "
              f"unanimous={p.get('unanimous')} prov={p['provenance']} cost=${p.get('cost_openrouter',0)}")
