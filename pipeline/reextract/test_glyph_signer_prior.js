/* Born-test: re-opening a row with a prior `corrected` tile PRESENTS the correction.
 * ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
 *
 * Runs a BUILT glyph-signer page (--pass3 --pass3-round 2) in jsdom, with its own shipped JS, and asserts in
 * the unit the signer actually looks at -- the tile's OWN element -- never against the whole document: the page's
 * stylesheet mentions `corrected` and the derived string carries the letter, so a document-wide grep passes on
 * furniture. The informational line "furniture passes" proves that, on the same page.
 *
 * Exit 0 only if every assertion holds. The python wrapper runs it on a JS_PASS4 page (must exit 0) and on a
 * JS_PASS3 page (must NOT: that is what makes it a gate rather than decoration).
 * Run: NODE_PATH=<dir containing jsdom> node test_glyph_signer_prior.js <page.html>
 */
const fs = require("fs");
const { JSDOM } = require("jsdom");
const file = process.argv[2];
const dom = new JSDOM(fs.readFileSync(file, "utf8"), { url: "https://localhost/", runScripts: "dangerously", pretendToBeVisual: true });
const w = dom.window, d = w.document;
const RESH = "ר";
let fail = 0, n = 0;
function expect(name, cond, detail) {
  n++;
  console.log((cond ? "  OK   " : "  FAIL ") + name + (!cond && detail !== undefined ? "   [" + detail + "]" : ""));
  if (!cond) fail = 1;
}
(async () => {
await new Promise(res => { if (d.readyState === "complete") res(); else w.addEventListener("load", res); });
await new Promise(r => setTimeout(r, 100));
const S = "p493:n3";
const tile = d.getElementById("t_" + S + "_4");
expect("tile p493:n3#4 exists", !!tile);
const tileText = tile ? tile.textContent : "";

/* furniture check: a document-wide search for the letter and for `corrected` succeeds on ANY console,
   including the one that hid the correction. Printed so the reader sees why the assertion is per tile. */
const bodyText = d.body.textContent;
console.log("  info furniture passes: document-wide text holds the letter=" + bodyText.includes(RESH) +
  " and 'corrected'=" + (bodyText.includes("corrected") || d.documentElement.innerHTML.includes("corrected")) +
  " (so a whole-document grep proves nothing)");

const badge = tile && tile.querySelector(".priorbadge");
expect("tile 4 carries a prior badge in its own element", !!badge);
expect("tile 4's own text says 'prior: corrected' + resh", tileText.includes("prior: corrected " + RESH), JSON.stringify(tileText.slice(0, 80)));
expect("the printed glyph (final pe) is not what the badge names", !(badge && badge.textContent.includes("ף")));
const rest = tile && tile.querySelector(".restnote");
expect("tile 4 says it was restored from pass 2 by ruling", !!rest && /restored from pass 2/.test(rest.textContent));

const btns = tile ? Array.from(tile.querySelectorAll(".tbtn")).filter(b => !/\bchg\b/.test(b.className)) : [];
expect("tile 4 has its five verdict buttons (check, cross, del, not-in-crop, sic)", btns.length === 5, btns.length);
expect("all five verdict buttons are inert until unlocked", btns.length === 5 && btns.every(b => b.disabled === true));
const chg = tile && tile.querySelector(".tbtn.chg");
expect("tile 4 offers a per-tile 'change' control", !!chg);

/* a click on a disabled button must not change the model; and the model-level guard holds even if the
   control were reached some other way */
if (btns[0]) btns[0].click();
if (typeof w.setVerdict === "function") w.setVerdict(S, 4, "confirmed", "");
const tv = () => w.ST[S].tv[4] || {};
expect("a click and a direct setVerdict leave the prior reading in force (corrected resh)",
  tv().verdict === "corrected" && tv().chose === RESH, JSON.stringify(tv()));
expect("prior state is separate from current state (r.pv beside r.tv)",
  !!w.ST[S].pv && !!w.ST[S].pv[4] && w.ST[S].pv[4].verdict === "corrected" && w.ST[S].pv[4].chose === RESH);

/* the other nine adjudicated items arrive as `take`: their prior badge names the CURRENT (pass-3) reading */
const takes = [["p493:n3", 0], ["p594:n0", 6], ["p594:n0", 7], ["p803:n0", 0], ["p803:n0", 1], ["p803:n0", 2]];
for (const [s, i] of takes) {
  const t = d.getElementById("t_" + s + "_" + i);
  expect("take seed " + s + "#" + i + ": tile's own text says 'prior: not in crop'", !!t && t.textContent.includes("prior: not in crop"));
}
const chips = Array.from(d.querySelectorAll('.insat[data-s="' + S + '"] .inschip'));
expect("p493:n3's 3 insertion chips are present", chips.length === 3, chips.length);
expect("each chip names 'prior: not in crop' and its buttons are inert",
  chips.length === 3 && chips.every(c => /prior: not in crop/.test(c.textContent) &&
    Array.from(c.querySelectorAll(".tbtn")).filter(b => !/\bchg\b/.test(b.className)).every(b => b.disabled)));

/* the p594:n0 sic seed still fires, with the verdict NOT preset by the seed */
const sicTiles = Object.keys(w.ST["p594:n0"].sic || {});
expect("p594:n0 sic seed fired (a sic draft exists)", sicTiles.length >= 1, JSON.stringify(sicTiles));
if (sicTiles.length) {
  const i = sicTiles[0], v = w.ST["p594:n0"].tv[i] || {};
  expect("  ... with expected letter seeded", (w.ST["p594:n0"].sic[i].expected || "") !== "");
  expect("  ... and the tile verdict not preset to sic by the seed (it is whatever the signer last signed)",
    v.verdict !== "sic", JSON.stringify(v));
}

/* unlock: both states legible; a change is recorded as a change */
if (chg) chg.click();
const now = tile && tile.querySelector(".nowbadge");
expect("after 'change', the buttons are live", btns.length === 5 && btns.every(b => b.disabled === false));
expect("after 'change', the tile shows both prior: and now:",
  !!tile && tile.textContent.includes("prior: corrected " + RESH) && !!now && now.textContent.includes("now: corrected " + RESH));
if (btns[0]) btns[0].click();   // the check button: confirm
expect("a deliberate change is applied (now: confirmed) and the prior is still displayed",
  tv().verdict === "confirmed" && tile.textContent.includes("now: confirmed") && tile.textContent.includes("prior: corrected " + RESH));
const exp = w.lines().split("\n").filter(Boolean).map(JSON.parse).find(r => r.span_id === S);
const et = exp.tiles.find(t => t.i === 4);
expect("export records what the signer was shown (prior_verdict/prior_chose) beside the new verdict",
  et.prior_verdict === "corrected" && et.prior_chose === RESH && et.verdict === "confirmed", JSON.stringify(et));
expect("export insertions carry prior_verdict", exp.insertions.length === 3 && exp.insertions.every(x => x.prior_verdict === "not_in_crop"));

console.log((fail ? "RESULT FAIL" : "RESULT PASS") + " (" + n + " assertions) " + file.split(/[\\/]/).pop());
process.exit(fail);
})();
