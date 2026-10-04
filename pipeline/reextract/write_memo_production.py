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


ON, PON = load(TEXTON)
OFF, POFF = load(NOTEXT)
SPANS = sorted({s for (m, s) in OFF if m in CAND} & {s for (m, s) in ON if m in CAND})
N = len(SPANS)


def ex(d, m, s):
    return diag.classify(d.get((m, s), ""), T[s]) == "exact"


def cls(d, m, s):
    return diag.classify(d.get((m, s), ""), T[s])


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


# ---- the findings the prose asserts, guarded ------------------------------------------------------------
PIX = sorted(CAND, key=lambda m: (-sum(ex(OFF, m, s) for s in SPANS), m))
BEST_PIX = PIX[0]
assert BEST_PIX == O, "the best arm on pixels is no longer opus-5.5; rewrite the recommendation: %s" % PIX

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
  u"`audits/%s`. Nothing was sent to produce this memo." % (TEXTON, NOTEXT, N, AXES))
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
  u"**%d/%d exact, %d shipped-wrong-and-unexamined, %d human card, $%.2f per volume.**"
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
P(u"| arm | pixels only | with gloss | $/read (pixels) | $/volume, one pass |")
P(u"| --- | --- | --- | --- | --- |")
for m in PIX:
    P(u"| `%s` | **%d/%d** | %d/%d | $%.5f | $%.2f |"
      % (m.split("/")[-1], sum(ex(OFF, m, s) for s in SPANS), N,
         sum(ex(ON, m, s) for s in SPANS), N, POFF[m], vol(POFF[m])))
P(u"")
P(u"`%s` is **absent from this table and from the pixel ranking entirely**: it covers %d spans in the gloss run "
  u"and none in the pixels run. Ruling (5) asked for it as a measured row; on the column that decides the "
  u"answer slot there is no row to report, and that is a gap, not a result."
  % (ASTRA.split("/")[-1], len([1 for (m, s) in ON if m == ASTRA])))
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
P(u"| arm run twice | exact on pixels | passes disagree | shipped wrong, nobody asked | $/volume, two passes |")
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
  u"measured, not assumed.** `%s` moves on %d span of %d and ships %d unexamined errors \u2014 it is both "
  u"inexact on the pixels and channel-stable, which is the worst combination for this instrument: its "
  u"errors are invisible to it. Detector coverage is an arm-selection criterion that is *not* an exact "
  u"rate, and it has to be measured for any arm before that arm is trusted in the answer slot."
  % (G.split("/")[-1], len(twopass(G)[1]), N, len(twopass(G)[2])))
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
hdr = (u"| design | exact with no human asked | unexamined errors | human cards per %d "
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
P(u"## The null floor, and the measurement this memo is missing")
P(u"")
P(u"A cross-channel disagreement is only a signal if the same arm run twice at **fixed** config does not "
  u"disagree with itself. The context-axes run carries a `base`/`base_rep` replicate pair, and on all three "
  u"local arms the null is **0 of %d** against 12\u201316 of %d for the channel contrast. The flags are not "
  u"a sampling artifact." % (N, N))
P(u"")
P(u"**That null is on endpoint D with deterministic local arms, and this lane forbids cross-endpoint "
  u"prediction.** There has never been a same-config replicate on endpoint C, where every figure in this "
  u"memo comes from, and a 6/6\u21920/6 flip at fixed config is on the record elsewhere in this project. "
  u"**The missing measurement is %d reads of one arm, repeating the pixels pass: %.1f cents on `%s`, "
  u"%.0f cents on `%s`.** No production run should start before it exists."
  % (N, 100 * N * POFF[Q], Q.split("/")[-1], 100 * N * POFF[O], O.split("/")[-1]))
P(u"")
P(u"## What this does NOT solve")
P(u"")
P(u"- **n=%d, and every box in it is already ratified.** Geometry is excluded by construction, so this memo "
  u"says nothing about the failure mode that has produced the most damage in this lane. The 100-span set is "
  u"where the design is actually tested." % N)
P(u"- **The precision claims rest on single-digit event counts** \u2014 %s. Zero unexamined errors out of %d "
  u"is not a rate; it is an absence of counterexamples in a small sample."
  % (u", ".join(u"`%s` %d flag%s" % (m.split("/")[-1], len(twopass(m)[1]),
                                     u"" if len(twopass(m)[1]) == 1 else u"s") for m in PIX), N))
P(u"- **The standard may still move.** Six of twenty signed truths \u2014 30% \u2014 did not survive being "
  u"looked at, the base rate has not been observed to stop, and `p912:n2` is still an open card. Every "
  u"figure here is against a standard with that history.")
_cont = sorted({s for m in CAND for s in twopass(m)[2] if cls(OFF, m, s) == "contains"})
if _cont:
    P(u"- **The one residual under the cheap configuration is punctuation, not a letter, and it may be a BOX "
      u"question.** %s: signed `%s`, read `%s` \u2014 a trailing stop. By the box rule a ratified span box "
      u"holds exactly the signed span, so if that stop is inside the crop the box holds more than it should "
      u"and the read is faithful to what it was shown. **Unresolved here; it needs an eye on the crop, not a "
      u"model.**" % (u", ".join(u"`%s`" % s for s in _cont), T[_cont[0]],
                     OFF.get((Q, _cont[0]), "")))
P(u"- **The two channels were run seven days apart**, so model-version drift is braided into the channel "
  u"contrast and cannot be separated from it in these artifacts. The replicate above is what would separate "
  u"them.")
P(u"- **No `:batch` route is measured.** Ruling (5) names `:batch` as the production route and every price "
  u"here is interactive, so the $/volume figures are an upper bound of unknown tightness.")
P(u"- **Glyph cards are assumed to be resolvable.** `p217:n2` took about a minute and no Hebrew, from one "
  u"disputed glyph beside exemplars at matched scale. Cards for spans with damaged ink *and* no clean "
  u"exemplar in the fount may not resolve at all, and this memo has no measurement of that rate.")
P(u"")
P(u"## Preconditions before a production run")
P(u"")
P(u"1. The endpoint-C null replicate above (%.1f cents on the cheap arm, %.0f on the deep one)."
  % (100 * N * POFF[Q], 100 * N * POFF[O]))
P(u"2. The 100-span truth set scored, **signed from pixels with the candidate withheld** \u2014 a second "
  u"table captured the old way inherits the same 30%.")
P(u"3. Box discipline: a ratified span box holds exactly the signed span. Ruling (5) already makes this a "
  u"precondition and the `contains` residual above is why.")
P(u"4. A standing **editorial standoff record** for `p217:n2` \u2014 the body text layer still carries the "
  u"overturned mem, and the apparatus will now be shipping the pe beside it.")
P(u"")
out = u"\n".join(L) + u"\n"
io.open(OUT, "w", encoding="utf-8").write(out)
print("wrote", OUT)
print("%d lines, %d chars" % (len(L), len(out)))
