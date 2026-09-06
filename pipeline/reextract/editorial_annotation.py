"""Editorial annotation — ONE standoff record type for every editor's mark on the printed text. The
corpus keeps what the page PRINTED; the editor's reading lives beside it as an annotation at a position,
never as an edit to the bytes (the same standoff discipline as the anchor layer). Three kinds, one
schema — don't build three mechanisms:

  name-variant  — the page prints a variant spelling of a known name (page: Vatabius; intended: Vatablus)
  emendation    — legible pixels give a form the editor believes is a printer's error or ink artifact
                  (page: חח; intended: חת); the corpus records חח, the intended reading is the annotation
  unresolved    — an ink-destroyed glyph the editor could not read (the '?' marker); no proposed reading

Each record carries: span_id, kind, printed (what the corpus records), proposed (the editor's reading;
None for unresolved), basis (evidence-grounded = the pixels/CV/another witness support it; prior-grounded
= it rests on outside knowledge like a lexicon), basis_note, confidence, editor. `indexed_for_retrieval`
means the proposed reading is indexed ALONGSIDE the printed form so a search for the intended reading
finds the note; `display: "editorial"` so a reader always sees it marked as an editor's call, not the page.
Neither claim contaminates the other, and a later reader with better evidence can overturn the annotation
without touching the corpus."""
KINDS = ("name-variant", "emendation", "unresolved")
BASES = ("evidence-grounded", "prior-grounded")
CONFIDENCE = ("high", "moderate", "low")

def make_annotation(span_id, kind, printed, proposed, confidence, editor,
                    basis=None, basis_note=None, *, indexed_for_retrieval=True):
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}: {kind}")
    if confidence not in CONFIDENCE:
        raise ValueError(f"confidence must be one of {CONFIDENCE}: {confidence}")
    if kind == "unresolved":
        if proposed not in (None, "", "?"):
            raise ValueError("unresolved carries no proposed reading")
        proposed = None
    else:
        if not proposed:
            raise ValueError(f"{kind} requires a proposed reading")
        if basis not in BASES:
            raise ValueError(f"basis must be one of {BASES} for {kind}: {basis}")
    if not printed:
        raise ValueError("printed (what the corpus records) is required")
    return {
        "kind": "editorial_annotation", "span_id": span_id, "annotation_kind": kind,
        "printed": printed, "proposed": proposed, "basis": basis, "basis_note": basis_note,
        "confidence": confidence, "editor": editor,
        "indexed_for_retrieval": bool(indexed_for_retrieval), "display": "editorial",
    }

def validate(a):
    """A record is a well-formed standoff annotation (not an edit) iff it names its span, its kind, what
    the page printed, and — unless unresolved — a proposed reading with a grounded basis and confidence."""
    for f in ("span_id", "annotation_kind", "printed", "confidence", "editor", "display"):
        if f not in a: raise ValueError(f"missing field: {f}")
    if a["annotation_kind"] not in KINDS: raise ValueError("bad annotation_kind")
    if a["confidence"] not in CONFIDENCE: raise ValueError("bad confidence")
    if a["display"] != "editorial": raise ValueError("display must be 'editorial' (never presented as the page)")
    if not a["printed"]: raise ValueError("printed is required")
    if a["annotation_kind"] != "unresolved":
        if not a.get("proposed"): raise ValueError("proposed reading required (non-unresolved)")
        if a.get("basis") not in BASES: raise ValueError("basis must be evidence- or prior-grounded")
    return True
