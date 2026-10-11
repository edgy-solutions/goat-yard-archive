// Node test for verse_truth_ui.js (pure logic). Run: node test_verse_truth_ui.mjs
import { createRequire } from "node:module";
import assert from "node:assert/strict";
const require = createRequire(import.meta.url);
const U = require("./verse_truth_ui.js");

const EXPECTED_TESTS = 20;
const tests = [];
function test(name, fn) { tests.push([name, fn]); }

const TOPS = [100, 157, 214, 271, 328];
const BOTS = [140, 197, 254, 311, 368];
const regionItem = {
  item_id: "r:5:left:100", item_kind: "verse", file_page: 5, printed_page: -83, item_sha16: "abc",
  rects: [{ file_page: 5, col: "left", box: [10, 157, 300, 254] }],
};
const consts = {
  SNAP: { "5": { left: { tops: TOPS, bottoms: BOTS }, right: { tops: [], bottoms: [] }, full: { tops: [], bottoms: [] } } },
  set_sha16: "S", ui_config_hash: "U", run_config_hash: "R", exported_utc: "T",
};

test("snap: nearest target", () => { assert.equal(U.snap(160, TOPS, 0, 1000), 157); });
test("snap: tie goes to the lower target", () => { assert.equal(U.snap(185.5, TOPS, 0, 1000), 157); assert.equal(U.snap(170, [160, 180], 0, 1000), 160); });
test("snap: ignores targets outside the crop range", () => {
  assert.equal(U.snap(100, TOPS, 150, 300), 157);
  assert.equal(U.snap(100, TOPS, 500, 600), null);
});
test("applyDrag: noSnap keeps the raw value, snapped false", () => {
  const r = U.applyDrag([10, 157, 300, 254], "top", 163, TOPS, [100, 400], true);
  assert.deepEqual(r.rect, [10, 163, 300, 254]);
  assert.equal(r.edgeInfo.snapped, false);
});
test("applyDrag: snap on moves to the target, snapped true", () => {
  const r = U.applyDrag([10, 157, 300, 254], "bottom", 300, BOTS, [100, 400], false);
  assert.equal(r.rect[3], 311);
  assert.equal(r.edgeInfo.snapped, true);
});
test("applyDrag: top dragged past bottom clamps to y1-1 (nearest valid), y0<y1 holds", () => {
  const r = U.applyDrag([10, 157, 300, 254], "top", 900, [100, 157, 254, 330], [100, 400], true);
  assert.equal(r.rect[1], 253);
  assert.ok(r.rect[1] < r.rect[3]);
  const s = U.applyDrag([10, 157, 300, 254], "top", 900, TOPS, [100, 400], false);
  assert.equal(s.rect[1], 214);   // nearest valid TARGET below y1
  assert.ok(s.rect[1] < s.rect[3]);
});
test("applyDrag: bottom dragged above top clamps to y0+1", () => {
  const r = U.applyDrag([10, 157, 300, 254], "bottom", 0, BOTS, [100, 400], true);
  assert.equal(r.rect[3], 158);
});
test("applyDrag: at_crop_limit set at the top boundary", () => {
  const r = U.applyDrag([10, 157, 300, 254], "top", 20, TOPS, [117, 294], true);
  assert.equal(r.rect[1], 117);
  assert.equal(r.edgeInfo.at_crop_limit, true);
});
test("applyDrag: at_crop_limit set at the bottom boundary, not set inside", () => {
  const r = U.applyDrag([10, 157, 300, 254], "bottom", 999, BOTS, [117, 294], true);
  assert.equal(r.rect[3], 294);
  assert.equal(r.edgeInfo.at_crop_limit, true);
  const q = U.applyDrag([10, 157, 300, 254], "bottom", 260, BOTS, [117, 294], true);
  assert.equal(q.edgeInfo.at_crop_limit, false);
});
test("linesMoved: unchanged is 0", () => { assert.equal(U.linesMoved(157, 157, TOPS), 0); });
test("linesMoved: one line down is +1", () => { assert.equal(U.linesMoved(157, 214, TOPS), 1); });
test("linesMoved: two lines up is -2", () => { assert.equal(U.linesMoved(271, 157, TOPS), -2); });
test("linesMoved: off-target ratified value counts only targets strictly between", () => {
  assert.equal(U.linesMoved(157, 230, TOPS), 1);   // 214 strictly between, 230 not a target
  assert.equal(U.linesMoved(157, 160, TOPS), 0);
});
test("verdictCoupling: drag sets adjusted and records the edge", () => {
  const d = U.applyDrag(regionItem.rects[0].box, "top", 214, TOPS, [117, 294], false);
  const { state } = U.verdictCoupling({}, { type: "drag", item: regionItem, rectIdx: 0, rect: d.rect, edge: "top", edgeInfo: d.edgeInfo });
  assert.equal(state.verdict, "adjusted");
  assert.deepEqual(state.ratified[0].box, [10, 214, 300, 254]);
  assert.equal(state.ratified[0].edges.top.snapped, true);
});
test("verdictCoupling: correct resets ratified to detected (asks confirm when different)", () => {
  const d = U.applyDrag(regionItem.rects[0].box, "top", 214, TOPS, [117, 294], false);
  const adj = U.verdictCoupling({}, { type: "drag", item: regionItem, rectIdx: 0, rect: d.rect, edge: "top", edgeInfo: d.edgeInfo }).state;
  const ask = U.verdictCoupling(adj, { type: "choose", value: "correct", item: regionItem });
  assert.equal(ask.needsConfirm, true);
  assert.equal(ask.state.verdict, "adjusted");
  const ok = U.verdictCoupling(adj, { type: "choose", value: "correct", item: regionItem, confirmed: true });
  assert.equal(ok.needsConfirm, false);
  assert.equal(ok.state.verdict, "correct");
  assert.deepEqual(ok.state.ratified[0].box, regionItem.rects[0].box);
});
test("verdictCoupling: not_a_verse nulls ratified; adjusted re-initialises it", () => {
  const n = U.verdictCoupling({}, { type: "choose", value: "not_a_verse", item: regionItem }).state;
  assert.equal(n.ratified, null);
  assert.equal(n.verdict, "not_a_verse");
  const back = U.verdictCoupling(n, { type: "choose", value: "adjusted", item: regionItem }).state;
  assert.deepEqual(back.ratified[0].box, regionItem.rects[0].box);
});
test("export row: verse adjusted with moved top edge (lines_moved, snapped, ints)", () => {
  const d = U.applyDrag(regionItem.rects[0].box, "top", 214, TOPS, [117, 294], false);
  const st = U.verdictCoupling({ printed_number_as_seen: "7" }, { type: "drag", item: regionItem, rectIdx: 0, rect: d.rect, edge: "top", edgeInfo: d.edgeInfo }).state;
  const row = U.buildExportRow(regionItem, st, consts);
  assert.equal(row.verdict, "adjusted");
  assert.equal(row.as_ratified[0].edges.top.lines_moved, 1);
  assert.equal(row.as_ratified[0].edges.bottom.lines_moved, 0);
  assert.equal(row.printed_number_as_seen, "7");
  assert.equal(row.adjusted_without_change, false);
  assert.equal(row.ui_version, 2);
  assert.deepEqual(row.as_detected, [{ file_page: 5, col: "left", box: [10, 157, 300, 254] }]);
});
test("export row: adjusted_without_change and correct_with_change flags; unrated; not_a_verse", () => {
  const adj = U.verdictCoupling({}, { type: "choose", value: "adjusted", item: regionItem }).state;
  assert.equal(U.buildExportRow(regionItem, adj, consts).adjusted_without_change, true);
  const bad = { verdict: "correct", ratified: [{ box: [10, 214, 300, 254], edges: { top: { snapped: false, at_crop_limit: false }, bottom: { snapped: false, at_crop_limit: false } } }] };
  assert.equal(U.buildExportRow(regionItem, bad, consts).correct_with_change, true);
  assert.equal(U.buildExportRow(regionItem, undefined, consts).verdict, "unrated");
  const nv = U.verdictCoupling({}, { type: "choose", value: "not_a_verse", item: regionItem }).state;
  const r = U.buildExportRow(regionItem, nv, consts);
  assert.equal(r.verdict, "not_a_verse");
  assert.equal(r.as_ratified, null);
});
const missItem = { item_id: "m:5:900", item_kind: "miss", file_page: 5, printed_page: -83, item_sha16: "mm", page_h: 5400 };
test("export row: miss region_drawn with a drawn rect, cause kept separate; zero rects is invalid", () => {
  const nr = U.newRect([0, 0, 2097, 5400], 905, 1100, TOPS.concat([900]), BOTS.concat([1111]), [0, 5400], false);
  assert.deepEqual(nr.rect, [0, 900, 2097, 1111]);
  const st0 = U.verdictCoupling({ cause_verdict: "cause_confirmed" }, { type: "draw", item: missItem, rect: { col: "left", file_page: 5, box: nr.rect, edges: nr.edges } }).state;
  const row = U.buildExportRow(missItem, st0, consts);
  assert.equal(row.verdict, "region_drawn");
  assert.equal(row.cause_verdict, "cause_confirmed");
  assert.equal(row.as_ratified.length, 1);
  assert.equal(row.as_ratified[0].edges.top.snapped, true);
  assert.equal(U.isRated(missItem, st0), true);
  const empty = U.verdictCoupling({}, { type: "choose", value: "region_drawn", item: missItem }).state;
  const inv = U.buildExportRow(missItem, empty, consts);
  assert.equal(inv.verdict, "invalid");
  assert.equal(U.isRated(missItem, empty), false);
  const cleared = U.verdictCoupling(st0, { type: "clear", item: missItem, rectIdx: 0 }).state;
  assert.equal(U.buildExportRow(missItem, cleared, consts).verdict, "invalid");
  const nv = U.verdictCoupling(st0, { type: "choose", value: "not_a_verse", item: missItem }).state;
  assert.deepEqual(nv.ratified, []);
  assert.equal(U.buildExportRow(missItem, nv, consts).as_ratified, null);
});
test("export row: page answered / unrated / invalid", () => {
  const p = { item_id: "p:5", item_kind: "page", file_page: 5, printed_page: -83, item_sha16: "pp" };
  assert.equal(U.buildExportRow(p, { heads_not_shown: "2" }, consts).heads_not_shown, 2);
  assert.equal(U.buildExportRow(p, { heads_not_shown: "x" }, consts).heads_not_shown, "invalid");
  assert.equal(U.buildExportRow(p, {}, consts).verdict, "unrated");
});

let pass = 0, fail = 0;
if (tests.length !== EXPECTED_TESTS) {
  console.log(`EXPECTED_TESTS mismatch: discovered ${tests.length}, expected ${EXPECTED_TESTS}`);
  process.exit(1);
}
for (const [name, fn] of tests) {
  try { fn(); pass++; console.log("  PASS " + name); }
  catch (e) { fail++; console.log("  FAIL " + name + "\n" + e.stack); }
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
