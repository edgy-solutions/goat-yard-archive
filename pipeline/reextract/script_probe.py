"""SCRIPT-PRESENCE PROBE BATTERY (Build 1) — disposes caveat #1's detection half. After extraction, ask
the model a SEPARATE, minimal question about a strip: does non-Latin script appear? Three probe forms,
each run as an INDEPENDENT pass (fresh context — an answer in context contaminates the next question;
share computation via the image prefix, never share context):
  (a) yesno      — "is Hebrew script present?"      (coarsest)
  (b) scriptlist — "which scripts appear?"          (predicted best: catches partial loss, no counting)
  (c) counts     — "how many Hebrew words?"         (predicted worst: individuation drifts to the hard task)

Wording EXCLUDES transliteration (the p674 trap: `Maacolot Asurot` is Latin letters, not Hebrew script).
Structured [image][question] so the image prefix is identical across probes for prefix-cache reuse —
verify_prefix_cache() measures whether our Ollama stack actually reuses it before we claim the economics.
Production keeps whichever probe clears the jaws, wired as MISS_SUSPECT reconciliation: probe says script
present, transcription contains none -> flag (the model's own two answers indicting each other).
"""
import re, time, base64, io
import httpx

def _b64(strip):
    buf = io.BytesIO(); strip.save(buf, format="PNG"); return base64.b64encode(buf.getvalue()).decode()

def _ask(strip_b64, question, host, model, num_ctx=2048):
    r = httpx.post(f"http://{host}:11434/api/generate",
        json={"model": model, "prompt": question, "images": [strip_b64], "think": False, "stream": False,
              "options": {"num_ctx": num_ctx, "temperature": 0}}, timeout=300).json()
    return (r.get("response", "") or "").strip(), r

Q_YESNO = ("Does this image contain any HEBREW-SCRIPT letters (the Hebrew alphabet itself, right-to-left)? "
           "Words spelled in Latin/Roman letters — even if they are transliterated Hebrew or Rabbinic names "
           "— do NOT count. Answer with only one word: YES or NO.")
Q_LIST = ("Which of these WRITING SYSTEMS actually appear in this image, judged by the letter-shapes used? "
          "Choose from: Latin, Hebrew, Greek, Arabic. A word transliterated into Latin/Roman letters counts "
          "as Latin, NOT as the language it transliterates. Reply with only a comma-separated list.")
Q_COUNT = ("How many separate HEBREW-SCRIPT words (written in the Hebrew alphabet, not Latin letters) appear "
           "in this image? Reply with only an integer.")

_SCRIPTS = ("latin", "hebrew", "greek", "arabic")

def probe_yesno(strip_b64, host, model):
    resp, _ = _ask(strip_b64, Q_YESNO, host, model)
    return {"probe": "yesno", "hebrew": resp.strip().lower().startswith("y"), "raw": resp[:60]}

def probe_scriptlist(strip_b64, host, model):
    resp, _ = _ask(strip_b64, Q_LIST, host, model)
    low = resp.lower()
    found = {s: (s in low) for s in _SCRIPTS}
    return {"probe": "scriptlist", **found, "raw": resp[:80]}

def probe_counts(strip_b64, host, model):
    resp, _ = _ask(strip_b64, Q_COUNT, host, model)
    m = re.search(r"\d+", resp)
    n = int(m.group(0)) if m else 0
    return {"probe": "counts", "hebrew": n > 0, "n_hebrew": n, "raw": resp[:40]}

def run_battery(strip, host, model):
    """All three probes, each a fresh independent pass over the same image."""
    b = _b64(strip)
    return {"yesno": probe_yesno(b, host, model), "scriptlist": probe_scriptlist(b, host, model),
            "counts": probe_counts(b, host, model)}

def verify_prefix_cache(strip, host, model):
    """Two identical [image][question] calls; if the stack reuses the image prefix, the 2nd call's
    prompt_eval_duration drops sharply. Prints both so the economics claim rests on measurement."""
    b = _b64(strip)
    out = []
    for i in range(2):
        t0 = time.time(); _, r = _ask(b, Q_YESNO, host, model)
        out.append({"call": i + 1, "wall_s": round(time.time() - t0, 2),
                    "prompt_eval_ms": round(r.get("prompt_eval_duration", 0) / 1e6),
                    "prompt_eval_count": r.get("prompt_eval_count"),
                    "load_ms": round(r.get("load_duration", 0) / 1e6)})
    return out
