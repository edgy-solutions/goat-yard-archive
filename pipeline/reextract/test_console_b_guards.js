/* Prove the backported guards fire in the REAL base console (sitting_b_console.html), by running its own
 * shipped JS in jsdom: neither-without-correction and over-60% correction must be refused (not exported),
 * a short valid span must pass, and a verdict must survive enter -> save -> blank -> restore.
 * Run: NODE_PATH=<jsdom>/node_modules node test_console_b_guards.js
 */
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const file = path.join(__dirname, "audits", "sitting_b_console.html");
const dom = new JSDOM(fs.readFileSync(file, "utf8"), { url: "https://localhost/", runScripts: "dangerously", pretendToBeVisual: true });
const w = dom.window, d = w.document;

const dis = d.querySelector(".card.dis");
const sid = dis.dataset.spanId;
const cands = JSON.parse(dis.dataset.candidates);
const notelen = Math.max(...cands.map(c => c.length));

function pick(card, value) {
  const r = card.querySelector(`input[value="${value}"]`);
  r.checked = true; r.dispatchEvent(new w.Event("input", { bubbles: true }));
  return r;
}
function setReason(card, text) {
  const i = card.querySelector(".reason"); i.value = text;
  i.dispatchEvent(new w.Event("input", { bubbles: true }));
}
function exported(id) { return w.records().some(r => r.span_id === id); }

let fail = 0;
function expect(name, cond) { console.log((cond ? "  OK  " : "  FAIL ") + name); if (!cond) fail = 1; }

console.log(`base console card ${sid}, note length ${notelen}`);

// GUARD 1 — neither, empty correction
pick(dis, "neither"); setReason(dis, "");
expect("neither + empty correction -> check() false", w.check(dis) === false);
expect("  ... and NOT exported", !exported(sid));
expect("  ... err shown", dis.querySelector(".err").classList.contains("on"));

// GUARD 2 — neither, correction longer than 60% of the note
setReason(dis, "x".repeat(Math.ceil(0.6 * notelen) + 3));
expect("over-60% correction -> check() false", w.check(dis) === false);
expect("  ... and NOT exported", !exported(sid));

// PASS — neither, a real short span
setReason(dis, "בהר");
expect("short RTL span -> check() true", w.check(dis) === true);
expect("  ... exported with the correction", (w.records().find(r => r.span_id === sid) || {}).disputed_span_correction === "בהר");

// PASS — take-extracted needs no correction
pick(dis, "take-extracted"); setReason(dis, "");
expect("take-extracted, no correction -> check() true", w.check(dis) === true);
expect("  ... exported", exported(sid));

// ROUND-TRIP — enter -> save -> blank -> restore survives
pick(dis, "neither"); setReason(dis, "בהר");
dis.querySelector('input[value="neither"]').checked = false;
dis.querySelector(".reason").value = "";
w.restore();
expect("verdict survived reload (radio)", dis.querySelector('input[value="neither"]').checked === true);
expect("correction survived reload", dis.querySelector(".reason").value === "בהר");

console.log(fail ? "\nFAIL" : "\nPASS — both guards fire in the base console, valid spans pass, state survives reload");
process.exit(fail);
