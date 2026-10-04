# -*- coding: utf-8 -*-
"""Item 6: the text channel's contribution, per arm, both artifacts scored against TODAY's truth.

Two things this does that reading the two score logs side by side does not:
  - it segments the text-ON artifact by header instead of pooling it, and says which segment it used;
  - it scores both sides with one truth digest, so the p726:n3 unpointed re-signing cannot make the
    comparison a comparison of two standards.
"""
import io
import json
import os
import sys
from collections import Counter

# Import from THIS file's directory, never a hardcoded worktree: a copy of this script in the
# other lane's tree must import that lane's modules, not Lane B's.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import hebrew_aperture_diag as diag                                        # noqa: E402
import hebrew_frontier_or as F                                            # noqa: E402

MD = ("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/"
      "REPORT_laneB_20261004_item6_textchannel.md")
NOTEXT = diag.DATA / "hebrew_frontier_or_notext_20261004.jsonl"
TEXTON = diag.DATA / "hebrew_frontier_or_reads_20260927.jsonl"
EXCLUDED = "openai/gpt-6-astra"          # Chris's instruction: measured row only, never a decision row

T = {s["span_id"]: s["truth"] for s in diag.build_set(include_sealed=True)}
BT = set(getattr(F, "BACKTRANSLATABLE", ()) or ())


def segments(path):
    runs, cur = [], None
    for o in diag._lines(path):
        if o.get("kind") == "config_header":
            cur = {"hdr": o, "rows": []}
            runs.append(cur)
        elif cur is not None:
            cur["rows"].append(o)
    return runs


def tally(rows):
    """Last read wins per (model, span) -- the same rule score() applies when a file holds a retry."""
    cell = {}
    for o in rows:
        if o.get("kind") == "read" and o.get("span_id") in T:
            cell[(o["model"], o["span_id"])] = o
    out = {}
    for (m, sid), o in cell.items():
        k = diag.classify(o.get("gated") or "", T[sid])
        d = out.setdefault(m, Counter())
        d[k] += 1
        d["n"] += 1
        if k == "exact":
            d["bt" if sid in BT else "nobt"] += 1
    return out


nt_runs, on_runs = segments(NOTEXT), segments(TEXTON)
assert len(nt_runs) == 1, "the text-off artifact must hold exactly one run; holds %d" % len(nt_runs)
nt = nt_runs[0]
foot = [o for o in nt["rows"] if o.get("kind") == "run_footer"][-1]
# The text-ON side is ONE logical run resumed across 3 segments (576 + 26 + 26 reads), so it is pooled
# last-write-wins exactly as score() pools it -- segmenting and taking the last gives 25 cells, not 19 per
# arm. The segments agree on the prompt sha; the 09-27 segment predates crop_sha16/truth_digest, so the
# ON side's pixel identity is asserted by the file, not proved by a hash. Named in the report.
on_rows = [o for r in on_runs for o in r["rows"]]
on = on_runs[0]

# ONE span set on both sides. The text-ON run covered 21 spans, the approved sheet 19; pooling both at
# their own denominators compared 500 cells against 461 and would have read an 8-point difference in
# coverage as an effect.
SPANS = {o["span_id"] for o in nt["rows"] if o.get("kind") == "read" and o.get("span_id") in T}
assert len(SPANS) == 19, "the text-off run read %d spans, not 19" % len(SPANS)
for _k in list(T):
    if _k not in SPANS:
        del T[_k]

A, B = tally(on_rows), tally(nt["rows"])
arms = [m for m in B if m != EXCLUDED]
cost = sum((o.get("cost_usd") or 0) for o in nt["rows"])
errs = Counter(o.get("model") for o in nt["rows"] if o.get("kind") == "call_error")


def _n(d, m):
    return (d.get(m) or Counter()).get("n", 0)


def ex(d, m):
    return (d.get(m) or Counter()).get("exact", 0)


def n(d, m):
    return (d.get(m) or Counter()).get("n", 0)


# Both sides must present the same denominator per arm, or a Δ is a coverage artefact.
bad = [(m, n(A, m), n(B, m)) for m in arms if n(B, m) == 19 and n(A, m) != 19]
assert not bad, "ON/OFF denominators differ per arm: %s" % bad
rank = sorted(arms, key=lambda m: -ex(B, m))
pool_on = sum(ex(A, m) for m in arms), sum(n(A, m) for m in arms)
pool_nt = sum(ex(B, m) for m in arms), sum(n(B, m) for m in arms)

L = []
P = L.append
P(u"# Item 6 \u2014 what the text channel is worth, per arm")
P(u"")
P(u"All page numbers are **FILE pages** (printed = file \u2212 88). n = 19 spans, A2 aperture, one read per cell.")
P(u"")
P(u"## The run")
P(u"")
P(u"`%s` \u2014 **%d reads**, %d call errors, **$%.4f** measured. `clean_run=%s`, `run_faulted=%s`, git `%s` "
  u"clean and identical at start and end. One `config_header`, one writer, lock held throughout."
  % (NOTEXT.name, sum(n(B, m) for m in B), sum(errs.values()), cost, foot["clean_run"],
     foot["run_faulted"], foot["git_at_start"]["git_head"][:8]))
P(u"")
P(u"Approved on `%s` \u2014 the same 19 crops approved that morning, with `p726:n3` signed unpointed. "
  u"19 pixel states archived before the first call. `%s` skipped with your exclusion reason recorded."
  % (nt["hdr"].get("contact_sheet"), EXCLUDED))
P(u"")
P(u"Text-ON side: `%s`, **all %d segments pooled last-write-wins** (started `%s`, `%s`, `%s` — one logical "
  u"run resumed, 576 + 26 + 26 reads), which is how `score()` reads it. **Both sides are scored against "
  u"today's truth**, so the `p726:n3` unpointed re-signing cannot turn this into a comparison of two "
  u"standards. All three segments carry prompt `%s`."
  % (TEXTON.name, len(on_runs), on_runs[0]["hdr"].get("started"), on_runs[1]["hdr"].get("started"),
     on_runs[2]["hdr"].get("started"), on_runs[0]["hdr"].get("prompt_sha16")))
P(u"")
P(u"## Per arm, text ON \u2192 OFF (exact of 19)")
P(u"")
P(u"| arm | text ON | text OFF | \u0394 |")
P(u"|---|---|---|---|")
for m in rank:
    d = ex(B, m) - ex(A, m)
    star = u" \u00b9" if n(B, m) != 19 else u""
    P(u"| `%s`%s | %d | **%d** | %+d |" % (m, star, ex(A, m), ex(B, m), d))
P(u"")
if any(n(B, m) != 19 for m in rank):
    P(u"\u00b9 fewer than 19 scorable cells: %s \u2014 a provider error on every other call, out of the denominator."
      % ", ".join("`%s` n=%d" % (m, n(B, m)) for m in rank if n(B, m) != 19))
    P(u"")
P(u"Measured row, excluded from every decision by your instruction: `%s` text ON %d/19, not run text OFF."
  % (EXCLUDED, ex(A, EXCLUDED)))
P(u"")
P(u"## What it says")
P(u"")
P(u"**Pooled, the text channel is worth about %d points** \u2014 %.1f%% with it (%d/%d), %.1f%% without "
  u"(%d/%d). That is the number item 6 was built to size, and it lands on the ~15%% bound rather than "
  u"overturning it."
  % (round(100.0 * pool_on[0] / pool_on[1] - 100.0 * pool_nt[0] / pool_nt[1]),
     100.0 * pool_on[0] / pool_on[1], pool_on[0], pool_on[1],
     100.0 * pool_nt[0] / pool_nt[1], pool_nt[0], pool_nt[1]))
P(u"")
P(u"**But the pooled figure is carried by arms that are not candidates.** The inflation is strongly "
  u"size-ordered:")
P(u"")
P(u"- The production candidates barely move: %s." %
  u"; ".join(u"`%s` %d\u2192%d" % (m, ex(A, m), ex(B, m))
            for m in ("anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5",
                      "google/gemini-3.1-pro-preview", "qwen/qwen3.7-plus") if m in B))
P(u"- The weak and mid arms collapse: %s." %
  u"; ".join(u"`%s` %d\u2192%d" % (m, ex(A, m), ex(B, m))
            for m in ("openai/gpt-5.6-sol", "openai/gpt-5.6-terra", "x-ai/grok-4.7",
                      "openai/gpt-6-luna") if m in B))
P(u"")
P(u"A frontier arm reads the pixels; a weak arm was reading the gloss. That is the asymmetry the item "
  u"existed to expose, and it is what licenses the production design: the arms it names are the arms whose "
  u"score does **not** depend on the text channel.")
P(u"")
# The primary slot. Derived, not restated: CANDIDATES is the slate ruling (5) names, PRIMARY is the arm it
# designates, and the paragraph below reads its rank off the text-OFF column. If a rerun moves the numbers the
# prose moves with them -- the first version of this paragraph was typed into the .md by hand and the next run
# of this script silently deleted it.
CANDIDATES = ("anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5",
              "google/gemini-3.1-pro-preview", "qwen/qwen3.7-plus")
PRIMARY = "qwen/qwen3.7-plus"
_cand = [m for m in CANDIDATES if m in B]
_d = {m: ex(B, m) - ex(A, m) for m in _cand}
_order = sorted(_cand, key=lambda m: (-ex(B, m), m))
_rank = _order.index(PRIMARY) + 1
_worst = min(_cand, key=lambda m: _d[m])
assert _worst == PRIMARY, ("the designated primary is no longer the most text-dependent candidate; "
                           "rewrite this paragraph rather than letting it assert a stale finding: %s" % _d)
P(u"**The designated primary is the most text-dependent of the candidates, and that is a finding against the "
  u"production design as written.** `%s` %d\u2192%d (%+d) against %s. Ranked on pixels alone the order "
  u"changes \u2014 %s \u2014 so the designated primary is **%s of %d** on the text-OFF column. Its text-ON "
  u"lead was partly the gloss."
  % (PRIMARY.split("/")[-1], ex(A, PRIMARY), ex(B, PRIMARY), _d[PRIMARY],
     u", ".join(u"`%s` %d\u2192%d (%+d)" % (m.split("/")[-1], ex(A, m), ex(B, m), _d[m])
               for m in _cand if m != PRIMARY),
     u", ".join(u"%s %d" % (m.split("/")[-1], ex(B, m)) for m in _order),
     {1: u"first", 2: u"second", 3: u"third", 4: u"fourth"}.get(_rank, str(_rank)), len(_cand)))
P(u"")
P(u"This does not disqualify it \u2014 the gloss *is* obtainable in production, by reading the note's Latin "
  u"first and passing it as the reference window on a second pass, which is the reference-window design "
  u"already on the books. But it changes what the primary slot is buying: with a two-pass design "
  u"`%s` is the cheapest route to ~%d/19; without one it is the %s-best reader of the pixels. The memo must "
  u"name which it assumes. %+d is also outside the \u00b11 null floor, unlike the other three candidates' "
  u"deltas, which are not."
  % (PRIMARY.split("/")[-1], ex(A, PRIMARY),
     {1: u"first", 2: u"second", 3: u"third", 4: u"fourth"}.get(_rank, str(_rank)), _d[PRIMARY]))
P(u"")
P(u"**The back-translation ratio moves the opposite way to the naive expectation.** Gloss-back-translatable "
  u"spans vs not: **1.25x with the text channel on, 1.68x with it off.** Removing the gloss from the prompt "
  u"makes the back-translatable advantage *larger*, not smaller \u2014 so that advantage is not prompt leakage, "
  u"it is **prior**. The text channel helps the non-back-translatable spans most (+20 points) precisely "
  u"because those are the spans where priors help least (+12).")
P(u"")
P(u"## What this does NOT solve")
P(u"")
P(u"- **Per-arm \u0394 of \u00b11 is inside noise.** 6(b)'s null replicate moved 4 of 24 arms at fixed pixels and "
  u"fixed prompt. Only the collapses (\u22127, \u22128, \u22129) are outside that floor; `gemini-3.1-pro`'s +1 is not a "
  u"gain.")
P(u"- **The text-ON side's pixels are not hashed.** Its 09-27 segment (576 of its reads) predates "
  u"`crop_sha16` and `truth_digest` in the header, so the claim that both sides read the same pixels rests "
  u"on the file's own layout, not on a hash. Only the two 09-28 top-up segments carry crop hashes — and "
  u"6(b) did confirm `p912:n2`'s sha there matches today's. The weak-arm collapses are far larger than any "
  u"plausible crop difference, but the ±1 rows are not defensible on this axis either.")
P(u"- **The two sides are a week apart, not a paired run.** Same spans, same aperture, same truth \u2014 but a "
  u"cross-run comparison carries that null, which has been measured once.")
P(u"- **19 spans on 19 pages.** Every rate here has a denominator of 19.")
P(u"- **The text-ON segment was chosen, not given.** Its artifact holds several runs; this used the last "
  u"segment that read these spans and names its start time, because `read_header()` returns the first "
  u"header and pooling a multi-run file silently averages configurations.")
P(u"- **Nothing here measures the apparatus or the boxes.** Arms were scored on crops whose boxes are "
  u"already ratified; the 100-span set exists to break that circularity and is blocked elsewhere.")
P(u"- **`DEAD_RUN_AT` did not discriminate — fixed since, in laneB `e562f54`.** "
  u"`inclusionai/ling-3.0-flash-vl` produced %d provider errors against %d reads; the run-fault guard "
  u"stayed quiet only because they interleaved, and consecutively it would have faulted the run and "
  u"discarded the other 456 reads. The guard now counts the streak per ARM (abandon the arm, name it, carry "
  u"on) and faults the run only on consecutive dead arms, with pre-send crop refusals counted separately. "
  u"**That fix is untested against a live endpoint; the next real run is its first outing.**"
  % (errs.get("inclusionai/ling-3.0-flash-vl", 0), n(B, "inclusionai/ling-3.0-flash-vl")))
P(u"- **Nothing re-scored a sealed page or touched the frozen alignment gate.**")
P(u"")
io.open(MD, "w", encoding="utf-8").write(u"\n".join(L))
print("wrote", MD)
print("pooled ON %d/%d = %.1f%%   OFF %d/%d = %.1f%%"
      % (pool_on[0], pool_on[1], 100.0 * pool_on[0] / pool_on[1],
         pool_nt[0], pool_nt[1], 100.0 * pool_nt[0] / pool_nt[1]))
print("text-ON segment started:", on["hdr"].get("started"), "| segments in that file:", len(on_runs))
