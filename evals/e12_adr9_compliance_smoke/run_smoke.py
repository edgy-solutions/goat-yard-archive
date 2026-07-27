#!/usr/bin/env python3
"""E-12: ADR-0009 structured-output compliance smoke (read-only reconnaissance).

Answers the go/no-go question for the ADR-0009 typed-schema migration BEFORE the
phase starts: can DeepSeek reliably HOLD a nested three-zone answer schema, and
does putting quotes in a dedicated `gill_quote` field make the model more
verbatim than free prose does? Tests current-vs-latest DeepSeek in the same run,
since the migration is the natural moment to move the generator if newer wins.

This is a capability probe, NOT the migration:
  - standalone script, no bot.py / serving-path changes, no baseline dependency
  - raw structured-output compliance = the CONSERVATIVE floor (BAML's retry/repair
    layer can only raise it; if raw clears the bar, BAML clears it)
  - results committed as the E-12 probe artifact feeding the ADR-0009 go/no-go note

Four questions (ADR-0009 forcing lines). This script lands Q1 (compliance) and
Q2 (field-verbatim-fidelity) with data captured for Q3/Q4:
  Q1 GO/NO-GO: schema-valid + correct field usage across 5 hard shapes, N per shape
  Q2 FIDELITY: is `gill_quote` verbatim against source? (the measurement-integrity payoff)
  Q3 FLUENCY:  reassembled-output readability (rendered sample saved for human read)
  Q4 ZONE-3:   does characterization leak into framing fields when no field invites it?

Usage:
  python evals/e12_adr9_compliance_smoke/run_smoke.py --n 8 \
      --models deepseek/deepseek-chat deepseek/deepseek-v3.2 deepseek/deepseek-v4-pro
"""
import argparse, json, os, re, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
load_dotenv(REPO / ".env")
OR_KEY = os.getenv("OPENROUTER_API_KEY")
OR_URL = "https://openrouter.ai/api/v1/chat/completions"

# ---------------------------------------------------------------------------
# Draft ADR-0009 answer schema. Three zones as typed fields:
#   refusal      -> Zone-1 honest scope (mode + gap statement), null on a real answer
#   zone1_bridge -> Zone-1 navigational framing that OWNS the modern-term<->Gill bridge
#   segments     -> Zone-2 body: plain-voice framing + VERBATIM gill_quote + sid
# There is deliberately NO field for characterizing Gill's position (Zone 3) —
# Q4 watches whether the impulse leaks into `framing` when the schema starves it.
# ---------------------------------------------------------------------------
SCHEMA = {
    "name": "gill_answer",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "refusal": {
                "type": ["object", "null"],
                "properties": {
                    "mode": {"type": "string", "enum": ["flat", "informative"]},
                    "gap_statement": {"type": "string"},
                },
                "required": ["mode", "gap_statement"],
                "additionalProperties": False,
            },
            "zone1_bridge": {"type": ["string", "null"]},
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "framing": {"type": "string"},
                        "gill_quote": {"type": "string"},
                        "sid": {"type": "string"},
                    },
                    "required": ["framing", "gill_quote", "sid"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["refusal", "zone1_bridge", "segments"],
        "additionalProperties": False,
    },
}

SYSTEM = """You surface John Gill's 18th-century commentary in a strict typed schema.
Fill exactly these fields:
- refusal: null when the retrieved context substantively answers the question. When it
  cannot, set refusal.mode = "flat" (question is off-domain / category error / no
  doctrinal or biblical connection to any retrieved chunk) or "informative" (the context
  is topically adjacent but does not directly address the specific subject asked), and
  refusal.gap_statement = an honest Zone-1 scope sentence naming what the indexed corpus
  does NOT contain (e.g. "the indexed corpus does not contain Gill's commentary on X").
- zone1_bridge: null unless the user's term is modern/anachronistic relative to Gill's
  vocabulary; then a plain-voice sentence owning the bridge between the modern term and
  the actual indexed material.
- segments: the body. Each segment = { framing: your brief plain modern connective voice,
  gill_quote: Gill's words VERBATIM from the provided context (exact spelling, punctuation,
  and any Hebrew characters preserved character-for-character), sid: the [SENTENCE_ID] the
  quote came from }. For a flat refusal, segments is empty. For an informative refusal you
  MAY include honestly-labelled adjacent material as segments (each cited).
NEVER characterize Gill's position, stance, or view in any field. Quote him; do not
summarize or interpret him. Output only the schema.

Return ONLY a single JSON object of exactly this shape (no prose, no markdown fence):
{
  "refusal": null | {"mode": "flat" | "informative", "gap_statement": "string"},
  "zone1_bridge": null | "string",
  "segments": [ {"framing": "string", "gill_quote": "string", "sid": "[SENTENCE_ID]"} ]
}
Every key MUST be present (use null / [] where empty). No additional keys."""


def _fmt_chunks(chunks):
    out = []
    for i, c in enumerate(chunks):
        ref = c.get("verse_ref") or f"CHUNK_{i}"
        sid = "[" + re.sub(r"[^A-Z0-9]+", "_", ref.upper()).strip("_") + f"_S{i:02d}]"
        out.append(f"{sid} ({ref}): {c.get('content','')}")
    return "\n\n".join(out)


def _normalize(t):
    t = (t or "")
    t = re.sub(r"\[\^[A-Za-z0-9_]+\]", "", t)
    t = t.lower()
    t = re.sub(r"[^\w\s֐-׿]", " ", t, flags=re.UNICODE)  # keep Hebrew block
    return re.sub(r"\s+", " ", t).strip()


def _verbatim(quote, source_norm):
    q = _normalize(quote)
    if len(q) < 8:
        return False
    if q in source_norm:
        return True
    # difflib coverage fallback
    from difflib import SequenceMatcher
    sm = SequenceMatcher(None, q, source_norm)
    matched = sum(b.size for b in sm.get_matching_blocks())
    return matched / max(1, len(q)) >= 0.85


# 5 hard shapes. `expect` is the correct-field-usage predicate for Q1.
def build_shapes(chunks):
    cov = chunks["covenant"]["chunks"]
    hal = chunks["hallel"]["chunks"]
    aqu = chunks["aquinas"]["chunks"]
    exc = chunks["exclusive"]["chunks"]

    def has_segs(o, n): return isinstance(o.get("segments"), list) and len(o["segments"]) >= n

    return [
        {"key": "A_multiphrase", "question": "What does Gill say about the covenant of grace?",
         "chunks": cov,
         "expect": lambda o: o.get("refusal") in (None, {}) and has_segs(o, 3),
         "note": "answer body, >=3 cited segments"},
        {"key": "B_informative_refusal", "question": "what did gill believe about aquinas",
         "chunks": aqu,
         "expect": lambda o: isinstance(o.get("refusal"), dict)
                   and o["refusal"].get("mode") == "informative"
                   and bool((o["refusal"].get("gap_statement") or "").strip()),
         "note": "refusal.mode=informative + gap statement"},
        {"key": "C_flat_refusal", "question": "How do I center a div in CSS?",
         "chunks": cov[:3],  # off-topic context
         "expect": lambda o: isinstance(o.get("refusal"), dict)
                   and o["refusal"].get("mode") == "flat"
                   and not (o.get("segments") or []),
         "note": "refusal.mode=flat + empty segments"},
        {"key": "D_zone1_bridge", "question": "exclusive psalmody?",
         "chunks": exc + hal[:4],
         "expect": lambda o: bool((o.get("zone1_bridge") or "").strip()) and has_segs(o, 1),
         "note": "zone1_bridge owns modern-term + >=1 segment"},
        {"key": "E_hebrew_quote", "question": "What psalms did Christ and the disciples sing?",
         "chunks": hal,
         "expect": lambda o: any("א" <= ch <= "ת" for seg in (o.get("segments") or [])
                                 for ch in (seg.get("gill_quote") or "")),
         "note": "a segment gill_quote preserves Hebrew characters"},
    ]


def _post(model, question, chunks, response_format, timeout):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"QUESTION: {question}\n\nRETRIEVED CONTEXT:\n{_fmt_chunks(chunks)}"},
        ],
        "temperature": 0.1,
    }
    if response_format:
        payload["response_format"] = response_format
    headers = {"Authorization": f"Bearer {OR_KEY}", "Content-Type": "application/json"}
    t0 = time.perf_counter()
    r = httpx.post(OR_URL, headers=headers, json=payload, timeout=timeout)
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        return {"ok_http": False, "err": f"HTTP {r.status_code}: {r.text[:180]}", "dt": dt}
    content = r.json()["choices"][0]["message"]["content"]
    return {"ok_http": True, "content": content, "dt": dt}


def call_model(model, question, chunks, timeout=180):
    """Prefer enforced json_schema; fall back to json_object (schema is also in the
    prompt). Records which mode actually served, so the go/no-go note can say whether
    a model needs enforcement or self-complies."""
    try:
        r = _post(model, question, chunks,
                  {"type": "json_schema", "json_schema": SCHEMA}, timeout)
        if r["ok_http"]:
            r["mode"] = "json_schema"; return r
        # json_schema unsupported by this model -> honest fallback to json_object
        if "json_schema" in (r.get("err") or "") or "response format" in (r.get("err") or "").lower():
            r2 = _post(model, question, chunks, {"type": "json_object"}, timeout)
            r2["mode"] = "json_object"; return r2
        return r
    except Exception as e:
        return {"ok_http": False, "err": f"{type(e).__name__}: {e}", "dt": 0.0}


def _schema_valid(o):
    """Structural validity of the draft schema (json_object mode is not provider-enforced)."""
    if not isinstance(o, dict):
        return False
    if set(o.keys()) != {"refusal", "zone1_bridge", "segments"}:
        return False
    ref = o["refusal"]
    if ref is not None:
        if not isinstance(ref, dict) or set(ref.keys()) != {"mode", "gap_statement"}:
            return False
        if ref["mode"] not in ("flat", "informative") or not isinstance(ref["gap_statement"], str):
            return False
    if o["zone1_bridge"] is not None and not isinstance(o["zone1_bridge"], str):
        return False
    segs = o["segments"]
    if not isinstance(segs, list):
        return False
    for s in segs:
        if not isinstance(s, dict) or set(s.keys()) != {"framing", "gill_quote", "sid"}:
            return False
        if not all(isinstance(s[k], str) for k in ("framing", "gill_quote", "sid")):
            return False
    return True


def score_one(shape, resp, source_norm):
    row = {"ok_http": resp.get("ok_http"), "mode": resp.get("mode"), "parse": False,
           "schema_valid": False, "field_ok": False, "verbatim_ok": None, "leak": None,
           "err": resp.get("err")}
    if not resp.get("ok_http"):
        return row
    content = (resp.get("content") or "").strip()
    # tolerate a stray ```json fence
    content = re.sub(r"^```(?:json)?|```$", "", content).strip()
    try:
        obj = json.loads(content)
        row["parse"] = True
    except Exception as e:
        row["err"] = f"JSON parse: {e}"; return row
    row["schema_valid"] = _schema_valid(obj)
    row["obj"] = obj  # kept for Q3 rendering + Q4 leak-text review
    try:
        row["field_ok"] = bool(row["schema_valid"] and shape["expect"](obj))
    except Exception as e:
        row["err"] = f"expect: {e}"
    # Q2 fidelity: every gill_quote verbatim against provided source
    segs = obj.get("segments") or []
    if segs:
        row["verbatim_ok"] = all(_verbatim(s.get("gill_quote", ""), source_norm) for s in segs)
    # Q4 zone-3 leak heuristic in framing fields (capture the offending text for review)
    leak_re = re.compile(r"gill\s+(?:\w+\s+){0,2}(distinguishes|affirms|argues|holds|teaches|believes|maintains|views|takes the|supports|advocates|rejects|denies|opposes|condemns)", re.I)
    fr = " ".join([(s.get("framing") or "") for s in segs] + [(obj.get("zone1_bridge") or "")])
    m = leak_re.search(fr)
    row["leak"] = bool(m)
    row["leak_text"] = fr[max(0, m.start() - 20): m.end() + 40] if m else None
    return row


def render(obj):
    """Q3: assemble the structured answer into reader-facing prose, the way a trivial
    ADR-0009 assembler would. Fluency of THIS is what the John 6:37 A/B judges."""
    parts = []
    ref = obj.get("refusal")
    if isinstance(ref, dict) and (ref.get("gap_statement") or "").strip():
        parts.append(ref["gap_statement"].strip())
    if (obj.get("zone1_bridge") or "").strip():
        parts.append(obj["zone1_bridge"].strip())
    for s in (obj.get("segments") or []):
        fr = (s.get("framing") or "").strip()
        q = (s.get("gill_quote") or "").strip()
        sid = (s.get("sid") or "").strip()
        seg = (fr + " " if fr else "") + (f'"{q}" {sid}' if q else "")
        if seg.strip():
            parts.append(seg.strip())
    return "\n\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--models", nargs="+",
                    default=["deepseek/deepseek-chat", "deepseek/deepseek-v3.2", "deepseek/deepseek-v4-pro"])
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()

    chunks = json.load(open(HERE / "chunks.json", encoding="utf-8"))
    shapes = build_shapes(chunks)
    src_norm = {s["key"]: _normalize(" ".join(c.get("content", "") for c in s["chunks"])) for s in shapes}

    jobs = []
    for model in args.models:
        for shape in shapes:
            for i in range(args.n):
                jobs.append((model, shape, i))

    print(f"E-12 compliance smoke: {len(args.models)} models x {len(shapes)} shapes x N={args.n} = {len(jobs)} calls")
    results = {m: {s["key"]: [] for s in shapes} for m in args.models}

    def run(job):
        model, shape, i = job
        resp = call_model(model, shape["question"], shape["chunks"])
        return model, shape["key"], score_one(shape, resp, src_norm[shape["key"]])

    done = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(run, j) for j in jobs]
        for f in as_completed(futs):
            model, key, row = f.result()
            results[model][key].append(row)
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(jobs)}", flush=True)

    # Aggregate
    summary = {}
    print("\n" + "=" * 78)
    for model in args.models:
        print(f"\nMODEL: {model}")
        modes = {r.get("mode") for s in shapes for r in results[model][s["key"]]}
        print(f"  serving mode(s): {modes}")
        msum = {}
        for shape in shapes:
            rows = results[model][shape["key"]]
            n = len(rows)
            sv = sum(1 for r in rows if r["schema_valid"])
            valid = sum(1 for r in rows if r["field_ok"])
            parse = sum(1 for r in rows if r["parse"])
            vb = [r["verbatim_ok"] for r in rows if r["verbatim_ok"] is not None]
            vb_ok = sum(1 for x in vb if x)
            leaks = sum(1 for r in rows if r.get("leak"))
            msum[shape["key"]] = {"n": n, "parse": parse, "schema_valid": sv, "field_ok": valid,
                                  "verbatim_ok": f"{vb_ok}/{len(vb)}" if vb else "n/a",
                                  "zone3_leak": leaks}
            print(f"  {shape['key']:24} field-ok {valid}/{n}  schema {sv}/{n}  parse {parse}/{n}  "
                  f"verbatim {f'{vb_ok}/{len(vb)}' if vb else 'n/a':>6}  z3-leak {leaks}/{n}   [{shape['note']}]")
        summary[model] = msum

    # Q3 fluency: render one representative answer per (model, shape) for a human read.
    # Q4: collect every zone-3 leak instance with its offending text.
    render_md = ["# E-12 Q3 fluency — rendered structured answers (read these as prose)\n"]
    leaks = ["# E-12 Q4 zone-3 leaks — characterization that reached a framing field\n"]
    for shape in shapes:
        render_md.append(f"\n## Shape {shape['key']} — {shape['note']}\nQ: {shape['question']}\n")
        for model in args.models:
            rows = results[model][shape["key"]]
            pick = next((r for r in rows if r.get("field_ok") and r.get("obj")), None) \
                or next((r for r in rows if r.get("parse") and r.get("obj")), None)
            render_md.append(f"\n### {model}\n")
            render_md.append("```\n" + (render(pick["obj"]) if pick else "(no parseable output)") + "\n```\n")
            for r in rows:
                if r.get("leak"):
                    leaks.append(f"- **{model}** / {shape['key']}: `{r.get('leak_text')}`")
    (HERE / "rendered_samples.md").write_text("\n".join(render_md), encoding="utf-8")
    (HERE / "zone3_leaks.md").write_text("\n".join(leaks) + "\n", encoding="utf-8")

    # Strip the bulky per-row obj from the persisted raw (kept only in-memory for rendering).
    for m in results:
        for k in results[m]:
            for r in results[m][k]:
                r.pop("obj", None)
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "n": args.n, "models": args.models, "summary": summary,
           "raw": {m: {k: results[m][k] for k in results[m]} for m in args.models}}
    (HERE / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWritten: {HERE/'results.json'}\n         {HERE/'rendered_samples.md'}\n         {HERE/'zone3_leaks.md'}")


if __name__ == "__main__":
    main()
