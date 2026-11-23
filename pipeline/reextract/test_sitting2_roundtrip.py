# -*- coding: utf-8 -*-
u"""End to end: the sitting page's OWN JavaScript writes an export, and the loader reads it.

Chris, 2026-11-22 (overnight): "check the second-sitting page end to end with a synthetic export,
so Chris's real export cannot fail on load."

The page and the loader are two sides of one contract written in two languages, and until now
nothing had ever carried a row across it. `sitting2_page.selftest` builds ONE row by hand in
Python -- which is a check that I can write what I expect, not that the page writes it. So this
file does the crossing for real:

  1. it extracts the `build_export` script from the BUILT page's bytes -- the artifact Chris opens,
     not a re-rendered copy -- and runs it under node with a DOM stub;
  2. it answers every tile and every disagreement by calling the page's OWN handlers (`setv`,
     `arm`, `pick_letter`, `setreason`, `setow`, `setbasis`), so the armed-tile rule, the letter
     palette and the required-reason logic are the ones a signer drives;
  3. it checks the page REFUSES to export while anything is open, before completing the sitting;
  4. it feeds the resulting file to `sitting2_load` and requires every row to be accepted;
  5. then it corrupts that real export eight ways and requires each one to be refused, with the
     reason naming what is wrong.

Step 5 is the part that makes step 4 mean anything. A loader that accepts everything would pass
step 4 too.

The export is written to a temporary directory. This test never writes the file the signer's
verdicts are appended to, and it never reads a model's reading of anything.

All page numbers are FILE pages: printed = file - 88.

    python -X utf8 pipeline/reextract/test_sitting2_roundtrip.py
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import sitting2_page as S

#: A date that is NOT the build date and NOT today, so the check that the signer's own date is
#: carried through verbatim cannot pass by coincidence.
SIGNER_DATE = "2026-12-03"
SIGNER = "Chris"

DRIVER = u"""
'use strict';
// Runs the page's own export code. argv: page.html out.ndjson stage
const fs = require('fs'), vm = require('vm'), path = process.argv[2];
const html = fs.readFileSync(path, 'utf8');
const bodies = [];
const re = /<script>([\\s\\S]*?)<\\/script>/g;
let m;
while ((m = re.exec(html)) !== null) { bodies.push(m[1]); }
const src = bodies.filter(b => b.indexOf('function build_export') !== -1);
if (src.length !== 1) {
  console.log(JSON.stringify({error: 'expected exactly one script with build_export, got '
                              + src.length + ' of ' + bodies.length}));
  process.exit(3);
}
// A DOM stub: enough for the page's render path, and nothing more.
const els = {};
function el(id) {
  if (!els[id]) { els[id] = {id: id, innerHTML: '', className: '', value: '',
                             children: [], appendChild: function (c) { this.children.push(c); }}; }
  return els[id];
}
const alerts = [];
const ctx = {
  document: {
    getElementById: el,
    createElement: function () {
      return {className: '', innerHTML: '', href: '', download: '', children: [],
              appendChild: function (c) { this.children.push(c); }, click: function () {}};
    }
  },
  URL: {createObjectURL: function () { return 'blob:stub'; }},
  Blob: function () {},
  alert: function (x) { alerts.push(String(x)); },
  console: console,
  JSON: JSON,
  String: String
};
vm.createContext(ctx);
// The signer bar is not in the script, so the stub supplies what the browser would hold.
el('signer').value = %(signer)s;
el('date').value = %(date)s;
vm.runInContext(src[0], ctx);          // this calls render() at the end, as the browser does

const out = {rows: ctx.ROWS.length, owed: ctx.OWED.length, owv: ctx.OWV, alerts: alerts};
// (3) nothing answered yet: the page must refuse to export.
ctx.build_export();
out.empty_export = el('out').value.slice(0, 60);

// (2) answer every tile through the page's own handlers, cycling the three verdicts so each
// branch is exercised, and naming a letter through the palette for every `changed`.
const letters = Object.keys(ctx.LETTERCH);
let a = 0, changed = 0, abstained = 0, kept = 0;
for (let i = 0; i < ctx.ROWS.length; i++) {
  const r = ctx.ROWS[i];
  for (let n = 0; n < r.tiles.length; n++) {
    const t = r.tiles[n], mode = a++ %% 3;
    if (mode === 0) { ctx.setv(r.span_id, t.i, 'keep_prior'); kept++; }
    else if (mode === 1) {
      ctx.arm(r.span_id, t.i);
      ctx.pick_letter(letters[a %% letters.length]);     // through the palette, as a signer does
      changed++;
    } else {
      ctx.setv(r.span_id, t.i, 'abstain');
      ctx.setreason(r.span_id, t.i, 'synthetic: stroke is cut by the gutter');
      abstained++;
    }
  }
}
out.kept = kept; out.changed = changed; out.abstained = abstained;
// A changed tile with no letter must still be open -- check before answering the disagreements.
if (ctx.ROWS.length) {
  const r0 = ctx.ROWS[0];
  ctx.arm(r0.span_id, r0.tiles[0].i);                 // armed, no letter named
  ctx.build_export();
  out.armed_no_letter = el('out').value.slice(0, 60);
  ctx.setv(r0.span_id, r0.tiles[0].i, 'keep_prior');  // put it back
}
for (let j = 0; j < ctx.OWED.length; j++) {
  ctx.setow(j, ctx.OWV[j %% ctx.OWV.length]);
  ctx.setbasis(j, 'synthetic: the lower stroke is visible in the crop');
}
out.open_after = ctx.problems().length;
ctx.build_export();
const text = el('out').value;
out.export_head = text.slice(0, 60);
fs.writeFileSync(process.argv[3], text, 'utf8');
out.bytes = Buffer.byteLength(text, 'utf8');
console.log(JSON.stringify(out));
"""


def _node():
    return shutil.which("node")


def drive(page, out_path, tmp):
    u"""Run the page's own JS. Returns the driver's summary dict."""
    node = _node()
    if not node:
        raise RuntimeError("no node on PATH: the page's own export code cannot be RUN here, so "
                           "this crossing is UNMEASURED -- a failure, not a skip")
    js = os.path.join(tmp, "driver.js")
    io.open(js, "w", encoding="utf-8", newline="\n").write(
        DRIVER % {"signer": json.dumps(SIGNER), "date": json.dumps(SIGNER_DATE)})
    proc = subprocess.Popen([node, js, str(page), out_path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    so, se = proc.communicate()
    so = so.decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not so:
        raise RuntimeError("the driver failed (rc=%s): %s / %s"
                           % (proc.returncode, so[-400:], se.decode("utf-8", "replace")[-400:]))
    return json.loads(so.splitlines()[-1])


def _write(path, rows):
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        u"".join(json.dumps(r, ensure_ascii=False) + u"\n" for r in rows))
    return path


def selftest():
    n, f = [0], [0]

    def ck(name, cond, extra=""):
        n[0] += 1
        if cond:
            print("  ok    %s" % name)
        else:
            f[0] += 1
            print("  FAIL  %s   %s" % (name, extra))

    tmp = tempfile.mkdtemp(prefix="sitting2_rt_")
    try:
        page = S.OUT
        print("(1) the page's own JavaScript, run over the BUILT page")
        ck("the built page is on disk -- this crossing is over the artifact Chris opens",
           os.path.isfile(str(page)), str(page))
        exp = os.path.join(tmp, "synthetic_sitting2_verdicts.jsonl")
        d = drive(page, exp, tmp)
        ck("the page carries the five prior rows and the open disagreements",
           d["rows"] == 5 and d["owed"] >= 1, (d["rows"], d["owed"]))
        ck("the page's three disagreement verdicts are the loader's three",
           tuple(d["owv"]) == S.OWED_VERDICTS, (d["owv"], S.OWED_VERDICTS))
        ck("with nothing answered, the page REFUSES to export",
           d["empty_export"].startswith("NOT EXPORTED"), d["empty_export"])
        ck("a tile armed for change with no letter named keeps the export shut",
           d.get("armed_no_letter", "").startswith("NOT EXPORTED"), d.get("armed_no_letter"))
        ck("every verdict branch was exercised: keep_prior, changed through the palette, abstain",
           d["kept"] and d["changed"] and d["abstained"], (d["kept"], d["changed"], d["abstained"]))
        ck("the page named no letter about nothing -- no alert was raised by the palette",
           d["alerts"] == [], d["alerts"])
        ck("with everything answered the page reports nothing open, and exports",
           d["open_after"] == 0 and not d["export_head"].startswith("NOT EXPORTED"),
           (d["open_after"], d["export_head"]))

        print("")
        print("(2) the loader reads what the page wrote")
        good, bad = S.sitting2_load(exp, S.PRIOR)
        ck("every row the page wrote is ACCEPTED -- the crossing the contract was never tested on",
           bad == [] and len(good) == 6,
           (len(good), [b.get("_refused", "")[:70] for b in bad]))
        kinds = sorted(set(r.get("kind") for r in good))
        ck("both row kinds crossed: the five tile rows and the disagreement row",
           kinds == ["sitting2_disagreement_verdicts", "sitting2_tile_verdicts"]
           and len([r for r in good if r["kind"] == "sitting2_tile_verdicts"]) == 5, kinds)
        tile_rows = [r for r in good if r["kind"] == "sitting2_tile_verdicts"]
        ck("the signer's own date is carried through VERBATIM, not the build date",
           all(r.get("date") == SIGNER_DATE for r in tile_rows)
           and S.TODAY != SIGNER_DATE, [r.get("date") for r in tile_rows])
        ck("every row names the signer and the priors it was made against, with their hash",
           all(r.get("signer") == SIGNER and r.get("prior_source") == S.PRIOR.name
               and r.get("prior_source_sha16") == S.sha16(S.PRIOR) for r in tile_rows))
        ck("each exported tile keeps the PRIOR beside the new verdict, so a reversal is visible",
           all("prior_verdict" in t for r in tile_rows for t in r["tiles"]))
        ck("every `changed` tile carries both the letter's name and its character",
           all(t.get("chose") and t.get("letter")
               for r in tile_rows for t in r["tiles"] if t["verdict"] == "changed"))
        ck("every `abstain` tile carries the reason the channel exists for",
           all((t.get("reason") or "").strip()
               for r in tile_rows for t in r["tiles"] if t["verdict"] == "abstain"))

        print("")
        print("(3) eight corruptions of that REAL export, each of which must be refused")
        rows = [json.loads(l) for l in io.open(exp, encoding="utf-8") if l.strip()]

        def refuse(name, mutate, expect):
            rs = json.loads(json.dumps(rows))          # a deep copy of the real export
            mutate(rs)
            p = _write(os.path.join(tmp, "m.jsonl"), rs)
            g, b = S.sitting2_load(p, S.PRIOR)
            why = " | ".join(x.get("_refused", "") for x in b)
            ck(name, len(b) == 1 and expect in why, (len(b), why[:110]))
            # The partition must keep the untouched rows: a bad row does not poison its neighbours.
            ck("...and the other %d rows are still accepted" % (len(rows) - 1),
               len(g) == len(rows) - 1, len(g))

        def first_tile(rs, v):
            for r in rs:
                if r.get("kind") != "sitting2_tile_verdicts":
                    continue
                for t in r["tiles"]:
                    if t["verdict"] == v:
                        return t
            raise RuntimeError("the export carries no %s tile to corrupt" % v)

        refuse("an abstain whose reason is blanked is refused, naming the reason as the content",
               lambda rs: first_tile(rs, "abstain").__setitem__("reason", "   "),
               "abstain with no reason")
        refuse("a change whose letter is removed is refused",
               lambda rs: first_tile(rs, "changed").__setitem__("chose", ""),
               "no letter was named")
        refuse("a verdict word the page cannot produce is refused",
               lambda rs: first_tile(rs, "keep_prior").__setitem__("verdict", "probably_resh"),
               "is not one of")
        refuse("a row whose crop hash is not the signed one is refused: other pixels, other picture",
               lambda rs: rs[0].__setitem__("crop_sha16", "0" * 16),
               "different picture")
        refuse("a strip whose tile indices do not correspond one-for-one is refused",
               lambda rs: rs[0]["tiles"].pop(0),
               "one-for-one")
        refuse("a verdict about a span nobody signed is refused",
               lambda rs: rs[0].__setitem__("span_id", "p999:n9"),
               "not in the prior export")
        refuse("a row of an unknown kind is refused rather than skipped",
               lambda rs: rs[0].__setitem__("kind", "sitting2_notes"),
               "unknown row kind")
        refuse("a disagreement with no basis is refused -- it reverses a signer on identical pixels",
               lambda rs: rs[-1]["verdicts"][0].__setitem__("basis", ""),
               "no basis")

        print("")
        ck("born-test check count is pinned, so a raise cannot quietly shorten the suite",
           n[0] == 31, n[0])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    print("%s: %d/%d checks" % ("PASS" if not f[0] else "FAIL", n[0] - f[0], n[0]))
    return f[0]


if __name__ == "__main__":
    sys.exit(selftest())
