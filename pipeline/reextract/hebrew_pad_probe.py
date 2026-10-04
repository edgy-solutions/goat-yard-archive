# -*- coding: utf-8 -*-
"""Item 6(b): the PAD probe on p912:n2 -- does the margin's foreign ink change the read?

    python hebrew_pad_probe.py sheet          # build the approval sheet. Sends nothing.

All page numbers are FILE pages (printed = file - 88). p912 is printed page 824.

WHAT THE PROBE ASKS. The A2 crop is the ratified span box plus a uniform 12px pad. On p912:n2 that
pad, and the box's own top two rows, carry the bottom of the LINE ABOVE at up to 241 dark pixels of
385 -- as much ink as the span's own line. Three arms read the span's two words in the wrong order and
one put a newline between them, which is what an arm would do if it were mapping two words onto the
two ink rows it can see. The probe removes the foreign rows and nothing else.

WHAT IT DOES NOT DO. It does not redraw a box. The band-clip only drops whole rows from the top and
bottom of an existing crop, and the outbound gate enforces exactly that: a clip is sendable only if it
IS a full-width row range of a sendable A2 crop, checked against the pixels
(hebrew_aperture_diag.bandclip_fault; twelve born tests in section 19 of the suite). A sidecar naming a
different parent fails the byte comparison; a clip of a clip is refused; one altered pixel is refused.

BOTH conditions go out in the SAME run. The recorded baseline is 15/26 exact from 2026-09-20, and
comparing a fresh clipped run against it would carry a cross-run confound. Item 6(a) measured that null
and found it small, but $0.036 buys the paired comparison outright, so the base crop is sent again
beside the clip.
"""
import base64
import html
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hebrew_aperture_diag as diag                                          # noqa: E402
import hebrew_frontier_or as F                                              # noqa: E402
from hebrew_contact_sheet import refuse_to_clobber                          # noqa: E402

SPAN = "p912:n2"
PRINTED_OFFSET = 88
PROBE = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/hebrew_pad_probe_20261004")
CLIP = PROBE / "p912_n2_A2_bandclip.png"

# The row facts, measured off the base crop (dark = L < 160, width 385). These are what the cut is
# derived from; they are in the sheet because a cut nobody can check is a cut nobody approved.
PROFILE = [
    ("0-13", "169-241", "x 25..384",
     "the BOTTOM OF THE LINE ABOVE. Rows 12-13 of it are inside the ratified box, not only in the pad.",
     "removed"),
    ("14-26", "12-28", "x 26..269",
     "the interline gap. Row 14 is the quietest row in the crop (12 dark px).",
     "row 14 kept as the new top margin"),
    ("27-65", "16-269", "x 0..384", "the span's own line of type.", "kept, untouched"),
    ("66-73", "15-28", "x 104..268",
     "the qof descender and the nikud of the span's own line -- looked at under 5x, this ink attaches "
     "to the line above it.", "kept, untouched"),
    ("74-80", "16-42", "x 0..384", "the line BELOW returns at full width.", "removed"),
]


def _b64(p):
    return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()


def _size(p):
    from PIL import Image
    return Image.open(p).size


def derived_out(crops):
    """The name is a function of the pixels, so a later build cannot land on this record.

    A fixed filename is how item 6's 19-span approval was destroyed by a 1-span rebuild on
    2026-10-04."""
    sig = ";".join("%s:%s" % (k, F.crop_sha(v)) for k, v in sorted(crops.items()))
    return PROBE.parent / ("contact_sheet_%s_padprobe_%s.html"
                           % (time.strftime("%Y%m%d"), F.diag_sha(sig)[:8]))


def build(out=None):
    base, span = None, None
    for s, c, _x in F.cells([SPAN]):
        span, base = s, Path(c)
    if base is None:
        raise RuntimeError("%s is not in the sendable population" % SPAN)
    if not CLIP.exists():
        raise RuntimeError("the band-clip has not been built: %s" % CLIP)

    crops = {"base": base, "clip": CLIP}
    for k, p in crops.items():
        fault = diag.gate_outbound(p, offnet=True)[1]
        if fault:
            raise RuntimeError("the %s crop would be REFUSED at the gate (%s) -- there is nothing to "
                               "approve until that is fixed" % (k, fault))
    out = Path(out) if out else derived_out(crops)
    sha = {k: F.crop_sha(v) for k, v in crops.items()}
    refuse_to_clobber(out, sha)

    try:
        prices = F.catalog(refresh=False)["models"]
    except Exception:
        prices = {}
    arms = [m for m in F.ARMS if prices.get(m, {}).get("status") == "ok"
            and m not in getattr(F, "EXCLUDED_ARMS", {})]
    truth = (span.get("truth") or "").strip()
    basis = span.get("truth_basis") or "(none recorded)"
    bw, bh = _size(base)
    cw, ch = _size(CLIP)

    P = []
    P.append("""<!doctype html><meta charset="utf-8"><title>Pad probe contact sheet</title>
<style>
 :root{--ink:#16130f;--bg:#faf7f2;--rule:#ddd5c8;--warn:#8a2f1d;--ok:#2c5c3a}
 @media (prefers-color-scheme:dark){:root{--ink:#eae4da;--bg:#16140f;--rule:#3a352c}}
 body{background:var(--bg);color:var(--ink);font:15px/1.5 Georgia,serif;padding:24px 16px;
      max-width:1100px;margin:0 auto}
 h1{font-size:26px;margin:0 0 4px} h2{font-size:19px;margin:32px 0 6px;
      border-bottom:1px solid var(--rule);padding-bottom:4px}
 .sub{color:#8a8274;font-size:13px}
 .heb{font-size:40px;line-height:1.35;direction:rtl;font-family:"Times New Roman",serif;margin:6px 0}
 figure{margin:0 0 16px} img{background:#fff;border:1px solid var(--rule);display:block}
 img.zoom{margin-top:6px;image-rendering:pixelated}
 figcaption{font-size:12px;color:#8a8274;margin-top:4px}
 table{border-collapse:collapse;font-size:13px;margin-top:8px}
 td,th{border:1px solid var(--rule);padding:3px 8px;text-align:left;vertical-align:top}
 code{font:12px/1.4 Consolas,monospace}
 .warn{color:var(--warn);font-weight:bold} .ok{color:var(--ok)}
 .note{background:#f0e8d8aa;border-left:3px solid var(--rule);padding:10px 14px;margin:14px 0;
       font-size:14px}
</style>""")
    P.append("<h1>Contact sheet &mdash; item 6(b), the pad probe</h1>")
    P.append('<p class="sub">All page numbers are FILE pages. Printed page = file page &minus; %d, so '
             '<code>%s</code> is printed page %d. Aperture A2 only. <b>Nothing has been sent.</b></p>'
             % (PRINTED_OFFSET, SPAN, int(SPAN.split(":")[0][1:]) - PRINTED_OFFSET))
    P.append('<div class="note"><b>What approving this means.</b> That both crops below show the '
             'Hebrew span its signed text names, and nothing else &mdash; and in particular that the '
             'clipped one still shows <i>every letter whole</i>. It does not mean the signed text is '
             'right; that is a separate judgement on the glyph cards. Crops at native size, then '
             '4&times; unsmoothed.</div>')
    P.append("<h2>The signed text</h2>")
    P.append('<div class="heb">%s</div>' % html.escape(truth))
    P.append('<p class="sub">basis <code>%s</code> &middot; truth table digest <code>%s</code></p>'
             % (html.escape(str(basis)), F.truth_digest()))

    P.append("<h2>Before &mdash; the A2 crop as it has always been sent (%d&times;%d)</h2>" % (bw, bh))
    u = _b64(base)
    P.append('<figure><img src="%s" width="%d" height="%d">'
             '<img class="zoom" src="%s" width="%d" height="%d">'
             "<figcaption>%s &middot; sha <code>%s</code></figcaption></figure>"
             % (u, bw, bh, u, bw * 4, bh * 4, html.escape(base.name), sha["base"]))
    P.append("<p>The band across the top is not this span. It is the bottom of the line above, and it "
             "carries as much ink as the span&rsquo;s own line.</p>")

    P.append("<h2>After &mdash; the band-clip, rows 14..72 of 81 (%d&times;%d)</h2>" % (cw, ch))
    u = _b64(CLIP)
    P.append('<figure><img src="%s" width="%d" height="%d">'
             '<img class="zoom" src="%s" width="%d" height="%d">'
             "<figcaption>%s &middot; sha <code>%s</code></figcaption></figure>"
             % (u, cw, ch, u, cw * 4, ch * 4, html.escape(CLIP.name), sha["clip"]))

    P.append("<h2>Where the cut falls, and why</h2>")
    P.append("<table><tr><th>rows</th><th>dark px/row</th><th>extent</th><th>what it is</th>"
             "<th>the cut</th></tr>")
    for r in PROFILE:
        P.append("<tr><td><code>%s</code></td><td>%s</td><td><code>%s</code></td><td>%s</td>"
                 "<td>%s</td></tr>" % tuple(html.escape(str(x)) for x in r))
    P.append("</table>")
    P.append('<div class="note"><b>P9, checked on the pixels rather than inferred from the score.</b> '
             "The prediction said that if exact drops, the first hypothesis is not &ldquo;the margin "
             "was doing work&rdquo; but &ldquo;the clip cut the letters&rdquo; &mdash; lamed ascends, "
             "qof descends &mdash; and that this is testable here, before spending. It was: the lamed "
             "is whole at the top of the clip, and the qof descender and the nikud below the line are "
             "inside it, because the bottom cut is at row 72 and that ink stops at row 73. "
             "<b>Nothing in the span was cut.</b></div>")
    P.append('<div class="note"><b>A thing the probe found before it ran.</b> The foreign band reaches '
             "<i>inside</i> the ratified box by two rows here, and the same measurement over all 19 "
             "spans puts foreign ink inside the box on <b>7 of 19</b> (1&ndash;4 rows each). "
             "Separately, this span&rsquo;s own qof descender runs <i>below</i> its box and survives "
             "only because the pad is 12px. The pad is doing two opposite jobs at once, so &ldquo;trim "
             "the pad to the band&rdquo; must never become &ldquo;trim the pad to the box&rdquo;.</div>")

    P.append("<h2>Scope: %d crops &times; %d arms = %d outbound calls</h2>"
             % (len(crops), len(arms), len(crops) * len(arms)))
    P.append("<p>Cost from the <i>measured</i> tokens of the 2026-09-27 frontier run, not an estimate: "
             "one call to each of the %d callable arms is <b>$0.036</b>, so this sheet is "
             "<b>$0.072</b>. Excluded arms are not counted, because they cannot be called.</p>"
             % len(arms))
    P.append("<table><tr><th>arm</th></tr>")
    for m in arms:
        P.append("<tr><td><code>%s</code></td></tr>" % html.escape(m))
    P.append("</table>")
    P.append('<p class="sub">Built %s. The run header will record both crop hashes; this sheet&rsquo;s '
             "sidecar records them now, and the file name is derived from them, so a later build over "
             "different pixels cannot land on this record.</p>" % time.strftime("%Y-%m-%dT%H:%M"))

    out.write_text("\n".join(P), encoding="utf-8")
    side = out.with_suffix(".json")
    side.write_text(json.dumps({
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "span": SPAN, "item": "6(b) pad probe",
        "crop_sha16": sha, "rows_kept": [14, 72], "parent_rows": 81,
        "arms": arms, "calls": len(crops) * len(arms), "cost_usd_measured": 0.0718,
        "truth": truth, "truth_basis": basis, "truth_digest": F.truth_digest(),
        "approved": None, "approved_by": None, "approved_at": None,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("sheet   %s" % out)
    print("sidecar %s" % side.name)
    print("scope   %d crops x %d arms = %d calls, $0.0718 measured"
          % (len(crops), len(arms), len(crops) * len(arms)))
    return out


OUT = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/"
           "hebrew_pad_probe_reads_20261004.jsonl")
SHEET_JSON = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/"
                  "contact_sheet_20261004_padprobe_a51226c7.json")
DEAD_RUN_AT = 6          # consecutive dead cells that invalidate the run rather than one item


def _gates(sheet_json):
    """Everything that must hold before a single call. Returns (span, ctx, {condition: path}, sheet rec).

    Order matters: every refusal here costs nothing and cannot be mistaken for a run that started."""
    rec = json.loads(Path(sheet_json).read_text(encoding="utf-8"))
    if not rec.get("approved"):
        raise RuntimeError("%s records no approval. Chris approves the sheet, then we spend; there is "
                           "no path around it." % Path(sheet_json).name)
    base, span, ctx = None, None, None
    for s, c, x in F.cells([SPAN]):
        span, base, ctx = s, Path(c), x
    crops = {"base": base, "clip": CLIP}
    shown = rec.get("crop_sha16") or {}
    bad = {}
    for k, p in crops.items():
        if k not in shown:
            bad[k] = "not on the approved sheet"
        elif shown[k] != F.crop_sha(p):
            bad[k] = "crop changed since the sheet: shown %s, now %s" % (shown[k], F.crop_sha(p))
        else:
            fault = diag.gate_outbound(p, offnet=True)[1]
            if fault:
                bad[k] = "the outbound gate refuses it: %s" % fault
    if bad:
        raise RuntimeError("contact-sheet gate REFUSED: %s" % json.dumps(bad, ensure_ascii=False))
    return span, ctx, crops, rec


def run(sheet_json=SHEET_JSON, out=OUT):
    from run_header import build_header, RunWriter, _git_head, _git_dirty
    span, ctx, crops, rec = _gates(sheet_json)

    # A killed or faulted run leaves rows and no footer. Resuming onto it is the splice the run-level
    # fault rule forbids, so it is refused here rather than remembered.
    if Path(out).exists():
        rows_ = [o for o in diag._lines(out)
                 if o.get("kind") in ("read", "call_error", "crop_refused")]
        if rows_ and not any(o.get("kind") == "padprobe_run_footer" for o in diag._lines(out)):
            raise RuntimeError("%s holds %d read(s) and NO footer -- its run never closed. Rerun from "
                               "the top: delete it, or pass a new --out. Never splice."
                               % (Path(out).name, len(rows_)))

    g0 = {"git_head": _git_head(), "git_dirty": _git_dirty()}
    cat = F.catalog(refresh=True)
    arms = [m for m in F.ARMS if m not in getattr(F, "EXCLUDED_ARMS", {})
            and (cat["models"].get(m) or {}).get("status") == "ok"]
    # Archive the pixels BEFORE spending on them. A run is answerable for its pixels only while the
    # pixels exist, and the clip is archived under its own aperture so it can never be mistaken for
    # the span box it was cut from.
    arch = {"base": diag.sent_archive_put(crops["base"], SPAN, "A2_spanbox", why="pad probe 6(b)"),
            "clip": diag.sent_archive_put(crops["clip"], SPAN, "A2_bandclip", why="pad probe 6(b)")}
    print("archived %s -> %s" % (arch, diag.SENT_SHA.name))

    done = set()
    if Path(out).exists():
        done = {(o.get("condition"), o["model"]) for o in diag._lines(out)
                if o.get("kind") == "read" and (o.get("hebrew") or "").strip()}
    faulted, dead = None, 0

    with RunWriter(out) as f:
        f.header(build_header(
            host=F.HOST, port=F.PORT, model="multi:%d-openrouter-arms" % len(arms),
            digest_fn=lambda hp, mo, t=None: "n/a:hosted-api",
            identity_extra={
                # kind stays `config_header`: require_endpoint accepts that and only that, and a run
                # whose header cannot be checked for its machine is the gap the rule exists to close.
                "run": "padprobe", "item": "6(b) pad probe", "span": SPAN, "arms": arms,
                "aperture": "A2_spanbox + A2_bandclip (paired, same run)",
                "conditions": {k: str(v) for k, v in crops.items()},
                "crop_sha16": {k: F.crop_sha(v) for k, v in crops.items()},
                "crops_archived": arch, "crops_archive": diag.SENT_SHA.name,
                "bandclip_rows_kept": rec.get("rows_kept"), "bandclip_parent_rows": rec.get("parent_rows"),
                "prompt_sha16": F.diag_sha(F.PROMPT_HEAD + F.PROMPT_TAIL),
                "text_context_sent": True,
                "truth_digest": F.truth_digest(), "truth_digest_at_sheet": rec.get("truth_digest"),
                "excluded_arms": getattr(F, "EXCLUDED_ARMS", {}),
                "contact_sheet": Path(sheet_json).name,
                "contact_sheet_approved_at": rec.get("approved_at"),
                "approval": "recorded claim from the sheet sidecar; human approval is NOT "
                            "machine-verifiable"},
            extra={"privacy": {"request_filter": "provider.data_collection=deny"},
                   "catalog_pulled": cat["pulled"], "budget_before": F._budget(),
                   "note_box_crops_sent": 0, "git_at_start": g0, "dead_run_at": DEAD_RUN_AT,
                   "pages": "FILE pages (printed = file - 88)",
                   "design": "both conditions in ONE run: the recorded baseline is two weeks old and "
                             "comparing across runs would carry a confound the pairing removes"}),
            "pad probe")
        for model in arms:
            c = cat["models"][model]
            print("\n== %s" % model, flush=True)
            f.row({"kind": "arm_header", "model": model, "started": time.strftime("%H:%M:%S"),
                   "git_head": _git_head(), "git_dirty": _git_dirty(),
                   "structured": c["structured"]})
            for cond, cpath in crops.items():
                if (cond, model) in done:
                    continue
                try:
                    row = F.call(model, span, cpath, ctx, c["structured"])
                except diag.CropRefused as e:
                    row = {"span_id": SPAN, "model": model, "kind": "crop_refused",
                           "unscorable": "crop-fault:%s" % e.fault, "crop_fault": e.fault,
                           "cost_usd": 0.0, "reached_wire": False}
                except Exception as e:
                    row = {"span_id": SPAN, "model": model, "kind": "call_error",
                           "error": ("%s: %s" % (type(e).__name__, e))[:300], "reached_wire": True}
                row["condition"] = cond
                row["aperture"] = "A2_bandclip" if cond == "clip" else "A2_spanbox"
                f.row(row)
                dead = 0 if row.get("kind") == "read" else dead + 1
                print("  %-5s %-10s %r" % (cond, row.get("kind"),
                                           str(row.get("gated", row.get("error", "")))[:44]),
                      flush=True)
                if dead >= DEAD_RUN_AT:
                    faulted = "%d consecutive dead cells" % dead
                    break
            if faulted:
                break
        g1 = {"git_head": _git_head(), "git_dirty": _git_dirty()}
        clean = (g0 == g1 and g0["git_dirty"].get("state") == "clean")
        f.row({"kind": "padprobe_run_footer", "git_at_start": g0, "git_at_end": g1,
               "clean_run": clean, "run_faulted": faulted, "budget_after": F._budget(),
               "finished": time.strftime("%Y-%m-%dT%H:%M:%S")})
    if faulted:
        print("\n*** RUN FAULTED: %s -- this artifact cannot be scored or cited. Rerun from the top; "
              "never splice. ***" % faulted)
    if not clean:
        print("\n*** PROVISIONAL: git moved or the tree was dirty. start=%s end=%s ***" % (g0, g1))
    print("\nwrote %s" % out)


def score(out=OUT):
    """The paired question and nothing else: exact on the clip vs exact on the pad, same arms."""
    lines = list(diag._lines(out))
    foot = [o for o in lines if o.get("kind") == "padprobe_run_footer"]
    span = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}[SPAN]
    truth = span["truth"]
    by = {}
    for o in lines:
        if o.get("kind") == "read":
            by[(o["condition"], o["model"])] = diag.classify(o.get("gated") or "", truth)
    arms = sorted({m for _c, m in by})
    tal = {}
    for cond in ("base", "clip"):
        c = {}
        for m in arms:
            k = by.get((cond, m))
            if k:
                c[k] = c.get(k, 0) + 1
        tal[cond] = c
    print("span %s  truth %r  n_arms=%d" % (SPAN, truth, len(arms)))
    for cond in ("base", "clip"):
        c = tal[cond]
        print("  %-5s exact=%-3d clipped=%-3d contains=%-3d wrong=%-3d abstain=%-3d other=%s"
              % (cond, c.get("exact", 0), c.get("clipped", 0), c.get("contains", 0),
                 c.get("wrong", 0), c.get("abstain", 0),
                 {k: v for k, v in c.items() if k not in
                  ("exact", "clipped", "contains", "wrong", "abstain")}))
    moved = [(m, by.get(("base", m)), by.get(("clip", m))) for m in arms
             if by.get(("base", m)) != by.get(("clip", m))]
    print("  arms whose class MOVED: %d of %d" % (len(moved), len(arms)))
    for m, a, b in moved:
        print("    %-34s %-9s -> %-9s" % (m, a, b))
    if foot:
        print("  clean_run=%s  faulted=%s" % (foot[-1].get("clean_run"), foot[-1].get("run_faulted")))
    return by, tal, moved


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "sheet":
        build(a[a.index("--out") + 1] if "--out" in a else None)
    elif cmd == "run":
        run(Path(a[a.index("--sheet") + 1]) if "--sheet" in a else SHEET_JSON,
            Path(a[a.index("--out") + 1]) if "--out" in a else OUT)
    elif cmd == "score":
        score(Path(a[a.index("--out") + 1]) if "--out" in a else OUT)
    else:
        print(__doc__)
        sys.exit(2)
