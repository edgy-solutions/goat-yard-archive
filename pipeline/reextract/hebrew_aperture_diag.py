"""Lane B item 1 - crop-vs-model Hebrew diagnostic. NO pipeline changes: this module reads the frozen v2
read path and the human-ratified box files and writes its own audit outputs. It imports from the pipeline;
nothing in the pipeline imports it.

Question: is the measured Hebrew error caused by CROP QUALITY or by THE READER? Both apertures are cut from
HUMAN-ratified boxes, so CV geometry is out of the loop on the box axis (presplit still owns the coordinate
FRAME - the human drew on the strip presplit produced - which is a named limit, not a silent one).

  A1  ratified NOTE box        note_box_truth_20260906_FINAL.jsonl   (door human-note-box-ratify)
  A2  ratified HEBREW-SPAN box span_box_verdicts_20260906.jsonl      (door human-box-ratify, 30/30 adjusted)

The context image (image 1 of the v2 recrop prompt) is held CONSTANT across apertures, so the only variable
is image 2. Scored against SIGNED verdicts only. Page numbers are FILE pages (printed = file - 88).

Usage:  python hebrew_aperture_diag.py crops          # build + save crops, no model calls
        python hebrew_aperture_diag.py run            # read both models x both apertures
        python hebrew_aperture_diag.py score          # score what run wrote
"""
import base64, io, json, os, re, sys, time, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from PIL import Image
import httpx
import cv_footnote_presplit as ps
from run_header import build_header, model_digests, normalize_hostport
import note_region, nikud_gate, script_gate, crop_quality
from hebrew_recrop import _RECROP_PROMPT

DATA = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
IMG = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
# The signed human sittings moved out of Downloads into the repo on 2026-09-20 (Chris's ruling 0):
# irreproducible human work must not live in a downloads folder. Same directory as DATA now.
DOWN = DATA
CROPDIR = DATA / "hebrew_aperture_crops_20260920"
OUT = DATA / "hebrew_aperture_reads_20260920.jsonl"
HOST = os.getenv("OLLAMA_HOST", "192.168.1.169")
MODELS = ["qwen3.6-16k:35b", "gemma4-32k:31b"]
NUM_CTX = 16384
PAD = 12                       # native px, applied AFTER the strip->native map so padding never straddles
                               # the 20px column gap

SEALED = {129, 206, 217, 293, 362, 423, 427, 478, 491, 543, 596, 726, 897, 912}
HEB = re.compile(r"[\u0590-\u05FF]")
NOT_HEBREW = "\x00NOT-HEBREW"  # sentinel: the correct answer is "there is no Hebrew here"

# Signed truth, span by span. Every string traces to a human verdict; `basis` says which and how.
# See audits/hebrew_aperture_prerun_20260920.md section 1 for the derivation of each.
# ---------------------------------------------------------------------------------------------------
# Chris's re-sign batch of 2026-09-27. Four spans, four verdicts given on SHAPE from the pixels, and
# not one new Hebrew string typed into this file: each is derived from the string already here by the
# rule the verdict names. Retyping Hebrew is the plausible-word-substitution risk this lane measures at
# 35%, and it does not stop being that risk when the typist agrees with the verdict.
#
# The licences are separate because they fail differently, and each guard fires in the direction of the
# MISTAKE rather than the direction of the intent:
#
#   GLYPH_RESIGN    one letter overturned from the pixels. Refuses unless the letter being replaced
#                   occurs EXACTLY ONCE, so "replace the mem" can never silently become "replace the
#                   first of two mems".
#   DEPOINTED       the page prints bare consonants. Refuses unless the string actually carries points,
#                   so a depointing ruling cannot be applied to a span that was never pointed.
GLYPH_RESIGN = {
    # span: (from, to, the shape observation the signature rests on)
    "p217:n2": ("\u05de", "\u05e4",
                "mem -> pe. Chris: 'that is not a mem - I can vouch for it - looks nothing like it.' "
                "Both mem diagnostics in this fount are absent (the top-left horn, the opening at the "
                "bottom left); the glyph is closed and boxy, which is an ink-filled pe, pe's enclosure "
                "being the first thing to fill on a heavy impression. The 11-arm majority for the "
                "canonical Genesis 18:14 form is the EXPECTED output of back-translation and is not "
                "the basis."),
    "p423:n3": ("\u05d1", "\u05d2",
                "bet -> gimel. Signed from the re-cut crop on 2026-09-27; the blank crop that made "
                "this span unscorable is fixed, so the pixels exist for the first time. The span reads "
                "on one line, which is why the ratified box stands and needs no redraw."),
    "p895:n0": ("\u05e2", "\u05e6",
                "ayin -> tsadi. Chris signed from the pixels: ayin is two arms meeting at a point, "
                "tsadi has a left stem with an arm joining from the upper right and a flat foot, and "
                "the glyph has the stem and the foot. Numbers 21:4 reads the tsadi form and the ayin "
                "form is not a word; both are corroboration recorded after the fact."),
}
DEPOINTED_POST_SITTING = {
    "p726:n3": "Chris's verdict from the 4x crop, 2026-09-27: BARE consonants, no points under or "
               "inside the letters. This was the last pointed truth in the table and had been flagged "
               "unruled since the p200:n2 ruling; the book-wide 'Gill's Hebrew is unpointed' "
               "assumption the prompt asserts on every span now has no counter-example in the signed "
               "set. It also retires a flagged interpretive risk: this span's scorability rested on "
               "reading 'correct but should have no makers' as a verdict about MARKERS and not about "
               "the Hebrew, and Chris has now signed the Hebrew itself.",
}


def _resign(s, frm, to):
    """One letter, overturned from the pixels. Refuses when the substitution is not unambiguous."""
    if s.count(frm) != 1:
        raise AssertionError(
            "resign %r -> %r: the string %r contains %d of them, and a rule that says 'the' letter "
            "may only be applied when there is exactly one" % (frm, to, s, s.count(frm)))
    return s.replace(frm, to)


def _depoint(s):
    """The page prints bare consonants. Refuses on a string that carries none, which would mean the
    ruling is being applied to the wrong span."""
    bare = nikud_gate.strip_nikud(s)
    if bare == s:
        raise AssertionError("depoint %r: it carries no points -- this ruling is on the wrong span" % s)
    return bare


TRUTH = {
    "p102:n0": ("\u05d1\u05e8\u05d0 - \u05dc\u05e2\u05e9\u05d5\u05ea", "signed-correct:candidate-verbatim"),
    "p124:n4": ("\u05dc\u05d0 \u05db\u05df", "signed-correction:partial-span"),
    "p138:n5": ("\u05dc\u05da", "signed-correct:candidate-verbatim"),
    # SIGNED 2026-09-27 by Chris (sequence item 5). The 2026-09-06 sitting left this span with
    # chosen == "wrong" and an EMPTY correction, which is what UNSCORABLE recorded: he could see the
    # candidate was wrong and did not supply the right string. The ruling supplies it.
    #
    # NOT retyped by me. The agent row of the SAME sitting recorded קנים on 2026-09-06, so the string
    # is derived from a file row and the derivation is asserted at import (_assert_derivation) under
    # the SUPPLIED licence. Corroborated independently by the candidate line itself, which reads
    # "לך nidos, Pagninus, Montanus." -- the Latin gloss is *nidos*, "nests", and קנים is "nests".
    # The candidate's Hebrew was לך, a different note's span entirely.
    "p138:n6": ("קנים", "signed-post-sitting:agent-row-verbatim-supplied-20260927"),
    # RULED 2026-09-27 by Chris: "those are not in the original". The pointing is NOT on the page.
    # The 2026-09-06 sitting showed him the candidate \u05d5\u05d9\u05d4\u05d9 \u05d4\u05e9\u05de\u05e9 \u05dc\u05b0\u05d1\u05b9\u05d0 -- pointed, and
    # with NO vav. His correction was \u05d5\u05d9\u05d4\u05d9 \u05d4\u05e9\u05de\u05e9 \u05dc\u05b0\u05d1\u05b9\u05d5\u05d0. The edit he made was
    # CONSONANTAL: he added the missing vav. The sheva and holam rode along from the candidate
    # string he was editing; they were never an assertion that the page is pointed. Corroborating:
    # p200:n2 measures the LOWEST nikud density of any span at BOTH apertures (0.179 / 0.227) and
    # never leaves `uncertain`. Independently, 18 of 30 arms read exactly these consonants.
    #
    # Derived by the same rule as p253:n2 -- strip_nikud(the signed correction) -- which makes the
    # table consistent: every entry is now the printed consonantal form. Pinned in
    # test_hebrew_sealed_truth.py so it cannot drift back.
    #
    # What the old entry cost: 18 of 30 arms scored `nikud-only` instead of `exact` on this span,
    # and two committed audits published it as having no correct candidate from any arm.
    "p200:n2": ("\u05d5\u05d9\u05d4\u05d9 \u05d4\u05e9\u05de\u05e9 \u05dc\u05d1\u05d5\u05d0",
                "signed-correction:vav-added-then-strip-nikud-ruled-20260927"),
    "p219:n0": ("\u05d4\u05d5\u05d0\u05dc\u05ea\u05d9 \u05dc\u05d3\u05d1\u05e8", "signed-correct:candidate-verbatim"),
    "p253:n2": ("\u05d4\u05e7\u05e8\u05d4 \u05e0\u05d0 \u05dc\u05e4\u05e0\u05d9",
                "signed-correction:derived-strip-nikud"),
    "p360:n0": ("\u05e9\u05d0\u05dc \u05e9\u05d0\u05dc", "signed-correct:candidate-verbatim"),
    # RE-SIGNED 2026-09-27 (batch): ayin -> tsadi, see GLYPH_RESIGN for the shape verdict. The string
    # below is the 2026-09-06 correction as the sitting recorded it; the signed truth is that string
    # with its single ayin replaced, computed here rather than retyped.
    #
    # Worth recording plainly: this re-sign was reported as ALREADY APPLIED in this morning's batch
    # document and in two sets of session notes, and it was not. The table still held the ayin form
    # until this batch. A literal would have carried that error indefinitely; the derivation is what
    # caught it.
    "p895:n0": (_resign("\u05d5\u05ea\u05e7\u05e2\u05e8 \u05e0\u05e4\u05e9", *GLYPH_RESIGN["p895:n0"][:2]),
                "signed-resign:ayin-to-tsadi-ruled-20260927"),
    "p900:n4": (NOT_HEBREW, "signed-correction:not-hebrew-greek"),
    "p657:n0": ("\u05d1\u05d4\u05e8", "signed-residue-correction"),
}
# Empty since 2026-09-27: p138:n6 was the only member and Chris signed it (see TRUTH above). Kept as a
# table rather than deleted, because "the signer marked it wrong and supplied nothing" is a state this
# harness must be able to represent -- a span with no signed string is not a span that scored zero.
UNSCORABLE = {}

# ---------------------------------------------------------------------------------------------------
# The SEALED-page half of the same signed sitting. Chris's ruling 2 (2026-09-20) opens sealed pages for
# THIS HARNESS ONLY: a Hebrew READ on a sealed page does not touch the alignment gate's evidence, which
# is what "sealed" protects. Nothing here re-scores an alignment decision, and the gate stays frozen.
#
# These strings are DERIVED from the sitting file rather than retyped, and the derivation is asserted
# against the four hand-written candidate-verbatim entries above at import time (_assert_derivation).
# Retyping Hebrew by hand is exactly the plausible-word-substitution risk this lane measures at 35%.
#
#   chosen == "correct"                  -> truth is the candidate's Hebrew span, verbatim
#   chosen == "wrong" + correction       -> truth is the correction string
#   chosen == "wrong" + empty correction -> UNSCORABLE (same rule that excluded p138:n6)
SEALED_TRUTH = {
    # RE-SIGNED 2026-09-27 (batch): mem -> pe, see GLYPH_RESIGN. The base string is the 2026-09-06
    # candidate, affirmed verbatim -- which is the whole point of this case. It is the fourth
    # inherited-property defect and the only one where the candidate was not even edited: the
    # machine's whole string was accepted and the third glyph was never the thing being looked at.
    # p200:n2 inherited pointing, p362:n1 inherited word division, p895:n0 inherited a letter from an
    # edited string, and this one inherited a letter from an unedited one. Four for four, one cause,
    # and the cause is attention rather than editing.
    "p217:n2": (_resign("\u05d4\u05d9\u05de\u05dc\u05d0", *GLYPH_RESIGN["p217:n2"][:2]),
                "signed-resign:mem-to-pe-ruled-20260927"),
    "p293:n0": ("יחמנה", "signed-correct:candidate-verbatim"),
    # RULED 2026-09-27 by Chris, from the rendered console card: "the signed one is correct but
    # there should be a space between the two parts ... the models found that". The printed form is
    # two words. Same mechanism as p200:n2 and worth naming: the 2026-09-06 sitting showed him the
    # candidate \u05dc\u05d4\u05ea\u05d2\u05dc\u05e2\u05dc\u05d9\u05e0\u05d5 -- one lamed short AND unspaced. His correction supplied the
    # missing lamed, a CONSONANTAL edit, and the missing word space rode along from the string he was
    # editing. The signer never asserted that the words are joined; he inherited it.
    #
    # NOT retyped. Derived from the agent row of the SAME sitting
    # (hebrew_sitting_agent_20260906.jsonl), which recorded \u05dc\u05d4\u05ea\u05d2\u05dc\u05dc \u05e2\u05dc\u05d9\u05e0\u05d5 with the space on
    # 2026-09-06 -- so the harness has held the corroborating record for three weeks. The derivation
    # asserts the two rows agree once spaces are removed, which proves the ruling moved word division
    # only and not one letter. Pinned in test_hebrew_sealed_truth.py.
    #
    # What the old entry cost: 7 of 30 arms scored `wrong` instead of `exact`, including all four
    # gate arms, and this span was published as having no correct candidate from any arm.
    "p362:n1": ("\u05dc\u05d4\u05ea\u05d2\u05dc\u05dc \u05e2\u05dc\u05d9\u05e0\u05d5",
                "signed-correction:word-space-restored-ruled-20260927"),
    # RE-SIGNED 2026-09-27 (batch): bet -> gimel, see GLYPH_RESIGN. Signed from the re-cut crop, the
    # first pixels this span has ever had -- the crop sent in the frontier run was uniform white, which
    # is why it was held UNSCORABLE and why the question "is the bet a diplomatic reading or a slip?"
    # could not be answered then. The base string is Chris's own 2026-09-06 correction.
    #
    # What this costs the set: the span was going to be its best back-translation probe precisely
    # BECAUSE its signed form differed from the biblical one -- every model reading gimel would have
    # been substituting. The probe is gone, and the reason it is gone is that the printed page reads
    # gimel. A probe that depends on the truth being unusual is worth exactly what the truth is.
    "p423:n3": (_resign("\u05d5\u05ea\u05d2\u05e2 \u05dc\u05e8\u05d1\u05dc\u05d9\u05d5",
                        *GLYPH_RESIGN["p423:n3"][:2]),
                "signed-resign:bet-to-gimel-ruled-20260927"),
    "p427:n4": ("הבאשתם", "signed-correct:candidate-verbatim"),
    "p491:n1": ("בשמע", "signed-correct:candidate-verbatim"),
    # SIGNED 2026-09-27 by Chris (sequence item 5), same shape as p138:n6: the sitting row was
    # chosen == "wrong" with an EMPTY correction, and the ruling supplies the string. Derived from the
    # agent row of the same sitting (סנה), asserted at import under the SUPPLIED licence.
    #
    # Worth recording because THREE different strings have been attached to this span: the candidate
    # line says "See Buxtorf. in voce היה.", the glm-ocr:bf16 arm looped "in voce נוס." forty times,
    # and the signed answer is סנה -- the burning bush of Exodus 3:2, which is what Buxtorf's lexicon
    # entry actually is. The candidate mis-transcribed the headword; the degenerate arm invented a
    # third. Neither is the page.
    "p596:n2": ("סנה", "signed-post-sitting:agent-row-verbatim-supplied-20260927"),
    # Chris marked this `wrong` but wrote "correct but should have no makers" - an adjudication about the
    # note's MARKERS, not about the Hebrew string, which he affirms. Truth is therefore the candidate
    # verbatim. This interpretation is load-bearing for n: the prerun's arithmetic ("n goes 10 -> 19")
    # counts this span as scorable and p596:n2 as not, which is only consistent with reading it this way.
    # Flagged in every report rather than buried; if Chris reads it otherwise, n is 18 and this span drops.
    # RULED 2026-09-27 by Chris from the 4x crop: BARE. See DEPOINTED_POST_SITTING. The base string is
    # the pointed candidate he affirmed in 2026-09-06 -- the fifth inherited-property case and the one
    # that had been flagged longest. The points came from the candidate he was shown, not from the page.
    #
    # Two things this closes. The "Gill's Hebrew is unpointed" assertion the prompt makes on every span
    # now has no counter-example in the signed set, so it needs no book-wide footnote. And this span's
    # scorability no longer rests on an interpretation of mine: it was scorable only if "correct but
    # should have no makers" is read as a verdict about the note's MARKERS rather than about the
    # Hebrew, which every report flagged as load-bearing for n. Chris has now signed the Hebrew.
    #
    # One consequence for the tally, not fixed here: arms that returned the pointed form will now
    # classify `nikud-only` rather than `exact`. That is the correct third state -- adding points to
    # the standard does not make an unpointed read wrong -- and it is item 5's business, not this
    # patch's.
    "p726:n3": (_depoint("\u05e9\u05b0\u05c1\u05d0\u05b8\u05e8 \u05d0\u05b8\u05d1\u05b4\u05d9\u05da\u05b0"),
                "signed-correction:derived-strip-nikud-ruled-20260927"),
    "p897:n4": ("ענו לה", "signed-correction:verbatim"),
    # UNCHANGED in the 2026-09-27 batch, on purpose. The open question here is word ORDER -- which
    # word is physically to the right on the page -- and the signature already answers that; the gloss
    # running "in Jahacob, in Israel" does not, because Gill's Hebrew and his gloss do not always run
    # in the same order. What is outstanding is the BOX: the A2 crop scored `clipped`, so this span's
    # reads are about a crop that cuts the span, and the box is queued for re-ratification. A box fault
    # is not a reason to touch a signed string.
    "p912:n2": ("ביעקב בישראל",
                "signed-correct:candidate-verbatim"),
}
# Empty since 2026-09-27, same ruling: p596:n2 was its only member. See the note on UNSCORABLE.
SEALED_UNSCORABLE = {}


def _lines(p):
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


# Spans the signer ruled on AFTER the sitting closed. The ruling is honoured, but it still may not be
# typed: each one names the file row it is derived from and what the ruling was allowed to change.
RULED_POST_SITTING = {
    "p362:n1": "agent-row-verbatim; ruling may change word division only",
    "p138:n6": "agent-row-verbatim; ruling SUPPLIES a string the sitting left empty",
    "p596:n2": "agent-row-verbatim; ruling SUPPLIES a string the sitting left empty",
}
# Two different licences are now in play and they check differently, so they are named rather than
# inferred. A CORRECTION ruling (p362:n1) edits a string the signer already wrote, so the check is
# "the ruling moved word division only" -- letters must match. A SUPPLIED ruling fills a field the
# signer left EMPTY, so there is no earlier string to compare against and the check is the opposite
# one: the sitting row must really be empty (otherwise this is a silent overwrite of a signed string,
# which is the failure mode worth guarding), and the recorded truth must equal the agent row VERBATIM,
# not modulo spaces -- nothing rode along from an edit here, so nothing is allowed to differ.
SUPPLIED_POST_SITTING = ("p138:n6", "p596:n2")


def _assert_derivation(sitting, agent=None):
    """Signed truths must fall out of the sitting file, not out of my typing. Checked at import.

    Covers SEALED_TRUTH **and** any TRUTH entry carrying a post-sitting ruling. That second clause is
    not tidiness: p138:n6 is on an unsealed page, so without it that span would be the one signed
    string in this module with no import-time derivation at all, which is precisely the entry a later
    reader would have no way to distinguish from something I typed."""
    todo = dict(SEALED_TRUTH)
    todo.update({k: v for k, v in TRUTH.items()
                 if k in RULED_POST_SITTING or k in GLYPH_RESIGN or k in DEPOINTED_POST_SITTING})
    for sid, (want, basis) in todo.items():
        rec = sitting.get(sid)
        if not rec:
            raise AssertionError(f"{sid}: not in the signed sitting")
        corr = (rec.get("disputed_span_correction") or "").strip()
        if sid in SUPPLIED_POST_SITTING:
            # The licence is "fills a field the signer left EMPTY". So the guard that matters runs in
            # the opposite direction from the correction case: if the field is NOT empty, this ruling
            # would be silently overwriting a string the signer actually wrote.
            # The correction field has THREE states in this sitting, not two, and the first version of
            # this guard tested for the wrong one. Measured over the signed corpus:
            #   a Hebrew string   -> the signer transcribed the right answer (p362:n1, p423:n3, ...)
            #   English PROSE     -> the signer wrote an instruction: "not hebrew" (p900:n4), "same as
            #                        extracted but without markers" (p253:n2), "correct but should have
            #                        no makers" (p726:n3). That is a verdict WITH content.
            #   genuinely empty   -> the signer supplied nothing at all (p138:n6, p596:n2).
            # Only the third licenses a fill. Testing `not HEB.search(corr)`, which is what this guard
            # did first, would have let a SUPPLIED ruling silently overwrite all three of the prose
            # rows -- precisely the failure the licence exists to prevent.
            if rec.get("chosen") != "wrong" or corr:
                raise AssertionError(
                    f"{sid}: licensed SUPPLIED, but the sitting row carries chosen="
                    f"{rec.get('chosen')!r} correction={corr!r} -- that is an overwrite, not a fill")
            arec = (agent or {}).get(sid)
            if not arec:
                raise AssertionError(f"{sid}: ruled post-sitting but the agent row is missing")
            got = (arec.get("disputed_span_correction") or "").strip()
            if not got:
                raise AssertionError(f"{sid}: the agent row is empty too - nothing to derive from")
            if _norm(got) != _norm(want):
                raise AssertionError(
                    f"{sid}: derived {got!r} != recorded {want!r} (SUPPLIED requires verbatim)")
            continue
        got = corr if (rec.get("chosen") == "wrong" and HEB.search(corr)) else _heb_span(
            rec["inputs"]["candidates"][0])
        if sid in RULED_POST_SITTING:
            arec = (agent or {}).get(sid)
            if not arec:
                raise AssertionError(f"{sid}: ruled post-sitting but the agent row is missing")
            ruled = (arec.get("disputed_span_correction") or "").strip()
            if got.replace(" ", "") != ruled.replace(" ", ""):
                raise AssertionError(f"{sid}: the ruling changed a letter, not just word division")
            got = ruled
        # The 2026-09-27 re-signs, applied to the FILE-derived string by the same rule the table
        # entry uses. This is not a tautology: it proves the base string in the table is the one the
        # sitting recorded. Get that base wrong -- as the p895:n0 notes did for a day -- and the
        # transformed strings disagree here.
        if sid in GLYPH_RESIGN:
            got = _resign(got, *GLYPH_RESIGN[sid][:2])
        if sid in DEPOINTED_POST_SITTING:
            got = _depoint(got)
        if _norm(got) != _norm(want):
            raise AssertionError(f"{sid}: derived {got!r} != recorded {want!r}")


def _heb_span(text):
    """The maximal Hebrew run in a candidate line, separators kept. Validated against the hand-written
    entries in TRUTH (p102, p138:n5, p219, p360) by test_hebrew_sealed_truth.py."""
    toks = re.findall(r"[֐-׿][֐-׿]*", text or "")
    if not toks:
        return None
    i, j = text.index(toks[0]), text.rindex(toks[-1]) + len(toks[-1])
    seg = text[i:j]
    return seg if re.fullmatch(r"[֐-׿ \-]+", seg) else " ".join(toks)


def build_set(include_sealed=False):
    """The carried spans with their signed verdict, latin context, and both ratified boxes (strip coords).

    n = len(TRUTH) scorable by default -- 11 since Chris signed p138:n6 on 2026-09-27, 10 before it.
    `include_sealed=True` adds the sealed half of the SAME signed sitting under Chris's ruling-2
    carve-out -> n = len(TRUTH) + len(SEALED_TRUTH), 21 since p596:n2 was signed the same day, 19
    before. Counts already MEASURED at n=19 keep their own denominator; see the audits. A sealed page is opened here for a READ only; no
    alignment evidence is re-scored and the gate stays frozen."""
    sitting = {o["span_id"]: o for o in _lines(DOWN / "hebrew_sitting_chris_20260906.jsonl") if "span_id" in o}
    resid = {o["span_id"]: o for o in _lines(DATA / "chris_sitting_b_residue_20260823.jsonl") if "span_id" in o}
    spanbox = {o["span_id"]: o for o in _lines(DOWN / "span_box_verdicts_20260906.jsonl")}
    notebox = {o["page"]: o for o in _lines(DATA / "note_box_truth_20260906_FINAL.jsonl") if "page" in o}
    truth = dict(TRUTH)
    unscorable = dict(UNSCORABLE)
    if include_sealed:
        agent = {o["span_id"]: o for o in _lines(DOWN / "hebrew_sitting_agent_20260906.jsonl")
                 if "span_id" in o}
        _assert_derivation(sitting, agent)
        truth.update(SEALED_TRUTH)
        unscorable.update(SEALED_UNSCORABLE)
    out = []
    for sid in list(truth) + list(unscorable):
        pg, ni = int(sid.split(":")[0][1:]), int(sid.split(":")[1][1:])
        if not include_sealed:
            assert pg not in SEALED, f"{sid} is on a SEALED page"
        rec = sitting.get(sid) or resid.get(sid)
        cand = rec["inputs"]["candidates"][0] if rec else ""
        nb = notebox.get(pg)
        sb = spanbox.get(sid)
        sbox = (sb or {}).get("ratified_box")
        # The note index in the Hebrew sitting and the index into the ratified NOTE-BOX list are two
        # different human truth files and are NOT guaranteed to agree (p124: they differ by one, because
        # the note-box sitting split a missed start the sitting's numbering never saw). Resolve A1 by
        # maximum y-overlap with the ratified SPAN box - which is drawn on the Hebrew pixels themselves -
        # and fall back to the declared index only when no span box exists. Both sources stay human.
        used, ovf, clip = ni, None, None
        if nb and sbox:
            best, bestf = ni, -1.0
            for i, n in enumerate(nb["notes"]):
                b = n["strip_box"]
                ov = max(0, min(sbox[3], b[3]) - max(sbox[1], b[1])) / max(1, sbox[3] - sbox[1])
                if ov > bestf:
                    best, bestf = i, ov
            used, ovf = best, round(bestf, 3)
            clip = round(1.0 - bestf, 3)           # fraction of the span's height the note box clips
        nbox = nb["notes"][used]["strip_box"] if nb and used < len(nb["notes"]) else None
        out.append(dict(
            span_id=sid, page=pg, note_idx=ni,
            signed=(rec or {}).get("chosen"), latin_context=cand,
            truth=truth.get(sid, (None, None))[0], truth_basis=truth.get(sid, (None, None))[1],
            unscorable=unscorable.get(sid), sealed=(pg in SEALED),
            note_box=nbox, note_box_status=(nb["notes"][used]["status"] if nbox else None),
            a1_idx_declared=ni, a1_idx_used=used, a1_span_overlap=ovf, a1_clips_span_frac=clip,
            span_box=sbox, column_bands=(nb or {}).get("column_bands"),
            n_ratified=(nb or {}).get("n_ratified")))
    # A span whose scored crop is faulted was never shown to any arm, so no arm can be graded on it --
    # not the frontier arms, not D, not C, all of which read the same crop folder. It is UNSCORABLE,
    # which is a different thing from "no arm read it correctly" and must never be reported as that.
    faults = crop_faults()
    for rec in out:
        # Stamped on every record so no consumer can read an absent measurement as a sound crop.
        # `unscorable` stays None in that case -- it is not a known fault -- which is precisely why
        # the unmeasured flag has to travel separately from it.
        rec["crop_unmeasured"] = faults is None
        if faults and faults.get(rec["span_id"]) and not rec["unscorable"]:
            rec["unscorable"] = f"crop-fault:{faults[rec['span_id']]}"
    return out


def _native_crop(page_img, strip_box, info, bands, pad=0):
    """Un-stack a strip box to native rects and cut them. A box straddling the column gap yields TWO rects;
    they are stacked vertically with the same 20px gap presplit uses, never merged into one spanning box."""
    rects = note_region.strip_box_to_native(strip_box, info, bands)
    W, H = page_img.size
    ims = []
    for r in rects:
        x0, y0, x1, y1 = r["box"]
        x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
        x1, y1 = min(W, x1 + pad), min(H, y1 + pad)
        if x1 - x0 > 4 and y1 - y0 > 4:
            ims.append(page_img.crop((x0, y0, x1, y1)))
    if not ims:
        return None, rects
    if len(ims) == 1:
        return ims[0], rects
    w = max(i.width for i in ims)
    h = sum(i.height for i in ims) + 20 * (len(ims) - 1)
    canv = Image.new("L", (w, h), 255)
    y = 0
    for i in ims:
        canv.paste(i, (0, y))
        y += i.height + 20
    return canv, rects


# --- CROP FAULT GATE ------------------------------------------------------------------------
# Standing law here is "an empty result from a claimed region is an error", and `crop_quality.
# crop_has_line()` has implemented it since Build 3. This harness never called it. The cost of that
# omission is measured, not hypothetical: p423:n3 and p726:n3 went out to 30 arms as PURE WHITE
# images -- extrema (255,255), ink 0.0000, at BOTH apertures -- and nothing failed loud. 7 of 8 arms
# answered p423 with Hebrew anyway, three of them with the canonical Exodus 4:25 wording that the
# Latin gloss translates. A blank crop does not produce blank output. It produces the back-
# translation, confidently. So the gate belongs BEFORE the spend, never in the scoring afterwards.
#
# Two faults, both previously silent, kept separate because they have different causes and homes:
#
#   blank         -- the cut landed off the text. MEASURED: the mapped rects for those two spans sit
#                    80-111px below the nearest inked row, past the last printed line of the page,
#                    while every other A2 crop carries 0.12-0.30 ink. WHY the map overshoots on
#                    exactly those two pages is NOT established and is not claimed here; the guard
#                    does not need the cause, it needs the pixels.
#   out-of-bounds -- the mapped rect ran off the page and the cut was silently CLAMPED, so the model
#                    was shown a narrower crop than the ratified box asked for. p726:n3's A1 asked
#                    for 1958px starting at x=1960 of a 3584px-wide page and was served 1624.
#                    p124:n4's A1 overruns by 16px. A clamp is a coordinate fault, not a crop option.
#
# The fault is recorded per APERTURE, because they fail independently: p124:n4's A1 is out-of-bounds
# while its A2 -- the one that is scored -- is clean.
# NEAR-UNIFORM threshold, derived from measurement rather than chosen: the ink fraction of all 740
# PNGs in the six artifact folders is BIMODAL with an empty band. Exactly 4 crops sit at 0.00000 ink
# (p423:n3 and p726:n3, both apertures each) and the next-lowest crop in the corpus is 0.02555
# (truthset_review/strip_619.png). There is NOTHING between. So 0.005 is ~5x below the lowest real
# crop and refuses only what is effectively empty.
#
# Honest consequence: on this corpus the near-uniform test catches nothing the uniform test does not
# already catch -- it is currently redundant, and it is here because 740 crops without a borderline
# case is not a promise about page 741. It is a guard, not a finding. If it ever fires alone, that is
# new information and the census will say so.
NEAR_UNIFORM_INK = 0.005


def crop_fault(im, rects, page_size, strip_box=None, strip_size=None):
    """The fault string for a cut, or None if it is safe to send. Checked before any outbound call.

    A rect leaving the page OR the strip is a geometry fault, per Chris 2026-09-27. The strip check
    is the earlier of the two and the more diagnostic: the strip box is what a human ratified, so a
    box that already leaves the STRIP was wrong before any mapping ran, while a box that leaves the
    page survived ratification and was broken by `strip_to_native`. Reporting them as one fault
    would merge a ratification error with a mapping error."""
    if strip_box and strip_size:
        x0, y0, x1, y1 = strip_box
        beyond = _beyond_strip(strip_box, strip_size)
        if beyond:
            return (f"out-of-strip:box={[x0, y0, x1, y1]}_strip={list(strip_size)}"
                    f"_beyond={beyond}")
    for r in rects:
        x0, y0, x1, y1 = r["box"]
        if clamp_loss(r["box"], page_size)[0]:
            return (f"out-of-bounds:rect={[x0, y0, x1, y1]}_page={list(page_size)}"
                    f"_lost={_lossdesc(r['box'], page_size)}")
    if im is None:
        return "no-rect"
    lo, hi = im.convert("L").getextrema()
    if lo == hi:
        return f"blank:uniform={lo}"
    ink = ink_fraction(im)
    if ink <= NEAR_UNIFORM_INK:
        return f"blank:near-uniform=ink{ink:.5f}"
    if not crop_quality.crop_has_line(im):
        return "blank:no-line"
    return None


def _beyond_strip(box, size):
    """How far a ratified strip box reaches outside the strip, per edge, or "" if it is inside.

    NOT a loss figure, and this distinction was got wrong once here before it was measured. The strip
    box is MAPPED by `note_region.strip_to_native`, not cut out of the strip, so an overrun is never
    clamped and no pixels are amputated. Measured on p900:n4's A2, whose box asks rows 268-332 of a
    330-row strip: the mapped native rect is the full 64 rows, sits entirely inside the page, and the
    served crop carries 0.2020 ink. It is a clean, usable crop.

    So the fault is real but its consequence is the opposite of a clamp: those 2 rows are page pixels
    the strip never represented, which means the crop silently INCLUDES material from outside the
    ratified region rather than losing material inside it. Unverified inclusion, not amputation.
    Reporting it as "lost=428px" -- which this function replaced -- was a claim about a mechanism
    nobody had tested."""
    x0, y0, x1, y1 = box
    W, H = size
    out = []
    if x0 < 0:
        out.append(f"left{-x0}")
    if y0 < 0:
        out.append(f"top{-y0}")
    if x1 > W:
        out.append(f"right{x1 - W}")
    if y1 > H:
        out.append(f"bottom{y1 - H}")
    return ",".join(out)


def clamp_loss(box, size):
    """(lost_pixels, lost_fraction) for cutting `box` out of a `size` substrate with silent clamping.

    This exists because "was clamped" spans 170x in severity and one boolean cannot carry that.
    MEASURED over the 21 spans: the two strip overruns lose 3.1% and 0.1% -- they overshoot the
    substrate edge into pixels that do not exist, so nothing is amputated and the defect is purely in
    the coordinates. The five page overruns lose 0.9% to 17.1%: p726:n3's A1 asked for 1958px of a
    3584px page starting at x=1960 and was served 1624, losing 19,372 real pixels of note.
    Both are refused -- a clamp fails loud, per Chris 2026-09-27 -- but a consumer that cannot tell
    them apart would treat a 2px phantom and a 17% amputation as one thing, and they are not."""
    x0, y0, x1, y1 = box
    W, H = size
    asked = max(0, x1 - x0) * max(0, y1 - y0)
    if not asked:
        return 0, 0.0
    sw = max(0, min(W, x1) - max(0, x0))
    sh = max(0, min(H, y1) - max(0, y0))
    lost = asked - sw * sh
    return max(0, lost), max(0.0, lost / float(asked))


def _lossdesc(box, size):
    n, frac = clamp_loss(box, size)
    return f"{n}px/{frac * 100:.1f}%"


def ink_fraction(im):
    """Fraction of pixels below mid-grey. One definition, used by the guard and by the census, so a
    crop can never be blank by one measure and inked by the other."""
    g = im.convert("L")
    h = g.histogram()
    dark = sum(h[:128])
    return dark / float(max(1, g.width * g.height))


# --- THE OUTBOUND CHOKEPOINT ---------------------------------------------------------------------
# Item 2 says the guard runs BEFORE ANY OUTBOUND CALL. A gate that an arm can forget to call is not
# that. The four arms (hebrew_frontier_or, hebrew_local_arms, hebrew_aperture_frontier,
# hebrew_recrop) each had their own base64 step reading PNGs straight off disk, so the gate sitting
# in `crops()` protected the crop BUILD and nothing else -- and since a faulted crop is still
# written to disk on purpose (it is the evidence of what was sent), the blank PNGs were there to be
# picked up and sent by anything that globbed the folder. They were.
#
# So the gate returns the BYTES. An arm cannot obtain sendable bytes without passing through it, and
# a refusal is a return value the caller has to handle rather than a warning it can ignore. This is
# the same shape as the record stores in hebrew_glyph_card: the safe path is the only path.
class CropRefused(Exception):
    """Raised by the gated encoder. It is an EXCEPTION and not a return value on purpose: an arm that
    ignores a returned fault still sends the image, while an arm that ignores this one does not run.
    The caller records the refusal as its own row -- UNSCORABLE, which is not the same thing as a
    wrong read and must never be tallied as one."""

    def __init__(self, fault, what=""):
        self.fault = fault
        self.what = what
        super().__init__(f"crop refused before send: {fault}" + (f" [{what}]" if what else ""))


def b64_gated(src, what="", **geo):
    """base64 of an image that PASSED the gate, or CropRefused. The ONLY sanctioned encoder.

    Every arm routes its base64 through here -- hebrew_frontier_or, hebrew_local_arms,
    hebrew_aperture_frontier, hebrew_recrop. The gate is placed at the ENCODE rather than beside the
    post() because an arm cannot reach the wire without encoding, so this is the one step that cannot
    be skipped by forgetting. A gate an arm has to remember to call is not a gate; it is a comment."""
    raw, fault = gate_outbound(src, **geo)
    if fault:
        raise CropRefused(fault, what or str(getattr(src, "name", "") or src)[-60:])
    return base64.b64encode(raw).decode()


def gate_outbound(src, page_size=None, rects=(), strip_box=None, strip_size=None):
    """(png_bytes, None) when it is safe to send; (None, fault) when it is refused.

    `src` is a path or a PIL image. Geometry arguments are optional because a recrop made in memory
    has no ratified rect to check -- but the pixel checks always run, so nothing reaches the wire
    unexamined."""
    if hasattr(src, "convert"):
        im = src
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        raw = buf.getvalue()
    else:
        pth = Path(src)
        if not pth.exists():
            return None, f"missing:{pth.name}"
        raw = pth.read_bytes()
        im = Image.open(io.BytesIO(raw))
    fault = crop_fault(im, list(rects), page_size or im.size, strip_box, strip_size)
    if fault:
        return None, fault
    return raw, None


# The crops that were actually sent to every arm, frozen before the 27-Sept re-cut. This directory
# is written once and never again: an audit does not overwrite its own evidence, and after a re-cut the
# live CROPDIR no longer answers the question "what did the model see?"
AS_SENT = CROPDIR.parent / "hebrew_aperture_crops_AS_SENT_20260920"


def _sha(p):
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16] if Path(p).exists() else None


def crop_sha(span_id, aperture="A2_spanbox", as_sent=False):
    """sha256[:16] of one crop, live or as-sent. None when that crop does not exist."""
    d = AS_SENT if as_sent else CROPDIR
    return _sha(d / f"{span_id.replace(':', '_')}_{aperture}.png")


def crops_changed(aperture="A2_spanbox"):
    """span_id -> (sha_as_sent, sha_now) for crops that differ from the ones the reads were taken on.

    A read is evidence about the pixels it was shown. When a crop is re-cut, every read recorded
    against it becomes STALE -- not wrong, not confirmed, just no longer about anything on disk -- and
    the span has to be re-run before it can be scored again.

    This is the union of two causes and is the right answer for VOIDING EVIDENCE, where they are the
    same: no read on record is about anything on disk either way. It is the wrong answer for SCOPE,
    where they are opposites -- see `crops_recut` and `crops_gone`. It used to be described as "the
    re-run scope" and it is not: a crop the geometry no longer produces cannot be re-run at all."""
    out = {}
    for p in sorted(AS_SENT.glob(f"*_{aperture}.png")):
        sid = p.name[:-len(f"_{aperture}.png")].replace("_n", ":n")
        a, b = _sha(p), _sha(CROPDIR / p.name)
        if a != b:
            out[sid] = (a, b)
    return out


def crops_recut(aperture="A2_spanbox"):
    """The re-cut half of `crops_changed`: a crop still exists, with different bytes.

    THIS is the half that can put a span back on the wire. There are new pixels to show a model."""
    return {k: v for k, v in crops_changed(aperture).items() if v[1] is not None}


def crops_gone(aperture="A2_spanbox"):
    """The vanished half: the current geometry no longer produces this crop at all.

    A missing file is not a value and it is not a task. These spans lose their reads exactly as the
    re-cut ones do, and unlike them they cannot be re-sent -- there is nothing to send. Keeping this
    set separate is what stops a debt (redraw the box) being scheduled as work (re-run the span)."""
    return {k: v[0] for k, v in crops_changed(aperture).items() if v[1] is None}


def a1_x_shifts():
    """Per-span x-shift of the note-box rects between as-sent and now, for spans with both.

    Chris's A1 clause is conditioned on Lane A's x-origin fix landing. This is the measurement that
    says whether it has: a non-zero dx anywhere means page geometry moved horizontally, which is the
    trigger. Width-only growth (dx 0, dw positive) is a clamp releasing on the right edge and is not.
    Returns span_id -> [(dx, dw), ...], one per rect, or span_id -> None when the rect count changed
    and the rects cannot be paired at all.

    CORRECTED 2026-09-27. This docstring used to read "width-only growth (dx 0, dw positive) is a clamp
    releasing on the right edge". That was my explanation of the +300..+450px growth here and it was
    false: those four boxes were already OVER THE CANVAS FILLER that presplit pads a narrow band with,
    and dc573ca merely stopped clamping them, so each crop grew by the filler it was always sitting on.
    See `band_overshoot` below, which measures it. dx is still the right trigger for Chris's A1 clause --
    what changed is that dw is not innocent, and a crop whose width grew is now a crop to re-examine
    rather than a crop to wave through.

    AND THE MEASUREMENT THAT SETTLED IT, 2026-09-27. After Lane A's clip landed (36c36c4), the A1
    crops of all four are byte-identical to the 2026-09-20 as-sent archive, and their widths equal
    the band widths exactly (p217 1625, p219 1566, p293 1570, p895 1641). So the widening was the
    whole of the difference and the clip is a restoration, not a new geometry. Byte equality is the
    claim here; WHY the 09-20 mapper produced band-width boxes is not established, and I am not
    replacing one causal story with another untested one."""
    live = {m["span_id"]: m for m in json.loads((CROPDIR / "manifest.json").read_text(encoding="utf-8"))}
    sent = {m["span_id"]: m for m in json.loads((AS_SENT / "manifest.json").read_text(encoding="utf-8"))}
    out = {}
    for sid in crops_recut("A1_notebox"):
        o = ((sent.get(sid) or {}).get("A1_notebox") or {}).get("native_rects")
        n = ((live.get(sid) or {}).get("A1_notebox") or {}).get("native_rects")
        if not o or not n or len(o) != len(n):
            out[sid] = None
            continue
        out[sid] = [(b[0] - a[0], (b[2] - b[0]) - (a[2] - a[0])) for a, b in zip(o, n)]
    return out


def clipped(flag="band-clipped"):
    """Every crop rect that Lane A's mapper CUT, as the manifest recorded it.

    The companion to `band_overshoot`, and the more trustworthy of the two: that one is my
    re-derivation of the band geometry, this one is what the mapper itself reported at cut time. They
    answer different questions and the pair is the point -- an empty `band_overshoot` says no box is
    outside its band NOW, and a non-empty `clipped` says why: nine of them were outside it and were
    cut back. If `band_overshoot` were empty because my band arithmetic had drifted, `clipped` would
    still hold the nine.

    -> [{span_id, aperture, rect_i, rect, edge, over}], one per cut rect."""
    man = json.loads((CROPDIR / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for m in man:
        for ap in ("A2_spanbox", "A1_notebox"):
            d = m.get(ap)
            if not d:
                continue
            for i, (r, e) in enumerate(zip(d["native_rects"], d.get("rect_edges") or [])):
                if e and flag in e:
                    ov = (d.get("band_overshoot_px") or [None] * (i + 1))[i]
                    out.append(dict(span_id=m["span_id"], aperture=ap, rect_i=i, rect=list(r),
                                    edge=list(e), over=ov))
    return out


def band_overshoot():
    """Every crop rect that lies outside the BAND it was detected in: a box over canvas filler.

    presplit pastes each band at canvas x=0 into a canvas as wide as the widest band, so a narrow band
    carries (canvas_w - band_w) px of white filler on its right. A box over that filler is not on the
    page. note_region gates the MAPPED result against page width, which catches the fault only when the
    overshoot happens to cross the page edge -- so the same mechanism is loud in the right column and
    silent in the left. Lane A found it (4b2e0de on body-path); this is Lane B's measurement of it, kept
    here because a gate must be able to see the failure it is accountable for, and because the five loud
    refusals in the fault table looked like five faults rather than nine.

    Bands sit SIDE BY SIDE natively -- the strip stacks them, the page does not -- so a rect's band is
    the one whose native x-range contains its left edge, and those ranges partition the page width
    exactly. No tolerance is needed and none is given: a left edge outside every band is itself a fault,
    which is how p217:n2's rect at native x=-2 is caught rather than rounded into band 0.

    -> [{span_id, aperture, rect, band, band_x0, band_x1, over, kind}], kind in
       {"overshoot", "left-of-every-band"}. Empty is the goal state, not a vacuous pass: the companion
    check counts the rects it examined."""
    import cv_footnote_presplit as _ps
    man = json.loads((CROPDIR / "manifest.json").read_text(encoding="utf-8"))
    cache, out, seen = {}, [], 0
    for m in man:
        pg = m.get("page") or m["span_id"].split(":")[0][1:]
        if pg not in cache:
            cache[pg] = _ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)[1]["bands"]
        bands = cache[pg]
        for ap in ("A2_spanbox", "A1_notebox"):
            d = m.get(ap)
            if not d:
                continue
            for r in d["native_rects"]:
                seen += 1
                hit = [(i, b) for i, b in enumerate(bands)
                       if b["native"][0] <= r[0] < b["native"][0] + b["size"][0]]
                if len(hit) != 1:
                    out.append(dict(span_id=m["span_id"], aperture=ap, rect=list(r), band=None,
                                    band_x0=None, band_x1=None, over=None,
                                    kind="left-of-every-band"))
                    continue
                bi, b = hit[0]
                x1 = b["native"][0] + b["size"][0]
                if r[2] > x1:
                    out.append(dict(span_id=m["span_id"], aperture=ap, rect=list(r), band=bi,
                                    band_x0=b["native"][0], band_x1=x1, over=r[2] - x1,
                                    kind="overshoot"))
    band_overshoot.rects_examined = seen
    return out


def sent_faults(aperture="A2_spanbox"):
    """The AS-SENT fault table, from the frozen archive. None when the archive has no fault file."""
    p = AS_SENT / "crop_faults.json"
    if not p.exists():
        return None
    return {k: v[aperture] for k, v in json.loads(p.read_text(encoding="utf-8")).items()
            if v.get(aperture)}


def crop_faults(aperture="A2_spanbox"):
    """span_id -> fault for the aperture that gets scored. {} when the fault file has not been built.

    Read from `crop_faults.json`, which the `faults` command writes WITHOUT re-cutting the PNGs: the
    crops on disk are the evidence of what was actually sent, and an audit does not overwrite its own
    evidence."""
    p = CROPDIR / "crop_faults.json"
    if not p.exists():
        # None, NOT {}. An empty dict reads as "measured, nothing faulted" -- a clean bill of health
        # nobody earned. Absence of the measurement is its own state and every caller must branch on
        # it, because the consumer below turns this into `unscorable`: a missing file would silently
        # declare the whole population sound.
        return None
    return {k: v[aperture] for k, v in json.loads(p.read_text(encoding="utf-8")).items()
            if v.get(aperture)}


def crops(save=True, include_sealed=False):
    CROPDIR.mkdir(parents=True, exist_ok=True)
    built, page_cache = [], {}
    for s in build_set(include_sealed=include_sealed):
        pg = s["page"]
        if pg not in page_cache:
            strip, info = ps.presplit(str(IMG / f"page{pg}_image1.png"), upscale=1)
            page_cache[pg] = (Image.open(IMG / f"page{pg}_image1.png").convert("L"),
                              strip.convert("L"), info)
        native, strip, info = page_cache[pg]
        bands = s["column_bands"] or note_region._column_bands(strip)
        rec = dict(s)
        for ap, box, pad in (("A1_notebox", s["note_box"], 0), ("A2_spanbox", s["span_box"], PAD)):
            if not box:
                rec[ap] = None
                continue
            # Since Lane A's dc573ca the strip->native map CLAMPS NOTHING: a box whose native rect
            # falls off the page raises instead of landing somewhere plausible. That is the behaviour
            # we asked for, but an audit of 21 spans must not die on the first bad box -- refusing a
            # crop IS the fault table's job, so the refusal is recorded and the sweep continues. The
            # crop is still never produced and so can never be sent.
            try:
                im, rects = _native_crop(native, box, info, bands, pad)
            except ValueError as e:
                rec[ap] = None
                rec[ap + "_fault"] = f"map-error:{e}"
                continue
            fault = crop_fault(im, rects, native.size, box, strip.size)
            if im is None:
                rec[ap] = None
                rec[ap + "_fault"] = fault
                continue
            p = CROPDIR / f"{s['span_id'].replace(':', '_')}_{ap}.png"
            if save:
                im.save(p)
            # Lane A's clip (36c36c4) flags every rect it cuts. Recording the box and dropping
            # the flag would leave the manifest unable to say that a crop we may pay for had been
            # amputated -- and the crop hash cannot say it either, because a clipped crop is a
            # perfectly valid PNG. Both fields are per-rect and positional with native_rects; a rect
            # that was not cut carries None, because Lane A's contract omits `edge` entirely rather
            # than sending an empty list.
            rec[ap] = dict(path=str(p), size=list(im.size),
                           native_rects=[r["box"] for r in rects], n_rects=len(rects),
                           rect_edges=[r.get("edge") for r in rects],
                           band_overshoot_px=[r.get("band_overshoot_px") for r in rects],
                           fault=fault)
        ctxp = CROPDIR / f"p{pg}_context_strip.png"
        if save and not ctxp.exists():
            strip.save(ctxp)
        rec["context_strip"] = str(ctxp)
        built.append(rec)
    if save:
        io.open(CROPDIR / "manifest.json", "w", encoding="utf-8").write(
            json.dumps(built, ensure_ascii=False, indent=1))
    return built


def _b64(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


def read_one(context_strip, crop, model):
    """The frozen v2 recrop read: same prompt, same two-image shape, same options. Only image 2 varies."""
    t0 = time.time()
    r = httpx.post(f"http://{HOST}:11434/api/generate",
                   json={"model": model, "prompt": _RECROP_PROMPT,
                         "images": [_b64(context_strip), _b64(crop)],
                         "think": False, "stream": False,
                         "options": {"num_ctx": NUM_CTX, "temperature": 0}}, timeout=900)
    d = r.json()
    return (d.get("response", "") or "").strip(), d.get("done_reason"), round(time.time() - t0, 1)


def run():
    built = crops(save=True)
    done = set()
    if OUT.exists():
        done = {(o["span_id"], o["aperture"], o["model"]) for o in _lines(OUT) if "span_id" in o}
    with io.open(OUT, "a", encoding="utf-8") as f:
        if not done:
            # Machine in the header and in the hash (ruling, 2026-09-20). This harness calls TWO models,
            # so there is no single set of weights: the per-model digest map goes into the hash, since
            # collapsing it to one model would let a run with a swapped witness hash alike.
            hp = normalize_hostport(HOST)
            hdr = build_header(host=HOST, model="+".join(MODELS),
                               identity_extra={"api_path": "/api/generate", "think": False,
                                               "temperature": 0, "num_ctx": NUM_CTX, "models": MODELS,
                                               "model_digests16": model_digests(hp, MODELS),
                                               "prompt_head": _RECROP_PROMPT[:40], "pad_native_px": PAD},
                               extra={"prerun": "hebrew_aperture_prerun_20260920.md"})
            f.write(json.dumps(hdr, ensure_ascii=False) + chr(10))
        for s in built:
            ctx = Image.open(s["context_strip"]).convert("L")
            for ap in ("A1_notebox", "A2_spanbox"):
                if not s.get(ap):
                    continue
                crop = Image.open(s[ap]["path"]).convert("L")
                for m in MODELS:
                    if (s["span_id"], ap, m) in done:
                        continue
                    raw, dr, secs = read_one(ctx, crop, m)
                    gated, nik_verdict, dens = nikud_gate.gated_strip(raw, crop)
                    sv, sr = script_gate.gate(gated, s["latin_context"])
                    f.write(json.dumps({"span_id": s["span_id"], "aperture": ap, "model": m,
                                        "raw": raw, "gated": gated, "nikud_verdict": nik_verdict,
                                        "nikud_density": round(float(dens), 3), "script_verdict": sv,
                                        "script_reason": sr, "done_reason": dr, "secs": secs,
                                        "crop_size": s[ap]["size"]}, ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"  {s['span_id']:10s} {ap:11s} {m:18s} {secs:6.1f}s  {raw[:48]!r}", flush=True)
    print("wrote", OUT)


def _norm(t):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t or "")).strip()


def _punct_fold(t):
    return _norm(t).replace("\u05be", "-").replace("\u2010", "-").replace("\u2011", "-")


DROPPED_ARMS = ("glm-ocr:bf16",)
"""Arms excluded from every future score and from the console, by Chris's instruction 2026-09-27.

glm-ocr:bf16 does not return a reading. It returns the surrounding note, at length, in a repetition
loop -- "See Buxtorf. in voce" x40 on p596:n2, "est.est.est." on p423:n3. MEASURED over the 787
recorded reads: all 19 with any repeated 12-char shingle are glm-ocr's, 17 of its 41 reads exceed a
0.5 ratio, and the maximum ratio over all 746 reads from every other arm is 0.000. It is dropped as
an arm, not merely reclassified, because a verbose non-reading pollutes the agreement matrix and the
console with strings that were never a candidate for the span."""


def repetition_ratio(text, k=12):
    """Fraction of k-char shingles that are repeats. A degenerate generation loop, not a reading.

    Not a tuned threshold: the gap it sits in is empty. Every non-glm-ocr read in the corpus scores
    exactly 0.000 and the lowest degenerate glm-ocr read scores 0.679, so any cut in between is the
    same cut. 0.35 is chosen to stay well clear of a legitimately repetitive short Latin note."""
    t = " ".join(text.split())
    if len(t) < k * 2:
        return 0.0
    sh = [t[i:i + k] for i in range(len(t) - k + 1)]
    return 1.0 - len(set(sh)) / len(sh)


DEGENERATE_AT = 0.35


def classify(read, truth):
    r, t = _norm(read), _norm(truth)
    # Before anything else: a repetition loop is not a reading and cannot be graded as one. It is
    # tested ahead of the NOT_HEBREW branch because glm-ocr's p900:n4 loop is Latin, and a truth of
    # "not Hebrew" would otherwise score that degenerate output `exact`.
    if repetition_ratio(read or "") >= DEGENERATE_AT:
        return "degenerate"
    if truth == NOT_HEBREW:
        return "exact" if not HEB.search(r) else "wrong"
    if not r or not HEB.search(r):
        return "abstain"
    if r == t:
        return "exact"
    if _punct_fold(r) == _punct_fold(t):
        return "punct-only"
    if nikud_gate.strip_nikud(r) == nikud_gate.strip_nikud(t):
        return "nikud-only"
    # `contains` and `clipped` are BOX faults wearing a reading's clothes, and neither is a misread:
    #   contains -- signed IN read: the ratified box held MORE than the signature, so an arm that
    #               transcribed everything in the crop (which is what the prompt asks for) returns the
    #               signed span with its neighbours attached. p124:n4's box holds two Hebrew runs and
    #               the Latin "quasi"; three arms returned the signed span intact and were scored wrong.
    #   clipped  -- read IN signed: the ratified box held LESS than the signature, so an arm can only
    #               return part of it. p912:n2's signature is two words and its box covers one; 14 arms
    #               transcribed that one word correctly and were scored wrong.
    # Both exist because the 30 span boxes and the 30 signatures were made in separate passes and were
    # never checked against each other. Folding them into `wrong` charges the reader for the geometry.
    if t and t in r:
        return "contains"
    if r and r in t:
        return "clipped"
    return "wrong"


def score():
    rows = [o for o in _lines(OUT) if "span_id" in o]
    sets = {s["span_id"]: s for s in build_set()}
    for o in rows:
        s = sets[o["span_id"]]
        o["cls"] = "UNSCORABLE" if s["unscorable"] else classify(o["gated"], s["truth"])
    return rows


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "crops"
    if cmd == "crops":
        for s in crops():
            a1 = s["A1_notebox"] and s["A1_notebox"]["size"]
            a2 = s["A2_spanbox"] and s["A2_spanbox"]["size"]
            print(f"{s['span_id']:10s} A1={a1} A2={a2} nb_status={s['note_box_status']}")
    elif cmd == "faults":
        # Recompute from the ratified boxes WITHOUT overwriting the crops that were actually sent.
        out = {}
        for s in crops(save=False, include_sealed=True):
            d = {ap: ((s.get(ap) or {}).get("fault") or s.get(ap + "_fault"))
                 for ap in ("A1_notebox", "A2_spanbox")}
            if any(d.values()):
                out[s["span_id"]] = d
        io.open(CROPDIR / "crop_faults.json", "w", encoding="utf-8").write(
            json.dumps(out, ensure_ascii=False, indent=1))
        print(f"crop faults: {len(out)} span(s) (FILE pages; printed = file - 88)")
        for sid, d in sorted(out.items()):
            for ap, fl in d.items():
                if fl:
                    print(f"  {sid:10s} {ap:12s} {fl}")
    elif cmd == "run":
        run()
    elif cmd == "score":
        for o in score():
            print(f"{o['span_id']:10s} {o['aperture']:11s} {o['model']:18s} {o['cls']:11s} "
                  f"{o['gated'][:40]!r}")
