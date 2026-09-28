# -*- coding: utf-8 -*-
"""The contact sheet: every crop that would be sent, at native size, beside its signed text.

    python hebrew_contact_sheet.py                       # the re-run scope, from the crop hashes
    python hebrew_contact_sheet.py --span p423:n3         # an explicit scope
    python hebrew_contact_sheet.py --out path.html

All page numbers are FILE pages (printed = file - 88).

WHY THIS EXISTS. Chris's rule, after a run in which 30 arms were charged for reading two pure-white
rectangles: "before any outbound call, produce a contact sheet: every crop to be sent, native size,
beside its signed text, before/after where changed; Chris approves it, then spend." The failure it
guards is not a bug in any component -- every component behaved -- it is that nobody LOOKED at the
pixels before paying for opinions about them.

WHAT IT SHOWS, AND WHAT THAT COSTS. A2 span-box crops only, which is the same aperture the frontier arm
can reach and the only one Chris authorised for outbound. A1 note-box crops are not shown, not because
this file leaves the machine (it does not) but because keeping ONE invariant everywhere -- "A2 is the
only aperture this lane renders or sends" -- is worth more than the extra context on a page where five
of the six A1 boxes currently refuse to cut at all.

The crops are embedded as data URIs so the sheet is one portable file, and each is shown at native
size AND at 4x with `image-rendering: pixelated`, because the thing being judged is a compositor's
letterform and a smoothed upscale invents strokes that are not on the page.

WHAT IT DOES NOT DO. It does not approve anything, it does not send anything, and it cannot tell you
whether a box is right -- only a human reading the pixels can do that. It also cannot show a crop that
was never produced: a refused aperture has no file, and the sheet says so in words rather than
rendering an empty frame that looks like a blank page.
"""
import base64
import html
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hebrew_aperture_diag as diag                                          # noqa: E402
import hebrew_frontier_or as F                                              # noqa: E402

APERTURE = "A2_spanbox"
OUT = diag.CROPDIR.parent / "contact_sheet_20260927.html"
PRINTED_OFFSET = 88


def _b64(p):
    p = Path(p)
    if not p.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def _man(d):
    f = Path(d) / "manifest.json"
    if not f.exists():
        return {}
    return {m["span_id"]: m for m in json.load(io.open(f, encoding="utf-8"))}


def a1_moved():
    """Sendable spans whose NOTE-BOX crop was re-cut while the span-box crop they are sent as is
    byte-identical.

    Chris's conditional term. It is measured and reported; it does not send. Two reasons, and the
    second is the load-bearing one:

      * the condition on it (Lane A's x-origin fix) landed on 2026-09-27 as a band clip plus a 2px
        canvas-slop clamp, and it did NOT move the page origin: `diag.a1_x_shifts()` still shows dx=0
        on every paired A1 rect, and the four spans this term used to hold came back byte-identical
        to the 2026-09-20 as-sent crops, which is why the term is now empty rather than live;
      * A1 is not a sendable aperture. No note-box crop leaves the network and `F.cells()` cannot
        reach one. A span in this set was sent precisely the pixels it still holds, so its reads are
        evidence about the crop we have. Nothing is void and nothing needs re-taking.

    If Lane A's fix does move page geometry, it will move the A2 crops too, and the hash-keyed scope
    picks those up on its own -- this term is a net under that, not the mechanism."""
    sendable = {s["span_id"] for s, _c, _x in F.cells()}
    a2_same = set(diag.crops_changed(APERTURE))
    return sorted(sid for sid in diag.crops_recut("A1_notebox")
                  if sid in sendable and sid not in a2_same)


def scope(include_a1=False):
    """The re-run scope, DERIVED: spans whose crop hash moved, plus the spans with no reads at all.

    Never a typed list. The whole point of hashing the crops is that the scope stops being something a
    human can get wrong.

    `voided` is drawn from the re-cut half only. A span whose crop the geometry no longer produces
    loses its reads the same way and cannot be sent at all; it leaves the population and shows up as a
    debt, never as work. `include_a1` folds in Chris's conditional term -- off by default, because its
    condition has not been met and because an A1-only change cannot have changed a sent pixel."""
    sendable = {s["span_id"] for s, _c, _x in F.cells()}
    scored = {o["span_id"] for o in F.rows()}
    # A span that lost its reads and GOT THEM BACK is not re-run scope. `stale_spans()` is "has a mute
    # read and no live one"; the old `sid in stale_reads()` test would have listed p423:n3 and p726:n3
    # as unsent work on 09-28, the day after they were sent, because their retired reads never leave
    # the artifact. The three terms are also disjoint now, so the decomposition is a partition and not
    # an arithmetic coincidence.
    voided = (sendable & set(F.stale_spans())) - scored
    never = sendable - scored - voided
    a1 = set(a1_moved()) if include_a1 else set()
    return sorted(voided | never | a1), sorted(voided), sorted(never), sorted(a1)


def _img(uri, w, h, label, note=""):
    if not uri:
        return (f'<div class="miss"><b>no crop</b><br>{html.escape(label)}<br>'
                f'<span class="sub">{html.escape(note or "this aperture was REFUSED; no file exists")}'
                f'</span></div>')
    return (f'<figure><img src="{uri}" width="{w}" height="{h}">'
            f'<img class="zoom" src="{uri}" width="{w * 4}" height="{h * 4}">'
            f'<figcaption>{html.escape(label)}</figcaption></figure>')


def build(spans=None, out=OUT, include_a1=False):
    want, voided, never, a1 = scope(include_a1)
    if spans:
        want = list(spans)
    cells = {s["span_id"]: (s, c, x) for s, c, x in F.cells(want)}
    live, sent = _man(diag.CROPDIR), _man(diag.AS_SENT)
    sfaults = diag.sent_faults(APERTURE) or {}
    changed = diag.crops_changed(APERTURE)
    cat = diag.CROPDIR  # noqa: F841  (kept for path display below)

    try:
        prices = F.catalog(refresh=False)["models"]
    except Exception:
        prices = {}
    arms_ok = [m for m in F.ARMS if prices.get(m, {}).get("status") == "ok"]

    P = []
    P.append("""<!doctype html><meta charset="utf-8"><title>Contact sheet</title>
<style>
 :root{--ink:#16130f;--bg:#faf7f2;--rule:#ddd5c8;--warn:#8a2f1d;--ok:#2c5c3a}
 @media (prefers-color-scheme:dark){:root{--ink:#eae4da;--bg:#16140f;--rule:#3a352c}}
 body{background:var(--bg);color:var(--ink);font:15px/1.5 Georgia,serif;margin:0;padding:24px 16px;
      max-width:1100px;margin:0 auto}
 h1{font-size:26px;margin:0 0 4px} h2{font-size:19px;margin:34px 0 6px;border-bottom:1px solid var(--rule);
      padding-bottom:4px}
 .sub{color:#8a8274;font-size:13px}
 .span{border:1px solid var(--rule);border-radius:6px;padding:14px 16px;margin:18px 0;background:#fff2}
 .heb{font-size:40px;line-height:1.35;direction:rtl;font-family:"Times New Roman",serif;margin:6px 0}
 .row{display:flex;gap:26px;flex-wrap:wrap;align-items:flex-start}
 figure{margin:0 0 10px} img{background:#fff;border:1px solid var(--rule);display:block}
 img.zoom{margin-top:6px;image-rendering:pixelated}
 figcaption{font-size:12px;color:#8a8274;margin-top:4px}
 .miss{border:1px dashed var(--warn);color:var(--warn);padding:14px;border-radius:4px;font-size:13px}
 table{border-collapse:collapse;font-size:13px;margin-top:8px}
 td,th{border:1px solid var(--rule);padding:3px 8px;text-align:left;vertical-align:top}
 code{font:12px/1.4 Consolas,monospace}
 .warn{color:var(--warn);font-weight:bold} .ok{color:var(--ok)}
 .note{background:#f0e8d8aa;border-left:3px solid var(--rule);padding:10px 14px;margin:14px 0;
       font-size:14px}
 @media (max-width:760px){.row{gap:14px}.heb{font-size:30px}}
</style>""")
    P.append(f"<h1>Contact sheet — the crops that would be sent</h1>")
    P.append('<p class="sub">All page numbers are FILE pages. Printed page = file page '
             f'&minus; {PRINTED_OFFSET}. Aperture A2 (ratified span box) only; no note-box crop is '
             'rendered here or reachable from the sending code. Nothing has been sent.</p>')
    P.append('<div class="note"><b>Read the Latin, not the flag.</b> The back-translation flag on '
             'each span tests whether the signed Hebrew appears <i>verbatim</i> in the note. '
             '<code>p138:n6</code> is the sharpest case in the corpus and the flag says no: its gloss '
             'is <i>nidos</i>, its signed truth is \u05e7\u05e0\u05d9\u05dd, and <i>nidos</i> is '
             '"nests". A correct read there may be a translation, not a reading. '
             '<code>p596:n2</code> leans the other way &mdash; its note glosses no Hebrew at all and '
             'names a different word (\u05d4\u05d9\u05d4) than the page carries.</div>')
    P.append('<div class="note"><b>The text beside each crop is the signed truth as it stands NOW.</b> '
             "Chris's batch of 2026-09-27 is applied: <code>p217:n2</code> mem&rarr;pe, "
             "<code>p423:n3</code> bet&rarr;gimel, <code>p895:n0</code> ayin&rarr;tsadi, and "
             "<code>p726:n3</code> depointed on his verdict from the 4&times; crop. "
             "<code>p912:n2</code>'s text is unchanged &mdash; what is outstanding there is the box. "
             'Every one of those strings was <i>derived</i> from the string the sitting recorded by the '
             "rule the verdict names; not one was retyped. The run header records this table's digest "
             f"(<code>{F.truth_digest()}</code>) so a score is answerable for its standard as well as "
             "for its pixels.</div>")
    P.append('<div class="note"><b>What approving this means.</b> That each crop below shows the '
             'Hebrew span its signed text names, and nothing else — not a neighbouring line, not '
             'margin, not half a word. It does not mean the signed text is right; that is a separate '
             'judgement on the glyph cards. Crops shown at native size, then 4&times; unsmoothed.</div>')

    P.append(f"<h2>Scope: {len(cells)} span(s), {len(arms_ok)} arms, "
             f"{len(cells) * len(arms_ok)} outbound calls</h2>")
    P.append("<table><tr><th>span</th><th>printed</th><th>why in scope</th><th>native size</th>"
             "<th>crop sha16</th><th>changed since sent</th></tr>")
    for sid in want:
        s, cpath, _x = cells[sid]
        m = live.get(sid, {}).get(APERTURE) or {}
        why = ("crop re-cut &rarr; its reads are void" if sid in voided else
               "newly signed &rarr; no reads at all" if sid in never else
               "A1 note-box re-cut (Chris's conditional term, folded in)" if sid in a1 else
               "named explicitly")
        ch = changed.get(sid)
        P.append(f"<tr><td><code>{sid}</code></td><td>{s['page'] - PRINTED_OFFSET}</td><td>{why}</td>"
                 f"<td>{m.get('size')}</td><td><code>{F.crop_sha(cpath)}</code></td>"
                 f"<td>{'<span class=warn>yes</span>' if ch else 'no'}</td></tr>")
    P.append("</table>")

    for sid in want:
        s, cpath, ctx = cells[sid]
        m = live.get(sid, {}).get(APERTURE) or {}
        om = sent.get(sid, {}).get(APERTURE) or {}
        w, h = (m.get("size") or [0, 0])
        P.append(f'<div class="span"><h3><code>{sid}</code> &nbsp; file page {s["page"]} '
                 f'(printed {s["page"] - PRINTED_OFFSET}), note {s["note_idx"]}</h3>')
        P.append('<div class="row"><div>')
        P.append(_img(_b64(cpath), w, h, f"NOW — {w}×{h} px, sha {F.crop_sha(cpath)}"))
        if sid in changed:
            ow, oh = (om.get("size") or [0, 0])
            fault = sfaults.get(sid)
            P.append(_img(_b64(diag.AS_SENT / Path(cpath).name), ow, oh,
                          f"AS SENT — {ow}×{oh} px" + (f", fault: {fault}" if fault else "")))
        P.append('</div><div>')
        P.append('<div class="sub">signed truth</div>')
        P.append(f'<div class="heb">{html.escape(s["truth"] or "")}</div>')
        P.append(f'<div class="sub">basis: {html.escape(str(s["truth_basis"]))}'
                 f'{" &nbsp;|&nbsp; SEALED page (read-only carve-out)" if s["sealed"] else ""}</div>')
        P.append("<table>")
        P.append(f"<tr><th>span box (strip)</th><td><code>{s['span_box']}</code></td></tr>")
        P.append(f"<tr><th>native rects</th><td><code>{m.get('native_rects')}</code></td></tr>")
        # Chris's p423 ruling turns on exactly this: "the box stands as ratified if the re-cut crop
        # shows the span on one line". One band = one line of type. Derived, so the judgement does not
        # depend on reading four numbers out of a list.
        _cut = [e for e in (m.get("rect_edges") or []) if e]
        if _cut:
            P.append("<tr><th>CUT</th><td><b>this crop was clipped</b> &mdash; "
                     f"<code>{_cut}</code>, {m.get('band_overshoot_px')}px past the band. "
                     "Part of the ratified box is NOT in these pixels; what you are approving is what "
                     "is left.</td></tr>")
        _nb = len(m.get("native_rects") or [])
        P.append(f"<tr><th>bands in this crop</th><td><b>{_nb}</b> "
                 + ("&mdash; the span is on ONE line, so a ratified box needs no redraw"
                    if _nb == 1 else "&mdash; the span straddles lines; a box judgement has to account "
                    "for every band") + "</td></tr>")
        P.append(f"<tr><th>note box status</th><td>{html.escape(str(s['note_box_status']))}"
                 f" &nbsp; overlap {s['a1_span_overlap']}</td></tr>")
        if sid in changed:
            a, b = changed[sid]
            P.append(f"<tr><th>crop sha</th><td>as sent <code>{a}</code> &rarr; now "
                     f"<code>{b}</code></td></tr>")
            if om.get("native_rects") and m.get("native_rects"):
                # native_rects is a list of [x0,y0,x1,y1], one per column the box straddles.
                d = [(n[0] - o[0], n[1] - o[1])
                     for o, n in zip(om["native_rects"], m["native_rects"])]
                P.append(f"<tr><th>delta (dx, dy)</th><td><b>{d}</b></td></tr>")
        bt = F._backtranslatable(s["latin_context"], s["truth"])
        P.append(f"<tr><th>gloss repeats the truth verbatim</th><td>{'<b>yes</b>' if bt else 'no'}"
                 ' &nbsp;<span class="sub">lower bound only &mdash; a gloss that TRANSLATES rather '
                 "than repeats (nidos for nests) reads 'no' here and still hands the answer over. "
                 "Judge the Latin below, not this flag.</span></td></tr>")
        P.append(f"<tr><th>text sent with it</th><td><code>{html.escape(ctx)}</code></td></tr>")
        P.append(f"<tr><th>local Latin (NOT sent)</th><td class=sub>"
                 f"{html.escape((s['latin_context'] or '')[:400])}</td></tr>")
        P.append("</table></div></div></div>")

    keep = sorted({s["span_id"] for s, _c, _x in F.cells()} - set(want))
    P.append(f"<h2>Not in scope: {len(keep)} span(s), zero calls</h2>")
    P.append('<p class="sub">Byte-identical crops. Their existing reads stand and are re-scored '
             'against the corrected truth table without a single new request. Listed so the scope '
             'is auditable in both directions — what is being sent, and what is being spared.</p>')
    P.append("<table><tr><th>span</th><th>printed</th><th>crop sha16</th><th>reads on record</th></tr>")
    nr = {}
    for o in F.rows():
        nr[o["span_id"]] = nr.get(o["span_id"], 0) + 1
    for sid in keep:
        P.append(f"<tr><td><code>{sid}</code></td>"
                 f"<td>{int(sid.split(':')[0][1:]) - PRINTED_OFFSET}</td>"
                 f"<td><code>{diag.crop_sha(sid, APERTURE)}</code></td>"
                 f"<td>{nr.get(sid, 0)}</td></tr>")
    P.append("</table>")

    # Chris's conditional term, shown whether or not it is folded in, so the decision is visible
    # rather than inferred from a flag nobody typed.
    pending = a1_moved()
    if pending:
        shifts = diag.a1_x_shifts()
        live_x = sorted(sid for sid, v in shifts.items() if v and any(dx for dx, _dw in v))
        P.append("<h2>Chris's A1 term: %d span(s), <b>not being sent</b></h2>" % len(pending))
        P.append('<p class="sub">The instruction was &ldquo;plus, <b>if Lane A&rsquo;s x-origin fix '
                 'lands before you send</b>, any span whose A1 crop hash changes&rdquo;. These spans '
                 'had their <b>note-box</b> crop re-cut while the <b>span-box</b> crop they are '
                 'actually sent as stayed byte-identical. They are excluded on two independent '
                 'grounds, either of which would be enough:</p>')
        P.append("<ul>")
        P.append('<li><b>The condition has not been met.</b> No A1 rect moved in x &mdash; every one '
                 'that moved grew in width at <code>dx=0</code> (a right-edge clamp releasing) or '
                 'shifted <code>dy=&minus;5</code>. Spans with a non-zero dx today: '
                 + ("<b class=warn>" + ", ".join(live_x) + "</b> &mdash; THE CONDITION HAS FIRED, "
                    "fold this term in" if live_x else "<b class=ok>none</b>") + ".</li>")
        P.append('<li><b>It could not have changed a sent pixel.</b> A1 is the note-box aperture; no '
                 'note-box crop leaves the network and the sending code cannot reach one. Each span '
                 'below was sent exactly the bytes it still holds, so its reads are evidence about '
                 'the crop on disk and nothing is void.</li>')
        P.append("</ul>")
        P.append("<table><tr><th>span</th><th>printed</th><th>A1 sha: sent &rarr; now</th>"
                 "<th>A1 (dx, dw) per rect</th><th>A2 sha (unchanged)</th><th>reads standing</th>"
                 "</tr>")
        rc = diag.crops_recut("A1_notebox")
        nread = {}
        for o in F.rows():
            nread[o["span_id"]] = nread.get(o["span_id"], 0) + 1
        for sid in pending:
            a, b = rc[sid]
            P.append(f"<tr><td><code>{sid}</code></td>"
                     f"<td>{int(sid.split(':')[0][1:]) - PRINTED_OFFSET}</td>"
                     f"<td><code>{a} &rarr; {b}</code></td>"
                     f"<td><code>{shifts.get(sid)}</code></td>"
                     f"<td><code>{diag.crop_sha(sid, APERTURE)}</code></td>"
                     f"<td>{nread.get(sid, 0)}</td></tr>")
        P.append("</table>")
        P.append('<p class="sub">Folding them in would cost %d span(s) &times; %d arms = '
                 '<b>%d further calls</b>. Run with <code>--include-a1</code> to do that; it is not '
                 'the default and this sheet was built without it.</p>'
                 % (len(pending), len(arms_ok), len(pending) * len(arms_ok)))

    mute = F.stale_reads()
    debt = sorted({sid for sid, _m, _h in mute} - {s["span_id"] for s, _c, _x in F.cells()})
    if debt:
        P.append("<h2>Void reads with no route back</h2>")
        P.append('<p class="sub">These spans lost their reads to the re-cut AND cannot be re-sent, '
                 'because their crop is refused. Not a queued task — a debt, payable only by '
                 'redrawing the box.</p><table><tr><th>span</th><th>reads void</th><th>why unsendable'
                 "</th></tr>")
        pop = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}
        for sid in debt:
            n = sum(1 for k in mute if k[0] == sid)
            P.append(f"<tr><td><code>{sid}</code></td><td>{n}</td>"
                     f"<td class=warn>{html.escape(str(pop[sid]['unscorable']))}</td></tr>")
        P.append("</table>")

    P.append("<h2>Arms this scope would reach</h2>")
    P.append(f'<p class="sub">{len(arms_ok)} of {len(F.ARMS)} arms resolve in the catalog. '
             f'{len(cells)} span(s) &times; {len(arms_ok)} arms = '
             f'<b>{len(cells) * len(arms_ok)} calls</b>, one image each.</p>')
    P.append("<p><code>" + html.escape(" ".join(arms_ok)) + "</code></p>")
    P.append('<div class="note">No request has been made. The sending code refuses a faulted crop '
             'before the wire, refuses any body containing a Hebrew character, and records the sha256 '
             'of every crop it sends in the run header — so this sheet and the run are checkable '
             'against each other afterwards.</div>')

    Path(out).write_text("\n".join(P), encoding="utf-8")
    # The sidecar is what `run` checks against: the exact crop each span was shown as. The HTML is for
    # the human; this is for the gate. Keyed by sha, so a crop re-cut after approval fails closed.
    side = Path(out).with_suffix(".json")
    side.write_text(json.dumps({
        "sheet": Path(out).name,
        "built": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        "aperture": APERTURE,
        "pages": "FILE pages (printed = file - 88)",
        "crop_sha16": {sid: F.crop_sha(cells[sid][1]) for sid in want},
        # The standard at build time. NOT a gate: Chris approves the pixels, and a truth change
        # does not move a pixel. `run` compares this with the digest at send and records both, which
        # is the honest shape -- a refusal would misdescribe what the approval was about.
        "truth_digest": F.truth_digest(),
        # What was cut off these crops before the pixels were taken. The crop hash cannot say it -- a
        # clipped crop is a valid PNG -- so the sheet says it, and `run`'s clip gate holds the answer
        # to what is on this page. {} is an answer; a missing key is silence.
        "clipped": F.clip_status(list(cells.values())),
        "arms_resolved": arms_ok,
        "calls_if_approved": len(want) * len(arms_ok),
        # Recorded so the run header says which way the conditional term was decided, and on what.
        "a1_term_spans": a1_moved(),
        "a1_term_folded_in": bool(include_a1),
        "a1_x_shift_nonzero": sorted(sid for sid, v in diag.a1_x_shifts().items()
                                     if v and any(dx for dx, _dw in v)),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return out, want, len(arms_ok)


if __name__ == "__main__":
    a = sys.argv[1:]
    sv = [x for i, t in enumerate(a) if t == "--span" for x in a[i + 1].split(",") if x] or None
    ov = a[a.index("--out") + 1] if "--out" in a else OUT
    p, want, n = build(sv, ov, include_a1="--include-a1" in a)
    print("scope (%d span%s): %s" % (len(want), "" if len(want) == 1 else "s", " ".join(want)))
    print("arms: %d   outbound calls if approved: %d" % (n, n * len(want)))
    print("wrote", p)
    print("wrote", Path(p).with_suffix(".json"), "  <- `run` checks against this")
    _a1 = a1_moved()
    if _a1:
        print("Chris's A1 term: %d span(s) %s -- %s"
              % (len(_a1), " ".join(_a1),
                 "FOLDED IN" if "--include-a1" in a else "not sent (condition unmet; A1 is not a "
                 "sendable aperture)"))
