"""Candidate-set seed derivation (config-v2, build after the matcher-viability finding).

The matcher measurement showed the two ends: OPEN read (24 candidates) is non-viable (34%), VERIFY (1 expected
letter) is zero-wrong. The unseeded runs live in BETWEEN, and that middle is where the value is (Chris,
2026-09-13): a run separated from a seeded run by an ambiguous page does not have an unknown seed — it has a
small CANDIDATE SET, because the true note count on the ambiguous page is one of a few values. So:

  - CHAIN-DERIVE a candidate set, not a seed. Walk the book-continuous chain from the nearest human seed to the
    unseeded run's first note, summing per-page note counts. A ±1 break page contributes {ext, det} (2 totals),
    ±2 gives 3; each distinct total maps to one candidate seed letter (wrap-aware, j/v-skipped).
  - The matcher runs as a VERIFIER over that set: confirm the candidate whose first-marker crop beats the others
    by the margin. `m` vs `o` confirms; `m` vs `n` (a confusable pair) abstains.
  - Escalate to the vision tier ONLY when the set is all-confusable, or UNCONSTRAINED — a collapse page
    (|gap|>=3, count unknown), a known compositor anomaly (skip/extra shifts the letters off the count), or an
    unconfirmed/confirmed reset in the walk (chain restart uncertainty). Those walks return still-open.

Honesty rule (Chris): a derived seed records its candidate set, margin, and the count it IMPLIES for the
ambiguous page. Choosing `n` over `m` asserts the ambiguous page had 13 notes not 12; when that page is later
mapped it must agree, or the seed reverts to unconfirmed. Provenance per seed: human | chain-derived-verified |
vision (still-open, deferred). Report: human / candidate-verified / still-open."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import numpy as np
import marker_alphabet as MA
import marker_harvest as MH
import marker_matcher as MM

A = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
APP = A.parent / "vol1_apparatus.jsonl"
COLLAPSE_GAP = 3
MAX_CANDIDATES = 4        # beyond this the set is too ambiguous to verify safely -> still-open


def _adv(marker, k):
    """The letter k steps after `marker` in the 24-letter chain (k may be negative), wrap-aware, j/v skipped."""
    return MA.ALPHABET[(MA.index(marker) + k) % len(MA.ALPHABET)]


def _load():
    census = json.loads((A / "chain_census.json").read_text(encoding="utf-8"))
    ext = {}
    for l in APP.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            if "page" in r:
                ext[r["page"]] = r.get("n_notes") or 0
    breaks = {b["page"]: b for b in census["breaks"]}
    boundaries = {b["page"] for b in census["candidate_boundaries"]}          # unconfirmed resets
    resets = {r["file_page"] for r in json.loads((A / "marker_resets_observed.json").read_text(encoding="utf-8"))["resets_observed"]}
    anomalies = {p["file_page"] for p in json.loads((A / "marker_anomalies_observed.json").read_text(encoding="utf-8"))["pages"]}
    seeds = {}
    for l in (A / "marker_seeds_human_20260913_FINAL.jsonl").read_text(encoding="utf-8").splitlines():
        if l.strip():
            s = json.loads(l); seeds[tuple(s["run"])] = dict(first_page=s["first_page"], letter=s["seed_letter"])
    return census, ext, breaks, boundaries | resets, anomalies, seeds


def _first_noted(run, ext):
    return next((p for p in range(run[0], run[1] + 1) if ext.get(p, 0) > 0), None)


def _walk_totals(p_from, p_to, ext, breaks, blockers):
    """Possible cumulative note counts over pages [p_from .. p_to-1]. Returns (set_of_totals, block_reason|None).
    A ±1/±2 break injects {ext, det}; a collapse/anomaly/reset page blocks (unconstrained)."""
    totals = {0}
    for p in range(p_from, p_to):
        if p in blockers:
            return None, f"reset/boundary@{p}"
        b = breaks.get(p)
        if b and abs(b["gap"]) >= COLLAPSE_GAP:
            return None, f"collapse@{p}(gap{b['gap']:+d})"
        counts = {b["extractor"], b["detector"]} if b else {ext.get(p, 0)}
        totals = {t + c for t in totals for c in counts}
        if len(totals) > MAX_CANDIDATES:
            return None, "too-ambiguous"
    return totals, None


def _candidates(target_run, ext, breaks, blockers, anomalies, seeds, exclude=None):
    """Candidate seed letters for an unseeded run's first note, from the NEAREST human seed with a clean walk
    (no collapse/anomaly/reset between). Tries preceding then following anchors by page distance. Returns
    (candidates_sorted, provenance_dict) or (None, {reason})."""
    tp = _first_noted(target_run, ext)
    if tp is None:
        return None, {"reason": "no-noted-page"}
    anchors = sorted((s for s in seeds if s != exclude), key=lambda r: abs(seeds[r]["first_page"] - tp))
    nearest_block = None
    for ar in anchors:
        ap = seeds[ar]["first_page"]; am = seeds[ar]["letter"]
        lo, hi = (ap, tp) if ap < tp else (tp, ap)
        anom = next((p for p in range(lo, hi + 1) if p in anomalies), None)
        if anom is not None:
            nearest_block = nearest_block or f"anomaly@{anom}(dist{hi-lo})"
            continue
        totals, block = _walk_totals(lo, hi, ext, breaks, blockers)
        if totals is None:
            nearest_block = nearest_block or f"{block}(dist{hi-lo})"
            continue
        cands = sorted({_adv(am, t) if ap < tp else _adv(am, -t) for t in totals}, key=MA.index)
        implied = {t: (_adv(am, t) if ap < tp else _adv(am, -t)) for t in totals}
        return cands, {"anchor_run": list(ar), "anchor_page": ap, "anchor_letter": am,
                       "direction": "fwd" if ap < tp else "bwd", "target_page": tp,
                       "candidate_totals": {str(k): v for k, v in implied.items()}}
    return None, {"reason": "no-clean-anchor", "nearest_block": nearest_block}


def _verify(target_page, cands, templates, margin):
    """Crop the target run's first marker and verify over the candidate set: confirm the top candidate iff it
    beats the runner-up by the margin. Returns (letter|None, detail)."""
    _strip, crops = MH._page_marker_crops(target_page)
    crop = next((c for _b, c in crops if c is not None), None)
    if crop is None:
        return None, {"status": "no-crop"}
    v = _vec_img(crop)
    scored = sorted(((MM.score(v, c, templates), c) for c in cands), reverse=True)
    if len(scored) == 1:
        return scored[0][1], {"status": "chain-exact", "score": round(scored[0][0], 4)}
    best, second = scored[0], scored[1]
    m = best[0] - second[0]
    bl = best[1]
    # SAFETY (learned from the [556,558] a->e miss): never confirm a winner that is confusable with ANY other
    # candidate — the matcher cannot separate that pair, so a margin between them is noise. And the winner must
    # additionally pass the standard confusable-set guard (beat its own confusables, in or out of the set).
    if any(bl in MM.CONF.get(c, []) or c in MM.CONF.get(bl, []) for _s, c in scored if c != bl):
        return None, {"status": "abstain-confusable-candidate", "top": bl, "second": second[1], "margin": round(m, 4)}
    if not MM.verify(v, bl, templates, margin)[0]:
        return None, {"status": "abstain-fails-confusable-guard", "top": bl, "margin": round(m, 4)}
    if m >= margin:
        return bl, {"status": "verified", "winner": bl, "runner_up": second[1], "margin": round(m, 4)}
    return None, {"status": "abstain-low-margin", "top": bl, "second": second[1], "margin": round(m, 4)}


def _vec_img(im):
    import numpy as np
    from PIL import Image
    a = 255 - np.asarray(im.convert("L"), float)
    if a.max() > a.min():
        a = (a - a.min()) / (a.max() - a.min())
    im2 = Image.fromarray((a * 255).astype("uint8")); w, h = im2.size; s = (MM.N - 4) / max(w, h)
    im2 = im2.resize((max(1, round(w * s)), max(1, round(h * s))))
    c = Image.new("L", (MM.N, MM.N), 0); c.paste(im2, ((MM.N - im2.size[0]) // 2, (MM.N - im2.size[1]) // 2))
    vv = np.asarray(c, float).ravel(); n = np.linalg.norm(vv)
    return vv / n if n else vv


def derive(self_test=False):
    census, ext, breaks, blockers, anomalies, seeds = _load()
    rows = MM._load()
    templates = MM._templates(rows)                 # all human exemplars as templates
    margin = MM._pick_margin(rows)
    note_runs = [tuple(r) for r in census["runs"] if _first_noted(tuple(r), ext) is not None]
    human = set(seeds)
    targets = ([r for r in human] if self_test else [r for r in note_runs if r not in human])

    out = {"human": [], "candidate_verified": [], "still_open": []}
    for T in targets:
        excl = T if self_test else None
        cands, prov = _candidates(T, ext, breaks, blockers, anomalies, seeds, exclude=excl)
        if cands is None:
            out["still_open"].append(dict(run=list(T), **prov)); continue
        tmpl = MM._templates([r for r in rows if r["run"] != T]) if self_test else templates  # no leakage in self-test
        letter, det = _verify(prov["target_page"], cands, tmpl, margin)
        rec = dict(run=list(T), candidates=cands, **prov, **det)
        if letter is None:
            rec["reason"] = det.get("status")
            out["still_open"].append(rec)
        else:
            rec["seed_letter"] = letter
            rec["implies_page_count"] = {k: v for k, v in prov.get("candidate_totals", {}).items() if v == letter}
            if self_test:
                rec["human_truth"] = seeds[T]["letter"]; rec["correct"] = (letter == seeds[T]["letter"])
            out["candidate_verified"].append(rec)

    # CEILING projection: chain-derivation is downstream of chain-uncertainty resolution. If the +-1/+-2 band
    # and the collapse pages were resolved, breaks become EXACT and candidate sets collapse to size 1 (chain-
    # exact, NO read). Count how many unseeded runs would then derive for free — this is the number that says
    # whether the seed problem is a reading job or a chain-resolution job.
    proj = {}
    if not self_test:
        def _reach(T, block_boundaries, block_anom=True):
            tp = _first_noted(T, ext)
            for ar in sorted(seeds, key=lambda r: abs(seeds[r]["first_page"] - tp)):
                ap = seeds[ar]["first_page"]; lo, hi = (ap, tp) if ap < tp else (tp, ap)
                if block_anom and any(p in anomalies for p in range(lo, hi + 1)):
                    continue
                if block_boundaries and any(p in blockers for p in range(lo, hi + 1)):
                    continue
                return True
            return False
        tg = [r for r in note_runs if r not in human]
        proj = {"unseeded_note_runs": len(tg),
                "derivable_now": len(out["candidate_verified"]),
                "ceiling_after_band_and_collapse_resolved": sum(1 for T in tg if _reach(T, True)),
                "ceiling_if_boundaries_also_confirmed": sum(1 for T in tg if _reach(T, False))}

    tag = "selftest" if self_test else "apply"
    (A / f"marker_seed_derive_{tag}.json").write_text(json.dumps(dict(
        margin=margin, n_note_runs=len(note_runs), n_human=len(human), projection=proj,
        counts={k: len(v) for k, v in out.items()}, **out), indent=1), encoding="utf-8")
    if proj:
        print(f"  CEILING: derivable now={proj['derivable_now']}, after band+collapse resolved="
              f"{proj['ceiling_after_band_and_collapse_resolved']}, +boundaries confirmed="
              f"{proj['ceiling_if_boundaries_also_confirmed']} (of {proj['unseeded_note_runs']})")
    print(f"[{tag}] note-bearing runs={len(note_runs)} human={len(human)} "
          f"targets={len(targets)}  ->  candidate-verified={len(out['candidate_verified'])}  "
          f"still-open={len(out['still_open'])}")
    if self_test:
        cv = out["candidate_verified"]
        correct = sum(1 for r in cv if r.get("correct"))
        print(f"  SELF-TEST accuracy on human runs treated as unseeded: {correct}/{len(cv)} verified correct "
              f"(WRONG must be 0): {[ (r['run'], r['seed_letter'], r['human_truth']) for r in cv if not r['correct'] ]}")
    # still-open reason histogram
    from collections import Counter
    reasons = Counter(r.get("reason") or r.get("status") for r in out["still_open"])
    print("  still-open reasons:", dict(reasons))
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true"); a = ap.parse_args()
    derive(self_test=a.selftest)
