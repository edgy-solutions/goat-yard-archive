"""Per-page apparatus re-extraction — the vertical slice: page image -> clean canonical footnote
markdown. Wires the three validated pieces: deterministic CV presplit (cv_footnote_presplit) ->
local VL transcription (profile model) -> deterministic assembler (canonical [^N] markers,
furniture removal, fail-loud stitch guard). NO book-specific facts here — all read from the profile.

Passes are generic; book_profile.gill.yaml makes them Gill-specific. Host is infra (env OLLAMA_HOST).
"""
import sys, os, re, io, base64, argparse
from pathlib import Path
import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cv_footnote_presplit as presplit
import assembler as A

TRANSCRIBE_PROMPT = (
    "This image is a strip of footnotes from an early Bible commentary, already cropped and placed "
    "in correct reading order. Transcribe EVERY footnote verbatim, one footnote per line. Each "
    "footnote begins with a single lowercase letter marker (a, b, c, ...) — keep that marker at the "
    "line start. Transcribe Latin, English, Greek and Hebrew exactly as printed; output Hebrew in "
    "Hebrew script (right-to-left). Do NOT translate, summarize, renumber, or invent. Omit running "
    "page-headers and signature marks. Output only the footnote lines.")

# few-shot layout note, appended when the profile declares the compositor's convention. This is the
# BELT to the CV note-start detector's suspenders (hanging_indent.py): it discourages the two model
# slips the fixtures showed — merging several marked footnotes into one line (segmentation-collapse),
# and pulling a page-signature into a note (furniture leak). Validating its EFFECT on extraction is a
# separate N>=6 gate (prompt-changes-shift-verbatim-boundary); this only assembles it from the profile.
def build_transcribe_prompt(profile):
    p = TRANSCRIBE_PROMPT
    cc = profile.get("compositor_conventions") or {}
    if cc.get("note_layout") == "hanging_indent":
        p += ("\n\nLAYOUT — the notes are set as a HANGING INDENT: a raised marker at the left, then "
              "the note text; a long note's continuation lines wrap WITHOUT a marker. EVERY marker "
              "begins a NEW footnote — never merge two marked footnotes onto one line, and never split "
              "one footnote across output lines. Example:\n"
              "  a First note, long enough that it\n"
              "    wraps to a line with no marker.\n"
              "  b Second note.")
    furn = profile.get("furniture") or {}
    sig = furn.get("signature_example") or "VOL. I.—OLD TEST. 4 D"
    p += (f"\n\nNEVER emit page furniture as a note: running headers, catchwords at the very bottom, "
          f"or printer signature marks (e.g. \"{sig}\") are NOT footnotes.")
    return p

def _b64_png(img):
    buf = io.BytesIO(); img.save(buf, format="PNG"); return base64.b64encode(buf.getvalue()).decode()

def transcribe(strip_img, profile, host):
    t = profile["transcription"]
    r = httpx.post(f"http://{host}:11434/api/generate",
        json={"model": t["model"], "prompt": build_transcribe_prompt(profile), "images": [_b64_png(strip_img)],
              "think": t.get("think", False), "stream": False,
              "options": {"num_ctx": t.get("num_ctx", 16384), "temperature": 0}}, timeout=900)
    d = r.json()
    return (d.get("response", "") or ""), d.get("done_reason")

# config-v2 Seam 1: transcription through BAML -> typed Note[]. The layout hint + signature are assembled
# from the SAME profile fields build_transcribe_prompt uses (no book facts baked into the BAML), so the two
# seams feed the model the same substance; only the transport (/v1) and the return shape (typed) differ. The
# NoteStatus enum members map back to the snake_case contract strings the assembler expects.
_STATUS_SNAKE = {"Complete": "complete", "TruncatedTop": "truncated_top", "TruncatedBottom": "truncated_bottom",
                 "TruncatedSide": "truncated_side", "NoFootnotePresent": "no_footnote_present", "Unreadable": "unreadable"}

def _layout_hint(profile):
    cc = profile.get("compositor_conventions") or {}
    if cc.get("note_layout") == "hanging_indent":
        return ("LAYOUT — the notes are set as a HANGING INDENT: a raised marker at the left, then the note "
                "text; a long note's continuation lines wrap WITHOUT a marker. EVERY marker begins a NEW "
                "footnote — never merge two marked footnotes into one note, and never split one across notes.")
    return None

def transcribe_baml(strip_img, profile):
    """Seam 1 transcription: returns (typed_note_dicts, done_reason). BAML MODULAR request/parse — BAML builds
    the prompt (with the typed-Note[] output schema) and parses the reply into the typed contract, but the
    request is SENT over Ollama's NATIVE /api/chat with think:false. This is deliberate: qwen3's thinking is a
    request-level toggle that Ollama's OpenAI-compatible /v1 endpoint DROPS (prompt `/no_think` is only a soft
    hint qwen3 doesn't always honor -> random empty replies), whereas /api/chat honors think:false — the same
    control the frozen /api/generate config used, which is why it never had empties. Typed contract preserved,
    no proxy. The BAML client (model qwen3.6-16k:35b, host .169) stays the single source of model+host+prompt."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from baml_client.sync_client import b
    from baml_py import Image as BamlImage
    sig = (profile.get("furniture") or {}).get("signature_example") or "VOL. I.—OLD TEST. 4 D"
    img = BamlImage.from_base64("image/png", _b64_png(strip_img))
    req = b.request.TranscribeApparatus(img, _layout_hint(profile), sig)     # BAML builds prompt + output schema
    body = req.body.json() if hasattr(req.body, "json") else req.body
    msg = body["messages"][0]                                                # one user message: text(s) + image
    texts = [p["text"] for p in msg["content"] if p.get("type") == "text"]
    imgs = [p["image_url"]["url"].split(",", 1)[1] for p in msg["content"] if p.get("type") == "image_url"]
    api_chat = str(req.url).replace("/v1/chat/completions", "/api/chat")     # native endpoint, same host
    r = httpx.post(api_chat, timeout=900, json={
        "model": body["model"], "think": False, "stream": False,
        "options": {"temperature": 0}, "messages": [{"role": "user", "content": "\n".join(texts), "images": imgs}]})
    content = ((r.json().get("message") or {}).get("content") or "").strip()
    if not content:
        return [], "empty"
    notes = b.parse.TranscribeApparatus(content)                            # BAML parses -> typed Note[]
    out = [{"text": n.text, "marker_letter": n.marker_letter,
            "status": _STATUS_SNAKE.get(getattr(n.status, "value", str(n.status)), "complete"),
            "partial": bool(n.partial)} for n in notes]
    return out, "baml-api-chat"

def _body_before_defs(md):
    return A.split_body_defs(md)[0]     # robust body/def split (all zoo def formats)

def extract_page(image_path, profile, host, body_md=None, seam="httpx", hebrew=False):
    page = re.search(r"page(\d+)", Path(image_path).name)
    page = page.group(1) if page else "?"
    # FRONT-MATTER BOUNDARY (book fact): images before commentary_start_page have no apparatus —
    # skip extraction entirely so body prose is never manufactured into footnotes (see profile).
    csp = profile.get("layout", {}).get("commentary_start_page")
    if csp and page != "?" and int(page) < int(csp):
        return {"page": page, "status": "no_apparatus", "notes": [], "n_notes": 0,
                "reason": "front_matter", "presplit_info": None}
    up = profile["transcription"].get("apparatus_upscale", 2)
    strip, info = presplit.presplit(str(image_path), upscale=up)
    if strip is None:
        return {"page": page, "status": "no_apparatus", "notes": [], "info": info}
    # SEAM: "baml" = config-v2 typed Note[] (assembler consumes typed notes, persists marker_letter+status);
    # "httpx" = frozen free-text line-parse. Both feed the same strip + profile substance to the same weights.
    if seam == "baml":
        typed, done = transcribe_baml(strip, profile)
        r = A.canonicalize_typed_notes(typed, profile)
    else:
        resp, done = transcribe(strip, profile, host)
        r = A.canonicalize_page(resp.splitlines(), profile)
    # config-v2 Hebrew layer (opt-in): attach per-note hebrew_verdict (script/glyph/nikud/span-box).
    # Non-destructive — the note text is untouched, so this never confounds the reproduction born-test.
    hebrew_summary = None
    if hebrew:
        import hebrew_layer
        r["notes"], hebrew_summary = hebrew_layer.apply(strip, r["notes"], profile)
    # REFUSAL-HONOR (3rd sibling of the "nothing here" law): the model's own "no footnotes here" is a
    # no_apparatus SIGNAL, not note content — else its honesty ships as a fabricated note (p4).
    import refusal_guard
    is_ref, phrase = refusal_guard.check_notes(r["notes"])
    if is_ref:
        return {"page": page, "status": "no_apparatus", "notes": [], "n_notes": 0,
                "reason": "model-refusal", "refusal_phrase": phrase, "done_reason": done,
                "presplit_info": info}
    recrop_changes = []
    if profile["transcription"].get("recrop_enabled"):   # DISABLED: net-negative (context amputation)
        import hebrew_recrop as hr
        recrop_changes = hr.recrop_nonlatin(image_path, r["notes"], profile, host)
    # CROP GATE (before stitch/anchor): the "nothing here" channel. A blank crop with notes is
    # FABRICATION (p86 front-matter -> 18 confabulated); ink-but-no-notes is a MISS. Fail-loud, and
    # runs BEFORE the stitch/anchor passes (which assume real notes). See crop_gate.py.
    import crop_gate
    floor = profile["transcription"].get("crop_content_floor", crop_gate.DEFAULT_FLOOR)
    kept, gate_status, gate_flag = crop_gate.gate_notes(strip, r["notes"], floor)
    if gate_status != "ok":
        return {"page": page, "status": gate_status, "done_reason": done, "n_notes": len(kept),
                "violations": [], "dropped_furniture": r.get("dropped_furniture", []), "notes": kept,
                "markdown": "", "presplit_info": info, "anchor_match": None,
                "recrop_changes": recrop_changes, "crop_gate": gate_flag}
    viol = A.assert_no_text_split(r["notes"], profile)
    md = "\n".join(f"{n['marker']}: {n['text']}" for n in r["notes"])
    status = "STITCH_VIOLATION" if viol else "OK"
    match = None
    if body_md and Path(body_md).exists():
        match = A.match_notes_to_anchors(r["notes"], _body_before_defs(Path(body_md).read_text(encoding="utf-8")), profile)
        if match["status"] != "OK" and status == "OK":
            status = f"ANCHOR_{match['status']}"     # e.g. ANCHOR_FLAGGED: notes with no body anchor
    return {"page": page, "status": status, "done_reason": done, "n_notes": len(r["notes"]),
            "violations": viol, "dropped_furniture": r["dropped_furniture"], "notes": r["notes"],
            "markdown": md, "presplit_info": info, "anchor_match": match, "recrop_changes": recrop_changes,
            "hebrew_summary": hebrew_summary, "marker_leaks": r.get("marker_leaks", 0)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="page image path(s)")
    ap.add_argument("--profile", default=str(Path(__file__).parent / "book_profile.gill.yaml"))
    ap.add_argument("--host", default=os.getenv("OLLAMA_HOST", "192.168.1.179"))
    ap.add_argument("--body-dir", default="", help="dir of body .md files (for anchor matching)")
    a = ap.parse_args()
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception: pass
    profile = A.load_profile(a.profile)
    for img in a.images:
        body_md = ""
        if a.body_dir:
            body_md = str(Path(a.body_dir) / (Path(img).stem + ".md"))
        res = extract_page(img, profile, a.host, body_md=body_md or None)
        print(f"\n{'='*66}\np{res['page']}: {res['status']}  notes={res.get('n_notes')} "
              f"done={res.get('done_reason')}  dropped_furniture={len(res.get('dropped_furniture',[]))}")
        if res.get("violations"): print("  !! STITCH VIOLATIONS:", res["violations"])
        if res.get("recrop_changes"): print("  hi-res recrop:", [f"{c['old']}→{c['new']}" for c in res["recrop_changes"]])
        m = res.get("anchor_match")
        if m: print(f"  anchor-match: {m['status']}  links={len(m['links'])} anchors={m['n_anchors']} "
                    f"unanchored={len(m['unanchored'])}"
                    + (f"  gaps={[u.get('expected_letter') for u in m['unanchored']]}" if m['unanchored'] else ""))
        print("-" * 66); print(res.get("markdown", ""))

if __name__ == "__main__":
    main()
