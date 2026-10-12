# -*- coding: utf-8 -*-
"""The scoring-run contact sheet: the 45 crops that would be sent, native size, beside their signed text. (Lane B)

    python contact_sheet_scoring45.py

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88). Every file this writes says so.

THE GATE. Chris, 2026-10-11: "Before any outbound call, produce a contact sheet: every crop to be sent, native
size, beside its signed text, before/after where changed; Chris approves it, then spend. Record the hash of every
crop sent in the run header." And: "Approve the crops on what they show, not the text beside them." The crop is
the subject of the approval; the signed text is shown so the reader can see what the scorer will compare a model's
read against -- and what KIND of thing that is (a pixel reading, or the signer's editorial correction).

THIS IS NOT THE SIGNING SHEET. `truth_set_sheet.py` withholds the candidate because those spans were not yet
signed and a shown candidate anchors the signer. These 45 are signed, so the signature is shown. Same two
helpers (native view, 4x nearest-neighbour view) -- but see HELPERS below.

THE RUN BEING GATED (a plan, not an event): 45 truth spans x 2 models (anthropic/claude-opus-5.5,
qwen/qwen3.7-plus) x 2 channels. Channel 1, BARE: the A2 span crop alone. Channel 2: the same span crop PLUS the
Latin note TEXT with every Hebrew run masked to U+2022 by `hebrew_frontier_or._ctx` (imported, not reimplemented).
No note-box crop ever leaves the network; channel 2 carries note TEXT only.

WHAT THIS DOES NOT DO. It sends nothing: no network call of any kind, no key read, no model named in a request.
It cannot say whether a crop is legible -- only a human reading the pixels can; it can only make sure that human
is shown the exact pixels and the exact bytes of text that would go out. It does not decide the scoring rule.

CHANNEL 2, REV 2 (supersedes CONTACT_SHEET_scoring45_adb9a26835533dbc). The first build took `latin_context` from
`hebrew_aperture_diag.build_set`, which reads the 2026-09-06 sitting records for the OLD ~21-span population, so
channel 2 came out ABSENT for 44 of 45 -- reported honestly, but the text was not missing, the loader was pointing
at the wrong file. This build takes the note text from `vol1_apparatus.jsonl` (every page, `notes[n].text`) and
masks it with the existing `hebrew_frontier_or._ctx`.

THE MAPPING IS A CLAIM AND IS WITNESSED, NOT ASSUMED. "n in a span id is an index into `notes`" is checked per
row against witnesses (see C2_NORM_RULE below). The signing exports named in the brief carry NO note text (the
signer shows a note CROP IMAGE; their `note` field is the signer's own free text), so they cannot be the witness;
the witnesses used are named on the sheet. A span any witness contradicts is ABSENT, never guessed. A string that
masks down to nothing is ABSENT too: a bulleted line with no words would tell an arm "this note has no words",
which is false.

HELPERS. `truth_set_sheet.py` is a script, not a module: importing it executes the whole 74-span sheet at module
level (reads its cut, renders HTML, writes files). Its `_uri` / `_uri_im` / `_views` therefore cannot be imported
here, and `_views` returns a matched-scale comparison, not the 4x view. The two tiny pieces needed (a PNG data
URI, a NEAREST upscale) are written below and say so; nothing was copied silently.

BORN-CHECKS are made over the EMITTED BYTES of the document, each with a liveness count (a probe that matches
nothing passes on everything), and the register check for the two called-out rows is made inside THEIR OWN row
element, because the stylesheet and header mention `corrected` and `sic` and a whole-document grep passes on
furniture.
"""
import base64
import hashlib
import html
import io
import json
import os
import re
import sys
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image                                                      # noqa: E402
import hebrew_aperture_diag as HAD                                        # noqa: E402
import hebrew_frontier_or as FOR                                          # noqa: E402  _ctx, ARMS, APERTURE
from clean_run import git_state, provisional                              # noqa: E402
import ch2_position as CP                                                 # noqa: E402  rev 5: position-sourced channel 2

SET = "0401b636ffa7bf1a"
PRINTED_OFFSET = 88
N_EXPECT = 45
N_PASS1, N_PASS2, N_PASS3 = 25, 17, 3
MODELS = ("anthropic/claude-opus-5.5", "qwen/qwen3.7-plus")
CHANNELS = ("bare", "text")
CROP_DIR_NAME = "truthset96_crops_4e73b10d46a41f4a"
CROPDIR = HAD.DATA / CROP_DIR_NAME
APERTURE = FOR.APERTURE
UPSCALE = 4
SHORT_PX = 40
REPOS = {"goatyard-laneB": "C:/Users/cnogr/git/goatyard-laneB",
         "dr-voluminous": "C:/Users/cnogr/git/dr-voluminous"}

F_PASS1 = HAD.DATA / ("signing_pass1_ingest_%s.json" % SET)
F_PASS1_TILES = HAD.DATA / ("glyphsign_signed_%s_20261004_pass1.jsonl" % SET)
F_PASS2 = HAD.DATA / "truth_pass2.jsonl"
F_PASS3R2 = HAD.DATA / "truth_pass3_r2.jsonl"
F_R1_EXPORT = HAD.DATA / ("glyphsign_%s_pass3_3span_signed_51c0e7ba.jsonl" % SET)
F_R2_EXPORT = HAD.DATA / ("glyphsign_%s_pass3_r2_3span_signed_70fc08e1.jsonl" % SET)
F_ADJ = HAD.DATA / "ADJUDICATION_pass3_r1_588879f2f4a2cee8.json"
F_COST_BARE = HAD.DATA / "hebrew_frontier_or_notext_20261004.jsonl"
F_COST_TEXT = HAD.DATA / "hebrew_frontier_or_reads_20260927.jsonl"
F_APP = HAD.DATA.parent / "vol1_apparatus.jsonl"
F_TRUTH74 = HAD.DATA / ("truth_set74_%s.json" % SET)
F_CUT74 = HAD.DATA / ("truthset74_cut_%s.json" % SET)
F_REV4 = HAD.DATA / "CONTACT_SHEET_scoring45_adb9a26835533dbc_c22cdb77d8a2779e2d.json"
SOURCES = (F_PASS1, F_PASS1_TILES, F_PASS2, F_PASS3R2, F_R1_EXPORT, F_R2_EXPORT, F_ADJ, F_COST_BARE, F_COST_TEXT,
           F_APP, F_TRUTH74, F_CUT74, F_REV4)
SUPERSEDES = "CONTACT_SHEET_scoring45_adb9a26835533dbc_c22cdb77d8a2779e2d"
SUPERSEDES_WHY = ("rev 4 of this sheet, because Chris rejected it for the p245:n1 text: its channel-2 string for "
                  "p245:n1 was the PREVIOUS note's gloss, 'in monte Dominus videbitur' (the signed string is note "
                  "[2]'s lemma, not note [1]'s). Rev 4 took the note by the candidate's note_index; the candidate, "
                  "its index and the note text were mutually consistent and all pointed at the wrong note. Rev 5 "
                  "re-sources channel 2 by the crop's POSITION on the page and cross-checks it against an "
                  "independent content witness. Rev 4 survives in git history and on disk, untouched.")
SUPERSEDES_REV1 = "CONTACT_SHEET_scoring45_adb9a26835533dbc"
SUPERSEDES_REV1_WHY = ("rev 1 remains the record of the absent-channel finding: it sourced channel 2 from "
                       "hebrew_aperture_diag.build_set (the 2026-09-06 sitting records, an old ~21-span population) "
                       "and so showed channel 2 ABSENT for 44 of 45 spans.")
C2_MAP_RULE = ("POSITION, not index. Span id pP:nN -> take the span's stored box (strip frame, upscale=1; "
               "truth_set74.box), compute page P's note regions with note_line_region (Lane A, called not edited), "
               "find the ONE region containing the box (rule below), and take that region's ordinal k -> the "
               "vol1_apparatus.jsonl line whose `page` == P (file page), item k (0-based) of its `notes` list; the "
               "string is that item's `text`, passed through hebrew_frontier_or._ctx (Hebrew runs -> U+2022). The "
               "note TEXT has no geometry of its own (one whole-strip read), so region -> text is ORDINAL within the "
               "page, valid only under the count gate. The span id's N is NOT used to choose the note.")
C2_NORM_RULE = ("Content witness: fold both sides to base consonants (NFC, strip `[` `]`, keep U+05D0-U+05EA, fold the "
                "five final forms ך ם ן ף ץ to כ מ נ פ צ); distance for a note = the better of (a) Levenshtein "
                "distance from the SIGNED string (signature_full, else signature) to the note's FIRST Hebrew run "
                "(its opening lemma) and (b) 0 if the signed string occurs anywhere in the note's Hebrew. The note "
                "with the lowest distance wins; a TIE for lowest between two notes is an ABSTENTION. Latin "
                "comparison (older_latin): remove U+0590-U+05FF, lower-case, keep word tokens [a-z0-9&]; the older "
                "token sequence must be a contiguous run of the apparatus tokens.")
C2_WITNESSES = ("CONTENT WITNESS (relied on for identity, cross-lineage: the signed string is a human's read of the "
                "PIXELS, the note text is the model's read of the STRIP; it is checked against every note on the "
                "page, see the normalisation rule). OTHER WITNESSES, shown and NOT relied on for identity: "
                "(1) index_self_consistency: the truth set's note_index (1-based) minus 1 == N, i.e. the "
                "candidate's note_index agrees with the apparatus list position WITHIN ONE LINEAGE; this is "
                "SELF-CONSISTENCY, NOT IDENTITY (falsifying instance below); "
                "(2) count_agreement: the truth set's notes_on_page == len(notes) on that page; a count agreement is "
                "not a correspondence; "
                "(3) candidate_in_note: the truth set's `hebrew` field, the extractor's candidate from the whole-note "
                "read (same lineage as the note text), occurs in note N; this is NOT the printed or signed reading, "
                "and what it establishes is bookkeeping within that lineage, not a pixel correspondence; "
                "(4) marker_same_record: note N's marker == [^N+1] (same record, so a consistency check, not "
                "independent); "
                "(5) older_latin: where the 2026-09-06 sitting records hold a Latin string for the span.")
INDEX_SC_FALSIFIER = ("Chris, 2026-10-11: `p245:n1`'s index chain is internally coherent and points at the wrong "
                      "note; its channel-2 string was the previous note's gloss, \"in monte Dominus videbitur\".")
INDEX_SC_TEXT = ("index_self_consistency: the candidate's note_index agrees with the apparatus list position within "
                 "ONE lineage (the extractor that proposed the candidate and the extractor that listed the notes "
                 "share the same page reading). That is self-consistency, not identity: it can agree and be "
                 "wrong. Falsifying instance: " + INDEX_SC_FALSIFIER)
REV5_TEXT = ("REV 5 (rev field = 5). Supersedes " + SUPERSEDES + " (rev 4) BECAUSE CHRIS REJECTED IT FOR THE p245:n1 "
             "TEXT. What changed: channel 2 is re-sourced by the crop's POSITION on the page (the note region "
             "containing the box), not by candidate note index, and all 45 rows are re-derived; a content witness "
             "(signed string against every note on the page, cross-lineage) cross-checks the position; a row that "
             "cannot be resolved by position, or where position and content disagree, runs BARE-ONLY (channel 1 "
             "only) and says so. The index witness is renamed index_self_consistency and no longer licenses a "
             "string. Rows whose channel-2 string changed from rev 4 are listed with old and new side by side. "
             "n_calls and cost are recomputed from the actual channel counts. The 45 rows, crop hashes, set "
             "digest, register call-outs, before/after blocks and candidate_vs_signed are unchanged. This is a "
             "proposal, not an approval record. " + SUPERSEDES_REV1 + " (rev 1) remains the record of the "
             "absent-channel finding.")

REV3_TEXT_OLD = ("REV 3. What changed from rev 2: (a) witness (3) is relabelled. Rev 2 described the truth set's `hebrew` "
             "field as the text printed on the page; it is the extractor's candidate from the whole-note read, the same lineage "
             "as the note text, so it establishes index bookkeeping within that lineage and not a pixel "
             "correspondence. (b) The divergence between that candidate and the signed signature is now measured "
             "and shown per row (candidate_vs_signed). The 45 rows, crop hashes, set digest and channel-2 source "
             "are unchanged. This is a proposal, not an approval record. Rev 1 remains "
             "CONTACT_SHEET_scoring45_adb9a26835533dbc; rev 2 survives in git history.")
REV4_TEXT = ("REV 4 (rev field = 4). What changed from rev 3: the candidate_vs_signed table compared the candidate "
             "with each row's in-crop `signature`, so for the 4 signed_partial_in_crop rows the out-of-crop letters "
             "(bracketed in `signature_full`) read as disagreement. Rev 4 compares on the WHOLE-SPAN basis "
             "(`signature_full`, bracketed letters kept as signed-span letters, brackets stripped; `signature` for "
             "rows that carry no signature_full), because the candidate is a whole-span read and that is the "
             "like-for-like comparison. The in-crop distance is kept beside it for the partial rows, labelled. "
             "`partial_in_crop` is an orthogonal flag, not a class; each substantially_different row now carries a "
             "`cause`. The 45 rows, crop hashes, set digest and channel-2 source are unchanged. This is a proposal, "
             "not an approval record. Rev 3 survives in git (9cf9a85); rev 1 is "
             "CONTACT_SHEET_scoring45_adb9a26835533dbc.")
BASIS_LINE = ("BASIS: every class and distance below is on the WHOLE-SPAN basis (signature_full, falling back to "
              "signature where a row has none); the 4 partial rows also show the in-crop basis, labelled.")
CAND_RULE = ("candidate_vs_signed: both strings NFC, `[` and `]` stripped, only U+05D0-U+05EA kept, the five final "
             "forms folded to their base letters, Levenshtein distance d on the result. Classes: identical = the two "
             "strings are equal after NFC and bracket stripping alone; nikud_or_final_only = not identical but "
             "d == 0; close = 0 < d <= 2 and not substantially different; substantially_different = d > 2 or "
             "d > half the shorter string.")
CAND_CLASSES = ("identical", "nikud_or_final_only", "close", "substantially_different")
SUB_MARK = "data-cand-marker=\"substantially_different\""
CAUSE_P245 = "a different word entirely; note identity is an open debt on this lane"
UNEXPLAINED = "unexplained"

POLICY = ("Before any outbound call, produce a contact sheet: every crop to be sent, native size, beside its "
          "signed text, before/after where changed; Chris approves it, then spend. Record the hash of every crop "
          "sent in the run header. (Chris, 2026-10-11.) Approve the crops on what they show, not the text beside "
          "them.")
RULES = (
    "No note-box crop ever leaves the network; channel 2 carries note TEXT only.",
    "No :batch model variants.",
    "Endpoint C 192.168.1.169:11434 for anything compared to signed verdicts; never 192.168.1.179 or "
    "192.168.1.188.",
)
DIGEST_RULE = ('Take each span as the line "<span_id> <crop_sha16>" (one ASCII space; span_id like p133:n5, FILE '
               'page; crop_sha16 = first 16 hex of the SHA-256 of the crop PNG file bytes). Sort the 45 lines in '
               'plain Python str order (code point). Join with "\\n", no trailing newline, encode UTF-8, '
               'SHA-256, take the first 16 hex. That is the set digest.')

CALLED_OUT = ("p493:n3", "p594:n0")
ROUND2 = ("p493:n3", "p594:n0", "p803:n0")

HEB_RX = re.compile(u"[\u0590-\u05ff]")
PROBE_HEB = u"\u05d0\u05d1"
CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


def sha16(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()[:16]


def _jl(p):
    return [json.loads(l) for l in open(str(p), encoding="utf-8") if l.strip()]


def esc(s):
    return html.escape(str(s), quote=True)


def sid_key(s):
    p, n = s.split(":")
    return (int(p[1:]), int(n[1:]))


def printed(sid):
    return int(sid.split(":")[0][1:]) - PRINTED_OFFSET


# ---------------------------------------------------------------- tile -> text (ported from ingest_pass2.py)
# ingest_pass2.py is a script that runs on import, so derive() cannot be imported; this is a port, and the
# r2 rows are cross-checked against the signed file's own signature_full below.

def tile_out(t, prior=False):
    v = t.get("prior_verdict") if prior else t.get("verdict")
    chose = t.get("prior_chose") if prior else t.get("chose")
    v, gap = v or "", t["kind"] == "gap"
    if v == "deleted":
        return ""
    if v == "not_in_crop":
        return "[ ]" if gap else "[" + t["shown"] + "]"
    if v in ("confirmed", "sic"):
        return " " if gap else t["shown"]
    if v == "corrected":
        if gap:
            return " " if chose == "space" else ""
        return chose or "?"
    return "?"


def ins_out(it, prior=False):
    v = it.get("prior_verdict") if prior else it.get("verdict")
    chose = it.get("prior_chose") if prior else it.get("chose")
    if not chose:
        return "?"
    s = " " if it["kind"] == "gap" else chose
    return "[" + s + "]" if v == "not_in_crop" else s


def derive(r, prior=False):
    ins = r.get("insertions", [])
    out = [ins_out(x, prior) for x in sorted((x for x in ins if x["after_i"] is None), key=lambda x: x["seq"])]
    for t in r["tiles"]:
        out.append(tile_out(t, prior))
        out.extend(ins_out(x, prior) for x in sorted((x for x in ins if x["after_i"] == t["i"]),
                                                     key=lambda x: x["seq"]))
    return "".join(out)


def counts_from_tiles(tiles):
    c = {"confirmed": 0, "corrected": 0, "sic": 0}
    for t in tiles:
        if t.get("kind") == "gap":
            continue
        if t.get("verdict") in c:
            c[t["verdict"]] += 1
    return c


# ---------------------------------------------------------------- the two view helpers (see HELPERS in the docstring)

def data_uri_png(im_or_bytes):
    if isinstance(im_or_bytes, bytes):
        raw = im_or_bytes
    else:
        b = io.BytesIO()
        im_or_bytes.save(b, format="PNG")
        raw = b.getvalue()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def upscale_nearest(im, k=UPSCALE):
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


# ================================================================ START
GIT_START = {k: git_state(v) for k, v in REPOS.items()}

# ---- 1. the 45, derived
p1 = json.load(io.open(str(F_PASS1), encoding="utf-8"))
check(p1.get("set_sha16") == SET, "pass-1 ingest is from set %r, not %r" % (p1.get("set_sha16"), SET))
P1_SIGNED = list(p1["dispositions"]["signed"]) + list(p1["dispositions"]["signed_span_aperture_only"])
P2_ROWS = _jl(F_PASS2)
P3_ROWS = _jl(F_PASS3R2)
P2_IDS = [r["span_id"] for r in P2_ROWS]
P3_IDS = [r["span_id"] for r in P3_ROWS]
ALL_IDS = sorted(set(P1_SIGNED) | set(P2_IDS) | set(P3_IDS), key=sid_key)
DERIVATION = ("pass 1 = dispositions.signed (%d) + dispositions.signed_span_aperture_only (%d) = %d; "
              "pass 2 = lines of truth_pass2.jsonl = %d; pass 3 r2 = lines of truth_pass3_r2.jsonl = %d; "
              "union = %d unique ids" % (len(p1["dispositions"]["signed"]),
                                         len(p1["dispositions"]["signed_span_aperture_only"]), len(P1_SIGNED),
                                         len(P2_IDS), len(P3_IDS), len(ALL_IDS)))
print(DERIVATION)
check(len(P1_SIGNED) == N_PASS1 and len(P2_IDS) == N_PASS2 and len(P3_IDS) == N_PASS3,
      "the files give %d + %d + %d, not %d + %d + %d: %s" % (len(P1_SIGNED), len(P2_IDS), len(P3_IDS),
                                                            N_PASS1, N_PASS2, N_PASS3, DERIVATION))
check(len(ALL_IDS) == N_EXPECT and len(P1_SIGNED) + len(P2_IDS) + len(P3_IDS) == N_EXPECT,
      "the files give %d unique ids (sum %d), not %d: %s" % (len(ALL_IDS),
                                                            len(P1_SIGNED) + len(P2_IDS) + len(P3_IDS),
                                                            N_EXPECT, DERIVATION))
PASS_OF = {}
for s in P1_SIGNED:
    PASS_OF[s] = 1
for s in P2_IDS:
    PASS_OF[s] = 2
for s in P3_IDS:
    PASS_OF[s] = 3

# ---- 2. signed text and register, per row
P1_DISPO = {s: k for k in ("signed", "signed_span_aperture_only") for s in p1["dispositions"][k]}
P1_TILES = {r["span_id"]: r for r in _jl(F_PASS1_TILES)}
P2_BY = {r["span_id"]: r for r in P2_ROWS}
P3_BY = {r["span_id"]: r for r in P3_ROWS}
R1 = {r["span_id"]: r for r in _jl(F_R1_EXPORT)}
R2 = {r["span_id"]: r for r in _jl(F_R2_EXPORT)}
ADJ = json.load(io.open(str(F_ADJ), encoding="utf-8"))

# ---- 3. channel 2 text, from vol1_apparatus.jsonl, mapping witnessed per row
# POP is kept only as a WITNESS (older Latin strings) and for loader_truth_agrees; it is not the source.
POP = {s["span_id"]: s for s in HAD.build_set(include_sealed=True)}
APP_NOTES = {}
for _i, _line in enumerate(io.open(str(F_APP), encoding="utf-8")):
    if not _line.strip():
        continue
    _o = json.loads(_line)
    if _i == 0:
        check(_o.get("kind") == "config_header", "vol1_apparatus.jsonl line 1 is not a config_header")
        continue
    APP_NOTES[int(_o["page"])] = _o["notes"]
T74 = {r["span_id"]: r for r in json.load(io.open(str(F_TRUTH74), encoding="utf-8"))["rows"]}
CUT74 = {r["span_id"]: r for r in json.load(io.open(str(F_CUT74), encoding="utf-8"))["rows"]}
REV4_BY = {r["span_id"]: r for r in json.load(io.open(str(F_REV4), encoding="utf-8"))["rows"]}
check(all(set(n) == {"marker", "text"} for ns in APP_NOTES.values() for n in ns),
      "an apparatus note item does not have exactly marker and text")
_HEB_CONS = re.compile(u"[^א-ת]")
_LAT_TOK = re.compile(r"[a-z0-9&]+")


def _heb_cons(s):
    return _HEB_CONS.sub("", unicodedata.normalize("NFC", s or ""))


_FINAL = str.maketrans(u"ךםןףץ", u"כמנפצ")


def _cand_norm(s, fold):
    t = unicodedata.normalize("NFC", s or "").replace("[", "").replace("]", "")
    if not fold:
        return t.strip()
    return _heb_cons(t).translate(_FINAL)


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cand_class(cand, signed):
    a, b = _cand_norm(cand, True), _cand_norm(signed, True)
    d = lev(a, b)
    if _cand_norm(cand, False) == _cand_norm(signed, False):
        return "identical", d
    if d == 0:
        return "nikud_or_final_only", d
    if d > 2 or d > min(len(a), len(b)) / 2.0:
        return "substantially_different", d
    return "close", d


def _lat_tokens(s):
    return _LAT_TOK.findall(re.sub(u"[֐-׿]+", " ", unicodedata.normalize("NFC", s or "")).lower())


def _contiguous(small, big):
    n = len(small)
    return n > 0 and any(big[i:i + n] == small for i in range(len(big) - n + 1))


WITNESS_KEYS = ("index_self_consistency", "count_agreement", "candidate_in_note", "marker_same_record", "older_latin")
WITNESS_KEYS_CMP = ("index_self_consistency", "count_agreement", "candidate_in_note", "older_latin")


def c2_witness(sid):
    """Per-witness verdicts for 'note N of the span id is notes[N] on that page'. None = not comparable."""
    p, n = int(sid.split(":")[0][1:]), int(sid.split(":")[1][1:])
    notes = APP_NOTES.get(p)
    w = {"in_apparatus": bool(notes) and 0 <= n < len(notes), "index_self_consistency": None,
         "count_agreement": None, "candidate_in_note": None, "marker_same_record": None, "older_latin": None}
    if not w["in_apparatus"]:
        return w
    nt = notes[n]
    t = T74.get(sid)
    if t:
        w["index_self_consistency"] = (int(t["note_index"]) - 1 == n)
        w["count_agreement"] = (int(t["notes_on_page"]) == len(notes))
        w["candidate_in_note"] = bool(_heb_cons(t["hebrew"])) and _heb_cons(t["hebrew"]) in _heb_cons(nt["text"])
    w["marker_same_record"] = (nt["marker"] == "[^%d]" % (n + 1))
    old = (POP.get(sid) or {}).get("latin_context")
    if old:
        w["older_latin"] = _contiguous(_lat_tokens(old), _lat_tokens(nt["text"]))
    return w

rows = []
for sid in ALL_IDS:
    ps = PASS_OF[sid]
    r = {"span_id": sid, "page_file": int(sid.split(":")[0][1:]), "page_printed": printed(sid), "pass": ps}
    if ps == 1:
        tr = P1_TILES[sid]
        c = counts_from_tiles(tr["tiles"])
        r.update(disposition=P1_DISPO[sid], signature=derive(tr), signature_full=None,
                 n_confirmed=c["confirmed"], n_corrected=c["corrected"], n_sic=c["sic"],
                 counts_source="derived from the pass-1 per-tile verdicts (consonant tiles only)",
                 signed_from=tr["signed_from"], box_fault=None, in_crop_trimmed=None, sic=[],
                 crop_sha16_signed=tr["crop_sha16"], signed_partial_in_crop=False)
    else:
        sr = (P2_BY if ps == 2 else P3_BY)[sid]
        r.update(disposition=sr["disposition"], signature=sr["signature"], signature_full=sr.get("signature_full"),
                 n_confirmed=sr.get("n_confirmed"), n_corrected=sr.get("n_corrected"), n_sic=sr.get("n_sic"),
                 counts_source="carried by the signed row" if sr.get("n_confirmed") is not None else "not carried",
                 signed_from=sr["signed_from"], box_fault=sr.get("box_fault") or None,
                 in_crop_trimmed=sr.get("in_crop_trimmed") or None, sic=sr.get("sic") or [],
                 crop_sha16_signed=sr["crop_sha16"],
                 signed_partial_in_crop=(sr["disposition"] == "signed_partial_in_crop"))
    path = CROPDIR / ("p%d_n%d_%s.png" % (r["page_file"], int(sid.split(":")[1][1:]), APERTURE))
    check(path.is_file(), "%s: crop %s does not exist" % (sid, path))
    raw = open(str(path), "rb").read()
    im = Image.open(io.BytesIO(raw))
    im.load()
    r.update(crop_file=path.name, crop_sha16=sha16(raw), crop_w=im.size[0], crop_h=im.size[1], _raw=raw, _im=im)
    check(r["crop_sha16"] == r["crop_sha16_signed"],
          "%s: crop file sha16 %s != the sha16 its signature was recorded over (%s) -- the signature is for "
          "other pixels" % (sid, r["crop_sha16"], r["crop_sha16_signed"]))
    check(bool(r["signature"]) and "?" not in r["signature"],
          "%s: signed text empty or carries an unresolved '?': %r" % (sid, r["signature"]))
    W = c2_witness(sid)
    r["ch2_witness"] = W
    check(sid in T74, "%s: not in the truth set, so no candidate to compare" % sid)
    r["cand_hebrew"] = T74[sid]["hebrew"]
    r["basis_full_text"] = r["signature_full"] or r["signature"]
    r["cand_class"], r["cand_dist"] = cand_class(r["cand_hebrew"], r["basis_full_text"])
    r["partial_in_crop"] = bool(r["signed_partial_in_crop"])
    r["cand_class_incrop"], r["cand_dist_incrop"] = (cand_class(r["cand_hebrew"], r["signature"])
                                                     if r["partial_in_crop"] else (None, None))
    r["cause"] = None
    if r["cand_class"] == "substantially_different":
        _nin = len(_heb_cons(r["signature"]))
        if r["span_id"] == "p245:n1":
            r["cause"] = CAUSE_P245
        elif r["n_corrected"] is not None and r["n_corrected"] > 0 and r["n_corrected"] >= _nin / 2.0 and r["span_id"] == "p493:n3":
            r["cause"] = ("the signer corrected %d of %d in-crop letters; corrections, not a mapping doubt"
                          % (r["n_corrected"], _nin))
        else:
            r["cause"] = UNEXPLAINED
    _pn = (int(sid.split(":")[0][1:]), int(sid.split(":")[1][1:]))
    # ---- channel 2, rev 5: POSITION first, then an independent CONTENT witness, then the combined state
    _t = T74[sid]
    _app_n = len(APP_NOTES.get(_pn[0]) or [])
    r["pos"] = CP.resolve(sid, _pn[0], _t["box"], _app_n, int(_t["notes_on_page"]),
                          CUT74[sid]["crop"]["native_rects"] if CUT74.get(sid, {}).get("crop") else None)
    r["content"] = (CP.content_witness(r["basis_full_text"], APP_NOTES[_pn[0]]) if _app_n else
                    {"distances": [], "best": None, "tied": [], "best_distance": None, "runner_up_distance": None})
    r["ch2_flag"] = ""
    r["ch2_note_ordinal"] = None
    r["ch2"] = ""
    if r["pos"]["state"] != "resolved":
        r.update(combined="bare_only_position_unresolved", ch2_state="absent",
                 ch2_why="position unresolved at the %s gate: %s" % (r["pos"]["gate"], r["pos"]["why"]))
    elif r["content"]["best"] is not None and r["content"]["best"] != r["pos"]["ordinal"]:
        r.update(combined="bare_only_position_content_disagree", ch2_state="absent",
                 ch2_why="position and content disagree about which note this span belongs to "
                 "(position: region %d; content: note %d at distance %d, runner-up %s)"
                 % (r["pos"]["ordinal"], r["content"]["best"], r["content"]["best_distance"],
                    r["content"]["runner_up_distance"]))
    else:
        _k = r["pos"]["ordinal"]
        r["ch2_note_ordinal"] = _k
        masked = FOR._ctx(APP_NOTES[_pn[0]][_k]["text"])
        if not masked.strip() or not re.search(r"[A-Za-z0-9]", masked):
            r.update(combined="bare_only_masks_to_nothing", ch2_state="absent",
                     ch2_why="the note masks down to nothing (no Latin words); a bare bullet line would tell an "
                     "arm the note has no words")
        elif r["content"]["best"] is None:
            r.update(combined="present_content_abstained", ch2_state="present", ch2=masked, ch2_why="",
                     ch2_flag="content_abstained")
        else:
            r.update(combined="present_agree", ch2_state="present", ch2=masked, ch2_why="")
    _old = REV4_BY[sid]
    r["ch2_rev4"] = {"state": _old["ch2_state"], "string": _old["ch2"]}
    r["ch2_changed"] = (r["ch2_rev4"]["state"], r["ch2_rev4"]["string"]) != (r["ch2_state"], r["ch2"])
    if sid in POP and POP[sid].get("truth") is not None:
        r["loader_truth_agrees"] = (POP[sid]["truth"] == r["signature"])
    rows.append(r)
BY = {r["span_id"]: r for r in rows}
N_CH2 = {k: sum(1 for r in rows if r["ch2_state"] == k) for k in ("present", "absent")}
C2_ABSENT_IDS = [r["span_id"] for r in rows if r["ch2_state"] == "absent"]
C2_WIT = {}
for _k in WITNESS_KEYS:
    _vals = [r["ch2_witness"][_k] for r in rows if r["ch2_witness"][_k] is not None]
    C2_WIT[_k] = {"n_matched": sum(1 for v in _vals if v), "n_comparable": len(_vals)}
_all_cmp = [r for r in rows if any(r["ch2_witness"][k] is not None for k in WITNESS_KEYS_CMP)]
C2_WIT["all_comparable_witnesses_agree"] = {
    "n_matched": sum(1 for r in _all_cmp if not any(r["ch2_witness"][k] is False for k in
                                                    WITNESS_KEYS)),
    "n_comparable": len(_all_cmp)}
CAND_N = {k: sum(1 for r in rows if r["cand_class"] == k) for k in CAND_CLASSES}
SUB_IDS = [r["span_id"] for r in rows if r["cand_class"] == "substantially_different"]
PARTIAL_IDS = [r["span_id"] for r in rows if r["partial_in_crop"]]
UNEXPLAINED_IDS = [s_ for s_ in SUB_IDS if BY[s_]["cause"] == UNEXPLAINED]
CAND_VS_SIGNED = {"basis": "whole_span (signature_full, else signature)", "basis_line": BASIS_LINE,
                  "rule": CAND_RULE, "counts": CAND_N, "n": len(rows), "substantially_different_ids": SUB_IDS,
                  "distances_of_substantially_different": {s_: BY[s_]["cand_dist"] for s_ in SUB_IDS},
                  "causes_of_substantially_different": {s_: BY[s_]["cause"] for s_ in SUB_IDS},
                  "unexplained_ids": UNEXPLAINED_IDS,
                  "partial_in_crop_ids": PARTIAL_IDS,
                  "partial_in_crop": {s_: {"whole_span_basis": {"text": BY[s_]["basis_full_text"], "class": BY[s_]["cand_class"],
                                                                "distance": BY[s_]["cand_dist"]},
                                           "in_crop_basis": {"text": BY[s_]["signature"], "class": BY[s_]["cand_class_incrop"],
                                                             "distance": BY[s_]["cand_dist_incrop"]},
                                           "candidate": BY[s_]["cand_hebrew"]} for s_ in PARTIAL_IDS},
                  "note": "the candidate is the extractor's whole-note read, not what the signer read off the pixels"}
CAND_TXT = ", ".join("%s %d" % (k, CAND_N[k]) for k in CAND_CLASSES)
C2_SRC_SHA = sha16(open(str(F_APP), "rb").read())
C2_WIT_TXT = "; ".join("%s %d/%d" % (k, v["n_matched"], v["n_comparable"]) for k, v in C2_WIT.items())

# ---- 3b. rev 5 aggregates: position, content, combined, changed rows, payload identity
COMBINED_KINDS = ("present_agree", "present_content_abstained", "bare_only_position_content_disagree",
                  "bare_only_position_unresolved", "bare_only_masks_to_nothing")
COMBINED_N = {k: sum(1 for r in rows if r["combined"] == k) for k in COMBINED_KINDS}
POS_RESOLVED_IDS = [r["span_id"] for r in rows if r["pos"]["state"] == "resolved"]
POS_UNRESOLVED = {r["span_id"]: r["pos"]["gate"] for r in rows if r["pos"]["state"] != "resolved"}
POS_GATE_N = {g: sum(1 for v in POS_UNRESOLVED.values() if v == g) for g in ("frame", "count", "containment")}
_idx0 = {r["span_id"]: int(T74[r["span_id"]]["note_index"]) - 1 for r in rows}
CONTENT_AGREE_IDX = [r["span_id"] for r in rows if r["content"]["best"] is not None and r["content"]["best"] == _idx0[r["span_id"]]]
CONTENT_DISAGREE_IDX = [r["span_id"] for r in rows if r["content"]["best"] is not None and r["content"]["best"] != _idx0[r["span_id"]]]
CONTENT_TIE = [r["span_id"] for r in rows if r["content"]["best"] is None]
SHIFT_DIST = {}
for _r in rows:
    if _r["content"]["best"] is not None:
        _sh = abs(_r["content"]["best"] - _idx0[_r["span_id"]])
        SHIFT_DIST[_sh] = SHIFT_DIST.get(_sh, 0) + 1
CONTENT_VS_POSITION_DISAGREE = [r["span_id"] for r in rows if r["pos"]["state"] == "resolved"
                                and r["content"]["best"] is not None and r["content"]["best"] != r["pos"]["ordinal"]]
POS_EQ_INDEX = [r["span_id"] for r in rows if r["pos"]["state"] == "resolved" and r["pos"]["ordinal"] == _idx0[r["span_id"]]]
CHANGED_IDS = [r["span_id"] for r in rows if r["ch2_changed"]]
BARE_ONLY_IDS = [r["span_id"] for r in rows if r["ch2_state"] == "absent"]
PAYLOAD_TRIPLES = sorted((r["span_id"], r["ch2_state"], r["ch2"]) for r in rows)
PAYLOAD_RULE = ("channel2_payload_sha16 = first 16 hex of the SHA-256 of the UTF-8 bytes of "
                "json.dumps([[span_id, ch2_state, ch2_string], ...], ensure_ascii=False, separators=(',', ':')) "
                "over the 45 triples sorted in plain Python tuple order; ch2_string is the exact masked text that "
                "would be sent ('' for an absent row).")
PAYLOAD_SHA16 = sha16(json.dumps([list(t_) for t_ in PAYLOAD_TRIPLES], ensure_ascii=False,
                                 separators=(",", ":")).encode("utf-8"))

# ---- 4. before/after for the three round-2 rows
check(set(R1) == set(ROUND2) and set(R2) == set(ROUND2) and set(P3_IDS) == set(ROUND2),
      "round-2 rows differ from the expected three: r1 %s r2 %s truth %s" % (sorted(R1), sorted(R2), sorted(P3_IDS)))
BEFORE_AFTER = {}
for sid in ROUND2:
    cur = derive(R2[sid])
    check(cur == P3_BY[sid]["signature_full"],
          "%s: derive(r2 tiles) = %r but the signed row's signature_full = %r" % (sid, cur, P3_BY[sid]["signature_full"]))
    r1_sig = derive(R1[sid])
    r2_prior = derive(R2[sid], prior=True)
    tile_diffs = []
    for t in R2[sid]["tiles"]:
        t1 = next(x for x in R1[sid]["tiles"] if x["i"] == t["i"])
        if (t1["verdict"], t1["chose"]) != (t["verdict"], t["chose"]):
            tile_diffs.append({"i": t["i"], "shown": t["shown"], "r1": [t1["verdict"], t1["chose"]],
                               "r2": [t["verdict"], t["chose"]],
                               "r2_prior_fields": [t.get("prior_verdict"), t.get("prior_chose")]})
    BEFORE_AFTER[sid] = {"pass3_r1_signature_full": r1_sig, "r2_prior_fields_signature_full": r2_prior,
                         "current_signature_full": cur, "tiles_changed_r1_to_r2": tile_diffs,
                         "pixels_byte_identical": R1[sid]["crop_sha16"] == R2[sid]["crop_sha16"]}
    check(BEFORE_AFTER[sid]["pixels_byte_identical"], "%s: the re-signed crop sha16 differs between rounds" % sid)

# the adjudication ruling that voided the p493:n3 tile-4 pass-3 confirm
RULING = next((x for x in ADJ["rulings"] if x["span_id"] == "p493:n3" and x.get("tile_i") == 4), None)
check(RULING is not None and RULING["verdict"] == "keep" and "void" in RULING["basis"],
      "ADJUDICATION_pass3_r1 holds no 'keep' ruling voiding p493:n3 tile 4: %r" % (RULING,))

# ---- 5. set digest, geometry, counts, cost
DIGEST_LINES = sorted("%s %s" % (r["span_id"], r["crop_sha16"]) for r in rows)
SET_DIGEST = sha16("\n".join(DIGEST_LINES))
SRC_SHA = {p.name: sha16(open(str(p), "rb").read()) for p in SOURCES}
N_BARE_ONLY = sum(1 for r in rows if r["ch2_state"] == "absent")
N_DUAL = sum(1 for r in rows if r["ch2_state"] == "present")
N_CALLS = (N_BARE_ONLY * 1 + N_DUAL * 2) * len(MODELS)       # a bare-only row is 2 calls, a dual-channel row 4
N_CALLS_REV4 = 180
check(N_BARE_ONLY + N_DUAL == len(rows) and N_CALLS == 2 * N_BARE_ONLY + 4 * N_DUAL,
      "call count %d does not follow the channel counts (%d bare-only, %d dual)" % (N_CALLS, N_BARE_ONLY, N_DUAL))
HS = [r["crop_h"] for r in rows]
WS = [r["crop_w"] for r in rows]
N_SHORT = sum(1 for h in HS if h < SHORT_PX)


def mean_cost(path, model):
    v = [float(o["cost_usd"]) for o in _jl(path) if o.get("model") == model and o.get("cost_usd") is not None]
    return (sum(v) / len(v), len(v)) if v else (None, 0)


COST = {"basis": ("DERIVED from measured per-call cost_usd in earlier runs, not a quote: channel 1 from %s, "
                  "channel 2 from %s; mean over the rows of that model that carry a cost_usd" %
                  (F_COST_BARE.name, F_COST_TEXT.name)), "per_model": {}, "total_usd": None}
_tot, _unk = 0.0, False
for m in MODELS:
    b, nb = mean_cost(F_COST_BARE, m)
    t, nt = mean_cost(F_COST_TEXT, m)
    if b is None or t is None:
        _unk = True
        COST["per_model"][m] = {"unknown": True}
        continue
    est = len(rows) * b + N_DUAL * t
    _tot += est
    COST["per_model"][m] = {"mean_usd_per_call_bare": round(b, 6), "n_costed_bare": nb,
                            "mean_usd_per_call_text": round(t, 6), "n_costed_text": nt,
                            "estimate_usd_for_%d_spans_actual_channels" % len(rows): round(est, 4)}
COST["total_usd"] = None if _unk else round(_tot, 4)
COST_REV4_USD = 0.2631             # rev 4 sidecar, 45 x (bare + text) per model, before any row was bare-only
COST["n_calls"] = N_CALLS
COST["channels"] = {"bare_only_rows": N_BARE_ONLY, "dual_channel_rows": N_DUAL}
COST["caveats"] = ("measured on the 19-20-span OLD population; these 45 crops differ in size and the text channel "
                   "is a masked note text. n_calls and the estimate follow the ACTUAL channel counts: a bare-only "
                   "row is 2 calls (one per model), a dual-channel row 4. A measurement of other inputs, not a "
                   "forecast." if not _unk else "cost UNKNOWN: no measured per-call cost found.")

# ---------------------------------------------------------------- the document
CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--mut:#555;--line:#c8c8c8;--card:#f6f6f2;--warn:#8a2a00;--ok:#14532d;--chip:#e8e8e0}
@media (prefers-color-scheme: dark){:root{--bg:#161616;--fg:#e8e8e8;--mut:#a0a0a0;--line:#444;--card:#202020;--warn:#ffb084;--ok:#86efac;--chip:#2c2c2c}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px;max-width:1400px}
h1{font-size:20px;margin:.2em 0}h2{font-size:16px;margin:1.4em 0 .4em}
code,pre{font:12px/1.4 ui-monospace,Consolas,monospace}
pre{white-space:pre-wrap;word-break:break-all;margin:.2em 0}
section.row{border:1px solid var(--line);background:var(--card);margin:14px 0;padding:10px;border-radius:4px}
.views{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;margin:6px 0}
.views figure{margin:0}figcaption{font-size:11px;color:var(--mut)}
.px{background:#fff;border:1px solid var(--line);image-rendering:pixelated;display:block}
.x4{max-width:100%;overflow-x:auto}
.meta td{padding:1px 10px 1px 0;vertical-align:top}.meta td:first-child{color:var(--mut);white-space:nowrap}
.heb{font:20px/1.3 'Times New Roman',serif;direction:rtl;unicode-bidi:isolate}
.chip{display:inline-block;background:var(--chip);border:1px solid var(--line);padding:0 6px;margin:1px;border-radius:3px}
.chip[data-register=corrected]{border-color:var(--warn);color:var(--warn)}
.chip[data-register=sic]{border-color:var(--warn);color:var(--warn);font-weight:700}
.chip[data-register=confirmed]{border-color:var(--ok)}
.chip[data-register=not_in_crop]{opacity:.55}
.callout{border-left:4px solid var(--warn);padding:4px 10px;margin:6px 0}
.mut{color:var(--mut)}.warn{color:var(--warn)}
.cand-sub{border-left:4px solid var(--warn);background:var(--chip);padding:2px 8px;font-weight:700;color:var(--warn)}
table.hdr td{padding:1px 10px 1px 0;vertical-align:top}
"""


def chip(t):
    shown, v, chose = t["shown"], t["verdict"], t.get("chose") or ""
    if t["kind"] == "gap":
        shown = "(space)"
    txt = {"confirmed": "%s printed" % shown, "corrected": "%s printed, read as %s" % (shown, chose or "?"),
           "sic": "%s printed (sic; expected %s)" % (shown, t.get("expected") or "?"),
           "not_in_crop": "%s not in crop" % shown}.get(v, "%s %s" % (shown, v))
    return '<span class="chip heb" data-register="%s" data-tile="%d">%s</span>' % (esc(v), t["i"], esc(txt))


def row_html(r):
    sid = r["span_id"]
    rid = "row-" + sid.replace(":", "-")
    x4 = upscale_nearest(r["_im"])
    L = ['<section class="row" id="%s" data-span="%s" data-sha16="%s">' % (rid, esc(sid), r["crop_sha16"]),
         "<h3 style='margin:0 0 4px'>%s <span class='mut'>file page %d, printed page %d, pass %d</span></h3>"
         % (esc(sid), r["page_file"], r["page_printed"], r["pass"]),
         '<div class="views"><figure><img class="px" src="%s" width="%d" height="%d" alt="%s native">'
         "<figcaption>native %dx%d px, no scaling</figcaption></figure>"
         % (data_uri_png(r["_raw"]), r["crop_w"], r["crop_h"], esc(sid), r["crop_w"], r["crop_h"]),
         '<figure class="x4"><img class="px" src="%s" width="%d" height="%d" alt="%s 4x nearest">'
         "<figcaption>4x nearest-neighbour (no smoothing)</figcaption></figure></div>"
         % (data_uri_png(x4), x4.width, x4.height, esc(sid)),
         '<table class="meta">',
         "<tr><td>crop</td><td><code>%s</code> &nbsp; sha16 <code>%s</code> &nbsp; %dx%d px%s</td></tr>"
         % (esc(r["crop_file"]), r["crop_sha16"], r["crop_w"], r["crop_h"],
            ' <span class="warn">(under %d px tall)</span>' % SHORT_PX if r["crop_h"] < SHORT_PX else ""),
         '<tr><td>signed text</td><td class="heb" dir="rtl">%s</td></tr>' % esc(r["signature"])]
    if r["signature_full"] and r["signature_full"] != r["signature"]:
        L.append("<tr><td>signature_full</td><td class='heb' dir='rtl'>%s</td></tr>" % esc(r["signature_full"]))
    L.append("<tr><td>disposition</td><td><code>%s</code></td></tr>" % esc(r["disposition"]))
    L.append("<tr><td>register</td><td>n_confirmed=<b>%s</b> n_corrected=<b>%s</b> n_sic=<b>%s</b> "
             "<span class='mut'>(%s)</span></td></tr>" % (esc(r["n_confirmed"]), esc(r["n_corrected"]),
                                                       esc(r["n_sic"]), esc(r["counts_source"])))
    L.append("<tr><td>signed_from</td><td><code>%s</code></td></tr>" % esc(r["signed_from"]))
    if r["box_fault"]:
        L.append("<tr><td>box_fault</td><td><code>%s</code></td></tr>" % esc(r["box_fault"]))
    if r["signed_partial_in_crop"]:
        L.append("<tr><td>signed_partial_in_crop</td><td>truth holds over the IN-CROP SUBSTRING ONLY; the signed "
                 "text above is that substring%s</td></tr>" %
                 ("; <code>in_crop_trimmed: %s</code>" % esc(r["in_crop_trimmed"]) if r["in_crop_trimmed"] else ""))
    L.append('<tr><td>extractor candidate</td><td><span class="heb" dir="rtl">%s</span> &nbsp; class <code>%s</code>, '
             "base-consonant edit distance %d <span class='mut'>(WHOLE-SPAN basis; the whole-note read, not the signed reading)</span>"
             "</td></tr>" % (esc(r["cand_hebrew"]), r["cand_class"], r["cand_dist"]))
    if r["partial_in_crop"]:
        L.append('<tr><td>partial_in_crop</td><td data-partial="1"><b>PARTIAL IN CROP</b> (orthogonal flag, not a class). '
                 "whole-span basis <span class='heb' dir='rtl'>%s</span>: class <code>%s</code>, d=%d; "
                 "in-crop basis <span class='heb' dir='rtl'>%s</span>: class <code>%s</code>, d=%d "
                 "<span class='mut'>(the in-crop figure counts the out-of-crop letters as disagreement)</span></td></tr>"
                 % (esc(r["basis_full_text"]), r["cand_class"], r["cand_dist"], esc(r["signature"]),
                    r["cand_class_incrop"], r["cand_dist_incrop"]))
    if r["cand_class"] == "substantially_different":
        L.append('<tr><td class="warn">candidate differs</td><td><div class="cand-sub" %s>SUBSTANTIALLY DIFFERENT '
                 "(whole-span basis): the note text for this span was selected by a candidate that is not what this "
                 'crop was signed as. cause: <span class="cause" data-cause="%s">%s</span></div>'
                 "</td></tr>" % (SUB_MARK, "unexplained" if r["cause"] == UNEXPLAINED else "stated", esc(r["cause"])))
    pos, ct = r["pos"], r["content"]
    _tf = {True: "agrees", False: "DISAGREES", None: "n/a"}
    if pos["state"] == "resolved":
        L.append("<tr><td>channel 2 position</td><td data-pos=\"resolved\" data-ordinal=\"%d\">RESOLVED: the box lies in "
                 "note region <b>%d</b> (0-based) of %d detected regions (apparatus notes %d, truth-set notes_on_page "
                 "%d). Share of the box's height per region: %s. Frame: box inside the strip, inside one band, maps "
                 "to the stored native rectangle(s), regions' union covers it (%.3f).</td></tr>"
                 % (pos["ordinal"], pos["ordinal"], pos["n_regions"], pos["apparatus_n"], pos["notes_on_page"],
                    esc(json.dumps(pos["overlap"])), pos["frame"]["union_cover_fraction"]))
    else:
        L.append("<tr><td>channel 2 position</td><td data-pos=\"unresolved\" data-gate=\"%s\"><b class='warn'>UNRESOLVED</b> "
                 "at the <b>%s</b> gate: %s</td></tr>" % (esc(pos["gate"]), esc(pos["gate"]), esc(pos["why"])))
    if ct["best"] is not None:
        L.append("<tr><td>channel 2 content witness</td><td data-content=\"best\" data-best=\"%d\">best note <b>%d</b> at "
                 "distance %d, runner-up distance %s; distance to every note: %s. <span class='mut'>(signed string "
                 "vs each note's opening Hebrew run, base consonants; cross-lineage)</span></td></tr>"
                 % (ct["best"], ct["best"], ct["best_distance"], esc(ct["runner_up_distance"]), esc(json.dumps(ct["distances"]))))
    else:
        L.append("<tr><td>channel 2 content witness</td><td data-content=\"abstain\"><b class='warn'>ABSTAINS</b>: notes %s "
                 "tie at distance %s; distance to every note: %s.</td></tr>"
                 % (esc(json.dumps(ct["tied"])), esc(ct["best_distance"]), esc(json.dumps(ct["distances"]))))
    L.append("<tr><td>channel 2 combined</td><td data-combined=\"%s\" data-ch2-state=\"%s\"><code>%s</code> &rarr; "
             "<b>%s</b>%s</td></tr>"
             % (r["combined"], r["ch2_state"], r["combined"], "dual-channel (4 calls)" if r["ch2_state"] == "present" else "BARE-ONLY (2 calls)",
                " <span class='warn'>flag: %s</span>" % esc(r["ch2_flag"]) if r["ch2_flag"] else ""))
    if r["ch2_state"] == "absent":
        L.append("<tr><td>channel 2 string</td><td><b class='warn'>ABSENT</b> <span class='mut'>(bare-only; not empty: %s)"
                 "</span><pre class=\"ch2\" data-state=\"absent\"></pre></td></tr>" % esc(r["ch2_why"]))
    else:
        _w = r["ch2_witness"]
        _k = r["ch2_note_ordinal"]
        L.append("<tr><td>channel 2 string</td><td><span class='mut'>present; exact bytes that would be sent as the "
                 "text part (apparatus note %d of file page %d, marker %s, chosen by POSITION; same-lineage "
                 "witnesses, not identity: %s):</span>"
                 "<pre class=\"ch2\" data-state=\"%s\">%s</pre></td></tr>"
                 % (_k, r["page_file"], esc(APP_NOTES[r["page_file"]][_k]["marker"]),
                    esc(", ".join("%s=%s" % (k, _tf[_w[k]]) for k in WITNESS_KEYS)),
                    r["ch2_state"], esc(r["ch2"])))
    if r["ch2_changed"]:
        L.append("<tr><td>channel 2 vs rev 4</td><td data-ch2-changed=\"yes\"><b class='warn'>CHANGED</b> from rev 4. "
                 "<div class=\"chgbox\">old (rev 4), state <code>%s</code>:<pre class=\"chg-old\">%s</pre>"
                 "new (rev 5), state <code>%s</code>:<pre class=\"chg-new\">%s</pre></div></td></tr>"
                 % (esc(r["ch2_rev4"]["state"]), esc(r["ch2_rev4"]["string"]), esc(r["ch2_state"]), esc(r["ch2"])))
    else:
        L.append("<tr><td>channel 2 vs rev 4</td><td data-ch2-changed=\"no\">identical to rev 4 (same state, same string)</td></tr>")
    L.append("</table>")
    if sid in CALLED_OUT:
        L.append(called_out_html(sid))
    if sid in ROUND2:
        L.append(before_after_html(sid))
    else:
        L.append('<div class="mut" data-changed="no">Unchanged: this row was signed once and has not been re-signed.'
                 "</div>")
    L.append("</section>")
    return "\n".join(L)


def called_out_html(sid):
    tiles = R2[sid]["tiles"]
    if sid == "p493:n3":
        return (
            '<div class="callout" data-callout="p493:n3"><b>Register: this signature is mostly an EDITORIAL '
            "reading, not a pixel reading.</b> Signature <span class='heb'>%s</span>, 4 of 8 letters in the "
            "in-crop substring; <b>1 confirmed + 3 corrected</b>. Only the yod is a confirmed printed glyph; the "
            "other three are the signer's corrections (ayin to chet, resh to samekh, final-pe to resh). A scorer "
            "that treats this as pixel evidence is scoring an editorial reading.<br>%s<br>"
            "Tile 4 (the final letter) is the <b>restored resh</b>: the pass-3 round-1 confirm of the printed "
            "final-pe over byte-identical pixels was VOIDED by Chris's ruling (%s, tile 4 verdict "
            "<code>keep</code>: %s).</div>"
            % (esc(BY[sid]["signature"]), " ".join(chip(t) for t in tiles if t["verdict"] != "not_in_crop" and t["kind"] != "gap"),
               esc(F_ADJ.name), esc(RULING["authority"])))
    sic = BY[sid]["sic"][0]
    return (
        '<div class="callout" data-callout="p594:n0"><b>Register: PRINTED and EXPECTED are two different '
        "things.</b> The signature <span class='heb'>%s</span> is the PRINTED reading: 4 confirmed + <b>1 sic</b>; "
        "the printed he IS in the signature. The expected chet stands BESIDE it, not in it.<br>"
        "<span data-register='printed'>printed: <span class='heb'>%s</span> (tile %d)</span> &nbsp; "
        "<span data-register='expected'>expected: <span class='heb'>%s</span></span> &nbsp; "
        "reason <code>%s</code> &nbsp; basis <code>%s</code><br>%s<br>"
        "<code>expected_match</code> is a SEPARATE scored outcome from <code>exact</code>: a model that reads the "
        "printed he is <code>exact</code>; a model that reads the expected chet is <code>expected_match</code> "
        "and not <code>exact</code>.</div>"
        % (esc(BY[sid]["signature"]), esc(sic["printed"]), sic["tile_i"], esc(sic["expected"]),
           esc(sic["reason"]), esc(sic["basis"]), " ".join(chip(t) for t in tiles if t["verdict"] != "not_in_crop" and t["kind"] != "gap")))


def before_after_html(sid):
    b = BEFORE_AFTER[sid]
    td = "".join("<li>tile %d <span class='heb'>%s</span>: round 1 %s, now %s</li>"
                 % (d["i"], esc(d["shown"]), esc("/".join(map(str, d["r1"]))), esc("/".join(map(str, d["r2"]))))
                 for d in b["tiles_changed_r1_to_r2"]) or "<li>no tile verdict differs between round 1 and now</li>"
    return ('<div class="callout" data-before-after="%s"><b>Before / after</b> (re-signed over byte-identical '
            "pixels, same crop sha16): <table class='meta'>"
            "<tr><td>pass-3 round 1</td><td class='heb' dir='rtl'>%s</td></tr>"
            "<tr><td>prior as recorded in the round-2 export (prior_verdict / prior_chose)</td>"
            "<td class='heb' dir='rtl'>%s</td></tr>"
            "<tr><td>current</td><td class='heb' dir='rtl'>%s</td></tr></table>"
            "<ul>%s</ul></div>"
            % (esc(sid), esc(b["pass3_r1_signature_full"]), esc(b["r2_prior_fields_signature_full"]),
               esc(b["current_signature_full"]), td))


def header_html():
    tb = ['<table class="hdr">']

    def kv(k, v):
        tb.append("<tr><td class='mut'>%s</td><td>%s</td></tr>" % (esc(k), v))
    kv("page convention", "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - %d). Every span id here is a file page." % PRINTED_OFFSET)
    kv("rev", "<b id='rev-field'>5</b>")
    kv("revision", esc(REV5_TEXT))
    kv("status", "NOTHING IS SENT. No network call of any kind was made to produce this sheet.")
    kv("policy", esc(POLICY))
    kv("approval is for", "the PIXELS in each row, not the text beside them. The signed text is shown because "
       "these spans are already signed; this is not the signing sheet.")
    kv("spans", "%d unique (%s)" % (len(rows), esc(DERIVATION)))
    kv("set digest", "<code>%s</code>" % SET_DIGEST)
    kv("digest rule", esc(DIGEST_RULE))
    kv("crop directory", "<code>%s</code> (class (b) regenerable, gitignored; nothing was re-cut)" % esc(CROP_DIR_NAME))
    kv("truth sources (sha16)", "<br>".join("<code>%s</code> %s" % (esc(k), v) for k, v in SRC_SHA.items()
                                            if k in (F_PASS1.name, F_PASS1_TILES.name, F_PASS2.name,
                                                     F_PASS3R2.name, F_R1_EXPORT.name, F_R2_EXPORT.name,
                                                     F_ADJ.name)))
    kv("models", ", ".join("<code>%s</code>" % esc(m) for m in MODELS))
    kv("channel 1 (bare)", "the A2 span crop alone")
    kv("channel 2 (text)", "the same A2 span crop PLUS the Latin note text, every Hebrew run masked to U+2022 by "
       "<code>hebrew_frontier_or._ctx</code>. Note TEXT only: no note-box crop.")
    kv("channel-2 availability", "%d present, %d ABSENT (of %d). ABSENT = BARE-ONLY: no note text is licensed for the "
       "span (position unresolved at a named gate, position and content disagree about the note, or the note masks "
       "down to nothing); bare-only rows: %s. Channel 2 is never guessed and never falls back to the index mapping. "
       "A string that masks to nothing is absent, never present."
       % (N_CH2["present"], N_CH2["absent"], len(rows), esc(", ".join(C2_ABSENT_IDS) or "none")))
    kv("channel-2 source", "<code>%s</code> sha16 <code>%s</code> (959 lines; line 1 config_header)"
       % (esc(F_APP.name), C2_SRC_SHA))
    kv("channel-2 mapping rule", esc(C2_MAP_RULE))
    kv("containment rule (position)", "<span id='containment-rule'>%s</span> Thresholds: win >= %d%% of the box's height; "
       "no other region >= %d%%; x-centre inside the winning region's x-range." % (esc(CP.RULE_TEXT), int(CP.WIN_FRAC * 100), int(CP.LOSE_FRAC * 100)))
    kv("frame assertion", esc("The stored box (truth_set74 `box`, strip frame, presplit upscale=1) and the note regions "
       "(note_line_region.detect_regions on the same upscale=1 strip) are asserted to share one frame, per span: the box "
       "lies inside the strip; its top lies in exactly one band's paste window and its x-extent within that band's "
       "width; strip_box_to_native(box) reproduces EXACTLY the native rectangle(s) the crop cut stored "
       "(truthset74_cut native_rects), which is the independent anchor; and the regions' union covers the box's "
       "y-extent. A page that cannot establish this makes every span on it unresolved."))
    kv("position result", "<b id='pos-result'>%d / %d</b> resolved by position; unresolved by gate: frame %d, count %d, "
       "containment %d%s. Of the resolved, the region ordinal equals the candidate's note_index-1 on <b>%d</b>."
       % (len(POS_RESOLVED_IDS), len(rows), POS_GATE_N["frame"], POS_GATE_N["count"], POS_GATE_N["containment"],
          (" (" + esc(", ".join("%s:%s" % kv_ for kv_ in sorted(POS_UNRESOLVED.items()))) + ")") if POS_UNRESOLVED else "",
          len(POS_EQ_INDEX)))
    kv("position is not independent of the index", esc("HONEST LIMIT: the stored boxes were themselves placed by "
       "note_line_region.locate_span inside regions[note_index-1] (draw_pool.py), so the region holding a box is "
       "the region the candidate's index named, by construction. Position therefore CANNOT by itself catch an "
       "index error; it removes the dependence on the apparatus list position and gives the count gate, and the "
       "CONTENT witness is the only channel here that can contradict the index."))
    kv("channel-2 witnesses", esc(C2_WITNESSES))
    kv("channel-2 normalisation", esc(C2_NORM_RULE))
    kv("content witness result", "<span id='content-result'>%d agree with the index mapping, %d DISAGREE (%s), %d TIE/abstain (%s)</span>; "
       "shift |content note - index note| distribution %s; content vs POSITION: %d disagree (%s)."
       % (len(CONTENT_AGREE_IDX), len(CONTENT_DISAGREE_IDX), esc(", ".join(CONTENT_DISAGREE_IDX) or "none"),
          len(CONTENT_TIE), esc(", ".join(CONTENT_TIE) or "none"), esc(json.dumps(SHIFT_DIST, sort_keys=True)),
          len(CONTENT_VS_POSITION_DISAGREE), esc(", ".join(CONTENT_VS_POSITION_DISAGREE) or "none")))
    kv("combined states", "<span id='combined-states'>%s</span> (partition of %d). present + absent = %d + %d."
       % (esc(", ".join("%s %d" % (k_, COMBINED_N[k_]) for k_ in COMBINED_KINDS)), len(rows), N_CH2["present"], N_CH2["absent"]))
    kv("same-lineage witnesses", "<b>%d / %d</b> comparable rows agree on every same-lineage witness; per witness "
       "(n_matched/n_comparable): %s. These are consistency checks within one extraction and license nothing. Witness "
       "source <code>%s</code> sha16 <code>%s</code>."
       % (C2_WIT["all_comparable_witnesses_agree"]["n_matched"], C2_WIT["all_comparable_witnesses_agree"]["n_comparable"],
          esc(C2_WIT_TXT), esc(F_TRUTH74.name), SRC_SHA[F_TRUTH74.name]))
    kv("index_self_consistency", "<span id='index-sc'>%s</span> Rows where it agrees: %d / %d, including the falsifying "
       "row." % (esc(INDEX_SC_TEXT), C2_WIT["index_self_consistency"]["n_matched"], C2_WIT["index_self_consistency"]["n_comparable"]))
    kv("changed channel-2 strings (vs rev 4)", "<span id='changed-count'><b>%d</b> of %d rows changed</span>: %s. Each is "
       "rendered old beside new in its own row."
       % (len(CHANGED_IDS), len(rows), esc("; ".join("%s: %s -> %s" % (
           s_, BY[s_]["ch2_rev4"]["state"] if not BY[s_]["ch2_rev4"]["string"] else BY[s_]["ch2_rev4"]["state"] + " " + repr(BY[s_]["ch2_rev4"]["string"][:60]),
           BY[s_]["ch2_state"] if not BY[s_]["ch2"] else BY[s_]["ch2_state"] + " " + repr(BY[s_]["ch2"][:60])) for s_ in CHANGED_IDS) or "none")))
    kv("channel2_payload_sha16", "<code id='payload-sha'>%s</code> %s" % (PAYLOAD_SHA16, esc(PAYLOAD_RULE)))
    kv("candidate_vs_signed", "<b>%s</b> <span id='cand-table'>%s</span> (n=%d). %s Substantially different: %s. The truth set's "
       "`hebrew` field is the extractor's candidate from the whole-note read; it is not the signed reading. The "
       "neighbour-note control gives candidate_in_note discriminating power on 44 of 45 rows (carried from rev 2), within "
       "one lineage: the witnesses share the note text's own extraction, so they are not independent of it."
       % (esc(BASIS_LINE), esc(CAND_TXT), len(rows), esc(CAND_RULE), esc(", ".join(SUB_IDS))))
    kv("partial_in_crop (4, orthogonal flag)", esc("; ".join("%s whole-span d=%d (%s) / in-crop d=%d (%s)" % (
        s_, BY[s_]["cand_dist"], BY[s_]["cand_class"], BY[s_]["cand_dist_incrop"], BY[s_]["cand_class_incrop"])
        for s_ in PARTIAL_IDS)))
    kv("causes", esc("; ".join("%s: %s" % (s_, BY[s_]["cause"]) for s_ in SUB_IDS)) +
       " Unexplained: " + esc(", ".join(UNEXPLAINED_IDS) or "none") + ".")
    kv("supersedes", "<code>%s</code>: %s" % (SUPERSEDES, esc(SUPERSEDES_WHY)))
    kv("record of the absent-channel finding", "<code>%s</code>: %s" % (SUPERSEDES_REV1, esc(SUPERSEDES_REV1_WHY)))
    kv("standing rules", "<ul>" + "".join("<li>%s</li>" % esc(x) for x in RULES) + "</ul>")
    kv("scoring", "per channel: <code>exact</code> / <code>nikud</code> / <code>wrong</code> / "
       "<code>expected_match</code>, plus the agreement-and-wrong rate. Predicted first.")
    kv("call count", "%d bare-only rows x 1 channel x %d models + %d dual-channel rows x 2 channels x %d models = <b id='n-calls'>%d</b> "
       "(rev 4: %d, which assumed all 45 dual-channel)" % (N_BARE_ONLY, len(MODELS), N_DUAL, len(MODELS), N_CALLS, N_CALLS_REV4))
    kv("cost", esc(json.dumps(COST, ensure_ascii=False)))
    kv("crop geometry", "width %d to %d px, height %d to %d px; %d crop(s) under %d px tall"
       % (min(WS), max(WS), min(HS), max(HS), N_SHORT, SHORT_PX))
    kv("re-signed rows", "Only the 3 round-2 rows (%s) were re-signed; each shows before/after below. No other row "
       "changed, and each of the other %d says so." % (", ".join(ROUND2), len(rows) - len(ROUND2)))
    kv("git at start", esc(json.dumps({k: {"head": v["git_head"], "dirty": v["git_dirty"]} for k, v in GIT_START.items()})))
    tb.append("</table>")
    return "\n".join(tb)


def end_header_html(git_end, prov, why):
    return ('<h2>Run record</h2><table class="hdr"><tr><td class="mut">git at end</td><td>%s</td></tr>'
            '<tr><td class="mut">verdict</td><td><b class="%s">%s</b> %s</td></tr></table>'
            % (esc(json.dumps({k: {"head": v["git_head"], "dirty": v["git_dirty"]} for k, v in git_end.items()})),
               "warn" if prov else "", "PROVISIONAL" if prov else "clean", esc(why)))


# the end-of-run git state is taken immediately before the document is composed (the outputs themselves are
# written afterwards and would otherwise dirty the very tree being described)
GIT_END = {k: git_state(v) for k, v in REPOS.items()}
PROV = any(provisional(GIT_START[k], GIT_END[k]) for k in REPOS)
WHY = []
for k in REPOS:
    if not GIT_START[k]["clean"] or not GIT_END[k]["clean"]:
        WHY.append("%s is not clean (%s)" % (k, json.dumps(GIT_END[k]["git_dirty"], ensure_ascii=False)[:300]))
    if GIT_START[k] != GIT_END[k]:
        WHY.append("%s moved between start and end" % k)
WHY_TXT = "; ".join(WHY) if WHY else "both repos clean and identical at both ends"

parts = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         "<title>Scoring run contact sheet, %d spans, digest %s</title><style>%s</style>" % (len(rows), SET_DIGEST, CSS),
         "<h1>Scoring-run contact sheet: %d spans, %d calls, nothing sent</h1>" % (len(rows), N_CALLS),
         header_html(), end_header_html(GIT_END, PROV, WHY_TXT),
         "<h2>Index</h2><p>%s</p>" % " ".join("<a href='#row-%s'>%s</a>" % (s.replace(":", "-"), s) for s in ALL_IDS)]
parts.extend(row_html(r) for r in rows)
DOC = "\n".join(parts) + "\n"

# ---------------------------------------------------------------- born-checks over the emitted bytes
sidecar = {
    "kind": "contact_sheet_scoring45", "rev": 5, "revision": 5, "revision_note": REV5_TEXT, "prior_revision_note_rev4": REV4_TEXT,
    "channel2_payload_sha16": PAYLOAD_SHA16, "channel2_payload_rule": PAYLOAD_RULE, "n_calls_rev4": N_CALLS_REV4,
    "cost_rev4_usd": COST_REV4_USD, "containment_rule": CP.RULE_TEXT,
    "containment_thresholds": {"win_fraction_of_box_height": CP.WIN_FRAC, "other_region_fraction_max_exclusive": CP.LOSE_FRAC,
                               "x_centre_in_winning_region_x_range": True},
    "index_self_consistency": {"text": INDEX_SC_TEXT, "falsifying_instance": INDEX_SC_FALSIFIER, "span_id": "p245:n1"},
    "combined_states": COMBINED_N, "position": {"resolved": len(POS_RESOLVED_IDS), "unresolved_by_gate": POS_UNRESOLVED,
                                                 "gate_counts": POS_GATE_N, "region_ordinal_equals_index": len(POS_EQ_INDEX)},
    "content_witness": {"agree_with_index": CONTENT_AGREE_IDX, "disagree_with_index": CONTENT_DISAGREE_IDX, "ties": CONTENT_TIE,
                        "shift_distribution": {str(k_): v_ for k_, v_ in SHIFT_DIST.items()},
                        "disagree_with_position": CONTENT_VS_POSITION_DISAGREE},
    "channel2_changed_vs_rev4": {s_: {"old": BY[s_]["ch2_rev4"], "new": {"state": BY[s_]["ch2_state"], "string": BY[s_]["ch2"]}} for s_ in CHANGED_IDS},
    "bare_only_ids": BARE_ONLY_IDS, "candidate_vs_signed": CAND_VS_SIGNED, "page_convention": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)",
    "nothing_sent": True, "set_digest": SET_DIGEST, "channel2_source_sha16": C2_SRC_SHA, "digest_rule": DIGEST_RULE, "digest_lines": DIGEST_LINES,
    "derivation": DERIVATION, "policy": POLICY, "standing_rules": list(RULES), "models": list(MODELS),
    "channels": {"bare": "A2 span crop alone", "text": "A2 span crop plus Latin note text, Hebrew runs masked to U+2022"},
    "n_calls": N_CALLS, "cost": COST, "truth_sources_sha16": SRC_SHA,
    "channel2_counts": N_CH2, "channel2_absent_ids": C2_ABSENT_IDS,
    "channel2_source": {"file": F_APP.name, "sha16": C2_SRC_SHA, "mapping_rule": C2_MAP_RULE,
                        "witnesses": C2_WITNESSES, "normalisation_rule": C2_NORM_RULE,
                        "witness_result": C2_WIT, "witness_source": F_TRUTH74.name},
    "supersedes": SUPERSEDES, "supersedes_why": SUPERSEDES_WHY, "record_of_absent_channel_finding": SUPERSEDES_REV1, "crop_w_range": [min(WS), max(WS)], "crop_h_range": [min(HS), max(HS)],
    "n_crops_under_%dpx_tall" % SHORT_PX: N_SHORT, "git_start": GIT_START, "git_end": GIT_END,
    "provisional": PROV, "provisional_reason": WHY_TXT, "before_after": BEFORE_AFTER,
    "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
}
SIDE = json.dumps(sidecar, ensure_ascii=False, indent=1, sort_keys=True) + "\n"

# 1. no note-box path anywhere
NB_RX = re.compile(r"A1_notebox|note_box")
check(NB_RX.search("C:/x/p1_n1_A1_notebox.png") and NB_RX.search("note_box"), "note-box detector does not fire on its probes")
check(len(re.findall(r"p\d+_n\d+_A2_spanbox\.png", DOC)) == N_EXPECT,
      "liveness: expected %d crop file names in the document, found %d"
      % (N_EXPECT, len(re.findall(r"p\d+_n\d+_A2_spanbox\.png", DOC))))
check(not NB_RX.search(DOC), "a note-box path appears in the document: %r" % NB_RX.search(DOC))
check(not NB_RX.search(SIDE), "a note-box path appears in the sidecar")

# 2. no key
KEY_RX = re.compile(r"sk-or-")
check(KEY_RX.search("sk-or-v1-probe"), "key detector does not fire on its probe")
check(not KEY_RX.search(DOC) and not KEY_RX.search(SIDE), "an sk-or- substring appears in the document or sidecar")
_env = os.environ.get("OPENROUTER_API_KEY", "")
check(not _env or (_env not in DOC and _env not in SIDE), "the OPENROUTER_API_KEY value appears in an output")

# 3. all 45 crop sha16 in the document
n_rows_in_doc = len(re.findall(r'<section class="row" id="row-[^"]+" data-span="[^"]+" data-sha16="([0-9a-f]{16})"', DOC))
check(n_rows_in_doc == N_EXPECT, "liveness: %d row elements in the document, expected %d" % (n_rows_in_doc, N_EXPECT))
n_sha_present = sum(1 for r in rows if r["crop_sha16"] in DOC)
check(n_sha_present == N_EXPECT, "only %d of %d crop sha16 values appear in the document" % (n_sha_present, N_EXPECT))
check(len(set(r["crop_sha16"] for r in rows)) == N_EXPECT, "crop sha16 values are not 45 distinct values")

# 4. channel-2 strings free of Hebrew
check(HEB_RX.search(PROBE_HEB), "Hebrew detector does not fire on its probe")
CH2 = re.findall(r'<pre class="ch2" data-state="(\w+)">(.*?)</pre>', DOC, flags=re.S)
check(len(CH2) == N_EXPECT, "liveness: %d channel-2 elements, expected %d" % (len(CH2), N_EXPECT))
ST = {k: sum(1 for s, _t in CH2 if s == k) for k in ("present", "absent")}
check(ST == N_CH2, "channel-2 states in the document %r != derived %r" % (ST, N_CH2))
n_nonempty = sum(1 for s, t in CH2 if html.unescape(t).strip())
check(n_nonempty == N_CH2["present"] and n_nonempty >= 1, "non-empty channel-2 count %d vs present %d" % (n_nonempty, N_CH2["present"]))
check(all(not HEB_RX.search(html.unescape(t)) for _s, t in CH2), "a channel-2 string carries a Hebrew codepoint")
n_masked = sum(1 for _s, t in CH2 if u"\u2022" in html.unescape(t))
check(n_masked >= 1, "liveness: no channel-2 string carries the U+2022 mask, so the masking was never exercised")
check(n_masked >= 10, "liveness: only %d channel-2 strings carry the mask; the 44-absent finding should be gone" % n_masked)
# present/absent counts stated in the document and the sidecar, equal to the derived counts
_hdr_txt = "%d present, %d ABSENT (of %d)" % (N_CH2["present"], N_CH2["absent"], N_EXPECT)
check(_hdr_txt in DOC and sidecar["channel2_counts"] == N_CH2 and N_CH2["present"] + N_CH2["absent"] == N_EXPECT,
      "the channel-2 present/absent counts are not stated consistently on the sheet and in the sidecar")
# every present string is non-empty AFTER masking and stripping and carries a Latin word; a bullets-only string is absent
check(all(re.search(r"[A-Za-z0-9]", html.unescape(t)) for s, t in CH2 if s == "present"),
      "a present channel-2 string has no Latin word after masking")
check(not any(s == "present" and not html.unescape(t).replace(u"\u2022", "").strip() for s, t in CH2),
      "a present channel-2 string is empty after masking and stripping")
# liveness for the emptiness predicate: a bullets-only string must be refused by it
check(not re.search(r"[A-Za-z0-9]", u"\u2022 \u2022"), "liveness: the bullets-only probe passes the Latin-word test")
# rev 5: a present row is licensed by POSITION resolved and CONTENT not disagreeing, never by a same-lineage witness
check(all(r["ch2_state"] == "absent" or (r["pos"]["state"] == "resolved" and
                                          (r["content"]["best"] is None or r["content"]["best"] == r["pos"]["ordinal"]))
          for r in rows), "a present row is not licensed by a resolved position and a non-disagreeing content witness")
check(C2_WIT["index_self_consistency"]["n_comparable"] >= 1 and C2_WIT["candidate_in_note"]["n_comparable"] >= 1,
      "liveness: a same-lineage witness compared nothing")
# the supersession and the channel-2 source digest are on the sheet and the sidecar
check(SUPERSEDES in DOC and SUPERSEDES_REV1 in DOC and C2_SRC_SHA in DOC and "supersedes" in SIDE and C2_SRC_SHA in SIDE
      and "BECAUSE CHRIS REJECTED IT FOR THE p245:n1 TEXT" in DOC,
      "the supersession (rev 4, with Chris's reason), the rev 1 record, or the channel-2 source sha16 is missing from an output")
check(all(t == "" for s, t in CH2 if s == "absent"), "an absent row carries channel-2 text")

# 5. register inside the called-out rows' OWN elements
def row_el(sid):
    m = re.search(r'<section class="row" id="row-%s".*?</section>' % re.escape(sid.replace(":", "-")), DOC, flags=re.S)
    return m.group(0) if m else ""


E493, E594 = row_el("p493:n3"), row_el("p594:n0")
check(E493 and E594 and E493 != E594, "liveness: could not extract the two called-out row elements")
check(E493.count('data-register="corrected"') == 3 and E493.count('data-register="confirmed"') == 1
      and 'data-register="sic"' not in E493 and "n_confirmed=<b>1</b>" in E493 and "n_corrected=<b>3</b>" in E493,
      "p493:n3 row element does not carry 1 confirmed + 3 corrected as tile chips")
check("restored resh" in E493 and F_ADJ.name in E493, "p493:n3 row element does not name the restored resh and the ruling")
check(E594.count('data-register="sic"') == 1 and E594.count('data-register="confirmed"') == 4
      and "n_sic=<b>1</b>" in E594 and "n_confirmed=<b>4</b>" in E594
      and "Exod 31:5 / fabrefactione" in E594 and "evidence_grounded" in E594
      and "data-register='printed'" in E594 and "data-register='expected'" in E594 and "expected_match" in E594
      and "in_crop_trimmed: trailing separator" in E594,
      "p594:n0 row element does not carry 4 confirmed + 1 sic, printed beside expected, reason, basis, expected_match")
n_other_with_tile_chips = sum(1 for r in rows if r["span_id"] not in CALLED_OUT and 'data-register="sic"' in row_el(r["span_id"]))
check(n_other_with_tile_chips == 0, "a row other than the two called-out rows carries a sic chip")
for r in rows:
    check("n_confirmed=<b>%s</b>" % r["n_confirmed"] in row_el(r["span_id"]),
          "%s: its own row element does not carry its n_confirmed" % r["span_id"])
n_unchanged = len(re.findall(r'data-changed="no"', DOC))
n_ba = len(re.findall(r'data-before-after="', DOC))
check(n_ba == 3 and n_unchanged == N_EXPECT - 3, "before/after elements %d, unchanged elements %d" % (n_ba, n_unchanged))
check(all(row_el(s).count('data-before-after="%s"' % s) == 1 for s in ROUND2), "a round-2 row lacks its own before/after block")
check(DOC.count("FILE PAGES") >= 1 and "FILE PAGES" in SIDE, "the file-page convention is missing from an output")

# 6. candidate_vs_signed: partition, liveness, own-element markers, relabelled witness text
check(lev(u"אבג", u"אדג") == 1 and lev(u"", u"אב") == 2 and cand_class(u"נפש", u"נפשות")[0] == "substantially_different"
      and cand_class(u"ך", u"כ")[0] == "nikud_or_final_only", "liveness: the Levenshtein/class probes do not behave")
check(sum(CAND_N.values()) == N_EXPECT and set(CAND_N) == set(CAND_CLASSES),
      "the four classes do not partition the %d rows: %r" % (N_EXPECT, CAND_N))
check(CAND_N["substantially_different"] > 0, "liveness: no substantially_different row, so the probe saw nothing")
_in_own = [s_ for s_ in SUB_IDS if row_el(s_).count(SUB_MARK) == 1]
check(_in_own == SUB_IDS, "a substantially_different row lacks its marker in its OWN element: %r" % sorted(set(SUB_IDS) - set(_in_own)))
check(all(SUB_MARK not in row_el(r["span_id"]) for r in rows if r["cand_class"] != "substantially_different"),
      "a row that is not substantially_different carries the marker")
check(DOC.count(SUB_MARK) == len(SUB_IDS), "the marker count in the document %d != %d substantially_different rows"
      % (DOC.count(SUB_MARK), len(SUB_IDS)))
check("p493:n3" in SUB_IDS and "p245:n1" in SUB_IDS, "p493:n3 or p245:n1 is not substantially_different on the whole-span basis")
_w3 = re.search(r"\(3\) candidate_in_note:.*?(?=; \(4\))", C2_WITNESSES, flags=re.S)
check(_w3 is not None and "printed Hebrew" not in _w3.group(0) and "NOT the printed or signed reading" in _w3.group(0)
      and "extractor's candidate" in _w3.group(0) and "printed Hebrew" not in C2_NORM_RULE
      and "printed Hebrew" not in DOC and "printed Hebrew" not in SIDE,
      "the relabelled witness (3) text is missing, or a 'printed Hebrew' claim survives")
check(json.loads(SIDE)["candidate_vs_signed"]["counts"] == CAND_N and CAND_TXT in DOC and "REV 5" in DOC,
      "candidate_vs_signed or the rev-4 statement is missing from an output")

# 7. rev 4: basis, partial flag, bracket assertion, cause in own element, rev field
_NI = [r for r in rows if r["cand_class"] == "nikud_or_final_only"]
check(all("[" not in (r["signature_full"] or "") and "]" not in (r["signature_full"] or "") for r in _NI),
      "a nikud_or_final_only row has a bracket in signature_full: %r" % [r["span_id"] for r in _NI if "[" in (r["signature_full"] or "")])
check(len(_NI) > 0 and CAND_N["nikud_or_final_only"] == len(_NI),
      "liveness: the nikud_or_final_only bracket assertion saw %d rows" % len(_NI))
check(len(PARTIAL_IDS) == 4 and all(r["signed_partial_in_crop"] == r["partial_in_crop"] for r in rows),
      "partial_in_crop is not exactly 4 / does not follow signed_partial_in_crop: %r" % PARTIAL_IDS)
check(all(BY[s_]["cand_dist"] is not None and BY[s_]["cand_dist_incrop"] is not None and BY[s_]["cand_class_incrop"]
          for s_ in PARTIAL_IDS) and all(BY[r["span_id"]]["cand_dist_incrop"] is None for r in rows if not r["partial_in_crop"]),
      "a partial row lacks a distance, or a non-partial row carries an in-crop one")
_sc = json.loads(SIDE)["candidate_vs_signed"]["partial_in_crop"]
check(set(_sc) == set(PARTIAL_IDS) and all(v["whole_span_basis"]["distance"] is not None and v["in_crop_basis"]["distance"] is not None
                                          for v in _sc.values()), "the sidecar's partial rows do not each carry both labelled distances")
check(all(row_el(s_).count("data-partial=\"1\"") == 1 for s_ in PARTIAL_IDS)
      and sum(row_el(r["span_id"]).count("data-partial=\"1\"") for r in rows) == 4, "partial flag not in exactly the 4 rows' own elements")
_close_sub = [r["span_id"] for r in rows if r["cand_dist"] <= 1 and r["cand_class"] == "substantially_different"]
check(not _close_sub, "a row whose whole-span distance is <= 1 is classed substantially_different: %r" % _close_sub)
_le1 = [r["span_id"] for r in rows if r["cand_dist"] <= 1]
check(len(_le1) > 0 and all(r["cand_class"] != "substantially_different" for r in rows if r["span_id"] in _le1),
      "liveness: no row has whole-span distance <= 1 (%d)" % len(_le1))
_boundary = [s_ for s_ in PARTIAL_IDS if BY[s_]["cand_dist_incrop"] > BY[s_]["cand_dist"]]
check(len(_boundary) > 0, "liveness: no partial row's in-crop distance exceeds its whole-span distance, so basis changed nothing")
check(all(BY[s_]["cause"] for s_ in SUB_IDS) and all(BY[r["span_id"]]["cause"] is None for r in rows if r["cand_class"] != "substantially_different"),
      "a substantially_different row lacks a cause, or another row carries one")
check(all(row_el(s_).count('class="cause"') == 1 and ('>%s</span>' % esc(BY[s_]["cause"])) in row_el(s_) for s_ in SUB_IDS)
      and sum(row_el(r["span_id"]).count('class="cause"') for r in rows) == len(SUB_IDS),
      "a substantially_different row does not render its cause in its OWN element")
check(json.loads(SIDE)["rev"] == 5 and json.loads(SIDE)["rev"] is not True and "id='rev-field'>5<" in DOC,
      "the sidecar rev field is missing or not 5, or rev is not visible on the HTML")
check(BASIS_LINE in DOC and "whole_span" in SIDE, "the basis statement is missing from an output")

# 8. rev 5: position-sourced channel 2, each with a liveness count
# 8a. the falsifying instance. Premises first, so the check cannot pass vacuously: the page has a note that carries
# 'benedicent se' and a different note that carries 'in monte Dominus videbitur'.
_n245 = APP_NOTES[245]
_idx_bene = [k_ for k_, n_ in enumerate(_n245) if "benedicent se" in n_["text"]]
_idx_monte = [k_ for k_, n_ in enumerate(_n245) if "in monte Dominus videbitur" in n_["text"]]
check(len(_idx_bene) == 1 and len(_idx_monte) == 1 and _idx_bene != _idx_monte,
      "premise: page 245 does not carry 'benedicent se' and 'in monte Dominus videbitur' in two different notes: %r %r"
      % (_idx_bene, _idx_monte))
_E245 = row_el("p245:n1")
_m245 = re.search(r'<pre class="ch2" data-state="(\w+)">(.*?)</pre>', _E245, flags=re.S)
check(_m245 is not None, "liveness: p245:n1 row element has no channel-2 element")
_st245, _tx245 = _m245.group(1), html.unescape(_m245.group(2))
P245_BRANCH = "bare-only" if _st245 == "absent" else "note-string"
check(_st245 in ("absent", "present"), "p245:n1 channel-2 state is %r" % _st245)
if _st245 == "absent":
    check(_tx245 == "" and BY["p245:n1"]["ch2_why"] != "" and 'data-combined="bare_only_' in _E245,
          "p245:n1 took the bare-only branch but carries text or no reason")
else:
    check("benedicent se" in _tx245 and "in monte Dominus videbitur" not in _tx245,
          "p245:n1 took the string branch but the string is not note [2]'s")
check("in monte Dominus videbitur" not in _tx245, "p245:n1's channel-2 string carries the previous note's gloss")
check(re.search(r'<pre class="chg-old">[^<]*in monte Dominus videbitur', _E245) is not None
      and re.search(r'<pre class="chg-new">[^<]*in monte Dominus videbitur', _E245) is None,
      "p245:n1: the old string is not shown in its own old element, or the new element carries it")
# 8b. no Hebrew in a channel-2 string; the U+2022 mask exercised
N_MASK_ROWS = n_masked
check(HEB_RX.search(PROBE_HEB) and all(not HEB_RX.search(html.unescape(t)) for _s, t in CH2) and N_MASK_ROWS >= 10,
      "a channel-2 string carries a U+0590-U+05FF codepoint, or the mask was not exercised (%d rows)" % N_MASK_ROWS)
# 8c. states partition 45
check(sum(COMBINED_N.values()) == N_EXPECT and set(COMBINED_N) == set(COMBINED_KINDS)
      and N_CH2["present"] + N_CH2["absent"] == N_EXPECT
      and COMBINED_N["present_agree"] + COMBINED_N["present_content_abstained"] == N_CH2["present"],
      "the combined states do not partition %d: %r" % (N_EXPECT, COMBINED_N))
check(len(re.findall(r'data-combined="(\w+)" data-ch2-state="', DOC)) == N_EXPECT
      and all(row_el(r["span_id"]).count('data-combined="%s"' % r["combined"]) == 1 for r in rows),
      "a row does not carry its combined state in its OWN element")
# 8d. every absent row has a non-empty reason, and the reason is rendered in the row
_abs_rows = [r for r in rows if r["ch2_state"] == "absent"]
check(len(_abs_rows) >= 1 and all(r["ch2_why"].strip() for r in _abs_rows)
      and all(esc(r["ch2_why"]) in row_el(r["span_id"]) for r in _abs_rows),
      "an absent row has an empty ch2_why or does not render it (absent rows: %d)" % len(_abs_rows))
# 8e. every present row's ordinal came from a REGION
_pres_rows = [r for r in rows if r["ch2_state"] == "present"]
check(len(_pres_rows) >= 1 and len(_pres_rows) == N_CH2["present"]
      and all(r["pos"]["state"] == "resolved" and r["pos"]["ordinal"] is not None and r["pos"]["overlap"]
              and r["ch2_note_ordinal"] == r["pos"]["ordinal"] for r in _pres_rows)
      and all('data-ordinal="%d"' % r["pos"]["ordinal"] in row_el(r["span_id"]) for r in _pres_rows),
      "a present row's note ordinal is not the position ordinal, or the position field is unpopulated")
# 8f. the containment thresholds are RENDERED TEXT on the sheet (inside their own element)
_cr = re.search(r"<span id='containment-rule'>(.*?)</span>", DOC, flags=re.S)
check(_cr is not None and ">= 80% of the box's height" in html.unescape(_cr.group(1))
      and ">= 20%" in html.unescape(_cr.group(1)) and "x-centre" in html.unescape(_cr.group(1))
      and "Thresholds: win >= 80%" in DOC and CP.WIN_FRAC == 0.80 and CP.LOSE_FRAC == 0.20,
      "the containment rule's thresholds are not rendered as text on the sheet")
# 8g. changed rows render old and new in the row's OWN element
check(len(CHANGED_IDS) >= 1 and DOC.count('<pre class="chg-old">') == len(CHANGED_IDS)
      and DOC.count('<pre class="chg-new">') == len(CHANGED_IDS)
      and DOC.count('data-ch2-changed="yes"') == len(CHANGED_IDS)
      and DOC.count('data-ch2-changed="no"') == N_EXPECT - len(CHANGED_IDS),
      "changed-string rows are not rendered one old/new pair each")
for _sid in CHANGED_IDS:
    _e = row_el(_sid)
    _o = re.search(r'<pre class="chg-old">(.*?)</pre>', _e, flags=re.S)
    _n = re.search(r'<pre class="chg-new">(.*?)</pre>', _e, flags=re.S)
    check(_o is not None and _n is not None and html.unescape(_o.group(1)) == BY[_sid]["ch2_rev4"]["string"]
          and html.unescape(_n.group(1)) == BY[_sid]["ch2"],
          "%s: old/new strings in its own row element do not match the derivation" % _sid)
check(all('data-ch2-changed="no"' in row_el(r["span_id"]) and "chg-old" not in row_el(r["span_id"]) for r in rows if not r["ch2_changed"]),
      "an unchanged row carries a changed marker or an old/new element")
check("<span id='changed-count'><b>%d</b> of %d rows changed" % (len(CHANGED_IDS), N_EXPECT) in DOC,
      "the changed-row count is not stated on the sheet")
# 8h. the rev 4 strings really are rev 4's (read from the file, not re-derived): 45 of them, and p245:n1's has the gloss
check(len(REV4_BY) == N_EXPECT and "in monte Dominus videbitur" in REV4_BY["p245:n1"]["ch2"],
      "the rev 4 comparison strings were not read from the rev 4 sidecar")
# 8i. the renamed witness, with the falsifying instance, on the sheet and the sidecar
check("index_self_consistency" in DOC and "index_self_consistency" in SIDE and "SELF-CONSISTENCY, NOT IDENTITY" in DOC
      and "self-consistency, not identity" in INDEX_SC_TEXT and INDEX_SC_FALSIFIER in html.unescape(DOC)
      and "in monte Dominus videbitur" in INDEX_SC_FALSIFIER and "index=ok" not in DOC
      and "witnesses index=" not in DOC and not any(('"%s"' % k_) in json.dumps(R_["ch2_witness"]) for R_ in rows for k_ in ("index", "count", "hebrew", "marker")),
      "the index witness is not renamed index_self_consistency with its falsifying instance")
# 8j. payload identity, recomputed from the EMITTED sidecar rows
_re = sorted((x_["span_id"], x_["ch2_state"], x_["ch2"]) for x_ in json.loads(SIDE)["rows"])
check(sha16(json.dumps([list(t_) for t_ in _re], ensure_ascii=False, separators=(",", ":")).encode("utf-8")) == PAYLOAD_SHA16
      and json.loads(SIDE)["channel2_payload_sha16"] == PAYLOAD_SHA16 and PAYLOAD_SHA16 in DOC and len(_re) == N_EXPECT,
      "channel2_payload_sha16 does not recompute from the emitted rows")
# 8k. n_calls follows the actual channel counts, on the sheet and the sidecar
check(N_CALLS == 2 * N_BARE_ONLY + 4 * N_DUAL and json.loads(SIDE)["n_calls"] == N_CALLS and "id='n-calls'>%d<" % N_CALLS in DOC
      and N_BARE_ONLY >= 1 and N_DUAL >= 1, "n_calls does not follow the channel counts (%d bare-only, %d dual)" % (N_BARE_ONLY, N_DUAL))
# 8l. the position gates REFUSE: liveness probes over the real page-245 strip and the pure containment rule
_r245 = T74["p245:n1"]
_nat245 = CUT74["p245:n1"]["crop"]["native_rects"]
_ok245 = CP.resolve("probe", 245, _r245["box"], 3, 3, _nat245)
check(_ok245["state"] == "resolved" and _ok245["ordinal"] == 1, "liveness: the position probe does not resolve p245:n1 to region 1")
check(CP.resolve("probe", 245, _r245["box"], 4, 3, _nat245)["gate"] == "count"
      and CP.resolve("probe", 245, _r245["box"], 3, 4, _nat245)["gate"] == "count",
      "liveness: the count gate does not refuse a region/apparatus mismatch")
check(CP.resolve("probe", 245, _r245["box"], 3, 3, [[0, 0, 1, 1]])["gate"] == "frame"
      and CP.resolve("probe", 245, [0, 0, 5, 5000], 3, 3, _nat245)["gate"] == "frame",
      "liveness: the frame gate does not refuse a box that maps elsewhere or lies outside the strip")
check(CP.decide([0.6, 0.4], 10, [[(0, 20)], [(0, 20)]])[0] == "unresolved"
      and CP.decide([0.5, 0.5], 10, [[(0, 20)], [(0, 20)]])[0] == "unresolved"
      and CP.decide([0.8, 0.2], 10, [[(0, 20)], [(0, 20)]])[0] == "unresolved"
      and CP.decide([0.0, 0.79], 10, [[(0, 20)], [(0, 20)]])[0] == "unresolved"
      and CP.decide([0.85, 0.15], 10, [[(0, 20)], [(0, 20)]]) == ("resolved", 0, "")
      and CP.decide([1.0, 0.0], 50, [[(0, 20)], [(0, 20)]])[0] == "unresolved",
      "liveness: the containment rule does not refuse straddles, ties, a sub-80% winner or an off-range x-centre")
# 8m. the content witness: reproduces the measured distribution and can see a wrong note
check(len(CONTENT_AGREE_IDX) + len(CONTENT_DISAGREE_IDX) + len(CONTENT_TIE) == N_EXPECT
      and len(CONTENT_DISAGREE_IDX) >= 1 and len(CONTENT_TIE) >= 1 and "p245:n1" in CONTENT_DISAGREE_IDX
      and "p493:n3" in CONTENT_TIE,
      "liveness: the content witness did not see the known disagreement and the known tie")
check(CP.content_witness(u"התברכו", _n245)["best"] == _idx_bene[0] and CP.content_witness(u"התברכו", _n245)["best_distance"] == 0,
      "liveness: the content witness does not pick the 'benedicent se' note for the signed string התברכו")
check(CP.fold(u"[מַלְךָ]") == u"מלכ" and CP.lev(u"אבג", u"אבד") == 1, "liveness: the fold/lev probes do not behave")

# the .md summary (a class (a) record)
OUT_STEM = "CONTACT_SHEET_scoring45_%s_c2%s" % (SET_DIGEST, PAYLOAD_SHA16)
MD = "\n".join([
    "# Scoring-run contact sheet, %d spans (digest `%s`)" % (len(rows), SET_DIGEST), "",
    "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - %d)." % PRINTED_OFFSET, "",
    "**Nothing was sent.** No network call of any kind. The sheet is `%s.html` (class (b), regenerable, not "
    "committed); this file and `%s.json` are the class (a) records." % (OUT_STEM, OUT_STEM), "",
    "Policy: %s" % POLICY, "",
    "- Spans: %d (%s)" % (len(rows), DERIVATION),
    "- Set digest rule: %s" % DIGEST_RULE,
    "- Models: %s" % ", ".join(MODELS),
    "- Channel 1 bare = A2 span crop alone; channel 2 = crop plus Latin note text with Hebrew masked to U+2022. "
    "No note-box crop leaves the network.",
    "- Calls: %d bare-only rows x 1 channel x %d models + %d dual-channel rows x 2 channels x %d models = %d (rev 4: %d)"
    % (N_BARE_ONLY, len(MODELS), N_DUAL, len(MODELS), N_CALLS, N_CALLS_REV4),
    "- Cost: %s" % (("derived estimate USD %s; %s" % (COST["total_usd"], COST["basis"])) if COST["total_usd"] is not None
                    else "UNKNOWN (no measured per-call cost found)"),
    "- Crop size: width %d-%d px, height %d-%d px; %d under %d px tall" % (min(WS), max(WS), min(HS), max(HS), N_SHORT, SHORT_PX),
    "- Channel 2 string: %d present, %d ABSENT (%s). Source `%s` sha16 `%s`." % (
        N_CH2["present"], N_CH2["absent"], ", ".join(C2_ABSENT_IDS) or "none", F_APP.name, C2_SRC_SHA),
    "- Channel 2 mapping rule: %s" % C2_MAP_RULE,
    "- Channel 2 witnesses: %s" % C2_WITNESSES,
    "- Channel 2 normalisation: %s" % C2_NORM_RULE,
    "- Same-lineage witness result (n_matched/n_comparable; consistency, not identity): %s" % C2_WIT_TXT,
    "- Containment rule: %s" % CP.RULE_TEXT,
    "- Position: %d / %d resolved by position; unresolved by gate %s%s. Region ordinal equals the candidate's note_index-1 on %d." % (
        len(POS_RESOLVED_IDS), len(rows), json.dumps(POS_GATE_N), (" (%s)" % json.dumps(POS_UNRESOLVED)) if POS_UNRESOLVED else "", len(POS_EQ_INDEX)),
    "- Content witness: %d agree with the index mapping, %d disagree (%s), %d tie (%s); shift distribution %s." % (
        len(CONTENT_AGREE_IDX), len(CONTENT_DISAGREE_IDX), ", ".join(CONTENT_DISAGREE_IDX) or "none", len(CONTENT_TIE),
        ", ".join(CONTENT_TIE) or "none", json.dumps(SHIFT_DIST, sort_keys=True)),
    "- Combined states: %s." % ", ".join("%s %d" % (k_, COMBINED_N[k_]) for k_ in COMBINED_KINDS),
    "- **index_self_consistency**: %s" % INDEX_SC_TEXT,
    "- Channel 2 strings changed from rev 4 (%d of %d): %s" % (len(CHANGED_IDS), len(rows), "; ".join(
        "%s: old [%s] %r -> new [%s] %r" % (s_, BY[s_]["ch2_rev4"]["state"], BY[s_]["ch2_rev4"]["string"], BY[s_]["ch2_state"], BY[s_]["ch2"])
        for s_ in CHANGED_IDS) or "none"),
    "- channel2_payload_sha16: `%s` (%s)" % (PAYLOAD_SHA16, PAYLOAD_RULE),
    "- rev: 5", "- %s" % REV5_TEXT, "- %s" % BASIS_LINE,
    "- candidate_vs_signed (n=%d, WHOLE-SPAN basis): %s. Substantially different: %s. %s" % (len(rows), CAND_TXT, ", ".join(SUB_IDS), CAND_RULE),
    "- partial_in_crop (orthogonal flag, 4): %s" % "; ".join("%s whole-span d=%d (%s) / in-crop d=%d (%s)" % (
        s_, BY[s_]["cand_dist"], BY[s_]["cand_class"], BY[s_]["cand_dist_incrop"], BY[s_]["cand_class_incrop"]) for s_ in PARTIAL_IDS),
    "- causes: %s. Unexplained: %s." % ("; ".join("%s: %s" % (s_, BY[s_]["cause"]) for s_ in SUB_IDS), ", ".join(UNEXPLAINED_IDS) or "none"),
    "- **Supersedes** `%s`: %s" % (SUPERSEDES, SUPERSEDES_WHY),
    "- Record of the absent-channel finding: `%s`: %s" % (SUPERSEDES_REV1, SUPERSEDES_REV1_WHY),
    "- Called-out registers: p493:n3 (1 confirmed + 3 corrected; editorial reading; tile 4 restored resh) and p594:n0 "
    "(4 confirmed + 1 sic; printed he in the signature, expected chet beside it; `expected_match` separate from `exact`).",
    "- Changed rows: only %s (re-signed over byte-identical pixels); no other row changed." % ", ".join(ROUND2),
    "- Git start: %s" % json.dumps({k: [v["git_head"][:8], v["git_dirty"].get("state")] for k, v in GIT_START.items()}),
    "- Git end: %s" % json.dumps({k: [v["git_head"][:8], v["git_dirty"].get("state")] for k, v in GIT_END.items()}),
    "- Verdict: %s. %s" % ("PROVISIONAL" if PROV else "clean", WHY_TXT), "",
    "## What this does NOT solve", "",
    "It does not say any crop is legible; Chris reading the pixels does. It does not supply a note text for the "
    "%d BARE-ONLY row(s). POSITION IS NOT INDEPENDENT OF THE INDEX: the stored boxes were placed by "
    "note_line_region.locate_span inside regions[note_index-1], so the region holding a box is the region the "
    "candidate's index named, by construction (it matched note_index-1 on %d of %d); position removes the "
    "dependence on the apparatus list position and supplies the count gate, but only the CONTENT witness can "
    "contradict the index, and it did so for %d row(s). The note TEXT has no geometry of its own, so region -> text "
    "is ordinal within the page: a count agreement is not a correspondence. The content witness compares the signed "
    "string only to each note's opening lemma or its Hebrew; it abstains on a tie (%d row(s)) and cannot adjudicate "
    "a note whose Hebrew is not the signed word. The truth-set candidate differs from the signed signature on %d of "
    "%d rows. It does not fix the scoring rule for the two editorial-register rows, and it does not explain WHY the "
    "box for p245:n1 sits in region 1 while the signed string is note [2]'s lemma." % (
        N_CH2["absent"], len(POS_EQ_INDEX), len(rows), len(CONTENT_DISAGREE_IDX), len(CONTENT_TIE), len(rows) - CAND_N["identical"], len(rows)), "",
    "## Rows", "", "| span (file page) | printed | pass | px | crop sha16 | signed text | disposition | ch2 |",
    "|---|---|---|---|---|---|---|---|"] +
    ["| %s | %d | %d | %dx%d | `%s` | %s | %s | %s |" % (r["span_id"], r["page_printed"], r["pass"], r["crop_w"],
                                                           r["crop_h"], r["crop_sha16"], r["signature"], r["disposition"],
                                                           r["ch2_state"]) for r in rows]) + "\n"

# EXPECTED_CHECKS is pinned to the count observed on the first full run (3 per row in the build loop, plus the
# file-level and born-checks above); a check added or removed changes it and this line then refuses to pass.
EXPECTED_CHECKS = 321   # was 294 before rev 5 (27 net: the rev 4 witness-licensing checks replaced by position/content licensing; new: p245:n1 falsifier premise + branch + gloss-absent + old-in-own-element, Hebrew/mask, partition x2, absent-why, present-ordinal, containment text, changed-row pairs (one per changed row), unchanged rows, changed count, rev 4 strings read, index_self_consistency rename, payload recompute, n_calls, five position-gate liveness probes, content witness liveness x3); was 281 before rev 4 (13 new: nikud bracket assertion + liveness, partial exactly 4, both distances, sidecar partials, partial own-element, no dist<=1 sub + liveness, boundary liveness, cause present, cause own-element, rev field, basis statement); was 227 before rev 3 (54 new: 1 candidate-in-truth-set per row x45, plus 9 candidate_vs_signed born-checks); was 217 before the channel-2 rev 2 (10 new: apparatus shape x2, mask liveness, counts, latin-word, non-empty, bullets probe, witnesses x2, supersession)
if CHECKS != EXPECTED_CHECKS:
    raise AssertionError("ran %d checks, expected %d" % (CHECKS, EXPECTED_CHECKS))

# ---------------------------------------------------------------- write (the only side effect)
for name, text in ((OUT_STEM + ".html", DOC), (OUT_STEM + ".json", SIDE), (OUT_STEM + ".md", MD)):
    with io.open(str(HAD.DATA / name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
print("set digest", SET_DIGEST)
print("crop px: width %d-%d, height %d-%d; under %d tall: %d" % (min(WS), max(WS), min(HS), max(HS), SHORT_PX, N_SHORT))
print("calls", N_CALLS, "cost", COST["total_usd"])
print("ch2", N_CH2, "masked-with-bullet", n_masked)
print("loader_truth_agrees", {r["span_id"]: r["loader_truth_agrees"] for r in rows if "loader_truth_agrees" in r})
print("born-check liveness: note-box probe ok; crop names %d; key probe ok; rows %d, sha present %d; ch2 elements %d "
      "(nonempty %d, masked %d); p493 corrected chips %d confirmed %d; p594 sic %d confirmed %d; before/after %d "
      "unchanged %d" % (N_EXPECT, n_rows_in_doc, n_sha_present, len(CH2), n_nonempty, n_masked,
                        E493.count('data-register="corrected"'), E493.count('data-register="confirmed"'),
                        E594.count('data-register="sic"'), E594.count('data-register="confirmed"'), n_ba, n_unchanged))
print("provisional", PROV, "-", WHY_TXT)
print("checks %d / %d" % (CHECKS, EXPECTED_CHECKS))
print("wrote", OUT_STEM)
