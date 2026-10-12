// Node test for verse_truth_ui.js (pure logic). Run: node test_verse_truth_ui.mjs
import { createRequire } from "node:module";
import assert from "node:assert/strict";
const require = createRequire(import.meta.url);
const U = require("./verse_truth_ui.js");

const EXPECTED_TESTS = 31;
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

const CARRY = { from_set_sha16: "OLDSET", from_ui_key: "versetruth_OLDSET_ui2", fields: ["cause_verdict", "note"],
  map: { "m:5:900": { old_item_id: "m:5:800", old_item_sha16: "osha", identity: {} },
         "m:6:10": { old_item_id: "m:6:10", old_item_sha16: "o2", identity: {} },
         "m:7:1": { old_item_id: "m:7:1", old_item_sha16: "o3", identity: {} } } };
const OLD = {
  "m:5:800": { cause_verdict: "cause_confirmed", note: "gutter", verdict: "region_drawn", ratified: [{ col: "left" }] },
  "m:6:10": { verdict: "not_a_verse" },
  "m:7:1": { cause_verdict: "x", note: "n7" },
  "m:99:1": { cause_verdict: "unmapped", note: "never copied" },
};
test("carryForward: copies cause_verdict + note + carried_from, nothing else; ignores unmapped old items", () => {
  const r = U.carryForward({}, OLD, CARRY);
  assert.deepEqual(r.items["m:5:900"], { cause_verdict: "cause_confirmed", note: "gutter",
    carried_from: { set_sha16: "OLDSET", item_id: "m:5:800", item_sha16: "osha", ui_version: 2 } });
  assert.equal("verdict" in r.items["m:5:900"], false);
  assert.equal("ratified" in r.items["m:5:900"], false);
  assert.equal(r.items["m:99:1"], undefined);
  assert.deepEqual(r.carried.sort(), ["m:5:900", "m:7:1"]);
});
test("carryForward: skips old items with no diagnosis (no_old_state), including absent ones", () => {
  const r = U.carryForward({}, OLD, CARRY);
  assert.deepEqual(r.skipped, [{ id: "m:6:10", reason: "no_old_state" }]);
  const r2 = U.carryForward({}, {}, CARRY);
  assert.equal(r2.carried.length, 0);
  assert.equal(r2.skipped.length, 3);
});
test("carryForward: never overwrites a new item that already has cause or note; pure on its inputs", () => {
  const cur = { "m:5:900": { cause_verdict: "mine" }, "m:7:1": { note: "typed", verdict: "not_a_verse" } };
  const before = JSON.stringify(cur);
  const r = U.carryForward(cur, OLD, CARRY);
  assert.equal(JSON.stringify(cur), before);
  assert.equal(r.items["m:5:900"].cause_verdict, "mine");
  assert.equal(r.items["m:7:1"].note, "typed");
  assert.equal(r.items["m:7:1"].verdict, "not_a_verse");
  assert.deepEqual(r.skipped.filter(s => s.reason === "new_already_set").map(s => s.id).sort(), ["m:5:900", "m:7:1"]);
  const again = U.carryForward(U.carryForward({}, OLD, CARRY).items, OLD, CARRY);
  assert.equal(again.carried.length, 0, "a second load carries nothing (idempotent)");
});
test("rowsToOldItems: refuses rows from another set, converts the rest", () => {
  const c = U.rowsToOldItems([{ item_id: "a", set_sha16: "OLDSET", cause_verdict: "c", note: "n" },
                              { item_id: "b", set_sha16: "OTHER", cause_verdict: "c", note: "n" }], "OLDSET");
  assert.equal(c.refused, 1);
  assert.deepEqual(Object.keys(c.items), ["a"]);
});
test("export row: carried_from and edited_after_carry for miss and non-miss items", () => {
  const cf = { set_sha16: "OLDSET", item_id: "m:5:800", item_sha16: "osha", ui_version: 2 };
  const row = U.buildExportRow(missItem, { cause_verdict: "c", note: "n", carried_from: cf, edited_after_carry: true }, consts);
  assert.deepEqual(row.carried_from, cf);
  assert.equal(row.edited_after_carry, true);
  const plain = U.buildExportRow(regionItem, undefined, consts);
  assert.equal(plain.carried_from, null);
  assert.equal(plain.edited_after_carry, false);
});

test("pageColumn: slanted col_split decides by y; geometry xdiv only without it", () => {
  const it = { xdiv: 1482, col_split: { slope: -0.0169, c0: 1754 } };
  // rule at y=700 is 1742.2, at y=4000 is 1686.4: the same x flips column with y
  assert.equal(U.pageColumn(it, 1700, 700), "left");
  assert.equal(U.pageColumn(it, 1700, 4000), "right");
  // geometry xdiv (223 px off) would have called x=1600 right everywhere
  assert.equal(U.pageColumn(it, 1600, 2000), "left");
  assert.equal(U.pageColumn({ xdiv: 1482 }, 1600, 2000), "right");
  assert.equal(U.pageColumn({ xdiv: 1482 }, 1400, 2000), "left");
  assert.equal(U.pageColumn({}, 1400, 2000), null);
});

const PRIOR = {
  from_set_sha16: "OLD",
  map: {
    "r:5:left:100": { "class": "carried_same_layout", match: "near", old_item_id: "r:5:left:90",
      seeded: { verdict: "adjusted", ratified: [{ box: [10, 150, 300, 260], edges: { top: { snapped: true, at_crop_limit: false }, bottom: { snapped: false, at_crop_limit: false } } }], note: "mine" },
      delta: { "5:left": [-7, 6] }, prior: { verdict: "adjusted", rects: [], note: "mine", heads_not_shown: null } },
    "r:5:left:400": { "class": "layout_changed", match: "exact", old_item_id: "r:5:left:400", seeded: null, delta: null,
      prior: { verdict: "correct", rects: [], note: "", heads_not_shown: null } },
    "r:6:left:50": { "class": "carried_verdict", match: "exact", old_item_id: "r:6:left:50", seeded: { verdict: "not_a_verse" }, delta: null,
      prior: { verdict: "not_a_verse", rects: [], note: "", heads_not_shown: null } },
  },
};

test("seedPrior: seeds only ids with `seeded` and no state, tags carried_from, never overwrites", () => {
  const existing = { "r:6:left:50": { verdict: "correct", note: "already decided" } };
  const r = U.seedPrior(existing, PRIOR);
  assert.deepEqual(r.seeded, ["r:5:left:100"]);
  assert.equal(r.state["r:6:left:50"].verdict, "correct", "existing state untouched");
  assert.equal(r.state["r:6:left:50"].carried_from, undefined);
  assert.deepEqual(r.state["r:5:left:100"].carried_from, { set_sha16: "OLD", item_id: "r:5:left:90", "class": "carried_same_layout", match: "near" });
  assert.equal(r.state["r:5:left:100"].verdict, "adjusted");
  assert.equal(r.state["r:5:left:400"], undefined, "layout_changed seeds nothing");
  assert.deepEqual(existing, { "r:6:left:50": { verdict: "correct", note: "already decided" } }, "input not mutated");
  const again = U.seedPrior(r.state, PRIOR);
  assert.deepEqual(again.seeded, [], "second pass seeds nothing");
  assert.deepEqual(again.state, r.state);
});

test("missingSummary: a miss with a verdict but no cause counts as cause, not region; formatMissing words it", () => {
  const items = [
    { item_id: "r:1", item_kind: "verse" }, { item_id: "r:2", item_kind: "continuation_unanchored" },
    { item_id: "m:1", item_kind: "miss" }, { item_id: "m:2", item_kind: "miss" }, { item_id: "m:3", item_kind: "miss" },
    { item_id: "p:1", item_kind: "page" }, { item_id: "p:2", item_kind: "page" },
  ];
  const state = {
    "r:2": { verdict: "correct" },
    "m:1": { verdict: "region_drawn" }, "m:2": { verdict: "region_drawn", cause_verdict: "unsure" },
    "p:2": { heads_not_shown: 0 },
  };
  const s = U.missingSummary(items, state);
  assert.deepEqual(s, { region: { verdict: 1 }, miss: { cause: 2, region: 1 }, page: { count: 1 } });
  assert.equal(U.formatMissing(s), "region: 1 needs a verdict · miss: 2 need a cause, 1 needs a region · page: 1 needs a count");
  assert.equal(U.formatMissing({}), "all complete");
  assert.equal(U.needsBadgeText(items[2], state["m:1"]), "needs: cause");
  assert.equal(U.needsBadgeText(items[5], undefined), "needs: heads-not-shown count");
  assert.equal(U.needsBadgeText(items[3], state["m:2"]), "");
});

test("nextIncompleteId: first incomplete after the cursor in document order, wrapping, null when none", () => {
  const items = [{ item_id: "a", item_kind: "verse" }, { item_id: "b", item_kind: "verse" }, { item_id: "c", item_kind: "verse" }];
  const st = { b: { verdict: "correct" } };
  assert.equal(U.nextIncompleteId(items, st, null), "a");
  assert.equal(U.nextIncompleteId(items, st, "a"), "c");
  assert.equal(U.nextIncompleteId(items, st, "c"), "a", "wraps");
  assert.equal(U.nextIncompleteId(items, { a: { verdict: "correct" }, b: { verdict: "correct" }, c: { verdict: "correct" } }, "a"), null);
});

test("buildExportRow carries prior_class / prior_match; null when not carried by a prior", () => {
  const seeded = U.seedPrior({}, PRIOR).state["r:5:left:100"];
  const item = { item_id: "r:5:left:100", item_kind: "verse", file_page: 5, printed_page: -83, item_sha16: "x",
                 rects: [{ file_page: 5, col: "left", box: [10, 157, 300, 254] }] };
  const row = U.buildExportRow(item, seeded, consts);
  assert.equal(row.prior_class, "carried_same_layout");
  assert.equal(row.prior_match, "near");
  assert.equal(row.verdict, "adjusted");
  const plain = U.buildExportRow(item, { verdict: "correct", carried_from: { set_sha16: "O", item_id: "m:1", item_sha16: "s", ui_version: 2 } }, consts);
  assert.equal(plain.prior_class, null);
  assert.equal(plain.prior_match, null);
  assert.equal(U.buildExportRow(item, { verdict: "correct" }, consts).prior_class, null);
});

test("priorBadgeText: carried, adjusted-with-delta, and layout-changed wordings", () => {
  const a = U.priorBadgeText(PRIOR.map["r:5:left:100"], {});
  assert.equal(a[0], "carried from your earlier verdict (near)");
  assert.equal(a[1], "your box differs from the new detection: top Δ-7, bottom Δ+6 px");
  const l = U.priorBadgeText(PRIOR.map["r:5:left:400"], {});
  assert.equal(l.length, 1);
  assert.ok(l[0].startsWith("LAYOUT CHANGED — your earlier verdict correct is shown below; this card needs a fresh verdict"));
  assert.deepEqual(U.priorBadgeText(null, {}), []);
  const m = Object.assign({}, PRIOR.map["r:5:left:100"], { match: "from_miss", seeded: { verdict: "correct" } });
  assert.deepEqual(U.priorBadgeText(m, {}), ["carried from your earlier verdict (from your drawn region)"]);
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
