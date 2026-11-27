# -*- coding: utf-8 -*-
u"""OFFLINE line localizer: which printed line carries each span's Hebrew type?  NO MODEL CALLS.

Lane B / session 50612c81.  ALL PAGE NUMBERS ARE FILE pages (printed = file - 88).

Runs the method registered in LOCK_line_localizer_20261126.json (digest 783c1ff204dbbd8d) over
the 74-span cut, scores the 6 spans that carry line-placement truth, and writes a census of the
other 68 as CLAIMS.  Every parameter is read FROM the lock -- not re-declared here -- so the run
cannot quietly use a number the prediction record does not contain.

The finder is the Tesseract layer's own Hebrew codepoints.  The ink channel has two named roles and
neither is finding: it corroborates a candidate's own pixels, and it reports whether the stored
box's line is entirely covered by confident Latin.

  --score   score S1/S1b/S2 and print the strata (default)
  --census  also write the 74-span census JSON
"""
import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score45_run as S

AUD = S.A
VOL = Path("C:/Users/cnogr/git/dr-voluminous/commentary/volume1")
LOCK_NAME = "LOCK_line_localizer_20261126.json"
LOCK_SHA = "783c1ff204dbbd8d"
OUT_NAME = "LOCALIZER_lines_20261126.json"


def jl(p):
    return json.loads(io.open(str(p), encoding="utf-8").read())


def load_lock():
    body = jl(AUD / LOCK_NAME)
    probe = dict(body)
    probe.pop("self_sha16")
    got = hashlib.sha256(S.canon(probe).encode("utf-8")).hexdigest()[:16]
    if got != body["self_sha16"] or got != LOCK_SHA:
        raise SystemExit("REFUSED: lock digest is %s, body says %s, this run expects %s.  The "
                         "prediction record has moved; a run under a changed lock is not the run "
                         "that was predicted." % (got, body["self_sha16"], LOCK_SHA))
    return body


class Params(object):
    u"""Parameters read from the lock.  Nothing here has a default: a missing key must abort, not
    silently become a number the prediction record never contained."""

    def __init__(self, lock):
        p = lock["params"]
        self.ink = p["ink_threshold"]
        self.conf_ok = p["latin_conf_ok"]
        self.ranges = [tuple(r) for r in p["hebrew_ranges"]]
        self.win = p["window_pitches"]
        self.pitch_fallback = p["pitch_fallback"]
        self.smooth_div = p["seg_smooth_divisor"]
        self.peak_half = p["seg_peak_halfwindow"]
        self.peak_floor = p["seg_peak_floor"]
        self.trim_floor = p["seg_trim_floor"]
        f = p["furniture_rule"]
        self.furn_w = f["min_width_frac_of_col"]
        self.furn_h = f["max_height_frac_of_pitch"]
        self.furn_d = f["min_density"]
        c = p["ink_corroboration"]
        self.min_ink = c["min_ink_frac"]
        self.min_hf = c["min_height_frac_of_pitch"]
        self.max_hf = c["max_height_frac_of_pitch"]

    def is_hebrew(self, text):
        for ch in (text or ""):
            o = ord(ch)
            for lo, hi in self.ranges:
                if lo <= o <= hi:
                    return True
        return False


def band_pitch(ocr, x0, x1, y_near, reach=500):
    tops = {}
    for wd in ocr:
        cx = wd["left"] + wd["width"] / 2.0
        if not (x0 <= cx <= x1) or abs(wd["top"] - y_near) > reach:
            continue
        tops.setdefault((wd["block_num"], wd["par_num"], wd["line_num"]), []).append(wd["top"])
    ys = sorted(sum(v) / float(len(v)) for v in tops.values())
    d = sorted(ys[i + 1] - ys[i] for i in range(len(ys) - 1) if 10 < ys[i + 1] - ys[i] < 200)
    return int(round(d[len(d) // 2])) if d else None


def smooth(a, k):
    return np.convolve(a.astype(float), np.ones(max(1, k)) / max(1, k), mode="same")


def segment(prof, pitch, P):
    sm = smooth(prof, max(3, pitch // P.smooth_div))
    if sm.max() <= 0:
        return []
    half = max(2, int(pitch * P.peak_half))
    peaks = []
    for y in range(len(sm)):
        lo, hi = max(0, y - half), min(len(sm), y + half + 1)
        if sm[y] >= sm[lo:hi].max() and sm[y] > P.peak_floor * sm.max():
            if not peaks or y - peaks[-1] >= half:
                peaks.append(y)
    out = []
    for i, p in enumerate(peaks):
        lo = 0 if i == 0 else int(np.argmin(sm[peaks[i - 1]:p])) + peaks[i - 1]
        hi = len(sm) - 1 if i == len(peaks) - 1 else int(np.argmin(sm[p:peaks[i + 1]])) + p
        seg = prof[lo:hi + 1]
        if seg.max() <= 0:
            continue
        nz = np.nonzero(seg > max(1, P.trim_floor * seg.max()))[0]
        if nz.size:
            out.append((lo + int(nz[0]), lo + int(nz[-1])))
    return out


def is_furniture(mask, lo, hi, pitch, col_w, P):
    u"""A printed rule IS an inked band and satisfies every liveness check."""
    sub = mask[lo:hi + 1, :]
    tot = int(sub.sum())
    if tot == 0:
        return False
    cols = np.nonzero(sub.sum(axis=0))[0]
    span_w = int(cols[-1] - cols[0] + 1) if cols.size else 0
    h = hi - lo + 1
    dens = float(tot) / (span_w * h) if (span_w and h) else 0.0
    return (span_w > P.furn_w * col_w and h < P.furn_h * pitch and dens > P.furn_d)


def corroborate(mask, x0, y0, wd, pitch, P):
    u"""Degeneracy guard on a candidate's own pixels: blank, or a rule, or plausible type."""
    a = max(0, wd["left"] - x0)
    b = min(mask.shape[1], wd["left"] + wd["width"] - x0)
    c = max(0, wd["top"] - y0)
    d = min(mask.shape[0], wd["top"] + wd["height"] - y0)
    if b <= a or d <= c:
        return False, {"reason": "candidate box outside the window"}
    sub = mask[c:d, a:b]
    tot = int(sub.sum())
    frac = float(tot) / sub.size if sub.size else 0.0
    rows = sub.sum(axis=1)
    nz = np.nonzero(rows)[0]
    ih = int(nz[-1] - nz[0] + 1) if nz.size else 0
    hf = ih / float(pitch) if pitch else 0.0
    ok = (frac >= P.min_ink and P.min_hf <= hf <= P.max_hf)
    return ok, {"ink_frac": round(frac, 3), "h_frac_of_pitch": round(hf, 2), "ih": ih}


def band_all_read(mask, ocr, x0, y0, lo, hi, P):
    u"""Negative test: is every inked column of this band covered by a confident Latin word?"""
    w = mask.shape[1]
    sub = mask[lo:hi + 1, :]
    inked = sub.sum(axis=0) > 0
    if not inked.any():
        return None
    ay0, ay1 = y0 + lo, y0 + hi
    read = np.zeros(w, dtype=bool)
    for wd in ocr:
        wy0, wy1 = wd["top"], wd["top"] + wd["height"]
        if min(wy1, ay1) - max(wy0, ay0) <= 0.4 * (ay1 - ay0):
            continue
        if wd["conf"] < P.conf_ok or not (wd.get("text") or "").strip():
            continue
        a, b = max(0, wd["left"] - x0), min(w, wd["left"] + wd["width"] - x0)
        if b > a:
            read[a:b] = True
    return bool(not (inked & (~read)).any())


def locate(row, P):
    u"""One span.  Returns the verdict dict; raises nothing and guesses nothing."""
    page = row["page"]
    box = row["crop"]["native_rects"][0]
    reg = row["note_context"]["native_rects"][0]
    img = Image.open(str(VOL / ("page%d_image1.png" % page)))
    if img.mode != "L":
        img = img.convert("L")
    ocr = jl(VOL / ("page%d_image1_ocr.json" % page))
    x0, x1 = reg[0], min(reg[2], img.size[0])
    pitch = band_pitch(ocr, x0, x1, box[1])
    pitch_defaulted = pitch is None
    if pitch_defaulted:
        pitch = P.pitch_fallback
    half = int(round(P.win * pitch))
    y0, y1 = max(0, box[1] - half), min(img.size[1], box[3] + half)
    mask = (np.asarray(img.crop((x0, y0, x1, y1))) < P.ink)
    col_w = x1 - x0
    raw = segment(mask.sum(axis=1), pitch, P)
    struck = [(a, b) for (a, b) in raw if is_furniture(mask, a, b, pitch, col_w, P)]
    bands = [(a, b) for (a, b) in raw if (a, b) not in struck]

    def line_of(y_abs, bs):
        for i, (a, b) in enumerate(bs):
            if y0 + a - 2 <= y_abs <= y0 + b + 2:
                return i
        return None

    box_mid = (box[1] + box[3]) // 2
    box_line = line_of(box_mid, bands)
    box_line_unstruck = line_of(box_mid, raw)

    cands = []
    for wd in ocr:
        cx = wd["left"] + wd["width"] / 2.0
        cy = wd["top"] + wd["height"] / 2.0
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            continue
        if not P.is_hebrew(wd.get("text")):
            continue
        ok, ink = corroborate(mask, x0, y0, wd, pitch, P)
        cands.append({
            "text": wd.get("text"), "conf": wd["conf"],
            "y": [wd["top"], wd["top"] + wd["height"]],
            "x": [wd["left"], wd["left"] + wd["width"]],
            "line": line_of(cy, bands), "line_unstruck": line_of(cy, raw),
            "corroborated": bool(ok), "ink": ink,
            "in_region": bool(reg[1] <= cy <= reg[3]),
        })
    good = [c for c in cands if c["corroborated"] and c["line"] is not None]
    heb_lines = sorted(set(c["line"] for c in good))

    out = {
        "span_id": row["span_id"], "page_file": page, "page_printed": page - 88,
        "pitch": pitch, "pitch_defaulted": pitch_defaulted,
        "window": [y0, y1], "n_bands": len(bands), "n_struck_furniture": len(struck),
        "box_native": box, "region_native": reg,
        "box_equals_region": bool(box == reg),
        "box_y0_equals_region_y0": bool(box[1] == reg[1]),
        "box_line": box_line, "candidate_lines": heb_lines,
        "candidates": cands, "n_candidates": len(cands), "n_corroborated": len(good),
        "box_band_all_read": None, "verdict": None, "offset": None,
        "offset_unstruck": None, "furniture_sensitive": False,
        "candidates_all_outside_region": bool(good) and all(not c["in_region"] for c in good),
    }
    if box_line is not None:
        a, b = bands[box_line]
        out["box_band"] = [y0 + a, y0 + b]
        out["box_band_all_read"] = band_all_read(mask, ocr, x0, y0, a, b, P)
    if box_line is None:
        out["verdict"] = "abstain_no_band"
        return out
    if not good:
        out["verdict"] = "abstain_no_candidate"
        out["abstain_detail"] = ("no Hebrew codepoint in the window" if not cands
                                 else "candidates present but none corroborated")
        return out
    if box_line in heb_lines:
        out["verdict"] = "on_hebrew"
        out["offset"] = 0
    else:
        offs = [box_line - l for l in heb_lines]
        out["offset"] = min(offs, key=lambda v: (abs(v), v))
        out["verdict"] = "off_by_lines"
    # the same offset recomputed with furniture bands left IN, to expose index sensitivity
    if box_line_unstruck is not None:
        ul = sorted(set(c["line_unstruck"] for c in good if c["line_unstruck"] is not None))
        if ul:
            uo = (0 if box_line_unstruck in ul
                  else min([box_line_unstruck - l for l in ul], key=lambda v: (abs(v), v)))
            out["offset_unstruck"] = uo
            out["furniture_sensitive"] = bool(uo != out["offset"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", action="store_true", help="write the 74-span census JSON")
    a = ap.parse_args()
    lock = load_lock()
    P = Params(lock)
    g0 = {"public": S.git_state("C:/Users/cnogr/git/goatyard-laneB"),
          "private": S.git_state("C:/Users/cnogr/git/dr-voluminous")}
    cut = jl(AUD / lock["inputs"]["cut_set"])
    truth = dict((r["span_id"], r) for r in jl(AUD / lock["inputs"]["truth_set"])["rows"])
    rows = sorted(cut["rows"], key=lambda r: (r["page"], r["span_id"]))
    if len(rows) != 74:
        raise SystemExit("REFUSED: cut carries %d rows, not 74" % len(rows))

    res = {}
    for r in rows:
        res[r["span_id"]] = locate(r, P)

    # ---- the three scored strata, each against its own truth ------------------------------
    St = lock["strata"]
    s1 = St["S1_geometry5_signed_lines"]
    scored = {"S1": [], "S1b": [], "S2": []}
    for sid in s1["spans"]:
        want = s1["truth"][sid]
        got = res[sid]
        scored["S1"].append({
            "span_id": sid, "signed_offset": want, "verdict": got["verdict"],
            "offset": got["offset"], "sign_ok": (got["offset"] is not None
                                                 and (got["offset"] > 0) == (want > 0)),
            "magnitude_ok": got["offset"] == want,
            "excluded_from_rate": sid in lock["geometry5_check"]["excluded_from_rate"],
            "box_band_all_read": got["box_band_all_read"],
            "candidates_all_outside_region": got["candidates_all_outside_region"],
            "n_candidates": got["n_candidates"],
        })
    for sid in St["S1b_geometry5_no_hebrew_on_crop"]["spans"]:
        got = res[sid]
        scored["S1b"].append({"span_id": sid, "verdict": got["verdict"], "offset": got["offset"],
                              "agrees_not_on_hebrew": got["verdict"] != "on_hebrew",
                              "box_band_all_read": got["box_band_all_read"]})
    for sid in St["S2_measured_wrong_line"]["spans"]:
        got = res[sid]
        scored["S2"].append({"span_id": sid, "verdict": got["verdict"], "offset": got["offset"],
                             "agrees_fault": got["verdict"] in ("off_by_lines",),
                             "box_band_all_read": got["box_band_all_read"]})

    # ---- the census over all 74, reported as claims ---------------------------------------
    from collections import Counter
    verdicts = Counter(v["verdict"] for v in res.values())
    onew = [sid for sid in res if truth[sid].get("words") == 1]
    multi = [sid for sid in res if truth[sid].get("words") != 1]

    def tally(ids):
        c = Counter(res[s]["verdict"] for s in ids)
        return {"n": len(ids), "on_hebrew": c["on_hebrew"], "off_by_lines": c["off_by_lines"],
                "abstain_no_candidate": c["abstain_no_candidate"],
                "abstain_no_band": c["abstain_no_band"]}

    offs = Counter(v["offset"] for v in res.values() if v["verdict"] == "off_by_lines")
    body = {
        "kind": "line_localizer_run",
        "lane": "B", "session": "50612c81", "date": "2026-11-26",
        "page_convention": "all page numbers are FILE pages (printed = file - 88)",
        "lock": {"name": LOCK_NAME, "self_sha16": lock["self_sha16"]},
        "spend": {"model_calls": 0, "usd": 0.0},
        "git_start": g0,
        "git_end": {"public": S.git_state("C:/Users/cnogr/git/goatyard-laneB"),
                    "private": S.git_state("C:/Users/cnogr/git/dr-voluminous")},
        "scored": scored,
        "scored_population": {
            "n": 6,
            "note": ("the only spans of the 74 carrying a statement about LINE PLACEMENT.  "
                     "Everything else in this record is a claim, not a score."),
        },
        "census_is": ("A CLAIM AWAITING ADJUDICATION.  GEOMETRY5 declared box_on_hebrew and never "
                      "used it, so no signed statement says any box is right and an on_hebrew "
                      "verdict here cannot be counted as a pass."),
        "census": {
            "all": dict(verdicts), "one_word": tally(onew), "multi_word": tally(multi),
            "offsets_when_off": dict((str(k), v) for k, v in sorted(offs.items())),
            "pitch_defaulted": sum(1 for v in res.values() if v["pitch_defaulted"]),
            "furniture_sensitive": sorted(s for s, v in res.items() if v["furniture_sensitive"]),
            "n_struck_furniture_total": sum(v["n_struck_furniture"] for v in res.values()),
            "box_equals_region": sum(1 for v in res.values() if v["box_equals_region"]),
            "box_y0_equals_region_y0": sum(1 for v in res.values()
                                           if v["box_y0_equals_region_y0"]),
            "candidates_all_outside_region": sorted(
                s for s, v in res.items() if v["candidates_all_outside_region"]),
            "box_band_all_read_and_abstained": sorted(
                s for s, v in res.items()
                if v["verdict"] == "abstain_no_candidate" and v["box_band_all_read"]),
        },
        "rows": [res[r["span_id"]] for r in rows],
    }
    body["self_sha16"] = None
    probe = dict(body)
    probe.pop("self_sha16")
    body["self_sha16"] = hashlib.sha256(S.canon(probe).encode("utf-8")).hexdigest()[:16]

    print("lock %s verified" % lock["self_sha16"])
    print("")
    print("S1  signed GEOMETRY5 offsets (sign / magnitude):")
    for r in scored["S1"]:
        print("   %-9s signed %+d  got %-20s offset %-5s sign=%-5s mag=%-5s%s"
              % (r["span_id"], r["signed_offset"], r["verdict"], r["offset"],
                 r["sign_ok"], r["magnitude_ok"],
                 "  [excluded_from_rate]" if r["excluded_from_rate"] else ""))
    print("S1b no_hebrew_on_crop:")
    for r in scored["S1b"]:
        print("   %-9s got %-22s agrees_not_on_hebrew=%s  box_band_all_read=%s"
              % (r["span_id"], r["verdict"], r["agrees_not_on_hebrew"], r["box_band_all_read"]))
    print("S2  measured fault_box_wrong_line:")
    for r in scored["S2"]:
        print("   %-9s got %-22s agrees_fault=%s  offset=%s"
              % (r["span_id"], r["verdict"], r["agrees_fault"], r["offset"]))
    print("")
    print("census over 74 (CLAIMS): %s" % dict(verdicts))
    print("  one_word  %s" % body["census"]["one_word"])
    print("  multi_word %s" % body["census"]["multi_word"])
    print("  offsets when off: %s" % body["census"]["offsets_when_off"])
    print("  box == region: %d of 74;  box.y0 == region.y0: %d of 74"
          % (body["census"]["box_equals_region"], body["census"]["box_y0_equals_region_y0"]))
    print("  furniture-sensitive: %d   pitch defaulted: %d   struck furniture bands: %d"
          % (len(body["census"]["furniture_sensitive"]), body["census"]["pitch_defaulted"],
             body["census"]["n_struck_furniture_total"]))
    print("  all candidates outside the note region: %d spans"
          % len(body["census"]["candidates_all_outside_region"]))
    print("  abstained on a fully-read Latin band: %d spans"
          % len(body["census"]["box_band_all_read_and_abstained"]))
    if a.census:
        out = AUD / OUT_NAME
        io.open(str(out), "w", encoding="utf-8", newline="\n").write(S.canon(body) + u"\n")
        print("")
        print("WROTE %s  self_sha16=%s" % (out, body["self_sha16"]))
    else:
        print("")
        print("-- nothing written; pass --census to emit %s" % OUT_NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
