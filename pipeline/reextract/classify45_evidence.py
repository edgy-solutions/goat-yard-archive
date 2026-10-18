"""Evidence table for the wrong-row classification (advisor ruling 3, 2026-10-18).

MEASUREMENT ONLY.  This file assigns no class.  It gathers, per wrong row, the signed signature, both
bare reads, the base-consonant edit distance, and every geometry fact the cut already recorded -- so
that a crop-class call can be made on geometry rather than on an impression of the picture, and so that
Chris can audit a crop-class call against numbers that came from the cut and not from my reading.

The division is deliberate.  Distance is REPORTED next to every row and never assigns a class
(PREDICTIONS_classify45_412fa98fbf25c2b0, registered 3): if distance could assign, the registered
claim "reader median <= 2, crop >= 3" would be measuring itself.

Sources, all committed:
  SCORE45_<run>.json          signature (in-crop, the scored basis), signature_full, per-arm reads
  truth_set74_<set>.json      signed box, verdict, letters/words, page_status
  truthset74_cut_<set>.json   crop + note_context geometry: native rects, text_bands, word_runs, ink
  truthset74_crops_<set>/     the approved crop pixels, read-only

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).
"""
import io
import json
import pathlib
import re
import unicodedata

A = pathlib.Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
RUN = "501ab577a18a6785"
SET = "0401b636ffa7bf1a"
CROPS = A / ("truthset74_crops_%s" % SET)
OUT = A / ("CLASSIFY45_EVIDENCE_%s.json" % RUN)

NIKUD = re.compile(r"[\u0591-\u05c7]")
OPUS = "anthropic/claude-opus-5.5"
QWEN = "qwen/qwen3.7-plus"

# Confusable PAIRS of this fount, as measured in this project -- not a general Hebrew list.  Three were
# found by signing glyph cards (ayin/tsadi, mem/pe, bet/gimel: the-ground-truth-is-a-claim-too), and the
# dalet/resh and kaf/bet pairs are the same kind of defect: a short descender or a corner that this
# fount does not resolve.  Membership here is EVIDENCE FOR a reader-confusable call, never proof.
CONFUSABLE = [set(p) for p in ("\u05e2\u05e6", "\u05de\u05e4", "\u05d1\u05d2", "\u05d3\u05e8",
                               "\u05db\u05d1", "\u05da\u05d1", "\u05d4\u05d7", "\u05d9\u05d5")]


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def cons(s):
    """Base consonants: NFC, marks removed.  The unit the registered distance is measured in."""
    return NIKUD.sub("", nfc(s))


def lev(a, b):
    """Levenshtein.  Small strings; the clear implementation is the right one."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def subs(a, b):
    """Positional substitutions when the two base strings are the same length, else []."""
    if len(a) != len(b) or a == b:
        return []
    return [{"pos": i + 1, "signed": x, "read": y, "confusable_pair": any({x, y} <= p for p in CONFUSABLE)}
            for i, (x, y) in enumerate(zip(a, b)) if x != y]


def main():
    score = json.load(io.open(A / ("SCORE45_%s.json" % RUN), encoding="utf-8"))
    truth = json.load(io.open(A / ("truth_set74_%s.json" % SET), encoding="utf-8"))
    cut = json.load(io.open(A / ("truthset74_cut_%s.json" % SET), encoding="utf-8"))
    T = {r["span_id"]: r for r in truth["rows"]}
    C = {r["span_id"]: r for r in cut["rows"]}
    S = {r["span_id"]: r for r in score["rows"]}

    nc = cut["note_context"]
    multi_line_regions = {d["span_id"] for d in nc.get("region_covers_3plus_lines", [])
                          if isinstance(d, dict) and "span_id" in d}
    behind_one = set(nc.get("note_identity_screen", []) or [])

    # the wrong rows, per arm, bare channel -- the populations the ruling names
    def wrong(arm):
        return sorted(s for s, r in S.items()
                      if r["results"].get("%s|bare" % arm, {}).get("class_primary") == "wrong")

    ow, qw = wrong(OPUS), wrong(QWEN)
    ids = sorted(set(ow) | set(qw))

    rows = []
    for sid in ids:
        s, t, c = S[sid], T[sid], C[sid]
        sig = nfc(s["signature"])
        sig_c = cons(sig)
        rec = {
            "span_id": sid, "page_file": s["page_file"], "page_printed": s["page_printed"],
            "signature": sig, "signature_full": s["signature_full"],
            "signature_cons": sig_c, "signed_letters": t.get("letters"), "signed_words": t.get("words"),
            "signed_nikud": bool(t.get("nikud")), "signed_verdict": t.get("verdict"),
            "signed_status": t.get("status"), "page_status": t.get("page_status"),
            "populations": s["populations"],
            "wrong_on": [a for a, k in (("opus", sid in ow), ("qwen", sid in qw)) if k],
            "reads": {}, "crop_png": None, "note_png": None,
        }
        for nm, arm in (("opus", OPUS), ("qwen", QWEN)):
            r = s["results"].get("%s|bare" % arm, {})
            read = nfc(r.get("hebrew") or "")
            read_c = cons(read)
            rec["reads"][nm] = {
                "read": read, "read_cons": read_c, "class": r.get("class_primary"),
                "dist_cons": lev(sig_c, read_c),
                "len_signed": len(sig_c), "len_read": len(read_c),
                "same_length": len(sig_c) == len(read_c),
                "substitutions": subs(sig_c, read_c),
                "read_has_nikud": bool(NIKUD.search(read)),
            }
        rec["arms_agree_bare"] = (rec["reads"]["opus"]["read"] == rec["reads"]["qwen"]["read"]
                                 and rec["reads"]["opus"]["read"] != "")
        rec["agreement_and_wrong_bare"] = rec["arms_agree_bare"] and len(rec["wrong_on"]) == 2
        rec["one_arm_exact"] = any(rec["reads"][n]["class"] == "exact" for n in ("opus", "qwen"))

        # ---- geometry, all of it from the cut, none of it from looking at the picture ----
        cr, no = c["crop"], c["note_context"]
        sx0, sy0, sx1, sy1 = cr["native_rects"][0]
        nx0, ny0, nx1, ny1 = no["native_rects"][0]
        rec["geometry"] = {
            "crop_size": cr["size"], "crop_sha16": cr["sha16"],
            "span_native_rect": [sx0, sy0, sx1, sy1],
            "note_native_rect": [nx0, ny0, nx1, ny1],
            # the span box inside the note-context crop, for the strip-with-box panel
            "box_in_note_px": [sx0 - nx0, sy0 - ny0, sx1 - nx0, sy1 - ny0],
            "note_size": no["size"],
            "text_bands_in_crop": cr.get("text_bands"),
            "word_runs_in_crop": cr.get("word_runs"),
            "n_word_runs": len(cr.get("word_runs") or []),
            "ink_px": cr.get("ink_px"), "ink_rows": cr.get("ink_rows"),
            "rect_edges": cr.get("rect_edges"), "band_overshoot_px": cr.get("band_overshoot_px"),
            "lines_in_segment": no.get("lines_in_segment"),
            "segments_in_note": no.get("segments_in_note"),
            "segment_held_the_span": no.get("segment_held_the_span"),
            "signed_box": t.get("box"), "cut_box_strip": c.get("box_strip"),
            "band": c.get("band"), "stitch_page": c.get("stitch_page"),
            "region_covers_3plus_lines": sid in multi_line_regions,
            "note_identity_screen": sid in behind_one,
            "crop_fault": c.get("fault"), "note_fault": c.get("note_fault") or None,
        }
        # SCREEN OUTPUTS: facts that bear on a crop-class call.  Named as questions, not as classes --
        # the class is assigned by hand, with these in front of me, and the mapping is written down in
        # the sheet so it can be disagreed with per row.
        g = rec["geometry"]
        nrun, nwords = g["n_word_runs"], (t.get("words") or 0)
        rec["screen"] = {
            "ratified_box_fault": "box_fault" in s["populations"],
            "signature_exceeds_crop": "partial_in_crop" in s["populations"],
            "crop_holds_more_than_one_line_of_type": (g["text_bands_in_crop"] or 1) > 1,
            "word_runs_vs_signed_words": "%d runs vs %d words" % (nrun, nwords),
            "fewer_runs_than_words": nrun < nwords,
            "more_runs_than_words": nrun > nwords,
            "span_truncated_by_the_cut": bool(g["crop_fault"]),
            "box_may_be_the_wrong_note": g["note_identity_screen"],
        }
        for nm in ("opus", "qwen"):
            p = CROPS / (sid.replace(":", "_") + "_A2_spanbox.png")
            q = CROPS / (sid.replace(":", "_") + "_notecontext.png")
            rec["crop_png"], rec["note_png"] = p.name, q.name
            assert p.exists() and q.exists(), "missing approved crop for %s" % sid
        rows.append(rec)

    out = {
        "kind": "classification_evidence",
        "note": "MEASUREMENT ONLY -- no class is assigned in this file",
        "run_classified": RUN, "set": SET,
        "prediction_locked": "PREDICTIONS_classify45_412fa98fbf25c2b0.json",
        "page_convention": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)",
        "distance_unit": "Levenshtein over NFC base consonants (marks removed); REPORTED, never used "
                         "to assign a class",
        "confusable_pairs_of_this_fount": ["".join(sorted(p)) for p in CONFUSABLE],
        "counts": {"opus_bare_wrong": len(ow), "qwen_bare_wrong": len(qw), "distinct_rows": len(ids),
                   "assignments": len(ow) + len(qw)},
        "opus_bare_wrong": ow, "qwen_bare_wrong": qw,
        "agreement_and_wrong_bare": [r["span_id"] for r in rows if r["agreement_and_wrong_bare"]],
        "rows": rows,
    }
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    print("wrote", OUT.name)
    print("opus bare wrong %d, qwen bare wrong %d, distinct rows %d, assignments %d"
          % (len(ow), len(qw), len(ids), len(ow) + len(qw)))
    print("agreement-and-wrong (bare):", out["agreement_and_wrong_bare"])
    print()
    hdr = "%-10s %-6s %-9s %-9s %-5s %-5s %-6s %-5s %s"
    print(hdr % ("span", "arms", "signature", "read", "dist", "bands", "runs/w", "flags", "pops"))
    for r in rows:
        for nm in r["wrong_on"]:
            d = r["reads"][nm]
            f = []
            if r["screen"]["ratified_box_fault"]:
                f.append("BOX")
            if r["screen"]["signature_exceeds_crop"]:
                f.append("PART")
            if r["screen"]["crop_holds_more_than_one_line_of_type"]:
                f.append("2LINE")
            if r["screen"]["fewer_runs_than_words"]:
                f.append("FEWER")
            if r["screen"]["box_may_be_the_wrong_note"]:
                f.append("IDENT")
            print(hdr % (r["span_id"], nm, r["signature_cons"], d["read_cons"], d["dist_cons"],
                         r["geometry"]["text_bands_in_crop"], r["screen"]["word_runs_vs_signed_words"],
                         ",".join(f) or "-", ",".join(r["populations"]) or "-"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
