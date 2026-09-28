"""Item 3 -- the (box, text) binding: is each signed text actually inside the crop its box cuts?

WHY THIS IS NOT THE TEST IT LOOKS LIKE. The obvious form of item 3 is "read every crop locally and
check the signed text came back." That test is INVALID here, and the reason is measured, not
supposed: every arm sends TWO images -- the context strip first, then the aperture crop
(`hebrew_local_arms.read_one`, `hebrew_aperture_diag.read_one`, both
`"images": [_b64(context_strip), _b64(crop)]`). The strips carry 9.8-16.2% ink. A model that can see
the strip can return the full signed text no matter what the box contains, so a full recovery is
evidence about the STRIP, not about the box.

p912:n2 is the proof. Its box holds one of two signed words; 14 reads came back `clipped`, and 2 came
back `exact`. Those 2 did not see a wider box. They read the strip. A binding test that counted them
as confirmation would have declared the box sound on the strength of the one span we already know is
broken.

So the evidence here is used ASYMMETRICALLY, which is the whole design:

  `clipped` (read is a strict substring of the signed text) is SOUND evidence the box is too small.
      The strip was available and would have let the model return MORE. It returned LESS. Nothing
      but the crop explains a short answer.

  full recovery (`exact` / `punct-only` / `nikud-only` / `contains`) is NOT ADMISSIBLE as
      confirmation while the strip is sent. It is recorded, and it is not counted.

The consequence, stated plainly rather than worked around: **this test can detect a broken binding
and cannot confirm an intact one.** Confirmation needs reads taken with the context strip withheld,
which is item 6. Item 3 therefore ships the half that is sound now and names the half that is
blocked, instead of producing a reassuring table built on a confound.

GEOMETRY IS THE AUTHORITY, and it needs no model at all: `crop_fault` for blank/clamped, and the
line-band count for whether the box holds exactly the one line a span occupies. That half is
deterministic, so code owns it (`hebrew_glyph_card.box_quality`). The reads are only consulted for
the one question geometry cannot answer: whether the box is wide enough for the WORDS, since a box
can hold exactly one line band and still cut a two-word span in half -- which is precisely p912:n2,
3 line bands tall and one word wide.

    python hebrew_bind.py              # the binding table
    python hebrew_bind.py cands        # candidate wrong signatures, for adjudication not for scoring
    python hebrew_bind.py selftest     # born-tests
"""
import collections
import io
import json
import sys
from pathlib import Path as _Path

import hebrew_aperture_diag as D
import hebrew_glyph_card as G

READ_FILES = (("C", "hebrew_aperture_reads_20260920.jsonl"),
              ("D", "hebrew_local_arms_reads_20260920.jsonl"),
              ("OR", "hebrew_frontier_or_reads_20260927.jsonl"))
LOCAL_LANES = ("C", "D")          # on-prem endpoints; OR is OpenRouter
FULL = ("exact", "punct-only", "nikud-only", "contains")
"""Classes in which the whole signed text came back. NOT admissible as binding confirmation -- see
the module docstring. Listed so the count is visible and its exclusion is deliberate."""


def reads(aperture="A2_spanbox"):
    """Every recorded read of `aperture`, tagged with the endpoint lane it came from."""
    out = []
    for lane, fn in READ_FILES:
        p = D.DATA / fn
        if not p.exists():
            continue
        for ln in io.open(p, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            o = json.loads(ln)
            if "span_id" not in o or o.get("aperture") != aperture:
                continue
            if o.get("model") in D.DROPPED_ARMS:
                continue
            o["lane"] = lane
            out.append(o)
    return out


def bind_rows(aperture="A2_spanbox", local_only=False, include_sealed=True):
    """Per signed span: the geometry verdict, the read evidence, and a binding verdict.

    Verdicts, and what each one licenses:
      `broken:box-too-small`  `clipped` reads OUTNUMBER full recoveries. SOUND. The box cuts the
                              signed text.

                              The ratio, not the count, and the cut is measured rather than chosen.
                              Seven spans have at least one clipped read; their clipped:full ratios
                              are 1:23, 2:21, 2:20, 3:22, 1:22, 1:7 -- and p912:n2 at 14:3. The band
                              between 0.14 and 4.7 is empty, so any cut inside it is the same cut.
                              A lone clipped read among twenty full recoveries is a reader stopping
                              early on a box twenty others read whole: p253:n2's three clips all
                              returned the first word of three, while twenty-two models returned all
                              three, so the box demonstrably holds them. Minority clips stay visible
                              in `n_clipped` rather than being dropped -- they are a weak signal, not
                              no signal.
      `broken:no-recovery`    reads exist, not one recovered the signature, none clipped. This says
                              the (box, text) pair does not hold together and does NOT say which of
                              the two is wrong -- a wrong box and a wrong signature look identical
                              from here. Adjudication is a card, never a tally.
      `unconfirmable`         the signature came back, which under a shared context strip is not
                              evidence about the box. Geometry is the only verdict available.
      `no-evidence`           the crop is faulted, so no read can speak about the aperture at all.
      `no-reads`             nothing read this span.
    """
    rs = reads(aperture)
    if local_only:
        rs = [r for r in rs if r["lane"] in LOCAL_LANES]
    bq = {r["span_id"]: r for r in G.box_quality(include_sealed=include_sealed)}
    # The crops that were ACTUALLY SENT, read from crop_faults.json rather than re-cut. None means the
    # measurement was never made, and an unmeasured crop cannot license a read: it is treated exactly
    # like a faulted one, so an absent audit can never be mistaken for a clean one.
    # From the frozen archive, NOT from the live fault table: the live one describes the re-cut
    # crops, which no arm has ever seen.
    sent = D.sent_faults(aperture)
    stale = D.crops_changed(aperture)
    rows = []
    for s in D.build_set(include_sealed=include_sealed):
        sid = s["span_id"]
        if not s["truth"] or s["truth"] == D.NOT_HEBREW:
            continue
        mine = [r for r in rs if r["span_id"] == sid]
        cls = collections.Counter(D.classify(r.get("gated") or "", s["truth"]) for r in mine)
        b = bq.get(sid, {})
        # fault_fresh answers "is the box sound today?" -- a geometry and ratification question.
        # fault_sent answers "can these reads speak about the aperture?" -- an evidence question, and
        # the only one that may decide the verdict. They came apart the moment the mapping was fixed:
        # a box that now cuts cleanly does not retroactively make a blank crop a valid stimulus.
        fault_fresh = b.get("fault")
        fault_sent = "unmeasured" if sent is None else sent.get(sid)
        # Two ways a read can fail to be evidence, and they are different facts. Either the crop it was
        # taken on was faulted when it was sent, or the crop has been re-cut since and the read is no
        # longer about any pixels we hold. A fresh geometry fault is NEITHER: it says the box is wrong
        # today, which has no bearing on whether a sound crop was shown yesterday.
        void = ("crop-faulted-as-sent:%s" % fault_sent if fault_sent else
                "crop-changed-since-read" if sid in stale else None)
        faulted = bool(void)
        n_clip, n_full = cls["clipped"], sum(cls[c] for c in FULL)
        if not mine:
            v = "no-reads"
        elif faulted:
            v = "no-evidence"
        elif n_clip > n_full:
            v = "broken:box-too-small"
        elif n_full:
            v = "unconfirmable"
        else:
            v = "broken:no-recovery"
        rows.append(dict(span_id=sid, page=s["page"], truth=s["truth"],
                         words=len(s["truth"].split()), fault=fault_sent or fault_fresh,
                         fault_sent=fault_sent, fault_fresh=fault_fresh, evidence_void=void,
                         crop_stale=sid in stale,
                         lines=b.get("lines"), one_band=bool(b.get("one_band")),
                         n_reads=len(mine), n_clipped=n_clip, n_full=n_full,
                         n_wrong=cls["wrong"], n_abstain=cls["abstain"],
                         classes=dict(cls), verdict=v))
    return rows


def bind_report(aperture="A2_spanbox", local_only=False):
    """(rows, verdict_counts, broken_span_ids) -- what item 3's born-test asserts against."""
    rows = bind_rows(aperture, local_only)
    counts = collections.Counter(r["verdict"] for r in rows)
    broken = [r["span_id"] for r in rows if r["verdict"].startswith("broken")]
    return rows, dict(counts), broken


def candidates(aperture="A2_spanbox", floor=0.5):
    """Spans where NOTHING recovered the signature and the readers agree on one other string.

    NOT a verdict, and deliberately not usable as one. Two independent reasons:
      - the readers share a context strip, so their agreement measures the shared channel and not
        the print (agreement exists != agreement discriminates);
      - a more-fluent reading that differs from the printed form is the plausible-word SUBSTITUTION
        class, which is the failure mode, not the fix. Fluency is evidence of a language model, not
        of a fount.
    So this returns a QUEUE for glyph-card adjudication by eye, with the modal string named so the
    card can be built. The detector is a human reading one glyph card; a vote threshold caught one
    of these at 80% and missed another at 48%, which is why `floor` selects what to LOOK at and
    decides nothing."""
    out = []
    for r in bind_rows(aperture):
        if r["verdict"] != "broken:no-recovery":
            continue
        mine = [x for x in reads(aperture) if x["span_id"] == r["span_id"]]
        c = collections.Counter(D._norm(x.get("gated") or "") for x in mine
                                if (x.get("gated") or "").strip() and D.HEB.search(x.get("gated") or ""))
        if not c:
            continue
        modal, n = c.most_common(1)[0]
        signed = D._norm(r["truth"])
        out.append(dict(span_id=r["span_id"], signed=signed, modal=modal, n_modal=n,
                        n_reads=r["n_reads"], share=round(n / float(max(1, r["n_reads"])), 3),
                        one_letter=_one_letter_apart(signed, modal),
                        above_floor=n / float(max(1, r["n_reads"])) >= floor))
    return sorted(out, key=lambda r: -r["share"])


_WS = (" ", chr(10), chr(9))   # a word boundary at the join; chr(10) written out because the shell eats escapes


def contains_population(aperture="A2_spanbox"):
    """Split the `contains` reads by WHY the signature is a substring of the read. A DIAGNOSTIC.

    It does not touch D.classify and does not move a single score. The scoring rules stay frozen until
    item 7's one re-tally, per the batch rule -- this function exists so that re-tally knows what it is
    absorbing, and so the claim below is pinned by a born-test instead of remembered.

    THE CLAIM IT REFUTES. The BOX QUALITY note in hebrew_glyph_card said the `contains` class is
    mechanically caused by PAD=12 pulling the lines above and below into the crop: "an arm asked to
    transcribe the crop returns the signed span with its neighbours attached and was scored wrong for
    obeying the prompt." Measured over all 22 contains reads AS THEY STOOD UNDER THE
    PRE-BATCH TRUTH TABLE (Chris's re-sign batch of 2026-09-27 moved four signatures, and the
    substring test runs against those signatures, so this population moved with them -- every
    figure in this docstring belongs to the table that was in force when it was measured),
    vertical neighbours account for none of them that can be identified as such. What is actually in the bucket:

      extra-material   whole extra words on the SAME line. 10 of 22, and 10 of those 10 are p124:n4 --
                       the widest box in the set (458px for a two-word signature), whose reads pick up
                       the Latin `quasi` sitting beside the Hebrew. A real box fault, on one box.
      appended-token   a letter or two glued to the signed word with no space: p491:n1 `bet-shin-mem-
                       ayin-vav` for `bet-shin-mem-ayin`, p200:n2 twice. These are MISREADS wearing the
                       contains label, because the test is `truth in read` and a suffix satisfies it.
      punct-tail       trailing punctuation only, e.g. p102:n0 `... :`. punct-only is checked BEFORE
                       contains in classify, so these reaching contains means its character set is
                       missing the mark -- a real defect, and the smallest one here.
      envelope-leak    not a reading at all: p293:n0 returned `{"hebrew":"...` and p491:n1 returned 200
                       characters of deliberation with the word quoted inside it. A broken parse gets
                       CREDITED by a substring test. This is the one that matters, because it is a free
                       pass for exactly the failure the typed contract exists to prevent.
      duplication      the signature twice (p427:n4), which is a degenerate loop, not containment.

    So `contains` names a geometric cause and implements a string relation, and the two populations
    barely overlap. The horizontal-overrun reading is corroborated three ways on p124:n4 only (widest
    box; most contains reads; Latin material in the reads). A word-group count per band was tried as a
    fourth signal and DISCARDED: with the whitespace gap swept 4 to 20px the per-span counts swing by
    up to 10 (p219:n0 goes 10 to 1), so the screen is dominated by a parameter nobody derived. p124:n4
    ranks highest at every gap, which is the only part of it that survives."""
    import re as _re
    full = {x["span_id"]: x for x in D.build_set(include_sealed=True)}
    out = {}
    for r in reads(aperture):
        sid = r["span_id"]
        t = (full.get(sid) or {}).get("truth")
        if not t:
            continue
        g = r.get("gated") or ""
        if D.classify(g, t) != "contains":
            continue
        i = g.find(t)
        before, after = g[:i], g[i + len(t):]
        extra = before + after
        # Each test keys on a distinct SHAPE of output, so that the split is not tuned to an answer.
        # A count of Latin words beats a longest-Latin-run test: the first version used a 12-character
        # run and put p491:n1's 200-character deliberation under extra-material, because its longest
        # Latin word is `something` at 9. Meanwhile p124:n4's single Latin `quasi` IS page material and
        # must stay extra-material. Prose is many Latin words; a transcription is at most a few.
        latin = [w for w in _re.findall(r"[A-Za-z]+", g) if len(w) >= 3]
        frag = [w for w in _re.findall(r"[^\W\d_]+", extra, _re.UNICODE) if len(w) >= 2]
        if '{"' in g or "}" in g or len(latin) >= 3:
            kind = "envelope-leak"
        elif t and g.replace(t, "").strip() == "":
            kind = "duplication"
        elif extra.strip() and not _re.search(r"[^\W\d_]", extra, _re.UNICODE):
            kind = "punct-tail"
        elif (before and not before.endswith(_WS)) or (after and not after.startswith(_WS)):
            kind = "appended-token"
        elif not frag:
            kind = "stray-letter"
        else:
            kind = "extra-material"
        out.setdefault(kind, []).append((sid, g))
    return out


def contains_counts(aperture="A2_spanbox"):
    """{kind: n} over the contains reads, plus the span each kind concentrates in."""
    pop = contains_population(aperture)
    return {k: len(v) for k, v in sorted(pop.items(), key=lambda kv: -len(kv[1]))}


def _one_letter_apart(a, b):
    """True when two equal-length unpointed strings differ in exactly one position.

    Reported because a single-glyph difference is what a FOUNT dispute looks like, while a whole
    different word is what a language model's guess looks like. It is a hint for triage; it is not
    a claim that either string is right."""
    a, b = G.strip_nikud(a or ""), G.strip_nikud(b or "")
    if len(a) != len(b):
        return False
    return sum(1 for x, y in zip(a, b) if x != y) == 1


def report(aperture="A2_spanbox", write=True):
    rows, counts, broken = bind_report(aperture)
    lrows, lcounts, lbroken = bind_report(aperture, local_only=True)
    one, tot, viol = G.one_band_report()
    lines = ["# Item 3 -- the (box, text) binding", "",
             "All page numbers are FILE pages; printed = file - 88.", "",
             "A full recovery of the signed text is **not** counted as confirmation: every arm is",
             "sent the context strip alongside the crop, so the signature can come back from the",
             "strip regardless of what the box holds. `clipped` is the sound signal -- the strip",
             "would have let the model say MORE, and it said LESS. See the module docstring.", "",
             "| span | words | lines | 1 band | reads | clipped | full | wrong | abstain | verdict |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| `%s` | %d | %s | %s | %d | **%d** | %d | %d | %d | `%s` |"
                     % (r["span_id"], r["words"], r["lines"], "yes" if r["one_band"] else "no",
                        r["n_reads"], r["n_clipped"], r["n_full"], r["n_wrong"], r["n_abstain"],
                        r["verdict"]))
    lines += ["", "Verdicts, all reads: `%s`" % counts,
              "", "Verdicts, local endpoints only (C+D): `%s`" % lcounts,
              "", "Geometry, independent of any read: **%d of %d** measurable boxes hold exactly one"
              " line band. Violating: %s" % (one, tot, ", ".join("`%s`" % v for v in viol)), ""]
    c = candidates(aperture)
    if c:
        lines += ["## Candidate wrong signatures -- a queue for adjudication, NOT a result", "",
                  "Nothing recovered the signature and the readers agree on another string. Their",
                  "agreement is confounded (shared strip) and fluency is the substitution class, so",
                  "these are cards to look at, not corrections to apply.", "",
                  "| span | signed | modal read | n | share | one letter apart |",
                  "|---|---|---|---|---|---|"]
        for r in c:
            lines.append("| `%s` | `%s` | `%s` | %d/%d | %.0f%% | %s |"
                         % (r["span_id"], r["signed"], r["modal"], r["n_modal"], r["n_reads"],
                            100 * r["share"], "**yes**" if r["one_letter"] else "no"))
        lines.append("")
    txt = "\n".join(lines) + "\n"
    if write:
        (D.DATA / "bind_report.md").write_text(txt, encoding="utf-8")
        (D.DATA / "bind_report.json").write_text(
            json.dumps(dict(rows=rows, counts=counts, local_counts=lcounts, broken=broken,
                            one_band=[one, tot, viol], candidates=c),
                       ensure_ascii=False, indent=1), encoding="utf-8")
    return rows, counts, broken, c


def selftest():
    n = f = 0

    def ck(name, cond, detail=""):
        nonlocal n, f
        n += 1
        if not cond:
            f += 1
        print("  %s  %s%s" % ("ok  " if cond else "FAIL", name,
                              "" if cond else "   <- %r" % (detail,)))

    rows, counts, broken, cands = report(write=False)
    by = {r["span_id"]: r for r in rows}

    # The confound is the whole design, so it is asserted structurally: if an arm ever stops sending
    # the strip, this test must fail and force the docstring to be rewritten rather than quietly
    # becoming a valid confirmation test that still refuses to confirm.
    _here = _Path(__file__).parent
    for mod in ("hebrew_local_arms.py", "hebrew_aperture_diag.py"):
        src = io.open(_here / mod, encoding="utf-8").read()
        # The literal, with no fallback clause. A check with an `or "context_strip" in src` escape
        # hatch passes on a module that merely mentions the word, which is every module here -- and a
        # probe that cannot miss is not a probe. If an arm stops sending the strip, this must go red
        # and force the docstring's reasoning to be redone, because the asymmetry below would then be
        # unnecessary and this file would be refusing to confirm for no reason.
        ck("%s sends the strip FIRST and the crop second, as one images list" % mod,
           '"images": [_b64(context_strip), _b64(crop)]' in src, mod)
        ck("%s has exactly one images list, so the check cannot miss a second call path" % mod,
           src.count('"images"') == 1, src.count('"images"'))

    ck("a full recovery is never counted as confirmation",
       all(r["verdict"] != "bound" for r in rows) and "bound" not in counts, counts)

    # p912:n2 -- the case the asymmetry exists for. 14 clipped AND 3 full; counting the full ones
    # would have called the one box we know is broken sound.
    p912 = by["p912:n2"]
    ck("p912:n2 is detected as box-too-small", p912["verdict"] == "broken:box-too-small", p912["verdict"])
    ck("p912:n2 shows clipped reads outnumbering full recoveries",
       p912["n_clipped"] >= 14 and p912["n_clipped"] > p912["n_full"],
       (p912["n_clipped"], p912["n_full"]))
    # This used to assert "and its crop is not one band", which was the ink-run artifact talking: the
    # crop holds ONE clean 37px band. The box is too NARROW, not multi-line, and no vertical measurement
    # can see that. The reads are the only evidence of it -- which is why the verdict is earned by the
    # clip ratio and not by geometry.
    ck("p912:n2's box is 2 signed words in ONE clean band -- the fault is horizontal",
       p912["words"] == 2 and p912["one_band"], (p912["words"], p912["lines"], p912["one_band"]))

    # p124:n4 -- the other direction. The box holds MORE than the signature, which is a box defect
    # that the read evidence cannot call broken, because `contains` is a full recovery.
    p124 = by["p124:n4"]
    ck("p124:n4 recovers the signature with neighbours attached (contains)",
       p124["classes"].get("contains", 0) >= 10, p124["classes"])
    ck("p124:n4 is therefore unconfirmable, not bound",
       p124["verdict"] == "unconfirmable", p124["verdict"])

    # The two blank crops cannot supply binding evidence, however much Hebrew came back from them.
    # This is asserted against the AS-SENT fault on purpose. Lane A's mapping fix made both boxes cut
    # cleanly, and for one turn bind called p423:n3 `broken:no-recovery` -- indicting a box for reads
    # taken off a white rectangle. A fixed box does not retroactively validate a blank stimulus.
    for sid in ("p423:n3", "p726:n3"):
        ck("%s yields no binding evidence (crop AS SENT was faulted)" % sid,
           by[sid]["verdict"] == "no-evidence" and by[sid]["fault_sent"],
           (by[sid]["verdict"], by[sid]["fault_sent"], by[sid]["fault_fresh"]))
    ck("both blank crops now cut clean, so the two fault questions genuinely disagree",
       all(by[sid]["fault_fresh"] is None and by[sid]["fault_sent"] for sid in ("p423:n3", "p726:n3")),
       {sid: (by[sid]["fault_sent"], by[sid]["fault_fresh"]) for sid in ("p423:n3", "p726:n3")})

    # Geometry is separate from, and stricter than, the read evidence.
    one, tot, viol = G.one_band_report()
    # WAS "unchanged at 3 of 18". That number was a measurement artifact, not a debt: the check behind
    # it counted INK RUNS at 12% of peak, and pointed Hebrew is built out of thin runs -- a nikud row,
    # an ascender, a neighbour's descender inside the 12px pad. 15 of 18 sound boxes were reported
    # multi-line, and those 15 were the held redraw queue. Corrected (hebrew_glyph_card.MIN_BAND_PX /
    # MAX_BAND_PX, both taken from empty bands in the measurements), the debt is ONE box: p362:n1,
    # whose single band is 67px where every other band in the corpus is 30 to 38.
    # PIN THE MEMBERSHIP, NOT THE TOTAL. This is the third time in one session that a 18-denominator
    # survived a change of ±2 in both directions and reported nothing. On 2026-09-27 p138:n6 and
    # p596:n2 entered the measurable population (Chris signed them, so they acquired truth) while
    # p423:n3 and p726:n3 left it (their A2 crops are blank, so there is nothing to measure) -- and
    # `(one, tot) == (17, 18)` stayed true across all four moves. Both new boxes measure one clean band
    # of 30 and 31px, which is an out-of-sample confirmation of MIN_BAND_PX rather than a coincidence:
    # neither was used to derive the 20px threshold.
    # 20 since Lane A's dc573ca (paste origins persisted). p423:n3 and p726:n3 joined because
    # box_quality cuts FRESH from the page -- it never reads the stored PNG -- so a mapping fix moves
    # this population immediately, while crop_faults.json still describes the crops actually sent.
    # Those two numbers are allowed to disagree until the re-cut; they measure different things.
    _MEASURED = {"p102:n0", "p124:n4", "p138:n5", "p138:n6", "p200:n2", "p217:n2", "p219:n0",
                 "p253:n2", "p293:n0", "p360:n0", "p362:n1", "p423:n3", "p427:n4", "p491:n1",
                 "p596:n2", "p726:n3", "p895:n0", "p897:n4", "p900:n4", "p912:n2"}
    _got = {r["span_id"] for r in G.box_quality(True) if r["lines"] is not None}
    ck("the measurable box population is exactly the expected set", _got == _MEASURED,
       sorted(_got ^ _MEASURED))
    # One, not three: the mapping fix recovered both previously-blank crops. p657:n0 stays
    # unmeasurable for a different and unfixed reason -- it has no ratified span box at all -- so this
    # set shrinking to a single id is the headline, and it is asserted rather than narrated.
    ck("the only unmeasurable box is p657:n0, which has no ratified span box",
       {r["span_id"] for r in G.box_quality(True) if r["lines"] is None} == {"p657:n0"},
       sorted({r["span_id"] for r in G.box_quality(True) if r["lines"] is None}))
    ck(f"the one-band debt is {len(_MEASURED) - 1} of {len(_MEASURED)} after the band rule was "
       f"corrected", (one, tot) == (len(_MEASURED) - 1, len(_MEASURED)), (one, tot))
    ck("the one remaining loose box is p362:n1", viol == ["p362:n1"], viol)
    ck("the corrected rule does not reject Chris's re-ratified p423:n3 box",
       G.band_geometry(G.rerat_load()[0]["p423:n3"]["_crop"])[0] == "one-band",
       G.band_geometry(G.rerat_load()[0]["p423:n3"]["_crop"]))
    # Edge clearance is REPORTED and never judged: an accept gate that required it would have thrown
    # out that ratified box, whose crop is 35px around a 35px band and so touches both edges.
    ck("p423:n3's ratified crop does touch both edges, and passes anyway",
       G.band_geometry(G.rerat_load()[0]["p423:n3"]["_crop"])[1]["clear_top"] == 0)
    rows_by = {r["span_id"]: r for r in bind_rows()}
    _cc = contains_counts()
    print("      contains population: %s" % _cc)
    # 23 SINCE CHRIS'S RE-SIGN BATCH of 2026-09-27, 22 before it. The substring test runs against the
    # signature, so moving a signature moves this population: one p217:n2 arm returned היפלא יהוה -- the
    # ruled PE plus the next word of Gen 18:14 -- which scored WRONG against the mem and is `contains`
    # against the pe. The figures in contains_population()'s docstring belong to the pre-batch table and
    # say so; this check derives the total instead of holding a number that a ruling can falsify.
    _cfull = {x["span_id"]: x for x in D.build_set(include_sealed=True)}
    _cind = sum(1 for x in reads()
                if (_cfull.get(x["span_id"]) or {}).get("truth")
                and D.classify(x.get("gated") or "", _cfull[x["span_id"]]["truth"]) == "contains")
    ck("every contains read is accounted for by exactly one shape",
       sum(_cc.values()) == _cind, (_cc, _cind))
    ck("the batch moved this population by one, and it is p217:n2 that joined",
       sum(_cc.values()) == 23 and "p217:n2" in {sid for sid, _g in contains_population()["extra-material"]},
       sum(_cc.values()))
    # 9 of them are not box faults in any sense: a glued letter, a trailing colon, a stray vav, a
    # duplication loop, and two broken parses. A substring test cannot tell those from page material.
    ck("9 contains reads are not a box fault at all",
       sum(v for k, v in _cc.items() if k != "extra-material") == 9, _cc)
    _em = collections.Counter(sid for sid, _g in contains_population()["extra-material"])
    ck("extra-material concentrates in p124:n4, the widest box in the set",
       _em.most_common(1)[0] == ("p124:n4", 10), _em.most_common())
    ck("and it is not p124:n4 alone -- p138:n5, p427:n4 and (since the batch) p217:n2 contribute too",
       set(_em) == {"p124:n4", "p138:n5", "p427:n4", "p217:n2"}, sorted(_em))
    # The one that matters: a broken parse gets CREDITED by `truth in read`. p293:n0 returned a JSON
    # envelope and p491:n1 returned 200 characters of deliberation with the word quoted inside it.
    ck("a broken parse is credited by the substring test", len(contains_population()["envelope-leak"]) == 2,
       contains_population()["envelope-leak"])
    # THE TWO AXES ARE DIFFERENT DIMENSIONS, and the old version of this check missed it because it
    # leaned on p912:n2 being multi-line -- which was the ink-run artifact, not a fact. Corrected, the
    # dissociation runs both ways and is real:
    #   p912:n2 holds ONE clean band and is still read short by 14 arms. Its box is too NARROW: 224px
    #           of a two-word signature, and the arms return the second word. band_geometry is a
    #           VERTICAL measurement and is structurally silent about that.
    #   p362:n1 fails the band rule (one 67px band, two lines merged) and is read WHOLE by 7 arms.
    # So the horizontal axis has only READ evidence behind it. A geometric horizontal test was tried --
    # count ink groups in the band and compare to the signature's word count -- and discarded: sweeping
    # the whitespace gap from 4 to 20px moves the per-span counts by up to 10. Saying "the vertical axis
    # is measured and the horizontal axis is inferred from reads" is the honest description of what this
    # harness can currently see.
    ck("a clean band does not mean a whole read: p912:n2 is one-band and still read short",
       by["p912:n2"]["one_band"] and rows_by["p912:n2"]["verdict"] == "broken:box-too-small",
       (by["p912:n2"]["one_band"], rows_by["p912:n2"]["verdict"]))
    ck("and a flagged band does not mean a broken read: p362:n1 fails the rule and reads whole",
       (not by["p362:n1"]["one_band"]) and rows_by["p362:n1"]["verdict"] == "unconfirmable",
       (by["p362:n1"]["one_band"], rows_by["p362:n1"]["verdict"]))

    # THE QUEUE IS EMPTY AS OF 2026-09-27 -- which is the queue WORKING, not the queue idle. p895:n0 was
    # its only member: the queue named a signature under suspicion, Chris read the 4x glyph card, ruled
    # the glyph a tsadi, and the signature moved to what the readers had been returning all along. The
    # span left by ADJUDICATION. A queue that still listed it would be re-proposing what is now signed.
    ck("the candidate queue is empty", cands == [], [c["span_id"] for c in cands])
    ck("p895:n0 left it because the signature moved, not because the queue changed its mind",
       by["p895:n0"]["truth"] == "ותקצר נפש"
       and rows_by["p895:n0"]["verdict"] == "unconfirmable", (by["p895:n0"]["truth"],
                                                             rows_by["p895:n0"]["verdict"]))
    # THE FLIP IS NOT A CONFIRMATION. 22 of 37 arms returned the ruled string exactly, and `unconfirmable`
    # is precisely the verdict that refuses to read that as 22 confirmations: the arms share a context
    # strip, so their agreement measures the shared channel. Item 6's 2x2 is what turns these into
    # evidence or into back-translation. This check exists so nobody reads the flip as vindication.
    ck("22 exact reads under a shared context strip are UNCONFIRMABLE, not confirmed",
       rows_by["p895:n0"]["classes"].get("exact") == 22
       and rows_by["p895:n0"]["verdict"] == "unconfirmable", rows_by["p895:n0"]["classes"])
    ck("no candidate ever proposes what is already signed",
       all(c["modal"] != D._norm(by[c["span_id"]]["truth"]) for c in cands), cands[:1])
    # An empty queue must not pass for want of a mechanism. The detector still fires on the signature
    # p895:n0 carried before the ruling -- derived by putting the ayin back, not retyped.
    _frm, _to, _why = D.GLYPH_RESIGN["p895:n0"]
    _pre = by["p895:n0"]["truth"].replace(_to, _frm)
    ck("the detector is not vacuous: it still fires on the pre-batch signature",
       _one_letter_apart(_pre, "ותקצר נפש") and _pre != by["p895:n0"]["truth"], _pre)
    ck("the candidate queue is not a verdict field",
       all("verdict" not in c and "correction" not in c for c in cands), cands[:1])

    ck("_one_letter_apart needs equal length and exactly one difference",
       _one_letter_apart("אבג", "אבד") and not _one_letter_apart("אבג", "אבגד")
       and not _one_letter_apart("אבג", "אדה"))

    print("")
    print("%s: %d/%d checks" % ("PASS" if not f else "FAIL", n - f, n))
    return f


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "table"
    if cmd == "selftest":
        sys.exit(1 if selftest() else 0)
    if cmd == "cands":
        for c in candidates():
            print("%-9s signed=%-14r modal=%-14r %2d/%-2d %4.0f%%  one-letter=%s"
                  % (c["span_id"], c["signed"], c["modal"], c["n_modal"], c["n_reads"],
                     100 * c["share"], c["one_letter"]))
        raise SystemExit(0)
    rows, counts, broken, cands = report()
    print("%-10s %-5s %-6s %-6s %-5s %-5s %s"
          % ("span", "words", "lines", "1band", "clip", "full", "verdict"))
    for r in rows:
        print("%-10s %-5d %-6s %-6s %-5d %-5d %s"
              % (r["span_id"], r["words"], r["lines"], "yes" if r["one_band"] else "no",
                 r["n_clipped"], r["n_full"], r["verdict"]))
    print("")
    print("verdicts: %s" % counts)
    print("broken:   %s" % ", ".join(broken))
    print("candidates for adjudication: %s" % ", ".join(c["span_id"] for c in cands))
    print("")
    print("wrote %s" % (D.DATA / "bind_report.md"))
