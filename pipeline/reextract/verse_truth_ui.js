/* verse_truth_ui.js -- PURE logic for the verse-box truth console UI 2 (no DOM, no globals).
 * Inlined verbatim into index.html by render_verse_truth.py --html-only (its sha256 goes into the
 * ui config hash); unit-tested by test_verse_truth_ui.mjs under node.
 *
 * Conventions: a box is [x0, y0, x1, y1] page-absolute native px; an edge is "top" (y0) or
 * "bottom" (y1); targets are sorted integer y values; cropRange is [lo, hi] (inclusive limits an
 * edge may take). x is never edited. */

function snap(value, targets, lo, hi) {
  // Nearest target inside [lo, hi]; tie -> the LOWER value. null when no target is in range.
  var best = null;
  for (var i = 0; i < targets.length; i++) {
    var t = targets[i];
    if (t < lo || t > hi) continue;
    if (best === null) { best = t; continue; }
    var dt = Math.abs(t - value), db = Math.abs(best - value);
    if (dt < db || (dt === db && t < best)) best = t;
  }
  return best;
}

function clampEdge(value, lo, hi) {
  return Math.min(Math.max(value, lo), hi);
}

function linesMoved(detected, ratified, targets) {
  // Signed count (+ = toward larger y): number of targets STRICTLY between the detected and the
  // ratified value, plus 1 if the ratified value is itself a target (and differs from detected).
  // 0 if unchanged. `targets` is the full snap list for that page/col/edge-type (not crop-limited).
  if (detected === ratified) return 0;
  var a = Math.min(detected, ratified), b = Math.max(detected, ratified);
  var seen = {}, n = 0;
  for (var i = 0; i < targets.length; i++) {
    var t = targets[i];
    if (seen[t]) continue;
    seen[t] = true;
    if (t > a && t < b) n++;
  }
  if (seen[ratified]) n++;
  return ratified > detected ? n : -n;
}

function applyDrag(box, edge, y, targets, cropRange, noSnap) {
  // Move one horizontal edge of `box` toward y. Returns {rect, edgeInfo:{snapped, at_crop_limit}}.
  // Invariants: y0 < y1 always (clamped to the nearest valid value/target), edge inside cropRange.
  var lo = cropRange[0], hi = cropRange[1];
  var idx = edge === "top" ? 1 : 3;
  var validLo = edge === "top" ? lo : box[1] + 1;
  var validHi = edge === "top" ? box[3] - 1 : hi;
  if (validLo > validHi) {
    return { rect: box.slice(), edgeInfo: { snapped: false, at_crop_limit: false } };
  }
  var v = clampEdge(Math.round(y), validLo, validHi);
  var snapped = false;
  if (!noSnap) {
    var s = snap(v, targets, validLo, validHi);
    if (s !== null) { v = s; snapped = true; }
  }
  var out = box.slice();
  out[idx] = v;
  return { rect: out, edgeInfo: { snapped: snapped, at_crop_limit: (v === lo || v === hi) } };
}

function newRect(colBox, yA, yB, tops, bottoms, range, noSnap) {
  // Draw a fresh rect in a column: x = the column extent, y from two raw mouse y values.
  // Returns {rect, edges:{top,bottom}} or null when it collapses (y0 >= y1 after snapping).
  var lo = range[0], hi = range[1];
  var a = Math.min(yA, yB), b = Math.max(yA, yB);
  var top = clampEdge(Math.round(a), lo, hi), bot = clampEdge(Math.round(b), lo, hi);
  var sTop = false, sBot = false;
  if (!noSnap) {
    var t = snap(top, tops, lo, hi); if (t !== null) { top = t; sTop = true; }
    var u = snap(bot, bottoms, lo, hi); if (u !== null) { bot = u; sBot = true; }
  }
  if (bot <= top) return null;
  return {
    rect: [Math.round(colBox[0]), top, Math.round(colBox[2]), bot],
    edges: {
      top: { snapped: sTop, at_crop_limit: (top === lo || top === hi) },
      bottom: { snapped: sBot, at_crop_limit: (bot === lo || bot === hi) },
    },
  };
}

function _freshEdges() {
  return { top: { snapped: false, at_crop_limit: false }, bottom: { snapped: false, at_crop_limit: false } };
}

function initialRatified(item) {
  // as_ratified initialised = as_detected (copies).
  return item.rects.map(function (r) { return { box: r.box.slice(), edges: _freshEdges() }; });
}

// Column under a page point. A miss item carrying col_split {slope, c0} (the printed rule, slanted:
// centre(y) = slope*y + c0) splits on that line at the pointer's page-y; otherwise the geometry xdiv.
function pageColumn(item, x, y) {
  if (item.col_split) return x < item.col_split.slope * y + item.col_split.c0 ? "left" : "right";
  return item.xdiv != null ? (x < item.xdiv ? "left" : "right") : null;
}

function _copy(o) { return JSON.parse(JSON.stringify(o)); }

function _boxesEqual(a, b) {
  return a.length === b.length && a.every(function (v, i) { return v === b[i]; });
}

function _ratifiedDiffers(item, st) {
  if (!st.ratified) return false;
  return st.ratified.some(function (r, i) { return !_boxesEqual(r.box, item.rects[i].box); });
}

function verdictCoupling(state, event) {
  // Code-owned verdict <-> geometry coupling. Pure: returns {state: <new>, needsConfirm: bool}.
  // event.item is the ITEMS entry. Events:
  //   {type:"choose", value, item, confirmed}  region: correct|adjusted|not_a_verse; miss: region_drawn|not_a_verse
  //   {type:"drag", item, rectIdx, rect, edge, edgeInfo}   region edge drag -> verdict "adjusted"
  //   {type:"draw", item, rect:{col,file_page,box,edges}}  miss: add/replace the col's drawn rect -> "region_drawn"
  //   {type:"mdrag", item, rectIdx, rect, edge, edgeInfo}  miss: handle drag on a drawn rect
  //   {type:"clear", item, rectIdx}                        miss: remove a drawn rect
  var st = _copy(state || {});
  var item = event.item;
  var isMiss = item.item_kind === "miss";
  if (event.type === "choose") {
    var val = event.value;
    if (isMiss) {
      if (val === "not_a_verse") st.ratified = [];
      else if (!st.ratified) st.ratified = [];
      st.verdict = val;
      return { state: st, needsConfirm: false };
    }
    if (val === "correct") {
      if (_ratifiedDiffers(item, st) && !event.confirmed) return { state: _copy(state || {}), needsConfirm: true };
      st.ratified = initialRatified(item);
      st.verdict = "correct";
    } else if (val === "not_a_verse") {
      st.ratified = null;
      st.verdict = "not_a_verse";
    } else {
      if (!st.ratified) st.ratified = initialRatified(item);
      st.verdict = val;
    }
    return { state: st, needsConfirm: false };
  }
  if (event.type === "drag") {
    if (!st.ratified) st.ratified = initialRatified(item);
    var r = st.ratified[event.rectIdx];
    r.box = event.rect.slice();
    r.edges[event.edge] = { snapped: !!event.edgeInfo.snapped, at_crop_limit: !!event.edgeInfo.at_crop_limit };
    st.verdict = "adjusted";
    return { state: st, needsConfirm: false };
  }
  if (event.type === "draw") {
    st.ratified = (st.ratified || []).filter(function (x) { return x.col !== event.rect.col; });
    st.ratified.push(_copy(event.rect));
    st.verdict = "region_drawn";
    return { state: st, needsConfirm: false };
  }
  if (event.type === "mdrag") {
    var d = st.ratified[event.rectIdx];
    d.box = event.rect.slice();
    d.edges[event.edge] = { snapped: !!event.edgeInfo.snapped, at_crop_limit: !!event.edgeInfo.at_crop_limit };
    st.verdict = "region_drawn";
    return { state: st, needsConfirm: false };
  }
  if (event.type === "clear") {
    st.ratified = (st.ratified || []).filter(function (_, i) { return i !== event.rectIdx; });
    return { state: st, needsConfirm: false };
  }
  throw new Error("verdictCoupling: unknown event type " + event.type);
}

function isRated(item, st) {
  if (!st) return false;
  if (item.item_kind === "page") return st.heads_not_shown !== undefined && st.heads_not_shown !== null && st.heads_not_shown !== "";
  if (item.item_kind === "miss") return !!st.verdict && !!st.cause_verdict;
  return !!st.verdict;
}

function _hasDiagnosis(st) {
  return !!st && (!!st.cause_verdict || (typeof st.note === "string" && st.note.trim() !== ""));
}

function carryForward(newItems, oldItems, carry) {
  // Pure. Copies cause_verdict + note from oldItems[old_item_id] into newItems[new_item_id] for each
  // mapped pair. Never overwrites a new item that already has a cause_verdict / non-empty note (or
  // already carries). Never touches any other field. Returns {items, carried:[ids], skipped:[{id, reason}]}.
  var items = _copy(newItems || {});
  var olds = oldItems || {};
  var carried = [], skipped = [];
  Object.keys(carry.map).forEach(function (nid) {
    var ent = carry.map[nid];
    var old = olds[ent.old_item_id];
    if (!_hasDiagnosis(old)) { skipped.push({ id: nid, reason: "no_old_state" }); return; }
    var cur = items[nid];
    if (_hasDiagnosis(cur) || (cur && cur.carried_from)) { skipped.push({ id: nid, reason: "new_already_set" }); return; }
    var st = cur || (items[nid] = {});
    if (old.cause_verdict) st.cause_verdict = old.cause_verdict;
    if (typeof old.note === "string") st.note = old.note;
    st.carried_from = { set_sha16: carry.from_set_sha16, item_id: ent.old_item_id, item_sha16: ent.old_item_sha16, ui_version: 2 };
    carried.push(nid);
  });
  return { items: items, carried: carried, skipped: skipped };
}

function rowsToOldItems(rows, fromSet) {
  // Import path: export rows -> {item_id: {cause_verdict, note}}; rows from another set are refused.
  var items = {}, refused = 0;
  (rows || []).forEach(function (r) {
    if (!r || r.set_sha16 !== fromSet) { refused++; return; }
    items[r.item_id] = { cause_verdict: r.cause_verdict || undefined, note: r.note || "" };
  });
  return { items: items, refused: refused };
}

function seedPrior(state, prior) {
  // Pure. For each PRIOR.map[id] with `seeded` and NO existing state for id (absent or empty),
  // state[id] = copy of seeded + carried_from {set_sha16, item_id, class, match}. Existing state is
  // NEVER overwritten. Returns {state, seeded:[ids]}.
  var out = _copy(state || {});
  var seeded = [];
  if (!prior || !prior.map) return { state: out, seeded: seeded };
  Object.keys(prior.map).forEach(function (id) {
    var ent = prior.map[id];
    if (!ent || !ent.seeded) return;
    var cur = out[id];
    if (cur && Object.keys(cur).length > 0) return;
    var st = _copy(ent.seeded);
    st.carried_from = { set_sha16: prior.from_set_sha16, item_id: ent.old_item_id, "class": ent["class"], match: ent.match };
    out[id] = st;
    seeded.push(id);
  });
  return { state: out, seeded: seeded };
}

function missingFields(item, st) {
  // The fields a card still needs: region -> ["verdict"]; miss -> ["region","cause"]; page -> ["count"].
  st = st || {};
  var k = item.item_kind, out = [];
  if (k === "page") {
    if (st.heads_not_shown === undefined || st.heads_not_shown === null || st.heads_not_shown === "") out.push("count");
  } else if (k === "miss") {
    if (!st.verdict) out.push("region");
    if (!st.cause_verdict) out.push("cause");
  } else if (!st.verdict) out.push("verdict");
  return out;
}

function missingSummary(items, state) {
  // {kind: {field: n}} with kind in region|miss|page (every region kind counts as "region").
  var out = {};
  (items || []).forEach(function (it) {
    var kind = it.item_kind === "miss" ? "miss" : (it.item_kind === "page" ? "page" : "region");
    missingFields(it, (state || {})[it.item_id]).forEach(function (f) {
      out[kind] = out[kind] || {};
      out[kind][f] = (out[kind][f] || 0) + 1;
    });
  });
  return out;
}

function formatMissing(summary) {
  // "region: 3 need a verdict · miss: 2 need a cause, 1 needs a region · page: 18 need a count"
  var parts = [];
  ["region", "miss", "page"].forEach(function (kind) {
    var fs = summary[kind];
    if (!fs) return;
    var bits = Object.keys(fs).sort().map(function (f) {
      return fs[f] + (fs[f] === 1 ? " needs a " : " need a ") + f;
    });
    parts.push(kind + ": " + bits.join(", "));
  });
  return parts.length ? parts.join(" · ") : "all complete";
}

function needsBadgeText(item, st) {
  var f = missingFields(item, st).map(function (x) { return x === "count" ? "heads-not-shown count" : x; });
  return f.length ? "needs: " + f.join(", ") : "";
}

function nextIncompleteId(orderedItems, state, cursorId) {
  // First incomplete card strictly after cursorId in document order, wrapping; null when none.
  var n = orderedItems.length, start = 0;
  if (cursorId) for (var i = 0; i < n; i++) if (orderedItems[i].item_id === cursorId) { start = i + 1; break; }
  for (var j = 0; j < n; j++) {
    var it = orderedItems[(start + j) % n];
    if (missingFields(it, (state || {})[it.item_id]).length) return it.item_id;
  }
  return null;
}

var _MATCH_TXT = { exact: "exact", near: "near", near_old_verse_unread: "near; your earlier card had no verse number read", from_miss: "from your drawn region", page: "page answer" };
function priorBadgeText(ent, st) {
  // Badge lines for a PRIOR.map entry given the current card state. [] when nothing to say.
  var out = [];
  if (!ent) return out;
  var v = (ent.prior && ent.prior.verdict) || "";
  if (ent["class"] === "layout_changed") {
    out.push("LAYOUT CHANGED — your earlier verdict " + (ent.prior.heads_not_shown != null ? ent.prior.heads_not_shown : v) +
             " is shown below; this card needs a fresh verdict");
    return out;
  }
  if (ent["class"] === "carried_same_layout" || ent["class"] === "carried_verdict") {
    out.push("carried from your earlier verdict (" + (_MATCH_TXT[ent.match] || ent.match) + ")");
    if (ent.seeded && ent.seeded.verdict === "adjusted" && ent.delta) {
      var keys = Object.keys(ent.delta);
      out.push("your box differs from the new detection: " + keys.map(function (k) {
        var d = ent.delta[k], sg = function (x) { return (x > 0 ? "+" : "") + x; };
        return (keys.length > 1 ? k + " " : "") + "top Δ" + sg(d[0]) + ", bottom Δ" + sg(d[1]);
      }).join("; ") + " px");
    }
  }
  return out;
}

function _intBox(b) { return b.map(function (v) { return Math.round(v); }); }

function _snapList(consts, fp, col, which) {
  var p = consts.SNAP && consts.SNAP[String(fp)];
  var c = p && p[col];
  return (c && c[which]) || [];
}

function buildExportRow(item, state, consts) {
  var st = state || {};
  var kind = item.item_kind;
  var row = {
    item_id: item.item_id, item_kind: kind, file_page: item.file_page, printed_page: item.printed_page,
    verdict: "unrated", cause_verdict: null, as_detected: null, as_ratified: null,
    printed_number_as_seen: null, note: st.note || "", heads_not_shown: null,
    adjusted_without_change: false, correct_with_change: false,
    item_sha16: item.item_sha16, set_sha16: consts.set_sha16, ui_config_hash: consts.ui_config_hash,
    run_config_hash: consts.run_config_hash, ui_version: 2, door: "human-verse-box-truth",
    session_freshness: "in-context-WARN", exported_utc: consts.exported_utc,
    carried_from: st.carried_from || null, edited_after_carry: !!st.edited_after_carry,
    prior_class: (st.carried_from && st.carried_from["class"]) || null,
    prior_match: (st.carried_from && st.carried_from.match) || null,
  };
  if (kind === "page") {
    var raw = st.heads_not_shown;
    if (raw === undefined || raw === null || raw === "") { row.heads_not_shown = null; row.verdict = "unrated"; }
    else {
      var n = Number(raw);
      var isInt = Number.isInteger(n) && n >= 0 && String(raw).trim() === String(n);
      row.heads_not_shown = isInt ? n : "invalid";
      row.verdict = "answered";
    }
    return row;
  }
  if (kind === "miss") {
    row.cause_verdict = st.cause_verdict || null;
    var mv = st.verdict;
    if (!mv) return row;
    row.verdict = mv;
    if (mv === "region_drawn") {
      var drawn = st.ratified || [];
      var bad = drawn.length === 0 || drawn.some(function (r) { return !(r.box[1] < r.box[3]); });
      if (bad) row.verdict = "invalid";
      row.as_ratified = drawn.map(function (r) {
        return {
          file_page: item.file_page, col: r.col, box: _intBox(r.box),
          edges: {
            top: { snapped: !!r.edges.top.snapped, lines_moved: null, at_crop_limit: !!r.edges.top.at_crop_limit },
            bottom: { snapped: !!r.edges.bottom.snapped, lines_moved: null, at_crop_limit: !!r.edges.bottom.at_crop_limit },
          },
        };
      });
    }
    return row;
  }
  // region kinds
  row.as_detected = item.rects.map(function (r) { return { file_page: r.file_page, col: r.col, box: _intBox(r.box) }; });
  if (kind === "verse") row.printed_number_as_seen = st.printed_number_as_seen || "";
  var v = st.verdict;
  if (!v) return row;
  row.verdict = v;
  if (v === "not_a_verse") return row;
  var rat = st.ratified || initialRatified(item);
  var anyMoved = false, anyDiff = false, invalid = false;
  row.as_ratified = rat.map(function (r, i) {
    var det = item.rects[i];
    var tl = linesMoved(det.box[1], r.box[1], _snapList(consts, det.file_page, det.col, "tops"));
    var bl = linesMoved(det.box[3], r.box[3], _snapList(consts, det.file_page, det.col, "bottoms"));
    if (tl !== 0 || bl !== 0) anyMoved = true;
    if (!_boxesEqual(_intBox(r.box), _intBox(det.box))) anyDiff = true;
    if (!(r.box[1] < r.box[3])) invalid = true;
    return {
      file_page: det.file_page, col: det.col, box: _intBox(r.box),
      edges: {
        top: { snapped: !!r.edges.top.snapped, lines_moved: tl, at_crop_limit: !!r.edges.top.at_crop_limit },
        bottom: { snapped: !!r.edges.bottom.snapped, lines_moved: bl, at_crop_limit: !!r.edges.bottom.at_crop_limit },
      },
    };
  });
  if (invalid) row.verdict = "invalid";
  row.adjusted_without_change = (v === "adjusted") && !anyMoved && !anyDiff;
  row.correct_with_change = (v === "correct") && anyDiff;
  return row;
}

if (typeof module !== "undefined") {
  module.exports = {
    pageColumn: pageColumn, snap: snap, clampEdge: clampEdge, linesMoved: linesMoved, applyDrag: applyDrag, newRect: newRect,
    initialRatified: initialRatified, verdictCoupling: verdictCoupling, isRated: isRated,
    buildExportRow: buildExportRow, carryForward: carryForward, rowsToOldItems: rowsToOldItems,
    seedPrior: seedPrior, missingFields: missingFields, missingSummary: missingSummary, formatMissing: formatMissing,
    needsBadgeText: needsBadgeText, nextIncompleteId: nextIncompleteId, priorBadgeText: priorBadgeText,
  };
}
