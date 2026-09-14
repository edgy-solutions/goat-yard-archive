// Config-v2 Seam 1 — the apparatus transcription seam moves from raw httpx + free-text "one note per line"
// to a BAML typed Note[] return, so the assembler receives a typed list and a bad shape is UNREPRESENTABLE
// (a clipped note cannot come back as `complete`; a symbol/superscript marker cannot masquerade as a letter).
// The assembler stays pure code: canonical [^N] numbering, furniture removal, stitch guard, all downstream.
//
// MODEL PIN: the ApparatusReader client pins qwen3.6:35b — the FROZEN apparatus model the 47-page truthset
// was adjudicated against — so the seam swap is a transport change, not a model change, and the born-test's
// reproduction-drift ≈ 0 against the signed verdicts stays meaningful. Do not swap the model here; a model
// change is its own eval-gate.

// The reader's typed self-report on one crop. An enum so "partial text presented as complete" is
// unrepresentable — the reader cannot return a clipped note without declaring it clipped (config-v2 contract;
// the sibling of the refusal-honor guard: the reader is ALLOWED to say "I can't read this properly", and the
// pipeline must honor it rather than accept whatever it produced anyway).
enum NoteStatus {
  Complete           @alias("complete")            @description("The whole note, cleanly readable end to end.")
  TruncatedTop       @alias("truncated_top")       @description("The note's marker or first line is cut off at the TOP of the strip.")
  TruncatedBottom    @alias("truncated_bottom")    @description("The note runs past the BOTTOM of the strip; its tail is missing.")
  TruncatedSide      @alias("truncated_side")      @description("The note is clipped on the LEFT or RIGHT (column bleed).")
  NoFootnotePresent  @alias("no_footnote_present") @description("This region is NOT a footnote — body text, a running header, or a printer signature. Return this instead of inventing a note.")
  Unreadable         @alias("unreadable")          @description("A footnote is present and un-clipped, but you cannot read it. Prefer this over guessing.")
}

// One extracted apparatus note. `text` is always returned, even when partial — a 90%-legible note is still
// evidence; it simply may never be counted as complete or feed the count/sequence gate. `marker_letter` is the
// PRINTED leading letter (a fact about the page the reader sees), or "?" for a symbol/superscript marker that
// is not a letter. `partial` is true iff status != complete.
class Note {
  text string @description("The footnote transcribed VERBATIM as printed — Latin, English, Greek, Hebrew (Hebrew in Hebrew script, right-to-left). Do NOT translate, summarize, renumber, or invent. CRITICAL: `text` must NEVER begin with the note's marker letter — the marker goes ONLY in `marker_letter`. Start `text` at the first word of the note's content (e.g. for a note printed `p In Cosmopœiam`, marker_letter is `p` and text is `In Cosmopœiam`).")
  marker_letter string @description("The single printed lowercase marker letter at the note's start (a, b, c, ...). Use \"?\" if the marker is a symbol or raised superscript rather than a plain letter. Report what is printed; do not renumber or infer from position.")
  status NoteStatus @description("Your typed self-report on this note's crop. Mandatory.")
  partial bool @description("true iff status is not `complete`. A partial note is evidence but is never a complete note.")
}

// The frozen apparatus reader, pinned. Host + model + ctx match the frozen config
// (`vol1-apparatus-frozen-config`), so Seam 1 is a transport swap only.
client<llm> ApparatusReader {
  provider openai
  options {
    // qwen3.6-16k:35b = same weights as the frozen qwen3.6:35b, num_ctx 16384 baked in = the frozen config's
    // num_ctx exactly. Host 192.168.1.169. (The empty-reply cause was NOT context — it was runaway THINKING:
    // the frozen /api/generate path set think:false; over /v1 the complex prompt sent qwen3.6 into an 8-minute
    // reasoning loop that returned empty. `/no_think` in the prompt disables it, matching the frozen config.)
    model "qwen3.6-16k:35b"
    base_url "http://192.168.1.169:11434/v1"
    api_key "ollama"
    temperature 0.0
  }
}

// Seam 1: transcribe one already-cropped, reading-order footnote strip into a typed Note[]. The prompt keeps
// the frozen reader's instructions verbatim in substance (verbatim transcription, keep-the-marker, no
// translate/renumber/invent, omit furniture) and adds ONLY the typed self-report — it does not change what
// text the model is asked to produce, which is what keeps reproduction-drift ≈ 0 on the 47 truthset pages.
// `layout_hint` and `signature_example` are assembled from book_profile.gill.yaml by the caller (no
// book-specific facts baked in here), mirroring build_transcribe_prompt.
function TranscribeApparatus(
  strip: image,
  layout_hint: string?,
  signature_example: string?
) -> Note[] {
  client ApparatusReader

  prompt #"
    {{ _.role("user") }}
    /no_think
    This image is a strip of footnotes from an early Bible commentary, already cropped and placed in correct
    reading order. Transcribe EVERY footnote verbatim. Each footnote begins with a single lowercase letter
    marker (a, b, c, ...). Transcribe Latin, English, Greek and Hebrew exactly as printed; output Hebrew in
    Hebrew script (right-to-left). Do NOT translate, summarize, renumber, or invent.

    Return ONE Note per footnote, in reading order. For each note:
    - `text`: the note transcribed verbatim, WITHOUT the leading marker letter.
    - `marker_letter`: the printed marker letter itself (or "?" if it is a symbol/superscript, not a letter).
    - `status`: your honest self-report. If the region is a running header, a catchword, or a printer
      signature mark rather than a footnote, return `no_footnote_present` — do NOT invent a note. If a note is
      clipped at the top/bottom/side of the strip, say so with the matching `truncated_*`. If a note is present
      but you genuinely cannot read it, return `unreadable` rather than guessing.
    - `partial`: true whenever `status` is not `complete`.

    Never emit page furniture as a note.
    {% if signature_example %}
    A printer signature mark such as "{{ signature_example }}" is NOT a footnote — mark such a region
    `no_footnote_present`.
    {% endif %}
    {% if layout_hint %}

    {{ layout_hint }}
    {% endif %}

    {{ strip }}

    {{ ctx.output_format }}
  "#
}
