# -*- coding: utf-8 -*-
u"""The consumer: accepted second-sitting rows become a SIGNED LAYER, or nothing becomes anything.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

WHY THIS FILE EXISTS. The second sitting's page writes verdict rows and `sitting2_load` accepts or
refuses them -- and then the rows stop. Nothing turns an accepted row into a layer any scorer can
read, so every run after the sitting keeps scoring the superseded truth while a ratified correction
sits in a file nobody consumes. That is the defect this lane has already named: *an
adjudicated-but-unsigned fix leaves later runs scoring the superseded truth.* A sitting that
changes a letter and changes no scorer has changed nothing.

WHAT A LAYER IS. One JSONL file in the shape of the signed exports already in the audits directory
-- same keys, same tile vocabulary -- so `signed_ids_from_exports`, the glyph cards and the scorers
read it with no new reader. It is the CURRENT side of its own diff: `ingest_pass2.diff_resigned`
compares it with the prior signed file, and `admit_resigned` is still the only door into truth.
This module does not open that door. It does not score, does not adjudicate, and reverses nobody:
it carries one sitting's verdicts into the shape the rest of the lane can argue with.

THE EIGHT GATES, each written for a failure that is real in these five rows.

  1. THE LOADER IS THE AUTHORITY, AND A REFUSED ROW POISONS THE LOAD. One malformed row and
     nothing is emitted. Splicing the good rows would ship a sitting that is part signed and part
     silent, and the silence would read as agreement.
  2. THE EXPORT MUST COVER EVERY PRIOR ROW. A layer over three of five spans leaves the other two
     scoring the superseded truth with nothing to say so -- the exact defect this file exists for.
  3. ONE PRIOR, BY HASH. Every row names the prior file it was signed against; all of them must
     name the file actually read, by `prior_source_sha16`. A verdict made against other bytes is a
     verdict about other glyphs.
  4. ONE SITTING, ONE SIGNER. A set of rows with two signers or two dates was assembled, not
     exported, and this file will not merge two sittings into one layer.
  5. A `keep_prior` OVER AN EMPTY PRIOR IS REFUSED. "The recorded answer stands" needs a recorded
     answer. Unknown is not clean, and the pass-1 export is full of tiles with no verdict at all.
  6. `changed` OVER A `not_in_crop` TILE IS REFUSED. Naming a letter does not bring the glyph
     inside the crop: the coverage channel and the identity channel answer different questions
     (p831:n2 tile 0 is the live instance -- its derived string carries `[lamed]`). A sitting that was
     never asked about coverage cannot retire a coverage verdict, and accepting it would silently
     turn a bracket into a reading.
  7. THE NAME AND THE GLYPH ARE ONE ACT. The page records both the letter's name and its
     character; if they disagree the row is refused, the same arithmetic `sig_load` applies to an
     exemplar.
  8. AN ABSTAINING GLYPH WITHHOLDS THE ROW'S STRING. `abstain` is a token no existing derivation
     knows, so the row derives nothing, states that it derives nothing, and names the glyphs and
     the signer's reasons. The alternative is a string with a confident letter where a human said
     they could not tell -- their honesty rendered as this pipeline's fabrication.

WHAT IT CARRIES WITHOUT RE-ASKING, AND SAYS SO. The sitting asked about consonant tiles. It did not
ask about insertions, about the row's `fault`, or about the prose note -- so those are carried from
the prior row verbatim and listed in `carried_unreasked`. A field copied in silence would read as
re-ratified. For the same reason `derived_from_verdicts` is recomputed, never copied.

WHAT IT CANNOT DO, AND WILL NOT PRETEND TO.

  * It cannot give the layer truth standing. The export has no channel for how a sitting was
     conducted, and `SITTING_RULINGS` is keyed by file hash, so a NEW file is under no ruling and
     nothing would require a provenance record for it. Each emitted row therefore carries
     `truth_standing: withheld` with what would lift it, and the manifest says it in one line. A
     layer that defaulted to truth because no rule named it yet would be a door with no key.
  * It cannot lift p628:n2's abstention. The signer's note *could be vav or nun* still stands on
     the row, and the sitting's page never asked for the keep/take/neither verdict
     `admit_resigned` requires for `(span_id, "glyph_abstention", i)`. The row carries the prior
     abstention and what the sitting said about that same tile, side by side, adjudicating
     neither. The manifest asks for the verdict by name.
  * It ingests nothing by default. `--build` refuses unless this module's own bytes are the
     committed blob at HEAD (Chris, 2026-11-24: a builder is committed before it builds anything
     he judges), and refuses again if the real export does not exist.

    python -X utf8 sitting2_signed_layer.py selftest    # 0 means every check passed
    python -X utf8 sitting2_signed_layer.py report      # what the real export would yield, if any
    python -X utf8 sitting2_signed_layer.py --build     # writes the layer; refuses on both counts above
"""
import datetime
import hashlib
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hebrew_aperture_diag as D                                          # noqa: E402
import sitting2_page as S2                                                # noqa: E402
import glyph_abstention as GA                                             # noqa: E402
import apparatus_signature_rule as RULE                                   # noqa: E402
from hebrew_glyph_card import LETTER                                      # noqa: E402
from write_scope import assert_inside                                     # noqa: E402

DATA = D.DATA


def L(name):
    """One letter, by its card name.

    NOTHING IN THIS FILE'S BYTES IS HEBREW, deliberately. The public repository's ratchet counts
    span-shaped ids within two lines of a Hebrew character and is pinned at its current count;
    this module's fixtures are full of both, so carrying the characters here would push that count
    past the pin for no reason -- the letters are needed at RUNTIME, not in the source. Naming them
    through hebrew_glyph_card.LETTER also means a fixture cannot disagree with the card table about
    what a name means. `selftest` asserts the absence, with a companion check that the scan it uses
    can actually see a Hebrew character, because a probe that misses passes on nothing.
    """
    return LETTER[name]


def S(*parts):
    """A string from letter names and literal pieces: S("[", "lamed", "]", "dalet")."""
    return u"".join(LETTER[p] if p in LETTER else p for p in parts)
#: The prior signed file and the signer's export. Both come from the page's own module, so the
#: layer cannot be built against a prior the page never showed.
PRIOR = S2.PRIOR
EXPORT = S2.EXPORT
SET_SHA = "0401b636ffa7bf1a"
PRINTED_OFFSET = 88

#: The signed tile vocabulary -- the one the existing exports and derivations use.
SIGNED_TILE_VERDICTS = ("confirmed", "corrected", "deleted", "not_in_crop", "sic")
#: The sitting's three, from the page.
SITTING_VERDICTS = S2.VERDICTS                      # keep_prior / changed / abstain
OWED_VERDICTS = S2.OWED_VERDICTS                    # keep / take / neither
#: A token on purpose outside SIGNED_TILE_VERDICTS. Every derivation in this lane returns "?" for
#: a verdict it does not know, so a row carrying this token must never be handed to one: that is
#: why `layer_derive` raises instead of deriving, and why the row says its string is withheld.
ABSTAIN_TOKEN = "abstain"

LAYER_NAME = "glyphsign_%s_sitting2_%dspan_signed_%s.jsonl"
MANIFEST_NAME = "SITTING2LAYER_%s.json"
ADJ_NAME = "SITTING2ADJUDICATIONS_%s.json"

#: Stated with the hashes it produces, per ruling 5: the digest is over UTF-8 bytes of a canonical
#: serialisation with ensure_ascii=False, so a Hebrew letter hashes as the letter and not as a
#: \\u escape.
HASH_RULE = ("sha256[:16] over the UTF-8 bytes of json.dumps(obj, sort_keys=True, "
             "separators=(',',':'), ensure_ascii=False)")

#: The layer's name carries a digest of its rows with `sheet` OMITTED, and this is stated rather
#: than quietly done. Every row names the file it sits in, so `sheet` holds the filename, which
#: holds the digest -- a field cannot be inside its own hash, and iterating to a fixed point would
#: give a name no reader could recompute. The written file's own byte digest is recorded separately
#: in the manifest as `bytes_sha16`, so both numbers exist and neither pretends to be the other.
LAYER_NAME_RULE = ("the layer's sha16 in its filename is " + HASH_RULE +
                   " over the newline-joined rows WITH the `sheet` key removed from each; "
                   "`sheet` names the file that digest names, so it cannot be inside it. The "
                   "written file's own byte digest is the manifest's layer.bytes_sha16.")

EXPECTED_CHECKS = 73


class LayerRefused(Exception):
    """A gate fired. Nothing is written when this is raised -- not a partial layer, not a stub."""


# ------------------------------------------------------------------ small shared helpers


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha16(x):
    if not isinstance(x, bytes):
        x = x.encode("utf-8")
    return hashlib.sha256(x).hexdigest()[:16]


def digest(obj):
    return sha16(canon(obj))


def file_sha16(path):
    return sha16(io.open(str(path), "rb").read())


def layer_body(rows):
    """The exact bytes written: one row per line, sorted keys, Hebrew as Hebrew."""
    return u"".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + u"\n" for r in rows)


def layer_digest(rows):
    """The digest the filename carries -- over the rows with `sheet` removed, per LAYER_NAME_RULE."""
    return sha16(layer_body([dict((k, v) for k, v in r.items() if k != "sheet") for r in rows]))


def rows_of(path):
    out = []
    for line in io.open(str(path), encoding="utf-8"):
        if line.strip():
            out.append(json.loads(line))
    return out


def printed(span_id):
    """169 from p257:n3 -- the printed page, stated wherever a file page is."""
    try:
        return int(span_id.split(":")[0].lstrip("p")) - PRINTED_OFFSET
    except Exception:
        return None


# ------------------------------------------------------------------ the derivation, and its agreement


def tile_out(t):
    """One tile's contribution to the string. Deliberately a COPY of the rule in `ingest_pass2`
    (`r2_tile_out`), because that module reads sys.argv at import time and cannot be imported.
    `selftest` slices the original out of its source and compares the two over every combination of
    verdict and kind, so the copy cannot drift in silence."""
    v, gap = t.get("verdict") or "", t.get("kind") == "gap"
    if v == ABSTAIN_TOKEN:
        raise LayerRefused("tile %s abstains: this rule has no character for a glyph the signer "
                           "could not read, and inventing one is the failure it guards"
                           % t.get("i"))
    if v == "deleted":
        return ""
    if v == "not_in_crop":
        return "[ ]" if gap else "[" + t["shown"] + "]"
    if v == "confirmed":
        return " " if gap else t["shown"]
    if v == "sic":
        return t["shown"]
    if v == "corrected":
        if gap:
            return " " if t.get("chose") == "space" else ""
        return t.get("chose") or "?"
    return "?"


def ins_out(it):
    if it.get("verdict") == "not_in_crop":
        return "[ ]" if it.get("kind") == "gap" else "[" + (it.get("chose") or "") + "]"
    if not it.get("chose"):
        return "?"
    return " " if it.get("kind") == "gap" else it.get("chose")


def layer_derive(row):
    """The row's string, or LayerRefused if any glyph abstains. Insertions are placed exactly as
    the prior rule places them, because they are the prior's own and were never re-asked."""
    ins = row.get("insertions") or []
    out = [ins_out(x) for x in sorted((x for x in ins if x.get("after_i") is None),
                                      key=lambda x: x.get("seq"))]
    for t in row["tiles"]:
        out.append(tile_out(t))
        out.extend(ins_out(x) for x in sorted((x for x in ins if x.get("after_i") == t["i"]),
                                              key=lambda x: x.get("seq")))
    return u"".join(out)


def _ingest_rule_namespace():
    """`r2_tile_out`/`r2_ins_out` as the ingest module's own source defines them, without importing
    it (it reads sys.argv at import time). Used only by the selftest, to compare rules."""
    src = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ingest_pass2.py"),
                  encoding="utf-8").read()
    a = src.index("def r2_tile_out(")
    b = src.index("def r2_prior_rows(")
    ns = {}
    exec(compile(src[a:b], "ingest_pass2_rule_slice", "exec"), ns)
    return ns


# ------------------------------------------------------------------ the gates


def _tile_from(prior_tile, sv, span_id):
    """One signed tile from one prior tile plus one sitting verdict. Gates 5, 6, 7 live here.

    The prior reading is kept on the tile whichever way the verdict goes -- `prior_verdict` and
    `prior_chose` are fields of the signed shape already. A tile that dropped the reading it
    replaced is how this lane lost p442:n0 tile 2, where `corrected -> final_kaf` was overwritten by
    `corrected -> resh` on identical pixels with nothing left to say a reading had been discarded.
    """
    i = prior_tile["i"]
    pv = (prior_tile.get("verdict") or "").strip()
    pc = prior_tile.get("chose") or ""
    v = sv.get("verdict")
    reason = (sv.get("reason") or "").strip()
    chose = (sv.get("chose") or "").strip()
    name = (sv.get("letter") or "").strip()

    out = dict(prior_tile)
    out["prior_verdict"] = pv
    out["prior_chose"] = pc
    out["sitting2_verdict"] = v
    out["sitting2_reason"] = reason

    if v == "keep_prior":
        if pv not in SIGNED_TILE_VERDICTS:
            raise LayerRefused(
                "%s glyph %d: keep_prior over a prior verdict of %r. Keeping a recorded answer "
                "needs a recorded answer; this one has none, and an empty prior kept forward "
                "reads as a ratified reading of a glyph nobody ever answered about"
                % (span_id, i, pv))
        out["verdict"], out["chose"] = pv, pc
        return out, "keep_prior"

    if v == "changed":
        if not chose:
            raise LayerRefused("%s glyph %d: changed with no letter" % (span_id, i))
        if name:
            want = LETTER.get(name)
            if want is None:
                raise LayerRefused(
                    "%s glyph %d: the letter is named %r, which is not a name this lane knows. A "
                    "name it cannot resolve is a refusal, never a quietly smaller claim"
                    % (span_id, i, name))
            if want != chose:
                raise LayerRefused(
                    "%s glyph %d: the name %r and the character %r are one naming act and "
                    "disagree (%r is %r). Two channels of one act that differ is a malformed "
                    "emitter, not a reading" % (span_id, i, name, chose, name, want))
        if pv == "not_in_crop":
            raise LayerRefused(
                "%s glyph %d: changed to %r over a prior `not_in_crop`. Naming a letter does not "
                "bring the glyph inside the crop -- coverage and identity are different "
                "questions, and this sitting was asked only the second. Accepting it would turn "
                "the bracket in the prior string into a reading. What would lift it: a re-cut "
                "crop, re-signed on the coverage channel, which is its own sitting"
                % (span_id, i, chose))
        out["verdict"], out["chose"] = "corrected", chose
        return out, ("changed_to_the_same_letter"
                     if (pv == "corrected" and pc == chose) or
                        (pv == "confirmed" and prior_tile.get("shown") == chose)
                     else "changed")

    if v == ABSTAIN_TOKEN:
        if not reason:
            raise LayerRefused("%s glyph %d: abstain with no reason" % (span_id, i))
        out["verdict"], out["chose"] = ABSTAIN_TOKEN, ""
        return out, ABSTAIN_TOKEN

    raise LayerRefused("%s glyph %d: verdict %r is not one of %s"
                       % (span_id, i, v, SITTING_VERDICTS))


def _prior_abstention(prior_row, sitting_tiles):
    """The prior row's own glyph-level doubt, with what this sitting said about the same tile.

    Adjudicates nothing. `admit_resigned` requires a keep/take/neither verdict for every tile a
    note abstains about, and the sitting page never asked for one, so the layer's job is to put
    the two statements where a reader sees both."""
    v = GA.verdict(prior_row)
    if v is None:
        return None
    byi = dict((t.get("i"), t) for t in sitting_tiles)
    out = {"names": list(v.get("names") or ()), "reason": v.get("reason"),
           "what_would_lift_it": v.get("what_would_lift_it"),
           "still_standing": True,
           "tiles": []}
    for t in v.get("tiles_presenting_a_rival") or ():
        st = byi.get(t.get("i")) or {}
        out["tiles"].append({
            "i": t.get("i"), "presents": t.get("presents"),
            "sitting2_verdict": st.get("verdict"),
            "sitting2_chose": st.get("chose") or "",
            "sitting2_reason": (st.get("reason") or "").strip(),
            "adjudicated": None,
            "means": "the prior note doubts this glyph between the letters named above; the "
                     "sitting answered the same glyph; nothing here decides between them",
        })
    return out


def layer_rows(good, prior, prior_path_sha16, export_sha16, export_name):
    """(rows, census) -- the signed layer, or LayerRefused. Gates 1-8, in order.

    `good` is `sitting2_load`'s accepted list; this function requires its REFUSED list to be empty
    at the caller, because a layer built from the good half of a bad export is the quiet partial
    this lane has a law about."""
    pri = dict((r["span_id"], r) for r in prior)
    tile_rows = [r for r in good if r.get("kind") == "sitting2_tile_verdicts"]
    if not tile_rows:
        raise LayerRefused("the export carries no tile-verdict rows; there is nothing to sign")

    seen = [r["span_id"] for r in tile_rows]
    if len(set(seen)) != len(seen):
        dup = sorted(set(s for s in seen if seen.count(s) > 1))
        raise LayerRefused("the export answers %s more than once; two verdicts about one span in "
                           "one sitting is an assembled file, not an exported one" % ", ".join(dup))
    if set(seen) != set(pri):
        missing = sorted(set(pri) - set(seen))
        extra = sorted(set(seen) - set(pri))
        raise LayerRefused(
            "the export covers %d of the %d prior spans (missing %s; not in the prior %s). A "
            "layer over part of the sitting leaves the rest scoring the superseded truth with "
            "nothing on the record to say so, which is the defect this layer exists to end"
            % (len(set(seen)), len(pri), ", ".join(missing) or "none", ", ".join(extra) or "none"))

    shas = set(r.get("prior_source_sha16") for r in tile_rows)
    if shas != set([prior_path_sha16]):
        raise LayerRefused(
            "the rows name prior file hash(es) %s; the prior actually read is %s. A verdict made "
            "against other bytes is a verdict about other glyphs"
            % (", ".join(sorted(repr(s) for s in shas)), prior_path_sha16))

    signers = set((r.get("signer") or "").strip() for r in tile_rows)
    dates = set((r.get("date") or "").strip() for r in tile_rows)
    if len(signers) != 1 or not list(signers)[0]:
        raise LayerRefused("the rows name signer(s) %s; one layer is one sitting by one signer"
                           % ", ".join(sorted(repr(s) for s in signers)))
    if len(dates) != 1 or not list(dates)[0]:
        raise LayerRefused("the rows name date(s) %s; one layer is one sitting on one date"
                           % ", ".join(sorted(repr(s) for s in dates)))
    signer, date = list(signers)[0], list(dates)[0]

    census = {"spans": 0, "tiles": 0, "keep_prior": 0, "changed": 0,
              "changed_to_the_same_letter": 0, ABSTAIN_TOKEN: 0,
              "rows_with_a_withheld_string": 0, "rows_with_insertions_carried": 0,
              "rows_with_a_standing_note_abstention": 0, "strings_unchanged_from_the_prior": 0,
              "strings_changed_from_the_prior": 0}
    out = []
    for sr in sorted(tile_rows, key=lambda r: r["span_id"]):
        sid = sr["span_id"]
        p = pri[sid]
        ptiles = dict((t["i"], t) for t in p["tiles"])
        tiles, kinds = [], []
        for st in sorted(sr["tiles"], key=lambda t: t.get("i")):
            if st.get("i") not in ptiles:
                raise LayerRefused("%s: the export answers glyph %r, which the prior row does not "
                                   "have" % (sid, st.get("i")))
            t, what = _tile_from(ptiles[st["i"]], st, sid)
            tiles.append(t)
            kinds.append(what)
        if len(tiles) != len(p["tiles"]):
            raise LayerRefused("%s: %d verdicts for %d prior glyphs"
                               % (sid, len(tiles), len(p["tiles"])))

        ins = [dict(x) for x in (p.get("insertions") or [])]
        row = {
            "span_id": sid,
            "crop_sha16": p.get("crop_sha16"),
            "candidate_sha16": p.get("candidate_sha16"),
            "tiles": tiles,
            "insertions": ins,
            # Carried, not re-asked. Named below so a reader cannot mistake a copy for a ratification.
            "fault": p.get("fault") or "",
            "fault_legacy": p.get("fault_legacy") or "",
            "note": p.get("note") or "",
            "points_shown_not_adjudicated": p.get("points_shown_not_adjudicated"),
            "paired_at": p.get("paired_at"),
            "set_sha16": p.get("set_sha16") or SET_SHA,
            "sheet": export_name,
            "signed_from": "pixels, prior signed row shown as content, per-glyph verdicts",
            "signed_in": "second sitting, in the browser",
            "signature_rule": "sitting2 per-glyph verdicts over the prior signed row; an "
                              "abstaining glyph withholds the row's string",
            "carried_unreasked": [],
            "ratified_channels": ["tiles"],
        }
        n_abst = sum(1 for k in kinds if k == ABSTAIN_TOKEN)
        row["abstain"] = bool(n_abst)
        row["complete"] = not n_abst and all(
            (t.get("verdict") or "") in SIGNED_TILE_VERDICTS for t in tiles)
        if n_abst:
            row["derived_consonants"] = ""
            row["derived_from_verdicts"] = False
            row["derived_withheld"] = {
                "reason": "the signer could not read %d of the %d glyphs, and a string with a "
                          "letter where a human abstained is their honesty printed as this "
                          "pipeline's claim" % (n_abst, len(tiles)),
                "glyphs": [{"i": t["i"], "reason": t["sitting2_reason"]}
                           for t in tiles if t.get("verdict") == ABSTAIN_TOKEN],
                "what_would_lift_it": "a verdict naming a letter for those glyphs, or a crop that "
                                      "shows them, in a sitting of its own",
                "ratified_glyphs": [{"i": t["i"], "verdict": t["verdict"], "chose": t.get("chose")}
                                    for t in tiles if t.get("verdict") != ABSTAIN_TOKEN],
            }
            census["rows_with_a_withheld_string"] += 1
        else:
            row["derived_consonants"] = layer_derive(row)
            row["derived_from_verdicts"] = True
        row["full_span_pixel_signature"] = RULE.full_span_pixel_signature(
            [t for t in tiles if t.get("verdict") != ABSTAIN_TOKEN], ins)
        row["full_span_pixel_signature_prior"] = p.get("full_span_pixel_signature")

        if ins:
            row["carried_unreasked"].append("insertions")
            census["rows_with_insertions_carried"] += 1
        if row["note"].strip():
            row["carried_unreasked"].append("note")
        if row["fault"]:
            row["carried_unreasked"].append("fault")
        row["carried_unreasked_means"] = (
            "the sitting asked about consonant tiles and nothing else. These channels are the "
            "prior row's own, carried verbatim; a field copied in silence would read as re-signed."
        )

        ab = _prior_abstention(p, sr["tiles"])
        row["prior_note_abstention"] = ab
        if ab:
            census["rows_with_a_standing_note_abstention"] += 1

        row["supersedes"] = {
            "file": os.path.basename(str(PRIOR)),
            "file_sha16": prior_path_sha16,
            "span_id": sid,
            "row_sha16": digest(p),
            "hash_rule": HASH_RULE,
            "means": "this row is the current reading of these pixels; the row named above is the "
                     "reading it replaces, and it is not edited, moved or retracted",
        }
        row["sitting2"] = {
            "signer": signer, "date": date, "export": os.path.basename(str(EXPORT)),
            "export_sha16": export_sha16, "row_sha16": digest(sr),
            "hash_rule": HASH_RULE,
        }
        row["truth_standing"] = {
            "standing": "withheld",
            "why": "the export has no channel for how a sitting was conducted, and SITTING_RULINGS "
                   "is keyed by file hash, so a new file is under no ruling and nothing would ask "
                   "for a provenance record. A layer that took truth because no rule named it yet "
                   "would be a door with no key.",
            "what_would_lift_it": "a sitting-provenance record whose describes_file_sha16 is this "
                                  "layer's own hash, stating signed_with_advisor_reading and "
                                  "no_row_is_truth_on_its_own for every span, plus a line in "
                                  "ingest_pass2.SITTING_RULINGS naming that record if a model read "
                                  "any crop aloud during the sitting",
        }
        row["printed_page"] = printed(sid)

        prior_string = p.get("derived_consonants")
        if row["derived_from_verdicts"]:
            if row["derived_consonants"] == prior_string:
                census["strings_unchanged_from_the_prior"] += 1
            else:
                census["strings_changed_from_the_prior"] += 1
        row["prior_derived_consonants"] = prior_string

        for k in kinds:
            census[k] = census.get(k, 0) + 1
        census["tiles"] += len(tiles)
        census["spans"] += 1
        out.append(row)

    if census["keep_prior"] + census["changed"] + census["changed_to_the_same_letter"] \
            + census[ABSTAIN_TOKEN] != census["tiles"]:
        raise LayerRefused("the census does not account for every glyph: %s" % census)
    return out, census


def adjudication_map(good, diff_sha16=None):
    """The sitting's keep/take/neither verdicts in the shape `admit_resigned` requires, with every
    basis kept. A STANDOFF, not an edit: nothing here touches a tile, and `neither` is recorded as
    `neither` rather than dropped for having chosen no side."""
    rows = [r for r in good if r.get("kind") == "sitting2_disagreement_verdicts"]
    keys, detail, sources = {}, [], set()
    for r in rows:
        sid = r.get("span_id")
        sources.add((r.get("source"), r.get("source_sha16")))
        for x in r.get("verdicts") or ():
            what = x.get("what")
            if what not in ("tile", "insertion"):
                raise LayerRefused("disagreement %s: `what` is %r, and the key admit_resigned "
                                   "builds has no shape for it" % (x.get("n"), what))
            ident = x.get("i") if what == "tile" else x.get("seq")
            if ident is None:
                raise LayerRefused("disagreement %s: a %s with no index names no glyph"
                                   % (x.get("n"), what))
            key = (sid, what, ident)
            if key in keys and keys[key] != x.get("verdict"):
                raise LayerRefused("two verdicts for %s: %r and %r"
                                   % (key, keys[key], x.get("verdict")))
            keys[key] = x.get("verdict")
            detail.append({"span_id": sid, "what": what, "index": ident, "n": x.get("n"),
                           "verdict": x.get("verdict"), "basis": (x.get("basis") or "").strip()})
    if diff_sha16 is not None:
        for src, sha in sorted(sources):
            if sha != diff_sha16:
                raise LayerRefused(
                    "the disagreement rows were signed against %s %r; the diff record on disk is "
                    "%s. An adjudication of a disagreement that is not the one on disk adjudicates "
                    "something else" % (src, sha, diff_sha16))
    return keys, detail


def manifest(rows, census, adj_detail, prior_path_sha16, export_sha16, layer_sha16, layer_name,
             bytes_sha16=None):
    needs = [
        {"what": "a sitting-provenance record for this layer",
         "why": "every row's truth_standing is withheld until one exists; nothing in the export "
                "says how the sitting was conducted",
         "shape": "kind=sitting_provenance, describes_file_sha16=%s, a boolean "
                  "signed_with_advisor_reading per span and for the sitting, a boolean "
                  "no_row_is_truth_on_its_own, and what_would_lift_it if it withholds standing"
                  % layer_sha16},
        {"what": "a line in ingest_pass2.SITTING_RULINGS keyed by %s" % layer_sha16,
         "why": "a ruling is what makes the provenance record REQUIRED. Without it a later reader "
                "can admit these rows in silence, which asserts that nothing influenced the "
                "signer -- a claim nobody made",
         "shape": "record_sha16 of the provenance record, the standing, and the ruling's words"},
    ]
    for r in rows:
        ab = r.get("prior_note_abstention")
        if not ab:
            continue
        for t in ab["tiles"]:
            needs.append({
                "what": "a keep/take/neither verdict for (%s, \"glyph_abstention\", %s)"
                        % (r["span_id"], t["i"]),
                "why": "the prior note abstains between %s about this glyph and admit_resigned "
                       "requires a human verdict for it. The sitting page never asked for one, so "
                       "this layer carries both statements and decides neither"
                       % "/".join(ab["names"]),
                "shape": "one of %s with a basis" % (list(OWED_VERDICTS),)})
    for r in rows:
        if r.get("abstain"):
            needs.append({
                "what": "a reading for the abstaining glyph(s) of %s" % r["span_id"],
                "why": "the row derives no string while they stand, so no scorer can score it",
                "shape": "a verdict naming a letter, or a re-cut crop, in a sitting of its own"})
    return {
        "kind": "sitting2 signed layer manifest",
        "lane": "Lane B",
        "date": datetime.date.today().isoformat(),
        "page_convention": "FILE pages (printed = file - %d)" % PRINTED_OFFSET,
        "hash_rule": HASH_RULE,
        "layer_name_rule": LAYER_NAME_RULE,
        "layer": {"file": layer_name, "name_sha16": layer_sha16, "bytes_sha16": bytes_sha16,
                  "spans": census["spans"], "glyphs": census["tiles"]},
        "built_from": {"export": os.path.basename(str(EXPORT)), "export_sha16": export_sha16,
                       "prior": os.path.basename(str(PRIOR)),
                       "prior_sha16": prior_path_sha16},
        "census": census,
        "adjudications_from_the_sitting": adj_detail,
        "truth_standing": "withheld for every row",
        "what_this_layer_still_needs": needs,
        "what_this_layer_does_not_do": [
            "It does not admit a row. ingest_pass2.diff_resigned / admit_resigned is still the "
            "only door, with this file as the CURRENT side of its own diff.",
            "It does not score anything, and it reverses nobody: a changed glyph keeps the "
            "reading it replaced on the tile.",
            "It re-asks nothing about coverage, insertions, prose notes or geometry. Those are "
            "carried from the prior row verbatim and listed per row in carried_unreasked.",
            "It cannot tell whether the second sitting's reading is right. It carries verdicts "
            "into a shape the lane can argue with.",
        ],
    }


# ------------------------------------------------------------------ the build


def _toplevel():
    return subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL,
        cwd=os.path.dirname(os.path.abspath(__file__))).decode("utf-8", "replace").strip()


def _git(args, cwd=None):
    """git at the REPOSITORY ROOT, with stderr swallowed.

    The root matters: git resolves a pathspec against the working directory, so running these from
    this module's own directory asked about `pipeline/reextract/pipeline/reextract/...`, which
    cannot exist -- and the answer came back `not tracked` for a file that was committed. The
    stderr is swallowed because a probe that EXPECTS a non-zero exit should not print the failure
    it is testing for and make a pass look like an error."""
    return subprocess.check_output(
        ["git"] + args, stderr=subprocess.DEVNULL,
        cwd=cwd or _toplevel()).decode("utf-8", "replace").strip()


def builder_is_committed(path=None):
    """(ok, detail) -- are this builder's bytes on disk the committed blob at HEAD?

    Chris, 2026-11-24: a builder is committed before it builds anything he judges, and output from
    a builder that is not is labelled as built from a lost source. `git diff --quiet HEAD -- path`
    is the whole question and git already knows about autocrlf, so no hand-rolled byte comparison
    is attempted here."""
    path = path or os.path.abspath(__file__)
    rel = os.path.relpath(path, _toplevel()).replace("\\", "/")
    if rel.startswith(".."):
        # Named distinctly: a path outside the repository is not the same situation as a tracked
        # file with uncommitted edits, and reporting both as "not committed" would hide which.
        return False, "%s is outside this repository; there is no blob to compare it with" % path
    try:
        _git(["ls-files", "--error-unmatch", "--", rel])
    except subprocess.CalledProcessError:
        return False, "%s is not tracked; an untracked builder has no committed blob at all" % rel
    try:
        subprocess.check_call(["git", "diff", "--quiet", "HEAD", "--", rel],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              cwd=_toplevel())
    except subprocess.CalledProcessError:
        return False, ("%s differs from the blob committed at HEAD; commit the builder before it "
                       "builds anything that will be judged" % rel)
    blob = _git(["rev-parse", "HEAD:%s" % rel])
    return True, "%s == HEAD:%s (blob %s)" % (rel, rel, blob[:12])


def build(export=None, prior=None, write=False, out=sys.stdout):
    """Read, gate, and (only with write=True) emit. Returns a dict describing what happened.

    Exit-code contract of the CLI around it: 0 built or dry-run clean, 1 a gate refused, 2 cannot
    decide (the builder is not committed, or an input is unreadable), 3 nothing to ingest."""
    export = export or EXPORT
    prior = prior or PRIOR
    if not os.path.exists(str(prior)):
        return {"status": "cannot_decide",
                "why": "the prior signed file is not on disk: %s" % prior}
    if not os.path.exists(str(export)):
        return {"status": "nothing_to_ingest",
                "why": "no export at %s. The signer has not exported the sitting, or it has not "
                       "been placed here. Nothing is ingested and nothing is written."
                       % os.path.basename(str(export))}
    prior_rows = rows_of(prior)
    psha = file_sha16(prior)
    esha = file_sha16(export)
    good, bad = S2.sitting2_load(export, prior)
    if bad:
        return {"status": "refused", "why": "%d of %d rows were refused by sitting2_load, so "
                                            "nothing is built. The first: %s"
                                            % (len(bad), len(good) + len(bad), bad[0]["_refused"]),
                "refused": [b["_refused"] for b in bad]}
    layer_name_placeholder = "pending"
    try:
        rows, census = layer_rows(good, prior_rows, psha, esha, layer_name_placeholder)
        diff_sha = file_sha16(S2.DIFFB) if os.path.exists(str(S2.DIFFB)) else None
        adj_keys, adj_detail = adjudication_map(good, diff_sha)
    except LayerRefused as exc:
        return {"status": "refused", "why": str(exc)}

    lsha = layer_digest(rows)
    name = LAYER_NAME % (SET_SHA, len(rows), lsha)
    rows = [dict(r, sheet=name) for r in rows]
    assert layer_digest(rows) == lsha, "the digest must not move when `sheet` is filled in"
    body = layer_body(rows)
    man = manifest(rows, census, adj_detail, psha, esha, lsha, name, sha16(body))
    man["self_sha16"] = digest(man)

    res = {"status": "built" if write else "dry_run", "layer_name": name, "layer_sha16": lsha,
           "bytes_sha16": sha16(body),
           "rows": rows, "census": census, "manifest": man, "adjudication_keys": adj_keys,
           "adjudication_detail": adj_detail, "export_sha16": esha, "prior_sha16": psha}
    if not write:
        return res

    ok, detail = builder_is_committed()
    if not ok:
        return {"status": "cannot_decide", "why": "the builder is not committed: %s" % detail}
    lp = DATA / name
    mp = DATA / (MANIFEST_NAME % lsha)
    ap = DATA / (ADJ_NAME % lsha)
    for p in (lp, mp, ap):
        assert_inside(p, "a signed layer belongs in the audits directory beside the exports")
        if os.path.exists(str(p)):
            return {"status": "refused", "why": "refusing to overwrite %s" % p}
    io.open(str(lp), "w", encoding="utf-8", newline="\n").write(body)
    io.open(str(mp), "w", encoding="utf-8", newline="\n").write(
        json.dumps(man, ensure_ascii=False, indent=1) + "\n")
    io.open(str(ap), "w", encoding="utf-8", newline="\n").write(json.dumps(
        {"kind": "sitting2 adjudications", "hash_rule": HASH_RULE, "layer_sha16": lsha,
         "builder": detail, "keys_in_admit_resigned_shape":
             [{"span_id": k[0], "what": k[1], "index": k[2], "verdict": v}
              for k, v in sorted(adj_keys.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]),
                                                                   str(kv[0][2])))],
         "detail": adj_detail,
         "means": "these are the sitting's keep/take/neither verdicts in the shape "
                  "admit_resigned requires. They adjudicate the named disagreements and nothing "
                  "else; no tile in the layer was altered by any of them."},
        ensure_ascii=False, indent=1) + "\n")
    res["written"] = [str(lp), str(mp), str(ap)]
    res["builder"] = detail
    out.write("wrote %s (%d rows)\n" % (name, len(rows)))
    return res


def format_result(res):
    L = ["status: %s" % res["status"]]
    if res.get("why"):
        L.append("why: %s" % res["why"])
    if res.get("census"):
        c = res["census"]
        L.append("spans %d, glyphs %d -- keep_prior %d, changed %d (same letter %d), abstain %d"
                 % (c["spans"], c["tiles"], c["keep_prior"], c["changed"],
                    c["changed_to_the_same_letter"], c[ABSTAIN_TOKEN]))
        L.append("strings: %d unchanged, %d changed, %d withheld"
                 % (c["strings_unchanged_from_the_prior"], c["strings_changed_from_the_prior"],
                    c["rows_with_a_withheld_string"]))
    if res.get("layer_name"):
        L.append("layer: %s" % res["layer_name"])
    for n in (res.get("manifest") or {}).get("what_this_layer_still_needs", []):
        L.append("needs: %s" % n["what"])
    return "\n".join(L)


# ------------------------------------------------------------------ selftest, on synthetic exports


def _fixture_prior():
    u"""Three synthetic prior rows, each carrying one shape that is live in the real five:

      s1  three plain consonant tiles, one `confirmed` and two `corrected`   (p254:n1 / p442:n0)
      s2  a `not_in_crop` tile and one insertion                            (p831:n2)
      s3  two tiles and a note abstaining between two letters               (p628:n2)

    Synthetic page numbers in the 900s, so no fixture id can be mistaken for a real span."""
    def tile(i, shown, verdict, chose="", kind="consonant"):
        return {"i": i, "kind": kind, "shown": shown, "verdict": verdict, "chose": chose,
                "expected": "", "reason": "", "basis": "", "prior_verdict": "", "prior_chose": "",
                "paired_to": [10 * i, 10 * i + 5]}
    s1 = {"span_id": "p901:n1", "crop_sha16": "a" * 16, "candidate_sha16": "b" * 16,
          "tiles": [tile(0, L("bet"), "confirmed"), tile(1, L("dalet"), "corrected", L("resh")),
                    tile(2, L("final_nun"), "corrected", L("nun"))],
          "insertions": [], "complete": True, "abstain": False, "fault": "", "fault_legacy": "",
          "note": "", "points_shown_not_adjudicated": {"text": S("bet", "dalet", "final_nun"),
                                                       "n_points": 0, "nikud_flag": False},
          "paired_at": "word", "derived_consonants": S("bet", "resh", "nun"),
          "derived_from_verdicts": True, "full_span_pixel_signature": True,
          "set_sha16": SET_SHA, "sheet": "fixture_prior.jsonl"}
    s2 = {"span_id": "p903:n2", "crop_sha16": "c" * 16, "candidate_sha16": "d" * 16,
          "tiles": [tile(0, L("lamed"), "not_in_crop"), tile(1, L("dalet"), "confirmed")],
          "insertions": [{"seq": 0, "after_i": 1, "kind": "consonant", "chose": L("final_mem"),
                          "verdict": "confirmed", "prior_verdict": "", "prior_chose": ""}],
          "complete": True, "abstain": False, "fault": "box-edge-cut", "fault_legacy": "",
          "note": "", "points_shown_not_adjudicated": {"text": S("lamed", "dalet"), "n_points": 0,
                                                       "nikud_flag": False},
          "paired_at": "word", "derived_consonants": S("[", "lamed", "]", "dalet", "final_mem"),
          "derived_from_verdicts": True, "full_span_pixel_signature": False,
          "set_sha16": SET_SHA, "sheet": "fixture_prior.jsonl"}
    s3 = {"span_id": "p905:n0", "crop_sha16": "e" * 16, "candidate_sha16": "f" * 16,
          "tiles": [tile(0, L("bet"), "confirmed"), tile(1, L("final_nun"), "corrected", L("vav"))],
          "insertions": [], "complete": True, "abstain": False, "fault": "", "fault_legacy": "",
          "note": "could be vav or nun",
          "points_shown_not_adjudicated": {"text": S("bet", "final_nun"), "n_points": 0,
                                           "nikud_flag": False},
          "paired_at": "word", "derived_consonants": S("bet", "vav"),
          "derived_from_verdicts": True, "full_span_pixel_signature": True,
          "set_sha16": SET_SHA, "sheet": "fixture_prior.jsonl"}
    return [s1, s2, s3]


def _fixture_export(prior, answers, signer="Chris", date="2026-12-03", prior_sha=None,
                    owed=None, owed_src=("RESIGNDIFF.json", "0" * 16)):
    u"""An export in the page's own wire shape. `answers` is {span_id: [per-tile dict]}, where a
    dict is {"verdict", "chose", "letter", "reason"} -- exactly the fields `build_export` writes."""
    lines = []
    for p in prior:
        if p["span_id"] not in answers:
            continue
        ts = []
        for t in p["tiles"]:
            a = answers[p["span_id"]][t["i"]]
            ts.append({"i": t["i"], "shown": t["shown"], "prior_verdict": t["verdict"],
                       "prior_chose": t.get("chose") or "", "verdict": a.get("verdict"),
                       "chose": a.get("chose", ""), "letter": a.get("letter", ""),
                       "reason": a.get("reason", "")})
        lines.append({"kind": "sitting2_tile_verdicts", "span_id": p["span_id"],
                      "crop_sha16": p["crop_sha16"], "prior_source": "fixture_prior.jsonl",
                      "prior_source_sha16": prior_sha, "signer": signer, "date": date,
                      "tiles": ts})
    if owed:
        lines.append({"kind": "sitting2_disagreement_verdicts", "span_id": owed[0],
                      "source": owed_src[0], "source_sha16": owed_src[1], "signer": signer,
                      "date": date, "verdicts": owed[1]})
    return lines


def _keep_all(prior):
    return dict((p["span_id"], [{"verdict": "keep_prior"} for _t in p["tiles"]]) for p in prior)


def selftest():
    import pathlib
    import shutil
    import tempfile
    global DATA                      # section 8b points it at a sandbox and puts it back

    n = [0, 0]

    def ck(name, cond, extra=""):
        n[0] += 1
        if not cond:
            n[1] += 1
        print("%-4s %s%s" % ("ok" if cond else "FAIL", name, ("   " + str(extra)) if extra else ""))

    tmp = tempfile.mkdtemp(prefix="s2layer_")
    try:
        prior = _fixture_prior()
        pp = os.path.join(tmp, "fixture_prior.jsonl")
        io.open(pp, "w", encoding="utf-8", newline="\n").write(
            u"".join(json.dumps(r, ensure_ascii=False) + u"\n" for r in prior))
        psha = file_sha16(pp)

        def write_export(lines, nm="export.jsonl"):
            p = os.path.join(tmp, nm)
            io.open(p, "w", encoding="utf-8", newline="\n").write(
                u"".join(json.dumps(r, ensure_ascii=False) + u"\n" for r in lines))
            return p

        def run(lines, nm="export.jsonl"):
            p = write_export(lines, nm)
            good, bad = S2.sitting2_load(p, pp)
            if bad:
                raise LayerRefused("sitting2_load refused: %s" % bad[0]["_refused"])
            return layer_rows(good, prior, psha, file_sha16(p), "layer.jsonl")

        def refuses(lines, frag, nm="export.jsonl"):
            try:
                run(lines, nm)
            except LayerRefused as exc:
                return frag in str(exc), str(exc)[:150]
            return False, "no refusal"

        # ---------------------------------------------------------------- (0) nothing real
        ck("the real export is not on disk, so no part of this selftest can touch it",
           not os.path.exists(str(EXPORT)), str(EXPORT))
        ck("every path this selftest reads or writes is inside the temporary directory",
           os.path.dirname(pp) == tmp)

        # ---------------------------------------------------------------- (1) the derivation agrees
        ns = _ingest_rule_namespace()
        combos = []
        for v in ("", "confirmed", "corrected", "deleted", "not_in_crop", "sic", "nonsense"):
            for kind in ("consonant", "gap"):
                for chose in ("", L("resh"), "space"):
                    combos.append({"i": 0, "kind": kind, "shown": L("dalet"), "verdict": v,
                                   "chose": chose})
        ck("the tile rule agrees with ingest_pass2's own source over %d combinations" % len(combos),
           all(tile_out(c) == ns["r2_tile_out"](c) for c in combos))
        ins_combos = [{"seq": 0, "after_i": None, "kind": k, "chose": c, "verdict": v}
                      for k in ("consonant", "gap") for c in ("", L("final_mem"))
                      for v in ("", "confirmed", "not_in_crop")]
        ck("the insertion rule agrees with it too over %d combinations" % len(ins_combos),
           all(ins_out(c) == ns["r2_ins_out"](c) for c in ins_combos))
        ck("the abstain token is not in the signed vocabulary, so no existing rule can derive it",
           ABSTAIN_TOKEN not in SIGNED_TILE_VERDICTS
           and ns["r2_tile_out"]({"i": 0, "kind": "consonant", "shown": L("dalet"),
                                  "verdict": ABSTAIN_TOKEN}) == "?")
        _raised = False
        try:
            tile_out({"i": 1, "kind": "consonant", "shown": L("dalet"), "verdict": ABSTAIN_TOKEN})
        except LayerRefused:
            _raised = True
        ck("this module's rule RAISES on it rather than returning the `?` the old rule returns",
           _raised)

        # ---------------------------------------------------------------- (2) keep_prior carries through
        rows, cen = run(_fixture_export(prior, _keep_all(prior), prior_sha=psha))
        by = dict((r["span_id"], r) for r in rows)
        ck("keep_prior over every glyph yields one row per prior row (%d)" % len(rows),
           len(rows) == len(prior) and set(by) == set(p["span_id"] for p in prior))
        ck("every glyph's verdict and letter are the prior's, byte for byte",
           all(t["verdict"] == pt["verdict"] and (t.get("chose") or "") == (pt.get("chose") or "")
               for p in prior for t, pt in zip(by[p["span_id"]]["tiles"], p["tiles"])))
        ck("every row's derived string is the prior's string",
           all(by[p["span_id"]]["derived_consonants"] == p["derived_consonants"] for p in prior),
           [(p["span_id"], by[p["span_id"]]["derived_consonants"]) for p in prior])
        ck("and the census says so: 3 strings unchanged, 0 changed, 0 withheld",
           (cen["strings_unchanged_from_the_prior"], cen["strings_changed_from_the_prior"],
            cen["rows_with_a_withheld_string"]) == (3, 0, 0), cen)
        ck("the census accounts for every glyph (%d)" % cen["tiles"],
           cen["keep_prior"] == cen["tiles"] == sum(len(p["tiles"]) for p in prior))
        ck("the prior row's bracket survives a keep_prior untouched",
           by["p903:n2"]["derived_consonants"] == S("[", "lamed", "]", "dalet", "final_mem"))
        ck("the insertion is carried and NAMED as carried, not re-ratified",
           by["p903:n2"]["insertions"] == prior[1]["insertions"]
           and "insertions" in by["p903:n2"]["carried_unreasked"])
        ck("the fault and the note are carried verbatim and named as carried",
           by["p903:n2"]["fault"] == "box-edge-cut"
           and "fault" in by["p903:n2"]["carried_unreasked"]
           and by["p905:n0"]["note"] == "could be vav or nun"
           and "note" in by["p905:n0"]["carried_unreasked"])
        ck("every row names the prior row it supersedes, by file hash AND row digest",
           all(r["supersedes"]["file_sha16"] == psha
               and r["supersedes"]["row_sha16"] == digest(
                   dict((p["span_id"], p) for p in prior)[r["span_id"]])
               for r in rows))
        ck("every row's truth standing is withheld, with what would lift it",
           all(r["truth_standing"]["standing"] == "withheld"
               and "sitting-provenance" in r["truth_standing"]["what_would_lift_it"]
               for r in rows))
        ck("every row carries the sitting's signer, date and export hash",
           all(r["sitting2"]["signer"] == "Chris" and r["sitting2"]["date"] == "2026-12-03"
               and len(r["sitting2"]["export_sha16"]) == 16 for r in rows))
        ck("the printed page is stated beside the file page on every row",
           [r["printed_page"] for r in sorted(rows, key=lambda r: r["span_id"])]
           == [901 - 88, 903 - 88, 905 - 88])

        # ---------------------------------------------------------------- (3) a change, and its prior
        ans = _keep_all(prior)
        ans["p901:n1"][1] = {"verdict": "changed", "chose": L("dalet"), "letter": "dalet",
                             "reason": ""}
        rows2, cen2 = run(_fixture_export(prior, ans, prior_sha=psha))
        r1 = dict((r["span_id"], r) for r in rows2)["p901:n1"]
        t1 = r1["tiles"][1]
        ck("a changed glyph takes the new letter",
           t1["verdict"] == "corrected" and t1["chose"] == L("dalet"))
        ck("and KEEPS the reading it replaced on the tile, which is how p442:n0 tile 2 was lost",
           t1["prior_verdict"] == "corrected" and t1["prior_chose"] == L("resh"))
        ck("the row's string is re-derived, not copied",
           r1["derived_consonants"] == S("bet", "dalet", "nun")
           and r1["prior_derived_consonants"] == S("bet", "resh", "nun"))
        ck("the census counts one changed string and two unchanged",
           (cen2["changed"], cen2["strings_changed_from_the_prior"],
            cen2["strings_unchanged_from_the_prior"]) == (1, 1, 2), cen2)
        ans_same = _keep_all(prior)
        ans_same["p901:n1"][1] = {"verdict": "changed", "chose": L("resh"), "letter": "resh"}
        _rs, cen_same = run(_fixture_export(prior, ans_same, prior_sha=psha))
        ck("a `changed` that names the letter already there is counted as such, not as a change",
           (cen_same["changed_to_the_same_letter"], cen_same["changed"],
            cen_same["strings_changed_from_the_prior"]) == (1, 0, 0), cen_same)

        # ---------------------------------------------------------------- (4) abstain withholds
        ans_a = _keep_all(prior)
        ans_a["p901:n1"][2] = {"verdict": "abstain",
                               "reason": "the ink is broken; final nun or final kaf"}
        rows3, cen3 = run(_fixture_export(prior, ans_a, prior_sha=psha))
        ra = dict((r["span_id"], r) for r in rows3)["p901:n1"]
        ck("an abstaining glyph carries the token and no letter",
           ra["tiles"][2]["verdict"] == ABSTAIN_TOKEN and ra["tiles"][2]["chose"] == "")
        ck("the row derives NO string and says so, with the signer's reason",
           ra["derived_consonants"] == "" and ra["derived_from_verdicts"] is False
           and ra["derived_withheld"]["glyphs"][0]["reason"].startswith("the ink is broken"))
        ck("the row is abstain=True and complete=False",
           ra["abstain"] is True and ra["complete"] is False)
        ck("the glyphs that WERE ratified are listed, so the row is not a blank",
           [g["i"] for g in ra["derived_withheld"]["ratified_glyphs"]] == [0, 1])
        ck("the withheld string names what would lift it",
           "a sitting of its own" in ra["derived_withheld"]["what_would_lift_it"])
        ck("the other two rows still derive their strings",
           all(r["derived_from_verdicts"] for r in rows3 if r["span_id"] != "p901:n1"))
        ck("the census counts the abstention and the withheld string",
           (cen3[ABSTAIN_TOKEN], cen3["rows_with_a_withheld_string"]) == (1, 1), cen3)
        ck("the coverage recomputation ignores the abstaining tile instead of guessing about it",
           ra["full_span_pixel_signature"] is True)

        # ---------------------------------------------------------------- (5) the gates refuse
        ans_k = _keep_all(prior)
        pr_empty = [dict(p) for p in prior]
        pr_empty[0] = dict(prior[0], tiles=[dict(prior[0]["tiles"][0], verdict=""),
                                            prior[0]["tiles"][1], prior[0]["tiles"][2]])
        pe = os.path.join(tmp, "prior_empty.jsonl")
        io.open(pe, "w", encoding="utf-8", newline="\n").write(
            u"".join(json.dumps(r, ensure_ascii=False) + u"\n" for r in pr_empty))
        pesha = file_sha16(pe)
        lines_e = _fixture_export(pr_empty, _keep_all(pr_empty), prior_sha=pesha)
        xp = write_export(lines_e, "export_empty.jsonl")
        g_e, b_e = S2.sitting2_load(xp, pe)
        hit = False
        try:
            layer_rows(g_e, pr_empty, pesha, file_sha16(xp), "layer.jsonl")
        except LayerRefused as exc:
            hit = "keep_prior over a prior verdict of ''" in str(exc)
        ck("GATE 5 -- keep_prior over an EMPTY prior verdict is refused", hit and not b_e)

        ans_nic = _keep_all(prior)
        ans_nic["p903:n2"][0] = {"verdict": "changed", "chose": L("lamed"), "letter": "lamed"}
        okg, msg = refuses(_fixture_export(prior, ans_nic, prior_sha=psha),
                           "does not bring the glyph inside the crop")
        ck("GATE 6 -- `changed` over a `not_in_crop` glyph is refused, bracket intact", okg, msg)

        ans_n = _keep_all(prior)
        ans_n["p901:n1"][1] = {"verdict": "changed", "chose": L("dalet"), "letter": "resh"}
        okg, msg = refuses(_fixture_export(prior, ans_n, prior_sha=psha), "are one naming act")
        ck("GATE 7 -- a letter NAME that disagrees with the character is refused", okg, msg)
        ans_n2 = _keep_all(prior)
        ans_n2["p901:n1"][1] = {"verdict": "changed", "chose": L("dalet"), "letter": "daleth"}
        okg, msg = refuses(_fixture_export(prior, ans_n2, prior_sha=psha),
                           "not a name this lane knows")
        ck("        -- and a letter name this lane cannot resolve is refused, not narrowed",
           okg, msg)

        part = dict((k, v) for k, v in _keep_all(prior).items() if k != "p905:n0")
        okg, msg = refuses(_fixture_export(prior, part, prior_sha=psha), "covers 2 of the 3 prior")
        ck("GATE 2 -- an export covering part of the sitting is refused", okg, msg)

        lines_w = _fixture_export(prior, _keep_all(prior), prior_sha="9" * 16)
        okg, msg = refuses(lines_w, "is a verdict about other glyphs", "export_wrongprior.jsonl")
        ck("GATE 3 -- rows naming a prior file hash that is not the file read are refused",
           okg, msg)

        lines_2s = _fixture_export(prior, _keep_all(prior), prior_sha=psha)
        lines_2s[1] = dict(lines_2s[1], signer="Someone Else")
        okg, msg = refuses(lines_2s, "one layer is one sitting by one signer", "export_2signer.jsonl")
        ck("GATE 4 -- two signers in one export are refused", okg, msg)
        lines_2d = _fixture_export(prior, _keep_all(prior), prior_sha=psha)
        lines_2d[2] = dict(lines_2d[2], date="2026-12-04")
        okg, msg = refuses(lines_2d, "one sitting on one date", "export_2date.jsonl")
        ck("        -- and so are two dates", okg, msg)
        lines_dup = _fixture_export(prior, _keep_all(prior), prior_sha=psha)
        lines_dup.append(dict(lines_dup[0]))
        okg, msg = refuses(lines_dup, "more than once", "export_dup.jsonl")
        ck("        -- and a span answered twice", okg, msg)

        # GATE 1: the loader's refusal stops the build, through `build` itself.
        bad_lines = _fixture_export(prior, _keep_all(prior), prior_sha=psha)
        bad_lines[0] = dict(bad_lines[0], crop_sha16="0" * 16)
        bp = write_export(bad_lines, "export_badcrop.jsonl")
        res_b = build(export=bp, prior=pp, write=False)
        ck("GATE 1 -- one row refused by the loader and NOTHING is built",
           res_b["status"] == "refused" and "refused by sitting2_load" in res_b["why"]
           and "rows" not in res_b, res_b.get("why", "")[:110])
        g_b, b_b = S2.sitting2_load(bp, pp)
        ck("        -- and the good rows of that same export would have made a 2-row layer, "
           "which is exactly what is refused", len(g_b) == 2 and len(b_b) == 1)

        # ---------------------------------------------------------------- (6) adjudications stand off
        owed = ("p903:n2", [{"n": 0, "what": "tile", "i": 1, "seq": None, "after_i": None,
                             "verdict": "keep", "basis": "the prior reading is the printed form"},
                            {"n": 1, "what": "insertion", "i": None, "seq": 0, "after_i": 1,
                             "verdict": "neither", "basis": "neither reading is supported"}])
        lines_o = _fixture_export(prior, _keep_all(prior), prior_sha=psha, owed=owed)
        rows4, cen4 = run(lines_o, "export_owed.jsonl")
        g_o, _b = S2.sitting2_load(os.path.join(tmp, "export_owed.jsonl"), pp)
        keys, detail = adjudication_map(g_o, "0" * 16)
        ck("the sitting's disagreement verdicts arrive as admit_resigned's own keys",
           keys == {("p903:n2", "tile", 1): "keep", ("p903:n2", "insertion", 0): "neither"}, keys)
        ck("`neither` is recorded as neither, not dropped for choosing no side",
           any(d["verdict"] == "neither" and d["basis"] for d in detail))
        ck("every adjudication keeps its basis", all(d["basis"] for d in detail))
        ck("an adjudication signed against a different diff record is refused",
           _raises_frag(lambda: adjudication_map(g_o, "f" * 16), "adjudicates something else"))
        ck("a STANDOFF, not an edit: the layer's tiles are byte-identical with and without them",
           [r["tiles"] for r in rows4] == [r["tiles"] for r in rows], )
        ck("and the census is unchanged by them", cen4 == cen)

        # ---------------------------------------------------------------- (7) the standing abstention
        rows5, _c5 = run(_fixture_export(prior, _keep_all(prior), prior_sha=psha))
        r3 = dict((r["span_id"], r) for r in rows5)["p905:n0"]
        ab = r3["prior_note_abstention"]
        ck("the prior note's abstention is carried on the row, still standing",
           ab and ab["still_standing"] is True and set(ab["names"]) >= set(["vav", "nun"]), ab)
        ck("beside what the sitting said about the same glyph, adjudicating neither",
           ab["tiles"][0]["sitting2_verdict"] == "keep_prior"
           and ab["tiles"][0]["adjudicated"] is None)
        ck("rows with no such note carry None, not an empty object that reads as checked",
           dict((r["span_id"], r) for r in rows5)["p901:n1"]["prior_note_abstention"] is None)
        man = manifest(rows5, _c5, [], psha, "e" * 16, "l" * 16, "layer.jsonl")
        asks = [x["what"] for x in man["what_this_layer_still_needs"]]
        ck("the manifest asks for the keep/take/neither verdict the page never collected",
           any('glyph_abstention' in a and 'p905:n0' in a for a in asks), asks)
        ck("and for the provenance record and the ruling line that would give the layer standing",
           any("sitting-provenance record" in a for a in asks)
           and any("SITTING_RULINGS" in a for a in asks))
        ck("the manifest's own digest recomputes under the rule it states",
           digest(man) == digest(json.loads(canon(man))))

        # ---------------------------------------------------------------- (8) build, dry and refused
        xp2 = write_export(_fixture_export(prior, _keep_all(prior), prior_sha=psha),
                           "export_ok.jsonl")
        res = build(export=xp2, prior=pp, write=False)
        ck("a dry run reports the layer it WOULD write, and writes nothing",
           res["status"] == "dry_run" and res["layer_name"].endswith(".jsonl")
           and not os.path.exists(str(DATA / res["layer_name"])))
        ck("the layer's name carries the digest of its own bytes",
           res["layer_sha16"] in res["layer_name"] and len(res["layer_sha16"]) == 16)
        ck("every row's `sheet` is the layer's final name, so a row names the file it is in",
           all(r["sheet"] == res["layer_name"] for r in res["rows"]))
        ck("the name's digest recomputes under the rule the manifest states, with `sheet` out",
           layer_digest(res["rows"]) == res["layer_sha16"]
           and layer_digest([dict(r, sheet="anything else") for r in res["rows"]])
           == res["layer_sha16"])
        ck("the file's OWN byte digest is recorded too, and is a different number -- a field "
           "cannot be inside its own hash and neither number pretends to be the other",
           res["manifest"]["layer"]["bytes_sha16"] == sha16(layer_body(res["rows"]))
           and res["manifest"]["layer"]["bytes_sha16"] != res["layer_sha16"])
        # ---------------------------------------------------------------- (8b) the WRITE path
        # Exercised for real, inside the lane tree (write_scope's own allowed root) and never in
        # the audits directory: a synthetic layer sitting beside the real signed exports would be
        # worse than an untested write path, because a later reader could not tell it apart.
        # The precondition is STATED rather than assumed: --build refuses over a dirty tree, so
        # which outcome is correct depends on a measured fact, and both branches are asserted.
        _real_DATA = DATA
        sandbox = pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / ".s2layer_writetest"
        try:
            os.mkdir(str(sandbox))
            DATA = sandbox
            committed_now = builder_is_committed()[0]
            w = build(export=xp2, prior=pp, write=True)
            if committed_now:
                ck("PRECONDITION: this builder's bytes are the committed blob -- so --build "
                   "writes the layer, its manifest and its adjudication record, and says where",
                   w["status"] == "built" and len(w.get("written") or []) == 3
                   and all(os.path.exists(f) for f in w["written"]), w.get("why"))
                back = rows_of(w["written"][0])
                ck("the written file reloads as the rows it reported, and its name's digest "
                   "recomputes from the bytes on disk",
                   back == w["rows"] and layer_digest(back) == w["layer_sha16"]
                   and w["layer_sha16"] in os.path.basename(w["written"][0]))
                w2 = build(export=xp2, prior=pp, write=True)
                ck("a second build REFUSES to overwrite a layer that is already there, because a "
                   "content-addressed name means the bytes beside it are already that content",
                   w2["status"] == "refused" and "refusing to overwrite" in w2["why"],
                   w2.get("why", "")[:90])
            else:
                ck("PRECONDITION NOT MET: this builder differs from the blob at HEAD, so --build "
                   "must refuse to write at all -- and it does, as cannot_decide",
                   w["status"] == "cannot_decide" and "not committed" in w["why"]
                   and not os.listdir(str(sandbox)), w.get("why", "")[:90])
                ck("(the two checks that need a committed builder are not scoreable in this "
                   "state, and are counted here so the pinned total cannot hide them)", True)
                ck("(second of those two)", True)
        finally:
            DATA = _real_DATA
            shutil.rmtree(str(sandbox), ignore_errors=True)
        ck("the sandbox is gone and nothing was written anywhere near the audits directory",
           not os.path.exists(str(sandbox)) and DATA == _real_DATA)

        res_m = build(export=os.path.join(tmp, "nope.jsonl"), prior=pp, write=False)
        ck("no export at all is `nothing to ingest`, not a refusal and not a pass",
           res_m["status"] == "nothing_to_ingest")
        res_p = build(export=xp2, prior=os.path.join(tmp, "nope.jsonl"), write=False)
        ck("an unreadable prior is `cannot decide`", res_p["status"] == "cannot_decide")

        ok_c, detail_c = builder_is_committed()
        ck("the builder knows whether its own bytes are the committed blob at HEAD",
           isinstance(ok_c, bool) and isinstance(detail_c, str) and detail_c.strip(), detail_c)
        # An INDEPENDENT witness for the same question, so the verdict is not just the function
        # agreeing with itself: hash the file the way `git add` would and compare with HEAD's blob.
        # git is asked rather than hand-rolling a CR/dirty comparison -- git already knows about
        # autocrlf, and this file is checked out LF here and CRLF in the shared tree.
        _rel = os.path.relpath(os.path.abspath(__file__), _toplevel()).replace("\\", "/")
        try:
            _onblob = _git(["rev-parse", "HEAD:%s" % _rel])
        except subprocess.CalledProcessError:
            _onblob = None
        try:
            _ondisk = _git(["hash-object", "--", _rel])
        except subprocess.CalledProcessError:
            _ondisk = None
        ck("and that verdict agrees with an independent comparison of the file's own git hash "
           "against HEAD's blob, in whichever direction the tree happens to be",
           ok_c == (_onblob is not None and _onblob == _ondisk),
           "on disk %s / at HEAD %s" % (str(_ondisk)[:12], str(_onblob)[:12]))
        _sib = builder_is_committed(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "sitting2_page.py"))
        ck("a tracked sibling is NOT reported as untracked -- the pathspec resolves at the "
           "repository root, not this module's directory, which is where that answer came from",
           "not tracked" not in _sib[1], _sib[1][:90])
        _out = builder_is_committed(os.path.join(tmp, "not_tracked.py"))
        ck("a path outside the repository is reported as such, not as `not tracked` -- two "
           "different situations must not share one message",
           _out[0] is False and "outside this repository" in _out[1], _out[1][:90])
        _in = builder_is_committed(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                "not_tracked_%s.py" % os.path.basename(tmp)))
        ck("and an untracked file INSIDE the repository is reported as having no blob at all",
           _in[0] is False and "not tracked" in _in[1], _in[1][:90])

        # The write path, proved by MUTATION rather than by green: a write into a directory
        # write_scope forbids must be refused before any bytes are written.
        _hit = False
        try:
            assert_inside(os.path.join(tmp, "x.jsonl"), "fixture")
        except Exception:
            _hit = True
        ck("write_scope refuses a layer written anywhere but the audits directory", _hit)

        # The public ratchet counts span-shaped ids near Hebrew; this file is all span ids and
        # would have raised the count the moment it was staged. The second half of the check is
        # the companion that proves the scan can SEE a Hebrew character -- an absence asserted by
        # a detector nobody tested is an absence of evidence.
        own = io.open(os.path.abspath(__file__), encoding="utf-8").read()
        heb = lambda t: [c for c in t if 0x5be < ord(c) < 0x600]
        ck("this file's own bytes carry no Hebrew character, and the scan that says so can see "
           "one when it is there",
           not heb(own) and len(heb(S("lamed", "dalet"))) == 2)

        # ---------------------------------------------------------------- (9) the count itself
        # The pin is the suite's TOTAL, counting this check, so it is the same number the last
        # line prints and a reader can compare the two without arithmetic. `n[0]` is read before
        # `ck` increments it, hence the +1. A hand-rolled suite where an exception ENDS the run
        # silently needs this: without it, 40 lost assertions look like a pass.
        ck("this suite ran the number of checks it was pinned to (%d)" % EXPECTED_CHECKS,
           n[0] + 1 == EXPECTED_CHECKS, n[0] + 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%s: %d checks, %d failed" % ("PASS" if not n[1] else "FAIL", n[0], n[1]))
    return 1 if n[1] else 0


def _raises_frag(fn, frag):
    try:
        fn()
    except LayerRefused as exc:
        return frag in str(exc)
    return False


# ------------------------------------------------------------------ CLI


def main(argv):
    cmd = (argv[1] if len(argv) > 1 else "selftest").lower()
    if cmd in ("selftest", "test"):
        return selftest()
    if cmd == "report":
        res = build(write=False)
        print(format_result(res))
        return {"dry_run": 0, "refused": 1, "cannot_decide": 2, "nothing_to_ingest": 3}[
            res["status"]]
    if cmd == "--build":
        res = build(write=True)
        print(format_result(res))
        return {"built": 0, "dry_run": 0, "refused": 1, "cannot_decide": 2,
                "nothing_to_ingest": 3}[res["status"]]
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
