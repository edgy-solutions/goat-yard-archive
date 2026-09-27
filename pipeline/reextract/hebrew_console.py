"""Build the Hebrew span console: the crops, every arm's read per span, and the run metrics.

One HTML file, self-contained (crops inlined as data URIs) so it opens from disk with no server and
no network. It stays in the private data repo: it holds page crops and the signed truth, and neither
leaves the machine.

    uv run hebrew_console.py

Reads only artifacts that already exist. Scores nothing new -- classification is diag.classify
against the signed truth, folded exactly as hebrew_local_arms._tally folds it, so the numbers here
are the same numbers as `hebrew_frontier_or.py score`.
"""
import base64
import collections
import io
import json
from pathlib import Path

import hebrew_aperture_diag as diag
import hebrew_frontier_or as F
import hebrew_local_arms as L

OUT = diag.DATA / "hebrew_span_console_20260927.html"
APERTURE = F.APERTURE
EX = ("exact", "punct-only")

# One class per outcome. `trunc` is NOT a shade of `abstain`: an empty reply that hit the token cap is
# a budget artifact, an empty reply that finished is a model declining to guess, and that distinction
# is the axis this whole comparison exists to measure.
CLS = {
    "exact": ("ex", "exact"),
    "punct-only": ("ex", "exact (punctuation only)"),
    "nikud-only": ("nik", "nikud-only"),
    "wrong": ("wr", "wrong"),
    "contains": ("wr", "wrong (contains)"),
    "abstain": ("ab", "abstain"),
    "UNSCORABLE": ("un", "unscorable"),
}


def _fam(m):
    """Model family, for the cross-family agreement column. Crude on purpose -- it only has to
    separate vendors, and a wrong split would understate agreement, not overstate it."""
    m = m.lower().split(" ")[0]
    head = m.split("/")[0]
    for k in ("openai", "anthropic", "google", "qwen", "moonshotai", "deepseek", "z-ai",
              "minimax", "xiaomi", "x-ai", "stepfun", "inclusionai"):
        if head == k:
            return k
    return head.split(":")[0]


def _arms():
    """Every read from every arm, tagged with its endpoint. Frontier = OR, local = D, legacy = C.

    The C arms carry `endpoint_id: None` in their artifact, which is the legacy provenance gap, so
    they are labelled unrecorded-endpoint everywhere they appear and never pooled into a rate.
    """
    rows = []
    for o in F.rows():
        rows.append(dict(o, arm=o["model"], lane="OR"))
    for o in L.score(include_sealed=True)[0]:
        if o.get("aperture") == APERTURE:
            rows.append(dict(o, arm=o["model"], lane="D"))
    for o in L.load_c_arms(include_sealed=True):
        if o.get("aperture") == APERTURE:
            rows.append(dict(o, arm=o["model"].replace(" (C)", ""), lane="C"))
    for o in rows:
        o["gated"] = (o.get("gated") or "").strip()
        o["truncated"] = bool(o.get("truncated"))
        o["fam"] = _fam(o["arm"])
    return rows


def _crop_uri(path):
    b = Path(path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode(), len(b)


def _esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _heb(t, cls="heb"):
    """Hebrew is printed RTL and is never normalised for display -- the printed form IS the datum."""
    if not t:
        return '<span class="none">-</span>'
    return f'<span class="{cls}" dir="rtl" lang="he">{_esc(t)}</span>'


def build():
    sets = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}
    man = {m["span_id"]: m for m in json.load(io.open(diag.CROPDIR / "manifest.json",
                                                      encoding="utf-8"))}
    rows = _arms()
    spans = sorted({o["span_id"] for o in rows},
                   key=lambda s: (int(s.split(":")[0][1:]), s))
    arms = sorted({(o["lane"], o["arm"]) for o in rows},
                  key=lambda t: ({"OR": 0, "D": 1, "C": 2}[t[0]], t[1]))
    at = {}
    for lane, a in arms:
        mr = [o for o in rows if o["arm"] == a and o["lane"] == lane and o["cls"] != "UNSCORABLE"]
        t = L._tally(mr)
        tc = sum(1 for o in mr if o["truncated"])
        at[(lane, a)] = {
            "exact": t["exact"], "nik": t["nikud-only"], "wrong": t["wrong"],
            "abst": t["abstain"] - sum(1 for o in mr if o["truncated"] and o["cls"] == "abstain"),
            "trunc": tc, "n": len(mr),
            "cost": sum(o.get("cost_usd") or 0 for o in mr),
            "tok_out": [o.get("tok_out") or 0 for o in mr],
            "prov": sorted({(o.get("provider") or "") for o in mr if o.get("provider")}),
            "rung": sorted({str(o.get("reasoning_applied")) for o in mr
                            if o.get("reasoning_applied")}),
        }
    idx = {(o["lane"], o["arm"], o["span_id"]): o for o in rows}

    h = []
    w = h.append
    w(HEAD)
    w('<h1>Hebrew span console <span class="sub">vol.1 footnote apparatus &middot; '
      'A2 aperture</span></h1>')
    w('<p class="lede">Every arm&rsquo;s read of every signed Hebrew span, beside the crop it was '
      'shown. <b>All page numbers are FILE pages (printed = file &minus; 88).</b> Scored against '
      'the signed verdicts only &mdash; a more fluent reading that differs from the printed form is '
      'a substitution, not an improvement.</p>')

    n_or = sum(1 for lane, _ in arms if lane == "OR")
    n_d = sum(1 for lane, _ in arms if lane == "D")
    n_c = sum(1 for lane, _ in arms if lane == "C")
    scor = [s for s in spans if not sets[s]["unscorable"]]
    w('<div class="facts">')
    for k, v in [("scorable spans", f"n = {len(scor)}"),
                 ("frontier arms (OR)", n_or), ("local arms (D)", n_d),
                 ("legacy arms (C)", f"{n_c} &mdash; unrecorded endpoint"),
                 ("frontier reads", sum(1 for o in rows if o["lane"] == "OR")),
                 ("frontier cost", "$0.911133115"),
                 ("aperture", "ratified span box + 12px native pad")]:
        w(f'<div><span class="k">{k}</span><span class="v">{v}</span></div>')
    w('</div>')
    w('<p class="warn"><b>This run is provisional.</b> Two commits landed while the frontier run '
      'was in flight and six arm-starts ran under a dirty tree, while the header claims one clean '
      'state. The prompt, crop, aperture and leak guard are byte-identical across all 468 reads, so '
      'the readings stand &mdash; but <code>git_head</code> over a tree that changes during a run '
      'is decoration, exactly as it is over a dirty one.</p>')

    # ---- per-span: the crop, the signed truth, and what the arms made of it -------------------
    w('<h2>The spans</h2>')
    w('<p class="note">Support counts use the 30 recorded arms (OR + D); the two legacy C arms '
      'carry an unrecorded endpoint and are shown without being counted. A reading is a distinct '
      'gated string; families are counted because same-family agreement is near-worthless. '
      '<b>Consensus is not correctness</b> &mdash; two spans below carry a large cross-family '
      'majority for a reading no arm got right.</p>')
    for s in spans:
        meta = sets[s]
        rs = [o for o in rows if o["span_id"] == s]
        e = (man.get(s) or {}).get(APERTURE)
        uri, nbytes = (_crop_uri(e["path"]) if e else (None, 0))
        # Support counts use the OR and D lanes only -- 30 arms, the same pool as the committed
        # design document. The C arms carry an unrecorded endpoint, so their readings are SHOWN but
        # never counted; folding them in moved p200:n2 from 60% to 59% and silently changed which
        # side of a threshold it fell on, which is itself the argument against the threshold.
        votes = [o for o in rs if o["gated"] and o["cls"] != "abstain" and not o["truncated"]
                 and o["lane"] != "C"]
        legacy = [o for o in rs if o["gated"] and o["lane"] == "C"]
        cnt = collections.Counter(o["gated"] for o in votes)
        ranked = cnt.most_common()
        right = {o["gated"] for o in rs if o["cls"] in EX}
        unsc = meta["unscorable"]
        top_share = (ranked[0][1] / len(votes)) if ranked and votes else 0
        top_right = bool(ranked) and ranked[0][0] in right
        # Both facts are shown when both are true. They are different failures -- "the arms converged
        # on the wrong word" and "no arm has the right word at all" -- and two spans here are both.
        flag = ""
        if not unsc and ranked and not top_right:
            flag += ('<span class="badge bad">top candidate WRONG &middot; '
                     f'{ranked[0][1]}/{len(votes)} = {top_share:.0%}</span>')
        if not unsc and not right:
            flag += ('<span class="badge bad">no correct candidate from any of the '
                     '30 recorded arms</span>')
        w(f'<section class="span" id="{_esc(s)}">')
        w(f'<div class="shead"><h3>{_esc(s)}</h3>'
          f'<span class="pg">file p{meta["page"]} &middot; printed p{meta["page"] - 88}</span>'
          f'{"<span class=badge un>UNSCORABLE</span>" if unsc else ""}{flag}</div>')
        w('<div class="srow">')
        w('<div class="cropcell">')
        if uri:
            w(f'<img class="crop" src="{uri}" alt="crop of {_esc(s)}" title="{_esc(s)} A2 crop, '
              f'{nbytes} bytes">')
            w(f'<div class="cap">A2 crop &middot; {nbytes} bytes</div>')
        else:
            w('<div class="cap none">no ratified span box &mdash; not scorable at A2</div>')
        w(f'<div class="truth">signed: {_heb(meta["truth"], "heb big")}</div>')
        bt = F._backtranslatable(meta["latin_context"], meta["truth"])
        w(f'<div class="cap">gloss back-translatable: '
          f'<b class="{"yes" if bt else "no"}">{"yes" if bt else "no"}</b></div>')
        w(f'<div class="cap ctx">context sent (Hebrew blanked to &bull;): '
          f'<i>{_esc(F._ctx(meta["latin_context"])[:180])}</i></div>')
        w('</div>')
        w('<div class="readcell"><table class="reads"><thead><tr><th>#</th><th>reading</th>'
          '<th>votes</th><th>families</th><th>arms</th></tr></thead><tbody>')
        for i, (g, c) in enumerate(ranked, 1):
            who = [o for o in votes if o["gated"] == g]
            fams = sorted({o["fam"] for o in who})
            ok = g in right
            w(f'<tr class="{"ok" if ok else ""}"><td class="rk">{i}</td>'
              f'<td>{_heb(g)}{" <span class=tick>signed</span>" if ok else ""}</td>'
              f'<td class="num">{c}</td><td class="num">{len(fams)}</td><td class="arms">'
              + "".join(f'<span class="chip {o["lane"].lower()}" title="{_esc(o["arm"])} '
                        f'[{o["lane"]}]">{_esc(o["arm"].split("/")[-1])}</span>' for o in who)
              + '</td></tr>')
        if legacy:
            w('<tr class="silent"><td></td><td class="none">legacy lane &mdash; shown, not counted'
              '</td><td class="num">&ndash;</td><td class="num">&ndash;</td><td class="arms">'
              + "".join(f'<span class="chip c" title="{_esc(o["arm"])} [C: unrecorded endpoint] '
                        f'{_esc(o["gated"])}">{_esc(o["arm"])}</span>' for o in legacy)
              + '</td></tr>')
        silent = [o for o in rs if (o["cls"] == "abstain" or o["truncated"] or not o["gated"])
                  and o["lane"] != "C"]
        if silent:
            ab = [o for o in silent if not o["truncated"]]
            tr = [o for o in silent if o["truncated"]]
            w('<tr class="silent"><td></td><td class="none">no reading returned</td>'
              f'<td class="num">{len(silent)}</td><td class="num">-</td><td class="arms">'
              + "".join(f'<span class="chip ab" title="{_esc(o["arm"])} abstained">'
                        f'{_esc(o["arm"].split("/")[-1])}</span>' for o in ab)
              + "".join(f'<span class="chip tr" title="{_esc(o["arm"])} truncated or empty">'
                        f'{_esc(o["arm"].split("/")[-1])}</span>' for o in tr)
              + '</td></tr>')
        w('</tbody></table></div></div></section>')

    # ---- the matrix ---------------------------------------------------------------------------
    w('<h2>Matrix &mdash; every arm &times; every span</h2>')
    w('<p class="note">Hover a cell for the string the arm actually returned. Cross-lane '
      '<b>differences are not reader quality</b>: the frontier arms saw one image and a text '
      'context, the D arms saw two images and a context strip, under a different prompt. Use this '
      'for agreement only.</p>')
    w('<div class="legend">'
      '<span class="sw ex"></span>exact <span class="sw nik"></span>nikud-only '
      '<span class="sw wr"></span>wrong <span class="sw ab"></span>abstain '
      '<span class="sw tr"></span>truncated / empty <span class="sw un"></span>unscorable '
      '<span class="sw na"></span>not run</div>')
    w('<div class="scroll"><table class="mx"><thead><tr><th class="am">arm</th>'
      '<th class="ln">lane</th>')
    for s in spans:
        w(f'<th class="sp"><span>{_esc(s)}</span></th>')
    w('<th class="tot">exact</th></tr></thead><tbody>')
    for lane, a in arms:
        t = at[(lane, a)]
        w(f'<tr><td class="am" title="{_esc(a)}">{_esc(a)}</td>'
          f'<td class="ln l{lane.lower()}">{lane}</td>')
        for s in spans:
            o = idx.get((lane, a, s))
            if not o:
                w('<td class="c na"></td>')
                continue
            if o["truncated"] and o["cls"] != "UNSCORABLE":
                k, lab = "tr", "truncated / empty"
            else:
                k, lab = CLS.get(o["cls"], ("wr", o["cls"]))
            txt = o["gated"] or "(nothing returned)"
            w(f'<td class="c {k}" title="{_esc(a)} &middot; {_esc(s)} &middot; {lab}&#10;'
              f'{_esc(txt)}"></td>')
        w(f'<td class="tot">{t["exact"]}</td></tr>')
    w('</tbody></table></div>')

    # ---- metrics -----------------------------------------------------------------------------
    w('<h2>Metrics per arm</h2>')
    w('<p class="note"><code>exact</code> folds <code>punct-only</code>; <code>wrong</code> folds '
      '<code>contains</code> &mdash; identical folding to <code>hebrew_local_arms._tally</code>, so '
      'nothing is re-scored here under a second convention. <code>trunc</code> is its own outcome '
      'and is subtracted out of <code>abst</code>. Cost and tokens exist for the OR lane only.</p>')
    w('<table class="met"><thead><tr><th>arm</th><th>lane</th><th>exact</th><th>nik</th>'
      '<th>wrong</th><th>abst</th><th>trunc</th><th>n</th><th>profile</th><th>med out</th>'
      '<th>cost $</th><th>$/1k spans</th><th>reasoning applied</th><th>provider served</th>'
      '</tr></thead><tbody>')
    for lane, a in sorted(arms, key=lambda t: (-at[t]["exact"], t[0], t[1])):
        t = at[(lane, a)]
        n = max(t["n"], 1)
        med = 0
        if t["tok_out"]:
            q = sorted(t["tok_out"])
            med = q[len(q) // 2]
        per1k = (t["cost"] / n * 1000) if t["cost"] else 0
        bar = "".join(f'<span class="b {k}" style="width:{100 * t[k] / n:.1f}%"></span>'
                      for k in ("exact", "nik", "wrong", "abst", "trunc") if t[k])
        w(f'<tr><td class="am">{_esc(a)}</td><td class="ln l{lane.lower()}">{lane}</td>'
          f'<td class="num hi">{t["exact"]}</td><td class="num">{t["nik"]}</td>'
          f'<td class="num">{t["wrong"]}</td><td class="num">{t["abst"]}</td>'
          f'<td class="num{" flagc" if t["trunc"] else ""}">{t["trunc"] or ""}</td>'
          f'<td class="num">{t["n"]}</td><td class="barc">{bar}</td>'
          f'<td class="num{" flagc" if med > F.OUT_TOKEN_FLAG else ""}">{med or ""}</td>'
          f'<td class="num">{("%.4f" % t["cost"]) if t["cost"] else ""}</td>'
          f'<td class="num">{("%.2f" % per1k) if per1k else ""}</td>'
          f'<td class="sm">{_esc(", ".join(t["rung"]))}</td>'
          f'<td class="sm">{_esc(", ".join(t["prov"])[:60])}</td></tr>')
    w('</tbody></table>')
    w('<p class="note">A median output over ' + str(F.OUT_TOKEN_FLAG) + ' tokens is flagged, never '
      'aborted. Six endpoints refuse to disable reasoning at all, so the runner steps the rung '
      'down &mdash; off, then minimal, then omitted &mdash; and records which rung carried the '
      'read.</p>')
    w('<p class="foot">Written by <code>hebrew_console.py</code> from '
      '<code>hebrew_frontier_or_reads_20260927.jsonl</code> and the endpoint-D/C artifacts. '
      'Self-contained: crops are inlined, nothing is fetched. Companion documents: '
      '<code>hebrew_frontier_or_result_20260927.md</code>, '
      '<code>hebrew_preadjudication_design_20260927.md</code>.</p>')
    w("</body></html>")
    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(h))
    return OUT, len(spans), len(arms)


HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hebrew span console</title>
<style>
:root{
  --bg:#12100e; --pane:#1b1815; --line:#332e28; --ink:#ece6dc; --dim:#9b9285;
  --ex:#4f9d5d; --nik:#b08a2e; --wr:#a8443c; --ab:#4a4a52; --tr:#8a5a2b; --un:#2a2a30;
  --na:#191713; --acc:#c9a227;
}
*{box-sizing:border-box}
body{margin:0;padding:28px 22px 60px;background:var(--bg);color:var(--ink);
  font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
h1{margin:0 0 6px;font-size:23px;font-weight:600;letter-spacing:-.2px}
h1 .sub{font-size:13px;font-weight:400;color:var(--dim);letter-spacing:0}
h2{margin:38px 0 8px;font-size:17px;font-weight:600;border-bottom:1px solid var(--line);
  padding-bottom:6px}
h3{margin:0;font-size:15px;font-family:ui-monospace,Consolas,monospace;color:var(--acc)}
.lede{max-width:78ch;color:#cfc7ba;margin:0 0 16px}
.note{max-width:92ch;color:var(--dim);font-size:12.5px;margin:0 0 14px}
.warn{max-width:92ch;background:#2a1d17;border-left:3px solid var(--tr);padding:9px 12px;
  border-radius:0 4px 4px 0;font-size:12.5px;color:#e0d4c6;margin:14px 0 0}
code{font-family:ui-monospace,Consolas,monospace;font-size:.92em;color:#d8cfbe}
.facts{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 0}
.facts div{background:var(--pane);border:1px solid var(--line);border-radius:5px;padding:7px 11px}
.facts .k{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;
  color:var(--dim)}
.facts .v{font-size:15px;font-weight:600}
.heb{font-family:"SBL Hebrew","Ezra SIL","Times New Roman",serif;font-size:19px;
  direction:rtl;unicode-bidi:isolate}
.heb.big{font-size:26px}
.none{color:var(--dim);font-style:italic}
section.span{background:var(--pane);border:1px solid var(--line);border-radius:7px;
  padding:13px 15px;margin:0 0 12px}
.shead{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:10px}
.pg{font-size:11.5px;color:var(--dim)}
.badge{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;padding:2px 7px;
  border-radius:3px;font-weight:700}
.badge.bad{background:#3a1c19;color:#e59b93;border:1px solid var(--wr)}
.badge.un{background:#26262c;color:#a7a7b4;border:1px solid #3c3c46}
.srow{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap}
.cropcell{flex:0 0 300px;min-width:260px}
.readcell{flex:1 1 440px;min-width:330px;overflow-x:auto}
img.crop{max-width:100%;background:#f6f1e6;border:1px solid var(--line);border-radius:4px;
  padding:3px;image-rendering:-webkit-optimize-contrast;transition:transform .12s;
  transform-origin:left top;cursor:zoom-in}
img.crop:hover{transform:scale(2.1);z-index:9;position:relative;box-shadow:0 8px 30px #000a}
.cap{font-size:11px;color:var(--dim);margin-top:5px}
.cap.ctx{max-height:3.6em;overflow:hidden}
.truth{margin-top:9px;padding-top:8px;border-top:1px solid var(--line);font-size:11px;
  color:var(--dim)}
.yes{color:var(--nik)} .no{color:var(--ex)}
table{border-collapse:collapse;width:100%}
.reads th{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);
  text-align:left;padding:3px 7px;border-bottom:1px solid var(--line);font-weight:600}
.reads td{padding:4px 7px;border-bottom:1px solid #26221d;vertical-align:middle}
.reads tr.ok{background:#16251a}
.reads tr.silent td{color:var(--dim)}
.rk{color:var(--dim);font-size:11px;width:22px}
.num{text-align:right;font-variant-numeric:tabular-nums;font-family:ui-monospace,Consolas,monospace}
.tick{font-size:9.5px;background:var(--ex);color:#08120a;padding:1px 5px;border-radius:2px;
  text-transform:uppercase;letter-spacing:.05em;font-weight:700;vertical-align:middle}
.arms{line-height:1.9}
.chip{display:inline-block;font-size:10px;font-family:ui-monospace,Consolas,monospace;
  padding:1px 5px;margin:1px 2px 1px 0;border-radius:3px;background:#262119;
  border:1px solid #3a332a;color:#c8bfae;white-space:nowrap}
.chip.d{background:#1d2630;border-color:#2f3f4f;color:#a8c4dc}
.chip.c{background:#241d28;border-color:#3d3147;color:#c0a8d0}
.chip.ab{background:#22222a;border-color:#34343f;color:#8e8e9c}
.chip.tr{background:#2a1d12;border-color:#4a3520;color:#c99a63}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--pane)}
.mx{font-size:11px}
.mx th,.mx td{border-bottom:1px solid #262119}
.mx th.sp{height:92px;white-space:nowrap;padding:0}
.mx th.sp span{display:block;transform:rotate(-90deg);width:22px;
  font-family:ui-monospace,Consolas,monospace;font-size:10.5px;color:var(--dim);font-weight:500}
.mx td.am,.mx th.am{position:sticky;left:0;background:var(--pane);text-align:left;padding:3px 9px;
  font-family:ui-monospace,Consolas,monospace;font-size:10.5px;max-width:230px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;border-right:1px solid var(--line)}
.mx td.c{width:22px;height:19px;padding:0;border-left:1px solid #1e1a16}
.mx td.c:hover{outline:2px solid var(--acc);outline-offset:-2px}
.ln{font-size:9.5px;text-align:center;letter-spacing:.05em;font-weight:700;width:34px}
.lor{color:#c8bfae} .ld{color:#a8c4dc} .lc{color:#c0a8d0}
.tot{text-align:right;padding:0 9px;font-family:ui-monospace,Consolas,monospace;
  font-weight:600;color:var(--acc)}
.c.ex,.sw.ex,.b.exact{background:var(--ex)} .c.nik,.sw.nik,.b.nik{background:var(--nik)}
.c.wr,.sw.wr,.b.wrong{background:var(--wr)} .c.ab,.sw.ab,.b.abst{background:var(--ab)}
.c.tr,.sw.tr,.b.trunc{background:var(--tr)} .c.un,.sw.un{background:var(--un)}
.c.na,.sw.na{background:var(--na)}
.legend{display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:11.5px;
  color:var(--dim);margin:0 0 9px}
.sw{display:inline-block;width:13px;height:13px;border-radius:2px;margin-left:9px;
  vertical-align:-2px}
.met{background:var(--pane);border:1px solid var(--line);border-radius:6px;overflow:hidden;
  font-size:12px}
.met th{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);
  text-align:right;padding:6px 8px;border-bottom:1px solid var(--line);font-weight:600;
  white-space:nowrap}
.met th:first-child,.met th:nth-child(2){text-align:left}
.met td{padding:4px 8px;border-bottom:1px solid #26221d}
.met td.am{font-family:ui-monospace,Consolas,monospace;font-size:11px;white-space:nowrap}
.met .hi{color:var(--acc);font-weight:700}
.met .sm{font-size:10.5px;color:var(--dim);text-align:left;white-space:nowrap}
.met .flagc{color:#d99a55;font-weight:700}
.barc{width:120px;padding:0 8px!important}
.b{display:inline-block;height:9px;border-radius:1px}
.foot{margin-top:30px;padding-top:12px;border-top:1px solid var(--line);font-size:11.5px;
  color:var(--dim);max-width:92ch}
@media(max-width:760px){.cropcell{flex:1 1 100%}.readcell{flex:1 1 100%}}
</style></head><body>"""

if __name__ == "__main__":
    p, ns, na = build()
    print(f"wrote {p}")
    print(f"  {ns} spans x {na} arms")
