# -*- coding: utf-8 -*-
"""Enumerate the corpus-wide Hebrew-span population from the frozen vol.1 apparatus.

The 100-span draw has no population to draw from: build_set() holds 21 spans and span_isolation is
imported only by its own test. This is the census -- TEXT level only, deterministic, no boxes. Boxes are
the localizer's job (span_isolation's own docstring forbids post-hoc alignment), so every row here is a
CANDIDATE whose crop does not exist yet.

Scratchpad only. Nothing here is drawn from, stratified or sent until the shape is reviewed.
"""
import io
import json
import re
import os
import sys
from collections import Counter

# Import from THIS file's directory, never a hardcoded worktree: a copy of this script in the
# other lane's tree must import that lane's modules, not Lane B's.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import span_isolation as SI                                               # noqa: E402

APP = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1/vol1_apparatus.jsonl"
# The committed artifacts, by their committed names. Not a session scratchpad: a script in the repo must be
# able to reproduce the artifact beside it in the repo, and the dated filename is deliberate -- these are
# dated observations of a frozen apparatus run, so a rerun under a new date writes a NEW file rather than
# quietly replacing the one an ADR cites.
DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
CENSUS = AUD + "/hebrew_span_census_20261004.json"
OUT = CENSUS

NIKUD = re.compile(u"[\u0591-\u05c7]")          # points + cantillation
LETTER = re.compile(u"[\u05d0-\u05ea]")         # consonantal letters only
FINAL = re.compile(u"[\u05da\u05dd\u05df\u05e3\u05e5]")

hdr = None
rows = []
pages_seen = 0
HEBFLAG = set()
pages_flagged_heb = 0
pages_with_span = 0
notes_total = 0
status_of_page = {}

for line in io.open(APP, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    o = json.loads(line)
    if o.get("kind") == "config_header":
        hdr = o
        continue
    pages_seen += 1
    page = o["page"]
    status_of_page[page] = o.get("status")
    if o.get("hebrew"):
        pages_flagged_heb += 1
        HEBFLAG.add(page)
    notes = o.get("notes") or []
    notes_total += len(notes)
    got = False
    for ni, nt in enumerate(notes, 1):
        if not isinstance(nt, dict):
            continue
        txt = nt.get("text") or ""
        spans = SI.hebrew_spans(txt)
        for si, sp in enumerate(spans, 1):
            got = True
            h = sp["hebrew"]
            rows.append({
                # span_id follows the marker's own number where the marker is [^N]; otherwise the note's
                # ordinal. The suffix only appears when one note carries more than one Hebrew run.
                # 0-BASED note index, because that is the convention the signed verdicts, SEALED_TRUTH
                # and the content-addressed approval sidecars already use. Settled by CONTENT: of the 30
                # ratified span_ids, 12 match the census Hebrew exactly at note_index-1 and 0 match at
                # the marker's printed number. Getting this wrong does not fail loudly -- 5 of the 30
                # ids collided with a DIFFERENT span under the 1-based scheme, which would have let a
                # sealed span into the draw while the exclusion list reported a hit.
                "span_id": "p%d:n%d%s" % (page, ni - 1, ("" if len(spans) == 1 else "s%d" % si)),
                "page": page,
                "note_index": ni,
                "notes_on_page": len(notes),
                "marker": nt.get("marker"),
                "page_status": o.get("status"),
                "hebrew": h,
                "letters": len(LETTER.findall(h)),
                "chars": len(h),
                "nikud": bool(NIKUD.search(h)),
                "nikud_marks": len(NIKUD.findall(h)),
                "finals": len(FINAL.findall(h)),
                "words": len([w for w in h.split() if LETTER.search(w)]),
                "greek_present": sp["greek_present"],
                "spans_in_note": len(spans),
                "ctx_len": len(sp["latin_context"]),
                "start": sp["start"], "end": sp["end"], "note_len": len(txt),
                # where the Hebrew sits inside its note, the only positional axis available without a box
                "pos_in_note": round(sp["start"] / float(max(1, len(txt))), 3),
            })
    if got:
        pages_with_span += 1

flag = {r["page"] for r in rows}
hdr_pages = set(status_of_page)
mismatch_no_span = sorted(p for p in hdr_pages if status_of_page.get(p) is not None
                          and p not in flag)
json.dump({"source": APP, "source_header": hdr, "rows": rows}, io.open(OUT, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

L = Counter()
for r in rows:
    L["1 word" if r["words"] <= 1 else ("2 words" if r["words"] == 2 else
                                        ("3-4 words" if r["words"] <= 4 else "5+ words"))] += 1
print("header git_head=%s profile_sha16=%s started=%s"
      % ((hdr or {}).get("git_head", "")[:8], (hdr or {}).get("profile_sha16"), (hdr or {}).get("started")))
print("pages %d | hebrew=True flag %d | pages with an isolated span %d | notes %d"
      % (pages_seen, pages_flagged_heb, pages_with_span, notes_total))
print("SPANS: %d   unique span_ids: %d" % (len(rows), len({r["span_id"] for r in rows})))
print("by word count:", dict(L))
print("nikud-bearing: %d (%.0f%%)  greek also in note: %d  multi-span notes: %d"
      % (sum(1 for r in rows if r["nikud"]), 100.0 * sum(1 for r in rows if r["nikud"]) / max(1, len(rows)),
         sum(1 for r in rows if r["greek_present"]), sum(1 for r in rows if r["spans_in_note"] > 1)))
print("letters: min %d  median %d  max %d"
      % (min(r["letters"] for r in rows), sorted(r["letters"] for r in rows)[len(rows) // 2],
         max(r["letters"] for r in rows)))
print("page_status of span-bearing pages:", dict(Counter(r["page_status"] for r in rows)))
# The flag and the isolator must agree: a page the extractor marked hebrew=True with no
# isolable Hebrew run is either a flag error or a note the isolator cannot see.
flagged = {p for p in status_of_page}
print("pages flagged hebrew=True but NO isolated span:", len(HEBFLAG - flag),
      sorted(HEBFLAG - flag)[:12])
print("pages with a span but NOT flagged hebrew=True:", len(flag - HEBFLAG),
      sorted(flag - HEBFLAG)[:12])
print("wrote", OUT)
