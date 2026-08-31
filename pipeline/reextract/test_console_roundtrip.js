/* Live round-trip born-test for the console export layer (the newly-rewritten code).
 * For each console: load the REAL HTML into jsdom (its own save/restore/records/export JS runs),
 * simulate a verdict (check a radio + type a rationale), fire the input event -> save() persists to
 * localStorage; then simulate a HARD RELOAD by blanking the form and calling the page's own restore()
 * against the persisted store; assert the verdict survived; then call the page's own records() and
 * assert the exported JSONL carries the pinned inputs (crop_sha16 + candidates) + door + freshness.
 * This is the enter -> reload -> survived -> export -> in-the-file path, run on the shipped bytes.
 *
 * Run:  node test_console_roundtrip.js   (requires jsdom on NODE_PATH; not a repo dependency)
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HERE = __dirname;

function roundtrip(file, { pickValue, expectDoor, expectCandidatesNonEmpty }) {
  const html = fs.readFileSync(path.join(HERE, "audits", file), "utf8");
  const dom = new JSDOM(html, { url: "https://localhost/", runScripts: "dangerously", pretendToBeVisual: true });
  const w = dom.window, d = w.document;

  const cards = [...d.querySelectorAll(".card")];
  if (cards.length === 0) throw new Error(`${file}: no cards`);
  const card = cards[0];
  const spanId = card.dataset.spanId;

  // --- enter a verdict on card 0 ---
  const radio = card.querySelector(`input[type=radio][value="${pickValue}"]`);
  if (!radio) throw new Error(`${file}: no radio value=${pickValue} on ${spanId}`);
  radio.checked = true;
  const reason = card.querySelector(".reason");
  reason.value = "roundtrip-probe";
  radio.dispatchEvent(new w.Event("input", { bubbles: true }));   // -> page save()

  // localStorage must now hold the verdict (append-as-made). Shape-agnostic: Sitting A persists an array
  // of records, Sitting B a dict of raw per-card state — either way the span id is in the serialized value.
  const KEY = Object.keys(w.localStorage).find(k => w.localStorage.getItem(k) && w.localStorage.getItem(k).includes(spanId));
  if (!KEY) throw new Error(`${file}: verdict not persisted to localStorage`);

  // --- simulate HARD RELOAD: blank the form, then run the page's own restore() ---
  radio.checked = false;
  reason.value = "";
  w.restore();
  const rehydrated = card.querySelector(`input[type=radio][value="${pickValue}"]`);
  if (!rehydrated.checked) throw new Error(`${file}: verdict did NOT survive reload (radio not re-checked)`);
  if (card.querySelector(".reason").value !== "roundtrip-probe")
    throw new Error(`${file}: rationale did NOT survive reload`);

  // --- export: the record the file would write ---
  const rec = w.records().find(r => r.span_id === spanId);
  if (!rec) throw new Error(`${file}: record absent from export`);
  const pv = rec.provenance || {}, inp = rec.inputs || {};
  if (pv.door !== expectDoor) throw new Error(`${file}: door ${pv.door} != ${expectDoor}`);
  if (pv.session_freshness !== "cold-context") throw new Error(`${file}: freshness not attested`);
  if (!inp.crop || !inp.crop_sha16) throw new Error(`${file}: inputs not pinned by hash`);
  if (expectCandidatesNonEmpty && (!Array.isArray(inp.candidates) || inp.candidates.length === 0))
    throw new Error(`${file}: candidates not pinned`);

  console.log(`  OK ${file} [${spanId}] entered=${pickValue} -> reload survived -> exported ` +
              `(door=${pv.door}, crop_sha=${inp.crop_sha16}, candidates=${(inp.candidates||[]).length})`);
  return true;
}

let fail = 0;
try {
  console.log("Sitting A:");
  roundtrip("sitting_a_console.html", { pickValue: "valid", expectDoor: "audited-by-agent-in-session", expectCandidatesNonEmpty: true });
  console.log("Sitting B (disagreement card):");
  roundtrip("sitting_b_console.html", { pickValue: "take-extracted", expectDoor: "adjudicated-by-human-review", expectCandidatesNonEmpty: true });
} catch (e) { fail = 1; console.error("  FAIL:", e.message); }

console.log(fail ? "\nFAIL — round-trip broken" : "\nPASS — enter -> hard-reload -> survived -> export -> pinned, both consoles");
process.exit(fail);
