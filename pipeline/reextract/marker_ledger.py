"""Two-series marker ledger: reconciles the body-text superscript sentinel stream against the
printed footnote-letter stream, page by page, into one slot per aligned letter. Pure, no I/O --
the caller (marker_ledger_run.py) supplies the per-page series and writes the result.

Two deliverables live here:
  body_markers / project_legacy  -- sentinel bookkeeping for the body-text markdown.
  reconcile                      -- the two-series alignment + chain-walk ledger builder.

See marker_alphabet.py (ALPHABET, normalize, run, is_consecutive_run) and chain_fill.py
(classify, _gap) -- this module reuses both rather than re-deriving the alphabet rules.
"""
import re
from itertools import permutations

import marker_alphabet as MA
import chain_fill as CF

SENTINEL_RE = re.compile(r"⟦([^⟦⟧]{1,3})⟧")   # "observes⟦a⟧" -> group 1 == "a"


def body_markers(text):
    """Raw sentinel contents in reading order (kept raw: 'a', '?', '*', 'j', 'α' ... unnormalized)."""
    return [m.group(1) for m in SENTINEL_RE.finditer(text or "")]


def project_legacy(text, link_numbers=None):
    """Replace the k-th sentinel with '[^{link_numbers[k]}]' (or '[^{k+1}]' when link_numbers is
    None). Sentinel-free text is returned UNCHANGED (same object). Refuses (ValueError) to drop
    or invent a ref: length mismatch, or any None entry in link_numbers."""
    matches = list(SENTINEL_RE.finditer(text or ""))
    if not matches:
        return text
    n = len(matches)
    if link_numbers is None:
        numbers = list(range(1, n + 1))
    else:
        if len(link_numbers) != n:
            raise ValueError(
                f"project_legacy: link_numbers has {len(link_numbers)} entries but text has "
                f"{n} sentinel(s)")
        if any(x is None for x in link_numbers):
            raise ValueError("project_legacy: link_numbers must not contain None (refuses to drop a ref)")
        numbers = link_numbers
    out = []
    pos = 0
    for k, m in enumerate(matches):
        out.append(text[pos:m.start()])
        out.append(f"[^{numbers[k]}]")
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------------
# reconcile() internals
# ---------------------------------------------------------------------------

def _successor(letter):
    """Wrap-aware next letter in the 24-letter alphabet."""
    i = MA.index(letter)
    if i < 0:
        return None
    return MA.ALPHABET[(i + 1) % len(MA.ALPHABET)]


def _classify_raw(raw):
    """('letter', normalized) | ('wild', reason) via chain_fill, or (None, None) for a missing item."""
    if raw is None:
        return (None, None)
    return CF.classify(raw)


def _is_symbol(raw):
    k, r = _classify_raw(raw)
    return k == "wild" and r == "symbol"


def _letters_only(raw_series):
    out = []
    for m in raw_series:
        k, v = CF.classify(m)
        if k == "letter":
            out.append(v)
    return out


def _reorder_for_columns(raw_series, cols):
    """Section E: if a page's series was captured in >=2 physical columns whose NATURAL
    concatenation order is not a consecutive letter run, but some permutation of the column
    BLOCKS is, return that permuted raw series plus the natural (broken) letter sequence (used
    to synthesize suppressed-break info). Returns None when no reorder is indicated."""
    if not cols or len(cols) < 2 or sum(cols) != len(raw_series):
        return None
    natural_letters = _letters_only(raw_series)
    if len(natural_letters) < 2:
        return None
    if MA.is_consecutive_run(natural_letters):
        return None
    blocks, pos = [], 0
    for c in cols:
        blocks.append(raw_series[pos:pos + c])
        pos += c
    identity = tuple(range(len(blocks)))
    for perm in permutations(range(len(blocks))):
        if perm == identity:
            continue
        candidate = []
        for bi in perm:
            candidate += blocks[bi]
        cand_letters = _letters_only(candidate)
        if len(cand_letters) == len(natural_letters) and MA.is_consecutive_run(cand_letters):
            return {"reordered": candidate, "natural_letters": natural_letters}
    return None


def _natural_break_points(natural_letters):
    """Adjacent positions in a (non-consecutive) letter sequence that are not a valid successor
    step -- used only to populate suppressed_breaks for a column_order_suspect page."""
    out = []
    for k in range(1, len(natural_letters)):
        if _successor(natural_letters[k - 1]) != natural_letters[k]:
            out.append((natural_letters[k - 1], natural_letters[k]))
    return out


def _pair_score(a_raw, b_raw):
    """NW pairing score for one body item + one notes item (both present, not a gap)."""
    ak, av = _classify_raw(a_raw)
    bk, bv = _classify_raw(b_raw)
    if ak == "wild" and av == "symbol" and bk == "wild" and bv == "symbol":
        return 3
    if ak == "letter" and bk == "letter":
        return 3 if av == bv else -2
    return 1   # either side wild (non-symbol-pair case)


GAP = -4


def _align(body_items, notes_items):
    """Needleman-Wunsch alignment of two item lists (dicts with file_page/idx/raw). Deterministic
    traceback tie order: diagonal, then body-only, then notes-only. Returns a list of columns:
    {"kind": "match"|"body_only"|"notes_only", "body": item|None, "notes": item|None,
     "cross_page_link": bool, "gap_unpinned": bool}
    """
    n, m = len(body_items), len(notes_items)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + GAP
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] + GAP
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = dp[i - 1][j - 1] + _pair_score(body_items[i - 1]["raw"], notes_items[j - 1]["raw"])
            up = dp[i - 1][j] + GAP     # body-only (A-insert)
            left = dp[i][j - 1] + GAP   # notes-only (B-insert)
            dp[i][j] = max(diag, up, left)

    cols = []
    i, j = n, m
    while i > 0 or j > 0:
        diag = dp[i - 1][j - 1] + _pair_score(body_items[i - 1]["raw"], notes_items[j - 1]["raw"]) if i > 0 and j > 0 else None
        up = dp[i - 1][j] + GAP if i > 0 else None
        left = dp[i][j - 1] + GAP if j > 0 else None
        cur = dp[i][j]
        candidates = [v for v in (diag, up, left) if v is not None]
        best = max(candidates)
        # tie order: diagonal, body-only, notes-only
        n_ties = sum(1 for v in candidates if v == best)
        if diag is not None and diag == best:
            bi, ni = body_items[i - 1], notes_items[j - 1]
            cross = bi["file_page"] != ni["file_page"]
            cols.append({"kind": "match", "body": bi, "notes": ni,
                         "cross_page_link": cross, "gap_unpinned": False})
            i, j = i - 1, j - 1
        elif up is not None and up == best:
            cols.append({"kind": "body_only", "body": body_items[i - 1], "notes": None,
                         "cross_page_link": False, "gap_unpinned": n_ties > 1})
            i -= 1
        else:
            cols.append({"kind": "notes_only", "body": None, "notes": notes_items[j - 1],
                         "cross_page_link": False, "gap_unpinned": n_ties > 1})
            j -= 1
    cols.reverse()
    return cols


def _page_items(series, file_page):
    if series is None:
        return None
    return [{"file_page": file_page, "idx": i, "raw": m} for i, m in enumerate(series)]


def reconcile(pages, resets=None, anomalies=None, prev_last=None):
    resets = resets or {}
    anomalies = anomalies or {}

    page_flags = {}

    def _flag_page(fp, flag):
        page_flags.setdefault(fp, [])
        if flag not in page_flags[fp]:
            page_flags[fp].append(flag)

    # --- Section E pre-pass: column-order correction + flagging, per page, independently
    # per series. Also collects synthetic suppressed-break info keyed by file_page.
    suppressed_break_info = {}   # file_page -> list of (from_letter, to_letter)
    prepared = []   # list of dicts: file_page, body(list|None), notes(list|None)
    for p in pages:
        fp = p["file_page"]
        body = p.get("body")
        notes = p.get("notes")
        body_cols = p.get("body_cols")
        notes_cols = p.get("notes_cols")
        if body is not None and body_cols:
            fix = _reorder_for_columns(body, body_cols)
            if fix:
                _flag_page(fp, "column_order_suspect")
                suppressed_break_info.setdefault(fp, []).extend(_natural_break_points(fix["natural_letters"]))
                body = fix["reordered"]
        if notes is not None and notes_cols:
            fix = _reorder_for_columns(notes, notes_cols)
            if fix:
                _flag_page(fp, "column_order_suspect")
                suppressed_break_info.setdefault(fp, []).extend(_natural_break_points(fix["natural_letters"]))
                notes = fix["reordered"]
        prepared.append({"file_page": fp, "body": body, "notes": notes})

    # --- empty_series_with_counterpart page flag
    for p in prepared:
        fp = p["file_page"]
        body, notes = p["body"], p["notes"]
        if body is not None and notes is not None:
            if (body == [] and notes != []) or (notes == [] and body != []):
                _flag_page(fp, "empty_series_with_counterpart")

    # --- Section B: build the global column sequence (NW-aligned groups + single-sided runs)
    all_cols = []   # each: {"file_page", "body": item|None, "notes": item|None, flags: set-ish}
    idx = 0
    while idx < len(prepared):
        p = prepared[idx]
        if p["body"] is not None and p["notes"] is not None:
            j = idx
            group = []
            while j < len(prepared) and prepared[j]["body"] is not None and prepared[j]["notes"] is not None:
                group.append(prepared[j])
                j += 1
            body_items = []
            notes_items = []
            for gp in group:
                body_items += _page_items(gp["body"], gp["file_page"])
                notes_items += _page_items(gp["notes"], gp["file_page"])
            for col in _align(body_items, notes_items):
                fp = col["body"]["file_page"] if col["body"] is not None else col["notes"]["file_page"]
                flags = []
                if col["cross_page_link"]:
                    flags.append("cross_page_link")
                if col["gap_unpinned"]:
                    flags.append("gap_unpinned")
                all_cols.append({"file_page": fp, "body": col["body"], "notes": col["notes"],
                                  "init_flags": flags})
            idx = j
        else:
            if p["body"] is not None:
                for item in _page_items(p["body"], p["file_page"]):
                    all_cols.append({"file_page": p["file_page"], "body": item, "notes": None,
                                      "init_flags": []})
            if p["notes"] is not None:
                for item in _page_items(p["notes"], p["file_page"]):
                    all_cols.append({"file_page": p["file_page"], "body": None, "notes": item,
                                      "init_flags": []})
            idx += 1

    # --- Pass 1: per-column seen/read/basic-candidate (no cross-slot chain fill yet)
    slots = []
    for col in all_cols:
        body_item, notes_item = col["body"], col["notes"]
        fp = col["file_page"]
        body_present = body_item is not None
        notes_present = notes_item is not None
        # Was the SERIES captured for this page at all?
        page = next(pp for pp in prepared if pp["file_page"] == fp)
        body_series_captured = page["body"] is not None
        notes_series_captured = page["notes"] is not None

        seen_in_body = True if body_present else (False if body_series_captured else None)
        seen_in_notes = True if notes_present else (False if notes_series_captured else None)
        body_read = body_item["raw"] if body_present else None
        notes_read = notes_item["raw"] if notes_present else None
        body_idx = body_item["idx"] if body_present else None
        notes_idx = notes_item["idx"] if notes_present else None

        bk, bv = _classify_raw(body_read)
        nk, nv = _classify_raw(notes_read)

        flags = list(col["init_flags"])
        is_outside = (bk == "wild" and bv == "symbol") or (nk == "wild" and nv == "symbol")

        letter = None
        filled_from = None
        letter_basis = None
        link_status = "open"
        reads_disagree = False

        if is_outside:
            # symbol marker column -- never a letter-chain slot
            if seen_in_body in (True,) and seen_in_notes in (True,):
                link_status = "linked"
            elif seen_in_body is None or seen_in_notes is None:
                link_status = "open"
            else:
                link_status = "linked" if (seen_in_body and seen_in_notes) else "open"
        else:
            both_seen_true = (seen_in_body is True and seen_in_notes is True)
            if both_seen_true and bk == "letter" and nk == "letter":
                if bv == nv:
                    letter, letter_basis, filled_from = bv, "two_reads_agree", None
                    link_status = "linked"
                else:
                    letter = None
                    reads_disagree = True
                    flags.append("reads_disagree")
                    link_status = "disputed"
            elif both_seen_true and (bk == "letter") != (nk == "letter"):
                # exactly one side is a real letter, the other is wild (present but unread)
                if bk == "letter":
                    letter, filled_from = bv, "body"
                else:
                    letter, filled_from = nv, "notes"
                letter_basis = "one_read"
                link_status = "linked"
            elif both_seen_true:
                # both wild (neither read a letter) -- candidate for two-sided chain fill (pass 2)
                link_status = "linked"
            elif (seen_in_body is True and seen_in_notes is False) or (seen_in_notes is True and seen_in_body is False):
                # one side present, the other a real gap in a captured series
                if bk == "letter":
                    letter, filled_from, letter_basis = bv, "body", "one_read"
                    link_status = "filled"
                elif nk == "letter":
                    letter, filled_from, letter_basis = nv, "notes", "one_read"
                    link_status = "filled"
                else:
                    link_status = "open"
            else:
                # at least one side's SERIES was never captured (seen None)
                if bk == "letter":
                    letter, filled_from, letter_basis = bv, "body", "one_read"
                elif nk == "letter":
                    letter, filled_from, letter_basis = nv, "notes", "one_read"
                link_status = "open"
                if seen_in_body is None:
                    flags.append("body_not_captured")
                if seen_in_notes is None:
                    flags.append("notes_not_captured")

        slots.append({
            "file_page": fp, "body_idx": body_idx, "notes_idx": notes_idx,
            "body_read": body_read, "notes_read": notes_read,
            "seen_in_body": seen_in_body, "seen_in_notes": seen_in_notes,
            "letter": letter, "filled_from": filled_from, "letter_basis": letter_basis,
            "link_status": link_status, "flags": flags, "is_outside": is_outside,
            "reads_disagree": reads_disagree,
        })

    # --- Pass 2: two-sided chain fill over runs of unresolved, non-outside, non-disagree slots
    i = 0
    N = len(slots)
    while i < N:
        s = slots[i]
        if s["is_outside"] or s["reads_disagree"] or s["letter"] is not None:
            i += 1
            continue
        j = i
        while j < N and not slots[j]["is_outside"] and not slots[j]["reads_disagree"] and slots[j]["letter"] is None:
            j += 1
        n_run = j - i
        left_letter = slots[i - 1]["letter"] if i > 0 else None
        if left_letter is None and i == 0:
            left_letter = MA.normalize(prev_last) if prev_last else None
        right_letter = slots[j]["letter"] if j < N else None
        if left_letter and right_letter:
            gap = CF._gap(left_letter, right_letter)
            if gap == n_run:
                fill = MA.run(left_letter, n_run + 1)[1:]
                for k in range(n_run):
                    slots[i + k]["letter"] = fill[k]
                    slots[i + k]["filled_from"] = "chain"
                    slots[i + k]["letter_basis"] = "chain"
        i = j

    # --- Pass 3: chain walk (section D), sequential over the resolved slots in final order.
    # `expected` is the letter the walk predicts for the NEXT slot it compares -- it is seeded
    # one step past prev_last (prev_last itself was already confirmed, outside this document).
    expected = _successor(MA.normalize(prev_last)) if prev_last else None
    anchor_kind = "anchored" if expected else "unknown"
    per_page_slot_ix = {}
    breaks = []
    suppressed_breaks = []
    anomaly_candidates = []

    def _advance_on_mismatch(expected_here, candidate, basis):
        """After a break, continue counting positions rather than trust a lone unverified read
        (letter_basis == 'one_read'); but when two independent reads agree (or a two-sided chain
        fill resolved it), that confirmed letter re-syncs the walk (e.g. a genuine skip-letter
        page: w,x,[skip y],z,a,b resumes counting from the confirmed 'z', not from the ghost 'y')."""
        return _successor(expected_here) if basis == "one_read" else _successor(candidate)

    for s in slots:
        fp = s["file_page"]
        slot_ix = per_page_slot_ix.get(fp, 0)
        per_page_slot_ix[fp] = slot_ix + 1
        s["slot"] = slot_ix

        if s["is_outside"]:
            s["chain"] = "outside"
            s["chain_expects"] = None
            continue

        reset_list = resets.get(fp)
        is_reset = reset_list is not None and slot_ix in reset_list
        reset_complete = fp in resets
        anomaly_entry = anomalies.get(fp)
        anomaly_observed = anomaly_entry.get("observed") if anomaly_entry else None

        candidate = s["letter"]

        if anomaly_entry is not None and isinstance(anomaly_observed, list) and slot_ix < len(anomaly_observed):
            expected_here = MA.normalize(anomaly_observed[slot_ix])
            s["chain_expects"] = expected_here
            s["chain"] = "anchored"
            s["flags"].append("anomaly_applied")
            # the human table IS the ground truth for this slot; it never disputes a read.
            expected = _successor(expected_here)
            anchor_kind = "anchored"
            continue

        if is_reset:
            expected_here = "a"
            s["chain_expects"] = expected_here
            s["chain"] = "anchored"
            s["flags"].append("reset_anchor")
            if candidate is None:
                # no usable read to contradict the (externally verified) reset -- it wins outright.
                s["letter"], s["filled_from"], s["letter_basis"] = "a", "chain", "chain"
            elif candidate != expected_here:
                orig_basis = s["letter_basis"]
                if orig_basis == "one_read":
                    s["letter"], s["filled_from"], s["letter_basis"] = None, None, None
                    s["link_status"] = "disputed"
                    s["flags"].append("reader_vs_chain")
                # else: two_reads_agree conflicting with an explicit reset -- letter stands,
                # flagged only via the break record below (never an anomaly_candidate: the
                # reset is a verified fact, not an unlisted-page chain expectation).
                breaks.append({"file_page": fp, "slot": slot_ix, "observed": candidate,
                                "expected": expected_here, "reason": "reset_conflict"})
                s["chain"] = "break"
                expected = _advance_on_mismatch(expected_here, candidate, orig_basis)
                anchor_kind = "anchored"
                continue
            expected = _successor("a")
            anchor_kind = "anchored"
            continue

        expected_here = expected
        s["chain_expects"] = expected_here

        if s["reads_disagree"]:
            s["chain"] = anchor_kind if expected_here is not None else "unknown"
            if expected_here is not None:
                expected = _successor(expected_here)
            continue

        if expected_here is None:
            if candidate is not None:
                s["chain"] = "internal"
                anchor_kind = "internal"
                expected = _successor(candidate)
            else:
                s["chain"] = "unknown"
            continue

        if candidate is None:
            s["chain"] = anchor_kind
            expected = _successor(expected_here)
            continue

        if candidate == expected_here:
            s["chain"] = anchor_kind
            expected = _successor(candidate)
            continue

        # --- mismatch: break, possible_reset, or dispute
        if candidate == "a" and not reset_complete:
            s["flags"].append("possible_reset")
            s["chain"] = "anchored"
            expected = _successor("a")
            anchor_kind = "anchored"
            continue

        # a genuine break
        orig_basis = s["letter_basis"]
        if orig_basis == "one_read":
            s["letter"] = None
            s["filled_from"] = None
            s["letter_basis"] = None
            s["link_status"] = "disputed"
            s["flags"].append("reader_vs_chain")
            s["chain"] = "break"
            breaks.append({"file_page": fp, "slot": slot_ix, "observed": candidate,
                            "expected": expected_here, "reason": "reader_vs_chain"})
        else:
            # two_reads_agree (or chain-filled) conflicting with chain: letter stands
            s["chain"] = "break"
            breaks.append({"file_page": fp, "slot": slot_ix, "observed": candidate,
                            "expected": expected_here, "reason": "chain_mismatch"})
            if anomaly_entry is None:
                anomaly_candidates.append({"file_page": fp, "slot": slot_ix,
                                            "observed": candidate, "expected": expected_here})
        expected = _advance_on_mismatch(expected_here, candidate, orig_basis)

    # --- column_order_suspect pages: move their natural-order breaks into suppressed_breaks,
    # scrub real breaks/anomaly_candidates recorded for them (the corrected order already
    # produced a clean walk above, so normally there is nothing to scrub; this also covers the
    # defensive case where some residual break slipped through).
    suspect_pages = {fp for fp, flags in page_flags.items() if "column_order_suspect" in flags}
    if suspect_pages:
        kept_breaks = []
        for b in breaks:
            if b["file_page"] in suspect_pages:
                suppressed_breaks.append(b)
            else:
                kept_breaks.append(b)
        breaks = kept_breaks
        anomaly_candidates = [a for a in anomaly_candidates if a["file_page"] not in suspect_pages]
    for fp, pairs in suppressed_break_info.items():
        for (frm, to) in pairs:
            suppressed_breaks.append({"file_page": fp, "note": "column_order_natural_break",
                                       "from": frm, "to": to})

    # --- assemble final slot records + summary
    out_slots = []
    by_link_status, by_filled_from, by_chain = {}, {}, {}
    for pos, s in enumerate(slots):
        rec = {
            "file_page": s["file_page"], "slot": s["slot"], "series_pos": pos,
            "body_idx": s["body_idx"], "notes_idx": s["notes_idx"],
            "body_read": s["body_read"], "notes_read": s["notes_read"],
            "seen_in_body": s["seen_in_body"], "seen_in_notes": s["seen_in_notes"],
            "letter": s["letter"], "filled_from": s["filled_from"], "letter_basis": s["letter_basis"],
            "link_status": s["link_status"], "chain": s["chain"], "chain_expects": s["chain_expects"],
            "flags": s["flags"], "tier": "best_effort",
        }
        out_slots.append(rec)
        by_link_status[rec["link_status"]] = by_link_status.get(rec["link_status"], 0) + 1
        by_filled_from[str(rec["filled_from"])] = by_filled_from.get(str(rec["filled_from"]), 0) + 1
        by_chain[rec["chain"]] = by_chain.get(rec["chain"], 0) + 1

    return {
        "slots": out_slots,
        "breaks": breaks,
        "suppressed_breaks": suppressed_breaks,
        "anomaly_candidates": anomaly_candidates,
        "page_flags": page_flags,
        "summary": {
            "by_link_status": by_link_status,
            "by_filled_from": by_filled_from,
            "by_chain": by_chain,
            "n_slots": len(out_slots),
        },
    }
