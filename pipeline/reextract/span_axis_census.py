# -*- coding: utf-8 -*-
"""Ruling (4)'s third stratification axis, measured: does a span's own Latin carry its truth?

The 100-span truth set was to be stratified three ways, the third axis being whether the note's Latin
context could BACK-TRANSLATE the Hebrew -- a printed verse address lets a signer (or a model) reconstruct
the span from the canonical text instead of reading the pixels, which is the `read is evidence only about
a guarded crop` failure arriving through the prompt rather than through the box.

This measures the axis over the drawable pool instead of assuming it is balanced. Four cells, first match
wins, strongest evidence first:

  verse-address  a book abbreviation with a chapter AND a verse number -- enough to look the span up.
  chapter-only   book plus chapter, no verse. Narrows the search; does not hand over the words.
  witness-only   a named version or commentator from the profile's own `authorities` list (Pagninus,
                 Targum, Junius...) and no address. Says the note is ABOUT a reading without giving one.
  none           neither.

Two scars are built into the patterns, and both are the reason this is a file and not a one-liner:

  1. ROMAN NUMERALS. Gill cites `Isa. vii. 14`, not `Isa 7:14`. An arabic-only pattern reported ZERO
     verse addresses in the whole volume and made the axis look absent when it is merely rare.
  2. A LEAKY ABBREVIATION IS A FALSE STRATUM. An unbounded alternation invented a `chapter-only` cell of
     4 spans out of nothing: `Malvenda` matched `Mal` + roman `v`, `Miclol` matched `Mic` + `l`. The
     lookarounds (`(?<![A-Za-z])`, `(?![a-z])`) and the required period are what killed that cell. A
     stratum that exists only in the regex is worse than a missing one -- it would have been balanced for.

`note_index` is stored 1-based but indexes the apparatus note list at `note_index - 1`; settled by
content, not by reading the writer (696 of 696 spans land inside their note at -1, 12 of 696 at 0).

What this does NOT do: decide anything about a span, or claim the witness list is exhaustive -- it is the
profile's 31 authorities, so `none` means "no authority THIS PROFILE knows", a book-scoped fact by design.
"""
import io
import json
import os
import re
import sys
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import assembler as ASM                                                    # noqa: E402
from clean_run import git_state, provisional, banner                       # noqa: E402

DV = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1"
AUD = DV + "/audits"
APP = DV + "/vol1_apparatus.jsonl"
CENSUS = AUD + "/hebrew_span_census_20261004.json"
VERDICTS = AUD + "/span_box_verdicts_20260906.jsonl"
POOL = AUD + "/draw_pool_20261004.json"
OUT = AUD + "/span_axis_census_20261004.json"
PROF = os.path.join(_HERE, "book_profile.gill.yaml")

BOOKS = (r"(?:Gen|Exod?|Lev|Num|Deut|Josh|Judg|Ruth|Sam|Kings?|Chron|Ezra|Neh|Esth|Job|Psal?m?|Prov|"
         r"Eccl|Cant|Isa|Jer|Lam|Ezek|Dan|Hos|Joel|Amos|Obad|Jon|Mic|Nah|Hab|Zeph|Hag|Zech|Mal|Matt|"
         r"Mark|Luke|John|Acts|Rom|Cor|Gal|Eph|Phil|Col|Thess|Tim|Tit|Heb|Jam|Pet|Jude|Rev)")
NUM = r"(?:\d+|[ivxlcIVXLC]+)"
ADDR = re.compile(r"(?<![A-Za-z])" + BOOKS + r"(?![a-z])\.?\s*" + NUM + r"\.?\s*[.:,]?\s*\d+")
CHAP = re.compile(r"(?<![A-Za-z])" + BOOKS + r"(?![a-z])\.\s*" + NUM + r"(?![a-z])")

GIT_START = git_state(_HERE)

prof = ASM.load_profile(PROF)
auth = prof.get("authorities") or prof.get("apparatus", {}).get("authorities") or []
assert auth, "the profile carries no `authorities` list, so `witness-only` could never fire and every " \
             "span would fall to `none` -- that is a vacuous pass, not a measurement"
WIT = re.compile("|".join(re.escape(a) for a in auth), re.I)
# A pattern that cannot match its own worked example is a probe that passes on nothing.
assert ADDR.search("as in Gen. xviii. 14, where the"), "ADDR misses a roman-numeral verse address"
assert not ADDR.search("so Malvenda and Miclol render it"), "ADDR matches an authority's NAME"
assert not CHAP.search("so Malvenda and Miclol render it"), "CHAP matches an authority's NAME"

notes = {}
for line in io.open(APP, encoding="utf-8"):
    if not line.strip():
        continue
    o = json.loads(line)
    if "page" in o:
        notes[o["page"]] = [n.get("text") or "" for n in (o.get("notes") or []) if isinstance(n, dict)]

cen = json.load(io.open(CENSUS, encoding="utf-8"))["rows"]
pool_art = json.load(io.open(POOL, encoding="utf-8"))
SEALED = set(pool_art["sealed_pages"])
BOXED = {r["span_id"] for r in pool_art["rows"] if r["verdict"] == "BOX"}
signed = {json.loads(l)["span_id"] for l in io.open(VERDICTS, encoding="utf-8") if l.strip()}

rows = []
for r in cen:
    t = notes[r["page"]][r["note_index"] - 1]
    cell = ("verse-address" if ADDR.search(t) else
            "chapter-only" if CHAP.search(t) else
            "witness-only" if WIT.search(t) else "none")
    rows.append({"span_id": r["span_id"], "page": r["page"], "note_index": r["note_index"],
                 "words": r["words"], "nikud": r["nikud"], "axis": cell,
                 "spent": r["span_id"] in signed or r["span_id"].split("s")[0] in signed
                          or r["page"] in SEALED,
                 "drawable": r["span_id"] in BOXED})
pool = [r for r in rows if not r["spent"]]
draw = [r for r in rows if r["drawable"]]
by = lambda rs: dict(Counter(r["axis"] for r in rs))
print("all %d %s" % (len(rows), by(rows)))
print("unspent pool %d %s" % (len(pool), by(pool)))
print("drawable %d %s" % (len(draw), by(draw)))
print("verse-address, unspent: %s" % [r["span_id"] for r in pool if r["axis"] == "verse-address"])

GIT_END = git_state(_HERE)
print(banner(GIT_START, GIT_END))
json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "git_start": GIT_START, "git_end": GIT_END,
           "provisional": provisional(GIT_START, GIT_END),
           "inputs": {"census": os.path.basename(CENSUS), "pool": os.path.basename(POOL),
                      "apparatus": os.path.basename(APP), "authorities": len(auth)},
           "cells": {"all": by(rows), "unspent_pool": by(pool), "drawable": by(draw)},
           "rows": rows}, io.open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", OUT)
