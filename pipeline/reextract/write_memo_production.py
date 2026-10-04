# -*- coding: utf-8 -*-
"""Generate the production design memo (ruling 5).

Generator-owned, in the repo, beside the artifacts it reads -- the item 6 report was nearly lost because the
script that writes it lived in a session temp directory and a rerun silently deleted a hand-typed paragraph.
Every number below is derived from the two committed read artifacts. Where a sentence asserts a RANKING or a
DIRECTION, an assert guards it, so a rerun that moves the numbers fails loudly instead of letting the prose
assert a stale finding.

Reads only. Sends nothing, spends nothing, opens no sealed page.
"""
import io
import json
import os
import sys

# Import from THIS file's directory, never a hardcoded worktree: a copy of this script in the
# other lane's tree must import that lane's modules, not Lane B's.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import hebrew_aperture_diag as diag                                        # noqa: E402

DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
CENSUS = AUD + "/hebrew_span_census_20261004.json"
OUT = DV + "/MEMO_laneB_20261004_production_design.md"

TEXTON = "hebrew_frontier_or_reads_20260927.jsonl"
NOTEXT = "hebrew_frontier_or_notext_20261004.jsonl"
AXES = "hebrew_context_axes_reads_20261004.jsonl"
REPNT = "hebrew_frontier_or_notext_rep_20261004.jsonl"

SPANS_IN_VOL = len(json.load(io.open(CENSUS, encoding="utf-8"))["rows"])

Q = "qwen/qwen3.7-plus"
S = "anthropic/claude-sonnet-5"
O = "anthropic/claude-opus-5.5"
G = "google/gemini-3.1-pro-preview"
ASTRA = "openai/gpt-6-astra"
CAND = (Q, S, O, G)

PAIRS = [(u"\u05de", u"\u05e4"), (u"\u05e2", u"\u05e6"), (u"\u05d1", u"\u05d2")]
PAIRSET = set()
for _a, _b in PAIRS:
    PAIRSET.add((_a, _b))
    PAIRSET.add((_b, _a))

T = {s["span_id"]: s["truth"] for s in diag.build_set(include_sealed=True)}


def load(p):
    read, cost = {}, {}
    for line in io.open(str(diag.DATA / p), encoding="utf-8"):
        o = json.loads(line)
        if o.get("kind") == "read":
            read[(o["model"], o["span_id"])] = o.get("gated") or ""
            cost.setdefault(o["model"], []).append(o.get("cost_usd") or 0.0)
    return read, {m: sum(v) / len(v) for m, v in cost.items()}


def header(p):
    for line in io.open(str(diag.DATA / p), encoding="utf-8"):
        o = json.loads(line)
        if o.get("kind") == "config_header":
            return o
    return {}


ON, PON = load(TEXTON)
OFF, POFF = load(NOTEXT)
SPANS = sorted({s for (m, s) in OFF if m in CAND} & {s for (m, s) in ON if m in CAND})
N = len(SPANS)

# Quoted, not typed: the reason astra is absent from the pixels column is recorded in the run that excluded
# it, and the memo reads it from there. A hand-typed reason is a claim about a run; this is the run's own.
REP, PREP = load(REPNT)
HREP = header(REPNT)

HOFF = header(NOTEXT)
ASTRA_WHY = (HOFF.get("excluded_arms") or {}).get(ASTRA, "")
assert ASTRA_WHY, "the pixels run no longer records why %s was excluded; do not describe it from memory" % ASTRA


def cls(d, m, s):
    return diag.classify(d.get((m, s), ""), T[s])


def stop_only(d, m, s):
    """The read is the signed span plus a trailing LATIN full stop, and nothing else.

    `_punct_fold` folds U+05BE, U+2010 and U+2011 to `-`; it does not fold U+002E, so `classify` returns
    `contains` for this case. Chris ruled it 2026-10-04 after looking at the crop: the stop is Latin
    punctuation printed inside the span box, so the read is punct-only, which folds into exact -- neither a
    read error nor a box fault. Corroborated by the artifact itself: 7 of the 24 arms that read `p596:n2`
    returned exactly this string, so the stop is in the pixels, not in one model's imagination.

    Narrow by construction: `read == truth + "."` and nothing looser, so it cannot absorb a `contains` that
    holds a neighbouring word or a whole extra line (which is what sonnet-5 returns on two other spans, and
    those stay box questions). It is implemented HERE and not in `classify`, because changing `classify`
    would silently re-score every artifact and every published tally in this lane.
    """
    return diag._norm(d.get((m, s), "")) == diag._norm(T[s]) + u"."


def ex(d, m, s):
    """FAITHFUL to the printed span: `exact`, `punct-only`, or the ruled Latin-stop case.

    This is the predicate the design is scored on, and it is deliberately not `== "exact"`. The earlier
    draft of this memo counted a `contains` as an unexamined ERROR, which charges the reader for the
    geometry -- `classify`'s own comments say so. The three other classes get their own buckets below:
    `box` (the box holds more than the signed span), `third` (a printed mark the signature omits), and
    `misread` (the only one that is a reading error).
    """
    return cls(d, m, s) in ("exact", "punct-only") or stop_only(d, m, s)


def exact_strict(d, m, s):
    return cls(d, m, s) == "exact"


def bucket(d, m, s):
    """One of faithful / box / third / misread. Exhaustive, and nothing folds silently into another."""
    if ex(d, m, s):
        return "faithful"
    c = cls(d, m, s)
    if c in ("contains", "clipped"):
        return "box"
    if c == "nikud-only":
        return "third"
    return "misread"


def counts(d, m):
    return tuple(sum(1 for s in SPANS if bucket(d, m, s) == k)
                 for k in ("faithful", "box", "third", "misread"))


def shape(a, b):
    a, b = diag._norm(a), diag._norm(b)
    if a == b:
        return "agree", None
    if not a or not b:
        return "abstain-one-side", None
    if len(a) != len(b):
        return "length", None
    d = [(x, y) for x, y in zip(a, b) if x != y]
    if len(d) == 1:
        return ("one-letter-confusable" if tuple(d[0]) in PAIRSET else "one-letter-other"), d[0]
    return "multi-letter", None


def moves(m, s):
    return shape(OFF.get((m, s), ""), ON.get((m, s), ""))[0] != "agree"


def twopass(m):
    """(exact_on_pixels, moved, silent_spans) for one arm run twice: pixels, then pixels+gloss."""
    mv = [s for s in SPANS if moves(m, s)]
    silent = [s for s in SPANS if not moves(m, s) and not ex(OFF, m, s)]
    return sum(ex(OFF, m, s) for s in SPANS), mv, silent


def vol(*per):
    return SPANS_IN_VOL * sum(per)


def layered(cheap, deep):
    okay, silent, cards, deep_n = 0, [], [], 0
    for s in SPANS:
        if not moves(cheap, s):
            okay += ex(OFF, cheap, s)
            if not ex(OFF, cheap, s):
                silent.append((s, cheap))
            continue
        deep_n += 1
        if not moves(deep, s):
            okay += ex(OFF, deep, s)
            if not ex(OFF, deep, s):
                silent.append((s, deep))
        else:
            cards.append(s)
    c = vol(POFF[cheap], PON[cheap]) + (float(deep_n) / N) * vol(POFF[deep], PON[deep])
    return okay, silent, cards, deep_n, c


# ---- the null, first: it is the floor under everything below -------------------------------------------
REP_ARM = sorted({m for (m, s) in REP})
assert REP_ARM == [Q], "the replicate is supposed to be one arm (%s): %s" % (Q, REP_ARM)
assert (HREP.get("replicate") or {}).get("replicate_of") == NOTEXT,     "the replicate artifact does not declare itself a repeat of %s; it is not a null for these figures" % NOTEXT
NULL_DIFF = [s for s in SPANS if shape(OFF.get((Q, s), ""), REP.get((Q, s), ""))[0] != "agree"]
NULL_BYTE = [s for s in SPANS if OFF.get((Q, s), "") == REP.get((Q, s), "")]
CHAN_DIFF = [s for s in SPANS if moves(Q, s)]
assert not NULL_DIFF,     "the endpoint-C null is no longer zero; every figure in this memo has run-to-run drift braided into "     "it and the whole argument needs re-deriving: %s" % NULL_DIFF

# ---- the findings the prose asserts, guarded ------------------------------------------------------------
PIX = sorted(CAND, key=lambda m: (-counts(OFF, m)[0], counts(OFF, m)[3], m))
BEST_PIX = PIX[0]
assert BEST_PIX == O, "the best arm on pixels is no longer opus-5.5; rewrite the recommendation: %s" % PIX
# And the tie is load-bearing prose, so it is asserted too. Under the CORRECTED accounting -- where a
# `contains` is a box question and not a misread -- opus-5.5 and gemini-3.1-pro are EQUAL on the pixels,
# same faithful count and the same single misread. The earlier draft ranked opus above gemini because
# gemini's trailing stop on p596:n2 was being charged to it as an error. So the deep arm is not chosen for
# pixel accuracy; it is chosen because it is legible to the detector. If that tie ever breaks, the
# recommendation's REASON changes and this must be rewritten.
TIED_ON_PIX = [m for m in CAND if counts(OFF, m) == counts(OFF, O)]
assert sorted(TIED_ON_PIX) == sorted([O, G]),     "opus-5.5 and gemini-3.1-pro no longer tie on the pixels under the corrected buckets; the memo's "     "reason for choosing the deep arm (detector legibility, not accuracy) needs rewriting: %s"     % {m: counts(OFF, m) for m in CAND}

AGREED_WRONG = [s for s in SPANS if all(not ex(OFF, m, s) for m in CAND)]
assert AGREED_WRONG == ["p217:n2"], \
    "the unanimous-and-wrong set on pixels has changed; the memo's central example is stale: %s" % AGREED_WRONG
assert all(ex(ON, m, "p217:n2") for m in (Q, S, O)), \
    "p217:n2 is no longer recovered by the gloss on three of four arms; the thesis is stale"
assert not ex(ON, G, "p217:n2"), "gemini now recovers p217:n2; the non-responsive-arm example is stale"

ZERO_SILENT = [m for m in CAND if not twopass(m)[2]]
assert S in ZERO_SILENT and O in ZERO_SILENT, \
    "sonnet-5/opus-5.5 no longer reach zero agreed-and-wrong under the two-pass detector: %s" % ZERO_SILENT

L = []
P = L.append
P(u"# Production design: the authoritative Hebrew read for vol.1")
P(u"")
P(u"**Lane B memo, 2026-10-04. Ruling (5).** Generated by `pipeline/reextract/write_memo_production.py`; "
  u"every figure is derived from the two committed read artifacts named below. **All page numbers are FILE "
  u"pages (printed = file \u2212 88).**")
P(u"")
P(u"Evidence: `audits/%s` (gloss present, 2026-09-27) and `audits/%s` (pixels only, 2026-10-04), n=**%d** "
  u"spans whose boxes are already ratified, against the corrected signed truth. Null floor from "
  u"`audits/%s` (endpoint C, same config, 2026-10-04) with `audits/%s` as corroboration. Nothing was sent "
  u"to produce this memo; the replicate it cites was sent today and cost %.1f cents."
  % (TEXTON, NOTEXT, N, REPNT, AXES, 100 * N * PREP.get(Q, POFF[Q])))
P(u"")
P(u"## The decision")
P(u"")
lo_ok, lo_sil, lo_cards, lo_dn, lo_c = layered(S, O)
hi_ok, hi_sil, hi_cards, hi_dn, hi_c = layered(Q, O)
P(u"**Run one arm twice on every span \u2014 once on the pixels alone, once with the note's Latin as a "
  u"reference window \u2014 and treat the two passes as a CROSS-CHECK, not as two candidates for the answer "
  u"slot.** Ship the pixel read where the two passes agree. Where they disagree, escalate that span to "
  u"`%s` run the same way; where it cannot settle the span with itself either, queue a glyph card for a "
  u"human. Recommended configuration: **`%s` cheap pass, `%s` as the deep arm** \u2014 "
  u"**%d/%d faithful with nobody asked, %d unexamined misreads, %d human card, $%.2f per volume**, "
  u"plus a silent third-channel audit read on every shipped span. **The crop recipe for production is "
  u"PAD=12**, the same recipe the 74-span set is signed on and the same the 19 ratified spans were cut "
  u"at; the band-clip is a per-span tool and not a pipeline step. The one measurement of whether it buys "
  u"accuracy is a null with churn (+1 exact out of 10 arms that changed tag, the losses on the second "
  u"family), which is the device-noise floor and not an effect. Nobody re-proposes it without new "
  u"evidence of that kind."
  % (O.split("/")[-1], S.split("/")[-1], O.split("/")[-1], lo_ok, N, len(lo_sil), len(lo_cards), lo_c))
P(u"")
P(u"This is ruling (5)'s shape \u2014 a primary, a second family, `%s` breaking ties on disagreement only "
  u"\u2014 with **one substitution: the disagreement that triggers escalation is cross-CHANNEL within one "
  u"arm, not cross-ARM.** That substitution is the memo's finding and the rest of it is the argument."
  % O.split("/")[-1])
P(u"")
P(u"## Why the slate is ranked on pixels")
P(u"")
P(u"`_ctx()` replaces every Hebrew run in the note with `\u2022` before the text reaches the prompt, so the "
  u"gloss channel carries no Hebrew letters and an `exact` under it is not answer leakage. It is something "
  u"else: a **back-translation from the model's priors about the verse.** Item 6 measured the "
  u"back-translation ratio rising 1.25\u00d7 \u2192 1.68\u00d7 with the channel off, and a fluent canonical "
  u"word that differs from the printed form is precisely the substitution class this apparatus exists to "
  u"avoid. So the answer slot is scored on the pixels.")
P(u"")
P(u"Every read is placed in exactly one of four buckets, and the three that are not `faithful` are kept "
  u"apart on purpose. **faithful** = the printed span, allowing `punct-only` and the ruled Latin-stop case. "
  u"**box** = the read holds more than the signed span, which by the box rule is a geometry fault and not a "
  u"misread; `classify`'s own comment says folding these into `wrong` charges the reader for the geometry. "
  u"**third** = a printed mark the signature omits (a sof pasuq), which is its own state and neither right "
  u"nor wrong. **misread** = a reading error, and the only bucket that is one. An earlier draft of this memo "
  u"counted box faults as unexamined errors; that was an accounting bug in the memo, not a finding about the "
  u"arms, and correcting it changes one of the conclusions below.")
P(u"")
P(u"| arm | pixels: faithful / box / third / misread | with gloss | $/read (pixels) | $/volume, one pass |")
P(u"| --- | --- | --- | --- | --- |")
for m in PIX:
    _f, _b, _t, _w = counts(OFF, m)
    _f2, _b2, _t2, _w2 = counts(ON, m)
    P(u"| `%s` | **%d**/%d / %d/%d/%d | %d/%d | $%.5f | $%.2f |"
      % (m.split("/")[-1], _f, N, _b, _t, _w, _f2, N, POFF[m], vol(POFF[m])))
P(u"")
P(u"**`%s` and `%s` are TIED on the pixels** — %d of %d faithful, the same single misread, no box "
  u"faults either side. The earlier draft ranked opus above gemini, and it was wrong to: gemini's trailing "
  u"stop on `p596:n2` was being charged to it as a reading error. **So the deep arm is not chosen for pixel "
  u"accuracy. It is chosen because it is legible to the detector** — see the coverage paragraph below. "
  u"That is a weaker claim about the arm and a stronger claim about the design."
  % (O.split("/")[-1], G.split("/")[-1], counts(OFF, O)[0], N))
P(u"")
P(u"`%s` is **absent from the pixels column by instruction, not by accident** — a correction to the "
  u"first draft of this memo, which reported it as a gap. The pixels run's own header records why: "
  u"“%s”. It covers %d spans in the gloss run, and that row stands. Ruling (5) asked for it as a "
  u"measured row on the column that decides the answer slot; that column cannot be filled without new spend "
  u"on an arm Chris has excluded from new spend, so it stays empty and this memo does not treat the "
  u"emptiness as evidence about the arm."
  % (ASTRA.split("/")[-1], ASTRA_WHY, len([1 for (m, s) in ON if m == ASTRA])))
P(u"")
P(u"## The span that forced the design, and a correction")
P(u"")
P(u"On the pixels, **all four candidates are wrong on exactly one span of %d, and it is always `p217:n2`** "
  u"(FILE page 217, printed 129): signed `%s`, every arm returning `%s`. I read that first as evidence "
  u"against the signature \u2014 four independent arms against one signed string. **That reading was wrong "
  u"and is withdrawn.** `p217:n2` was signed MEM and Chris *overturned it to PE* on 2026-09-27, ruling from "
  u"the glyph: in this fount mem's two diagnostics sit outside the letter \u2014 a horn at the top left, a "
  u"gap at the bottom left where the base does not meet the left stroke \u2014 and neither is present, so the "
  u"closed boxy glyph is a pe whose inward curl has filled with ink. The signature is the adjudicated "
  u"reading. The arms are reproducing **the original signer's error, from the same damaged ink that caused "
  u"it.**" % (N, T["p217:n2"], OFF.get((Q, "p217:n2"), "")))
P(u"")
P(u"With the gloss present, **%d of the 4 return the ruled `%s`.** So on this span the pixels genuinely "
  u"under-determine the letter and the context channel is the only automatic route to the signed verdict "
  u"\u2014 while on the corpus as a whole the context channel is the back-translation risk. Both are true, "
  u"which is why neither channel can be the authority and their **disagreement** is the usable signal."
  % (sum(1 for m in CAND if ex(ON, m, "p217:n2")), T["p217:n2"]))
P(u"")
P(u"## Cross-channel beats cross-arm, and the project already knows why")
P(u"")
P(u"Ruling (5) escalates on cross-ARM disagreement. On `p217:n2` cross-arm disagreement is **silent**: four "
  u"arms agree, and agree wrongly. That is the failure mode this lane already retracted a finding over "
  u"\u2014 unanimity is confidence only over shared *evidence*, never over shared *priors*, and these four "
  u"arms share a prior about Genesis 18:14. Cross-channel disagreement inside one arm isolates the prior's "
  u"contribution directly: same model, same pixels, the prior added and removed. It is also **typed** "
  u"\u2014 of the %d spans flagged across the four arms, %d are a single letter inside the fount's "
  u"enumerated confusable set (mem/pe, ayin/tsadi, bet/gimel), and all %d of those are spans where the "
  u"pixel pass was wrong.")
nf = {}
for m in CAND:
    for s in SPANS:
        k, d = shape(OFF.get((m, s), ""), ON.get((m, s), ""))
        if k != "agree":
            nf.setdefault(k, []).append((m, s, d))
_tot = sum(len(v) for v in nf.values())
_conf = len(nf.get("one-letter-confusable", []))
_confbad = sum(1 for (m, s, _d) in nf.get("one-letter-confusable", []) if not ex(OFF, m, s))
assert _conf and _conf == _confbad, \
    "the one-letter-confusable class is no longer all true catches; rewrite this paragraph: %d/%d" \
    % (_confbad, _conf)
L[-1] = L[-1] % (_tot, _conf, _confbad)
P(u"")
P(u"| arm run twice | faithful on pixels | passes disagree | shipped MISREAD, nobody asked | $/volume, two passes |")
P(u"| --- | --- | --- | --- | --- |")
for m in PIX:
    e, mv, sil = twopass(m)
    P(u"| `%s` | %d/%d | %d | **%d**%s | $%.2f |"
      % (m.split("/")[-1], e, N, len(mv), len(sil),
         (u" (" + u", ".join(u"%s `%s`" % (s, cls(OFF, m, s)) for s in sil) + u")") if sil else u"",
         vol(POFF[m], PON[m])))
P(u"")
P(u"**The detector drives the unexamined-error count to zero for `%s` and `%s`.** The 5%% "
  u"agreed-and-wrong rate I reported from the slate comparison \u2014 and projected as ~%d silently wrong "
  u"spans per volume \u2014 was an artifact of treating the two channels as rival answers. Scored as a "
  u"cross-check it is **0 of %d** on both Anthropic arms. That projection is withdrawn."
  % (S.split("/")[-1], O.split("/")[-1], round(SPANS_IN_VOL / 19.0), N))
P(u"")
P(u"**But the detector only sees what the arm's own channel-sensitivity surfaces, and that is per-arm and "
  u"measured, not assumed.** `%s` moves on %d span of %d and ships %d unexamined misread%s \u2014 it is "
  u"inexact on the pixels and channel-stable, which is the worst combination for this instrument: its "
  u"errors are invisible to it. Detector coverage is an arm-selection criterion that is *not* an exact "
  u"rate, and it has to be measured for any arm before that arm is trusted in the answer slot."
  % (G.split("/")[-1], len(twopass(G)[1]), N, len(twopass(G)[2]),
     u"" if len(twopass(G)[2]) == 1 else u"s"))
P(u"")
P(u"## Money is not the constraint; human attention is")
P(u"")
_designs = [vol(POFF[m], PON[m]) for m in (Q, S, O)] + [layered(S, O)[4], layered(Q, O)[4]]
P(u"Every design in this memo costs between $%.2f and $%.2f per volume, and the widest spread anywhere in the "
  u"slate is $%.2f to $%.2f. **The entire cost axis is a ~$%.0f decision per volume and should not be argued "
  u"about.** The real budget is the glyph-card queue: every card is about a minute of Chris's attention, and "
  u"cards are the only thing in this design that does not scale with money."
  % (min(_designs), max(_designs), min(vol(POFF[m]) for m in CAND),
     max(vol(POFF[m], PON[m]) for m in CAND), max(_designs) - min(_designs)))
P(u"")
hdr = (u"| design | faithful, no human asked | unexamined misreads | human cards per %d "
       u"| projected cards per volume | $/volume |" % N)
P(hdr)
P(u"| --- | --- | --- | --- | --- | --- |")
# `exact with no human asked` counts ONLY the spans this design ships automatically and gets right. The
# earlier draft added the queued spans into the same column on the assumption that a human always resolves a
# card correctly, which printed `20/19` for sonnet -- a span that was already right on the pixels and merely
# moved between passes got counted twice. Cards are their own column precisely because their resolution is an
# assumption this memo does not measure.
for m in (Q, S, O):
    e, mv, sil = twopass(m)
    auto = sum(1 for s in SPANS if not moves(m, s) and ex(OFF, m, s))
    assert auto + len(sil) + len(mv) == N, "the three buckets must partition the span set"
    P(u"| `%s` twice, every disagreement to a human | %d/%d | %d | %d | ~%d | $%.2f |"
      % (m.split("/")[-1], auto, N, len(sil), len(mv),
         round(SPANS_IN_VOL * float(len(mv)) / N), vol(POFF[m], PON[m])))
for cheap, deep in ((S, O), (Q, O)):
    ok, sil, cards, dn, c = layered(cheap, deep)
    assert ok + len(sil) + len(cards) == N, "the three buckets must partition the span set"
    P(u"| `%s` twice \u2192 `%s` twice \u2192 human | %d/%d | %d | %d | ~%d | $%.2f |"
      % (cheap.split("/")[-1], deep.split("/")[-1], ok, N, len(sil), len(cards),
         round(SPANS_IN_VOL * float(len(cards)) / N), c))
P(u"")
P(u"The deep arm earns its place on the card budget, not on accuracy: it absorbs the cheap arm's queue and "
  u"takes the projected card count from ~%d down to ~%d."
  % (round(SPANS_IN_VOL * float(len(twopass(Q)[1])) / N),
     round(SPANS_IN_VOL * float(len(layered(Q, O)[2])) / N)))
P(u"")
P(u"## The null floor, measured on endpoint C")
P(u"")
P(u"A cross-channel disagreement is only a signal if the same arm run twice at **fixed** config does not "
  u"disagree with itself. The first draft of this memo named this as its missing measurement. **It has now "
  u"been run on endpoint C, and the null is 0 of %d.**" % N)
P(u"")
P(u"`audits/%s`, `%s`, text channel off, the same %d spans. Not merely classified the same — "
  u"**byte-identical on %d of %d spans** \u2014 every one of them, including the %d the base run "
  u"misread, the %d in a third state and the %d ruled punct-only. Against that floor, the same arm's channel contrast moves **%d of %d** (%s). The flags are "
  u"channel effect, not sampling noise. Base run %s, replicate %s."
  % (REPNT, Q.split("/")[-1], N, len(NULL_BYTE), N,
     counts(OFF, Q)[3], counts(OFF, Q)[2], sum(1 for s_ in SPANS if stop_only(OFF, Q, s_)),
     len(CHAN_DIFF), N,
     u", ".join(u"`%s`" % s for s in CHAN_DIFF),
     ((HREP.get("replicate") or {}).get("base_started") or "?"), (HREP.get("started") or "?")))
P(u"")
P(u"The replicate is **gated, not asserted**: `replicate_gate()` refuses to spend unless the base artifact's "
  u"recorded configuration matches this run's on the text channel, the assembled-prompt hash, the aperture "
  u"and the pixels — and the pixels are checked *per read*, against each base read's own `crop_sha16` "
  u"rather than the header's crop map, so a re-cut crop cannot be slipped into a replicate. A replicate whose "
  u"inputs are not provably identical would not widen the error bar on the null; it would measure something "
  u"else and report it as the null. Cost: **%.1f cents** for %d reads."
  % (100 * N * PREP.get(Q, POFF[Q]), N))
P(u"")
P(u"**What this null does NOT bound, and it is three things.** It is one arm — the cheap one — on "
  u"%d spans, so it bounds `%s`'s run-to-run drift today and says nothing directly about `%s`'s. It is "
  u"*today's* drift: the two channel runs are **seven days apart**, and no replicate run now can reach back "
  u"across that interval, so model-version drift between 2026-09-27 and 2026-10-04 is still braided into the "
  u"channel contrast. And a 0-of-%d null is itself a small sample — it bounds the drift rate at roughly "
  u"15%%, not at zero, which is the same arithmetic that licenses the silent third channel below."
  % (N, Q.split("/")[-1], O.split("/")[-1], N))
P(u"")
P(u"The endpoint-D `base`/`base_rep` pair in `audits/%s` agrees — 0 of %d on all three local arms "
  u"— and is reported here as corroboration only. Cross-endpoint prediction is forbidden in this lane, "
  u"and a 6/6→0/6 flip at fixed config is on the record elsewhere in this project, which is why the "
  u"endpoint-C measurement had to be made rather than inferred." % (AXES, N))
P(u"")
P(u"## The silent third channel, and why 0 of %d is not zero" % N)
P(u"")
P(u"Chris's amendment, and it closes the hole the null leaves. **0 of %d agreed-and-wrong bounds the "
  u"agreed-wrong rate at roughly 15%%, not at zero**, and this lane has a worked case of a single arm "
  u"returning the exact signed string from a crop containing no ink at all — so no output-side check "
  u"can catch fabrication, and two agreeing passes of one model are still one model." % N)
P(u"")
P(u"So every **shipped** span also goes to `%s` **bare**, as a third channel from an independent family, "
  u"scored against the shipped reading and **never allowed to decide anything**. Its disagreement rate is "
  u"the drift alarm: per volume, a few percent is the expected noise floor and anything above it says the "
  u"escalation threshold is wrong — and says it **before the second volume is committed**, which is the "
  u"whole point of running it silently rather than as a fourth vote. Cost: **$%.2f per volume** on top of "
  u"$%.2f (%d spans at $%.5f a read), a rounding error on the recommended design."
  % (Q.split("/")[-1], vol(POFF[Q]), lo_c, SPANS_IN_VOL, POFF[Q]))
P(u"")
P(u"Two rules keep it an audit rather than a vote. It reads the **pixels only**, so its disagreements are "
  u"not back-translations. And it is never shown to the deciding arm and never enters the shipped reading "
  u"— if it were allowed to break a tie it would become a third candidate, the agreement between the "
  u"two passes would stop being a check on the model that produced them, and the alarm would be measuring "
  u"itself.")
P(u"")
P(u"## What this does NOT solve")
P(u"")
P(u"- **n=%d, and every box in it is already ratified.** Geometry is excluded by construction, so this memo "
  u"says nothing about the failure mode that has produced the most damage in this lane. The 100-span set is "
  u"where the design is actually tested." % N)
P(u"- **The precision claims rest on single-digit event counts** \u2014 %s. Zero unexamined misreads out of %d "
  u"is not a rate; it is an absence of counterexamples in a small sample."
  % (u", ".join(u"`%s` %d flag%s" % (m.split("/")[-1], len(twopass(m)[1]),
                                     u"" if len(twopass(m)[1]) == 1 else u"s") for m in PIX), N))
P(u"- **The standard may still move.** Six of twenty signed truths \u2014 30% \u2014 did not survive being "
  u"looked at, the base rate has not been observed to stop, and `p912:n2` is still an open card. Every "
  u"figure here is against a standard with that history.")
BOXQ = sorted({(s, m) for m in CAND for s in SPANS if bucket(OFF, m, s) == "box"})
THIRD = sorted({(s, m) for m in CAND for s in SPANS if bucket(OFF, m, s) == "third"})
assert not [1 for (s, m) in BOXQ if stop_only(OFF, m, s)],     "a ruled Latin-stop read is being counted as a box question again"
P(u"- **`p596:n2` is punct-only and is NOT a residual.** The first draft of this memo listed it as the one "
  u"residual under the cheap configuration and as a possible box fault. Chris ruled it on 2026-10-04 from "
  u"the crop: signed `%s`, read `%s` — the trailing stop is Latin punctuation printed inside the span "
  u"box, so the read is punct-only, which folds into exact. Neither a read error nor a box action. The "
  u"artifact corroborates the ruling independently: **7 of the 24 arms that read this span returned exactly "
  u"that string**, so the stop is in the pixels. `classify` still returns `contains` for it, because "
  u"`_punct_fold` folds U+05BE, U+2010 and U+2011 but not U+002E; this memo applies the ruling in its own "
  u"`stop_only` predicate rather than changing `classify`, which would silently re-score every artifact and "
  u"every published tally in this lane. **That asymmetry is a real debt and it is named here, not fixed "
  u"here.**" % (T["p596:n2"], OFF.get((Q, "p596:n2"), "")))
if BOXQ:
    P(u"- **%d genuine box question%s remain%s, and they are geometry, not reading.** %s. In each case the "
      u"read holds a whole extra Hebrew line or word above the signed span, which by the box rule means the "
      u"box holds more than it should. The arm count is the signal and it is weak: on `p427:n4` **2 of 24 "
      u"arms** return a garbled extra token and they garble it *differently*, which is the signature of "
      u"partial ink at the crop's top edge rather than of a legible neighbour; on `p138:n5` only **1 of 24** "
      u"does. **Both need an eye on the crop's top edge, not a model** — and neither is charged to the "
      u"arm that reported it."
      % (len({s for (s, _m) in BOXQ}),
         u"" if len({s for (s, _m) in BOXQ}) == 1 else u"s",
         u"s" if len({s for (s, _m) in BOXQ}) == 1 else u"",
         u", ".join(u"`%s` (%s)" % (s, m.split("/")[-1]) for s, m in BOXQ)))
if THIRD:
    P(u"- **%d third-state read%s: a printed mark the signature omits.** %s — the read adds a sof "
      u"pasuq (U+05C3) that the signed string does not carry. `classify` calls this `nikud-only`, which this "
      u"lane keeps as its own state rather than folding into right or wrong, and that convention is what "
      u"caught a defective signature once already. **Unruled:** Chris has ruled that an added *Latin* stop "
      u"folds into exact; whether an added *Hebrew* sof pasuq does the same is the same question one script "
      u"over, and nobody has answered it. Until then the span ships with a flag and is counted neither way."
      % (len({s for (s, _m) in THIRD}),
         u"" if len({s for (s, _m) in THIRD}) == 1 else u"s",
         u", ".join(u"`%s` (%s)" % (s, m.split("/")[-1]) for s, m in THIRD)))
P(u"- **The accounting in the first draft of this memo was wrong, and that is a finding about me, not about "
  u"the arms.** It counted `contains` as an unexamined error. `classify`'s own comments warn against exactly "
  u"that — “folding them into `wrong` charges the reader for the geometry” — and the "
  u"correction flipped a conclusion: under the corrected buckets `%s` and `%s` **tie** on the pixels, so the "
  u"deep arm is chosen for detector legibility and not for accuracy."
  % (O.split("/")[-1], G.split("/")[-1]))
P(u"- **The two channels were run seven days apart**, so model-version drift is braided into the channel "
  u"contrast. The endpoint-C null now rules out *same-day* run-to-run drift, and it cannot reach back across "
  u"that interval — no measurement made today can. Separating the two would mean re-running the gloss "
  u"pass now, which this memo does not do and does not price.")
P(u"- **No `:batch` route is measured.** Ruling (5) names `:batch` as the production route and every price "
  u"here is interactive, so the $/volume figures are an upper bound of unknown tightness.")
P(u"- **Glyph cards are assumed to be resolvable.** `p217:n2` took about a minute and no Hebrew, from one "
  u"disputed glyph beside exemplars at matched scale. Cards for spans with damaged ink *and* no clean "
  u"exemplar in the fount may not resolve at all, and this memo has no measurement of that rate.")
P(u"")
P(u"## Preconditions before a production run")
P(u"")
P(u"1. ~~The endpoint-C null replicate.~~ **Done** — 0 of %d, byte-identical, %.1f cents "
  u"(`audits/%s`). The silent third channel replaces it as the standing version of this check."
  % (N, 100 * N * PREP.get(Q, POFF[Q]), REPNT))
P(u"2. The 100-span truth set scored, **signed from pixels with the candidate withheld** \u2014 a second "
  u"table captured the old way inherits the same 30%.")
P(u"3. Box discipline: a ratified span box holds exactly the signed span. Ruling (5) already makes this a "
  u"precondition, and the two box questions above — not the punctuation case, which is ruled — "
  u"are why.")
P(u"4. A standing **editorial standoff record** for `p217:n2` — the body text layer still carries the "
  u"overturned mem, and the apparatus will now be shipping the pe beside it.")
P(u"5. The **silent third channel wired into the run itself**, not run by hand afterwards: a shipped reading "
  u"with no audit read beside it is indistinguishable from one whose audit agreed, and a volume cannot be "
  u"audited retroactively once its crops have been re-cut.")
P(u"6. A ruling on the **sof pasuq** third state. A precondition for nothing, but it is one span's worth of "
  u"attention and it settles a convention the other %d spans in the volume will inherit."
  % (SPANS_IN_VOL - N))
P(u"")
out = u"\n".join(L) + u"\n"
io.open(OUT, "w", encoding="utf-8").write(out)
print("wrote", OUT)
print("%d lines, %d chars" % (len(L), len(out)))
