"""APPARATUS ROUTER — the model-dispatch config, driven by a MEASURED signature, never a page list.

The bakeoff settled the trade-off: gemma reads Hebrew + keeps lemmas best; qwen3.8 segments best. No
single model wins both, so route:
  - PRIMARY = gemma (best Hebrew/lemma, decent segmentation).
  - If gemma's note-count materially diverges from the DETERMINISTIC CV note-start count
    (hanging_indent — the arbiter), cross-check the FALLBACK = qwen3.8 (8/8 segmentation) and keep
    whichever reading's count better matches the CV structure.
  - If NEITHER matches the CV count, the segmentation is unrecoverable by either model -> QUEUE.

Dispatch is on the measured collapse signature, so vol2's collapse pages route themselves — no
hardcoded 129/146 (deterministic-property-not-a-model / constrain-direction). Readers injected ->
born-testable; the real readers are gemma/qwen3.8 VLM adapters (extract_apparatus.transcribe with the
model overridden). Residual disagreement AFTER routing goes to the agreement_ladder -> blind_retry chain.
"""
import hanging_indent as hi

def _matches(n, cv, tol_frac=0.25, tol_min=2):
    """Does a reader's note-count n match the CV structural count cv, within tolerance?"""
    return abs(n - cv) <= max(tol_min, round(tol_frac * cv))

def route(strip, primary_reader, fallback_reader, cv_count=None):
    """Route one strip. Readers are fn(strip)->list-of-notes. Returns:
      notes, route ('primary'|'fallback'|'queue'), cv_count, queued, primary_n, fallback_n.
    fallback_reader is NOT called when the primary already matches the CV count (cost + independence)."""
    if cv_count is None:
        cv_count, _, _ = hi.count_notes(strip)
    primary = primary_reader(strip)
    if cv_count < 3 or _matches(len(primary), cv_count):
        return {"notes": primary, "route": "primary", "cv_count": cv_count, "queued": False,
                "primary_n": len(primary), "fallback_n": None}
    fallback = fallback_reader(strip)
    label, notes = min((("primary", primary), ("fallback", fallback)),
                       key=lambda kv: abs(len(kv[1]) - cv_count))
    matched = _matches(len(notes), cv_count)
    return {"notes": notes, "route": label if matched else "queue", "cv_count": cv_count,
            "queued": not matched, "primary_n": len(primary), "fallback_n": len(fallback)}

if __name__ == "__main__":
    import sys
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    N = lambda k: (lambda strip: [{"text": f"n{i}"} for i in range(k)])   # stub reader of k notes
    # primary matches CV -> ship primary, fallback never called
    print("primary ok  ->", route("S", N(13), N(99), cv_count=13)["route"])
    # gemma undershoots (7), qwen3.8 recovers (13) -> fallback
    print("collapse    ->", route("S", N(7), N(13), cv_count=13)["route"])
    # both collapse (1, 2) vs cv 13 -> queue
    print("both fail   ->", route("S", N(1), N(2), cv_count=13)["route"])
