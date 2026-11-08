# -*- coding: utf-8 -*-
u"""Measure readiness under ruling 2026-11-01 item 4: "has a surface and all needs met".

Two tables, and the second is a COLUMN not a proxy. The readiness verdict is surface AND needs;
exemplar supply is reported beside it because it is what several needs are ABOUT, not because a
supply count makes a span ready. The previous readiness table measured strip, box and exemplars and
never asked whether a surface existed -- which is how it called four cards signable when two had
nowhere to be signed.

A SURFACE is a built document in which a per-glyph verdict for that span can be captured and
exported, AND WHICH IS NOT SPENT. The first draft of this script got that second clause wrong: it
counted the 74-span and pass-2/3 sheets as surfaces, which says a verdict can be recorded there
now -- but those sheets were signed, their exports exist, and their signatures are the very things
the 2026-10-25 audit adjudicated. Offering a spent sheet as a place to sign is how a signature gets
recorded where nobody will read it. Spent status is derived from the presence of the family's signed
export, not asserted.

It also picked "the most recent" document with `sorted(...)[-1]`, which is alphabetical, not recent
-- and it duly named the PROVISIONAL intermediate of the 5-span console instead of the clean-run
one. Recency is now read from mtime.
"""
import glob
import io
import os
import re
import sys
import time

import laneB_report as LBR

# This session, as ListAgents prints it. Typed in, not sniffed from the environment: a
# session id guessed wrong attributes a measurement to a run that did not make it, which
# is worse than one missing. A later session re-running this must change this line.
SESSION = u"goat-yard-archive-eb [aca358]"

LANE = "C:/Users/cnogr/git/goatyard-laneB/pipeline/reextract"
AUDITS = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits"
sys.path.insert(0, LANE)
os.chdir(LANE)
import hebrew_glyph_card as G                 # noqa: E402
import audit_overlay_20261025 as A            # noqa: E402

OUT = []


def w(s=u""):
    OUT.append(s)


# ---- the documents, and whether each is spent ---------------------------------------------------
STEM = re.compile(r"^(glyphsign_[0-9a-f]+(?:_[a-z0-9]+)*?)_[0-9a-f]{8}\.html$")
DOCS = []
for fn in sorted(os.listdir(AUDITS)):
    m = STEM.match(fn)
    if not m:
        continue
    stem = m.group(1)
    signed = sorted(os.path.basename(p) for p in glob.glob(os.path.join(AUDITS, stem + "_signed_*.jsonl")))
    # Pass 1's export is not stem-suffixed: the 74-span sheet's signed rows live in the base jsonl.
    if not signed and "_74span" in stem:
        base = "glyphsign_0401b636ffa7bf1a.jsonl"
        if os.path.exists(os.path.join(AUDITS, base)):
            signed = [base]
    txt = io.open(os.path.join(AUDITS, fn), encoding="utf-8", errors="replace").read()
    DOCS.append(dict(fn=fn, stem=stem, signed=signed, mtime=os.path.getmtime(os.path.join(AUDITS, fn)),
                     spans=set(re.findall(r"p\d+:n\d+", txt)),
                     captures=('id="dl"' in txt or "doConfirm" in txt or 'class="tile' in txt)))

CARDS = [c["span_id"] for c in G.CARDS]
POP = sorted(set(r["span_id"] for r in A.AUDIT) | set(G.NEEDS))
spans = G.card_spans()[0]


def verdicts(sid):
    return ", ".join(sorted(set(r["verdict"] for r in A.AUDIT if r["span_id"] == sid))) or "-"


def surfaces(sid):
    live = [d for d in DOCS if sid in d["spans"] and d["captures"] and not d["signed"]]
    spent = [d for d in DOCS if sid in d["spans"] and d["signed"]]
    live.sort(key=lambda d: d["mtime"], reverse=True)
    return (live[0] if live else None), live[1:], spent


for _line in LBR.header(
        u"Lane B readiness — 2026-11-08 reissue, with p596:n2 read as SEALED",
        SESSION,
        built_from=u"Built from `hebrew_glyph_card` + `audit_overlay_20261025` at commit `%s`."
                   % os.popen("git -C %s rev-parse --short HEAD" % LANE).read().strip(),
        supersedes=u"**Supersedes** `REPORT_laneB_20261101_readiness_reissued.md`, which in "
                   u"turn superseded `REPORT_laneB_20261101_sitting_readiness.md` (committed "
                   u"`3ed712ef`). Both files are kept. From the sitting report, nothing is "
                   u"withdrawn except its readiness count, which had no surface clause. From "
                   u"the 11-01 reissue, **one paragraph is withdrawn**: it reported p596:n2 "
                   u"as having no surface *at all* and read that absence as a gap. The "
                   u"absence is a **seal** — see below. Its readiness counts stand; the "
                   u"cause it gave for that one row does not."):
    w(_line)
w()
w(u"## What readiness means here")
w()
w(u"**Readiness = has a live surface AND every recorded need met.** Two clauses, and the first one")
w(u"is the one the previous readiness table was missing: it measured strip, box and exemplar supply")
w(u"and never asked whether anywhere existed to record an answer, which is how it called four cards")
w(u"signable when two of them had nowhere to be signed.")
w()
w(u"A **surface** is a built document in which a per-glyph verdict for that span can be captured and")
w(u"exported. The glyph-card page (`hebrew_glyph_cards_20260927.html`) is **not** one: it poses the")
w(u"question and carries no controls. That separation is deliberate \u2014 the verdict-only law keeps")
w(u"model reads off any surface a human signs on.")
w()
w(u"A surface is **live** only if it is not spent. A sheet whose signed export exists is spent: its")
w(u"signatures are the very things the 2026-10-25 audit adjudicated, and offering one as a place to")
w(u"sign would record a verdict where nobody will read it. Spent status below is derived from the")
w(u"presence of that family's signed export, not asserted.")
w()
w(u"## Table 1 \u2014 readiness")
w()
w(u"| span | FILE page | audit verdict(s) | qualifies (item 3, clause 1) | needs recorded | unmet "
  u"| live surface | READY |")
w(u"|---|---|---|---|---|---|---|---|")
rows = []
for sid in POP:
    q, qwhy = G.audit_qualifies(sid)
    ns = G.needs_state(sid)
    un = [n["key"] for n in ns if not n["met"]]
    live, _older, spent = surfaces(sid)
    ready = bool(live) and q and not un
    # The span id NAMES the page, so a row the build-set dict does not hold still has a FILE
    # page. A dash there read as "no page known", which is false of all fourteen. The dict is
    # kept as a cross-check rather than as the source.
    pg = int(sid.split(":")[0][1:])
    if sid in spans and int(spans[sid]["page"]) != pg:
        pg = u"%d (the record says %s)" % (pg, spans[sid]["page"])
    rows.append((sid, ready, live, spent, q, un))
    w(u"| `%s` | %s | %s | %s | %s | %s | %s | %s |"
      % (sid, pg, verdicts(sid), u"yes" if q else u"no \u2014 " + qwhy,
         u", ".join(u"%s (%s)" % (n["key"], n["source"]) for n in ns) or u"none",
         u", ".join(un) or u"none",
         (u"`%s`" % live["fn"]) if live else u"**none**",
         u"**YES**" if ready else u"no"))
w()
w(u"**Ready: %d of %d** \u2014 %s. All five are on the live re-sign console."
  % (sum(1 for r in rows if r[1]), len(rows), u", ".join(u"`%s`" % r[0] for r in rows if r[1])))
w()
w(u"The nine that are not ready split by CAUSE, and the two causes are not the same thing:")
w()
w(u"- **Eight fail the verdict clause**, i.e. a human already decided they need no re-signing or")
w(u"  never decided at all: `crop_edge_cut` (p326:n11, p428:n0, p622:n0 \u2014 the box was wrong, not")
w(u"  the reading), `agreed` (p558:n3, p594:n0), `not_adjudicated` (p735:n0, p910:n3 \u2014 the audit")
w(u"  did not reach them), and p596:n2, which has no audit row at all — and which is **sealed**,")
w(u"  so it will not get one. See below.")
w(u"- **One fails on an unmet need**: p233:n4, which a human WANTS settled and cannot have yet \u2014")
w(u"  there is no zayin exemplar anywhere, signed or in a ratified signature (Table 2, 0 + 0).")
w()
w(u"**None of the nine has a live surface**, and that is by construction rather than by accident:")
w(u"the console's population IS the rule, so a span the rule excludes is absent from the only")
w(u"unspent sheet. The two clauses therefore agree on all fourteen rows here — which means this")
w(u"table cannot currently distinguish \"no surface\" from \"does not qualify\". It will the moment a")
w(u"verdict lands on p735:n0 or p910:n3 without a console being rebuilt.")
w()
# READ off the predicate, never typed. The sentence this replaces was wrong because it was
# typed from a tally; a corrected sentence typed the same way is one ruling away from being
# wrong again. The `else` branch exists so that a lifted seal cannot print a stale claim.
_sealed, _seal_why = G.seal_state(u"p596:n2")
_sheet_met, _sheet_why = G.need_met(u"p596:n2", u"sheet")
_wd = (G.DIRECTED.get(u"p596:n2") or {}).get(u"sheet_withdrawn") or {}
if _sealed:
    w(u"One span has no surface, and the cause is a **seal**, not an oversight: **p596:n2 is")
    w(u"SEALED**. Measured: `%s`. Fourteen pages are sealed and ten spans are in the Hebrew"
      % _seal_why)
    w(u"seal table, and **none of the ten appears in the 96-span parent draw or in the frozen")
    w(u"74**. So no sheet could have contained this span without the seal having been broken")
    w(u"first. It is in the 21-span build set and not in the frozen 74, which is the seal")
    w(u"operating at the draw — upstream of every sheet.")
    w()
    w(u"**The 11-01 reissue reported this as \"no surface *at all* … nobody has ever been shown")
    w(u"it to sign\" and read it as a gap. That paragraph is withdrawn.** Every clause in it was")
    w(u"true and the reading was wrong: it filed a decision as an omission, and a reader came")
    w(u"away thinking a sheet was owed.")
    if _wd:
        w()
        w(u"Asked whether ruling 2's read-only carve-out reached a human signing surface, Chris")
        w(u"ruled **no** on %s: \"%s\" The sheet clause is **withdrawn**, the pin and"
          % (_wd["on"], _wd["words"]))
        w(u"`seal_ruling=None` are kept as the record, and the span's standing is **sealed and")
        w(u"final**. Its `sheet` need is therefore **closed, not owed** — the console reports it")
        w(u"as `%s`" % _sheet_why.split(u":")[0])
        w(u"while leaving it unmet, because the span has never been on a sheet and that stays")
        w(u"true. Its other recorded need, `audit_row`, is in the same position: nobody will")
        w(u"adjudicate a span nobody may open.")
    else:
        w()
        w(u"**No withdrawal is recorded and no ruling lifts the seal.** The directive to sheet")
        w(u"this span and the seal are in collision and the console refuses to build. A human")
        w(u"must rule.")
else:
    w(u"**p596:n2 is no longer sealed** (`%s`), so the paragraph this report used to carry"
      % _seal_why)
    w(u"about it does not apply and has not been replaced. Whoever lifted the seal owes this")
    w(u"report a line; `sheet` need reads: %s" % _sheet_why)
w()

# ---- the exemplar column ------------------------------------------------------------------------
w(u"## Table 2 \u2014 exemplar supply (a column, not a proxy)")
w()
w(u"Counted exactly as the card renders it: signed per-letter exemplars from the volume, plus span")
w(u"exemplars drawn from ratified signatures with the card's own span excluded and every RIVAL")
w(u"candidate at that position excluded (exemplar rule 2 \u2014 an exemplar whose truth contains the")
w(u"rival begs the question it was shown to settle). A **0 in the signed column is the volume-wide")
w(u"fact**: there are no signed per-letter exemplars at all yet. A 0 in the span column is usually")
w(u"principled rather than a gap \u2014 dalet and resh share almost every word in this fount, so")
w(u"excluding resh leaves no dalet.")
w()
w(u"| span | position | candidates | letter | signed | span | total | ready? |")
w(u"|---|---|---|---|---|---|---|---|")
RDY = {r[0]: r[1] for r in rows}
for c in G.CARDS:
    sid = c["span_id"]
    for a in G.card_asks(c):
        for letter in a["candidates"]:
            partners = tuple(x for x in a["candidates"] if x != letter)
            nsig = len(G.sig_exemplars(letter))
            nspan = len(G.exemplars(letter, partners, exclude=(sid,)))
            w(u"| `%s` | %s | %s | %s | %d | %d | %d | %s |"
              % (sid, a.get("pos"), u"/".join(a["candidates"]), letter, nsig, nspan, nsig + nspan,
                 u"yes" if RDY.get(sid) else (u"no" if sid in RDY else u"not in the audit population")))
w()
w(u"Read the two tables together and the point of keeping them apart is visible: **p831:n2 is READY")
w(u"with a 0 in the dalet column, and p233:n4 is NOT READY with a 0 in the zayin column.** Supply is")
w(u"not the verdict. p831:n2's zero is exemplar rule 2 doing its job (every dalet word in the")
w(u"corpus also carries a resh); p233:n4's zero is an absence nothing on the card can fix.")
w()
w(u"## Surfaces, classified")
w()
w(u"| document | family | spent by | captures | holds (of the population) |")
w(u"|---|---|---|---|---|")
for d in sorted(DOCS, key=lambda d: d["mtime"]):
    held = sorted(d["spans"] & set(POP))
    w(u"| `%s` | `%s` | %s | %s | %d: %s |"
      % (d["fn"], d["stem"], (u", ".join(u"`%s`" % s for s in d["signed"])) or u"**not spent**",
         u"yes" if d["captures"] else u"no", len(held),
         u", ".join(held) if len(held) <= 6 else u"%s, \u2026" % u", ".join(held[:6])))
w()

w(u"## Which document to open")
w()
w(u"Three unspent documents hold overlapping populations under near-identical names, so:")
w()
w(u"- **Open `glyphsign_0401b636ffa7bf1a_resign_5span_73bcd073.html`.** Clean run at commit")
w(u"  `f784bdd`, 5 rows, 18 consonant tiles / 0 gap, 24 counted checks, prose digest `2688fad8`,")
w(u"  87389 bytes, reversal guard sha16 `af5d39a25217ed5c`.")
w(u"- `..._resign_4span_0dee578b.html` is item 1's console as ruled, built on a clean run before")
w(u"  item 3 widened the population to five. Nothing in it is false; it is superseded, and kept.")
w(u"- `..._resign_5span_eb747398.html` has been **moved to `audits/superseded_20261101/`**. It was")
w(u"  built on a dirty tree (its own banner says PROVISIONAL) and its subtitle still told the signer")
w(u"  that p628:n2's prior signature had been \"ruled a SIGNATURE ERROR by the audit of 2026-10-25\".")
w(u"  The audit ruled no such thing — it refused to decide that span. A signing surface handing")
w(u"  the signer a prior dressed as a finding is the one thing this console must not do, so it is")
w(u"  out of the way rather than beside the good one under a name one character different.")
w()
w(u"## What this does NOT answer")
w()
w(u"- Readiness says a verdict CAN be recorded, not that it is right to record one. p628:n2 is ready")
w(u"  because every need the audit recorded is met; whether the strip actually settles the")
w(u"  ascender/descender question is for the person looking at it.")
w(u"- The surface clause is derived from built files on disk. A document deleted or moved changes")
w(u"  this table, and nothing pins it: there is no assertion anywhere that the live console still")
w(u"  exists. The signer's own run is what proves that, each time.")
w(u"- \"Spent\" is derived from the presence of a signed export for the family. A sheet signed but")
w(u"  never exported would read as live here, and a sheet exported under a name this pattern misses")
w(u"  would read as live too. The pattern is stated above so it can be checked.")
w(u"- Table 2's signed column is 0 in every row. That is the volume-wide fact and it has not moved:")
w(u"  **no per-letter exemplar has been signed anywhere in vol. 1**. Every exemplar on every card is")
w(u"  a span exemplar drawn from a ratified signature.")
w(u"- p910:n3 and p735:n0 are unchanged by this ruling. Their recorded need is a human adjudication,")
w(u"  which no renderer can supply, so they wait on the audit being extended — not on code.")
w()

# A NEW dated file. The 11-01 reissue is not overwritten: it is what this lane said on that
# date, and a dated report rewritten in place is a report that was never wrong.
p = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1/REPORT_laneB_20261108_readiness_sealed.md"
io.open(p, "w", encoding="utf-8", newline="\n").write(u"\n".join(OUT) + u"\n")
print("wrote %s (%d lines)" % (p, len(OUT)))
for ln in OUT:
    if ln.startswith("|") or ln.startswith("**Ready"):
        print(ln)
