# -*- coding: utf-8 -*-
r"""Which build of the console produced the 2026-10-04 pass-1 export, and did it have insertions?

Lane B. ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

`diff_resigned` refuses to compare the four re-signed spans against the 2026-10-04 pass-1 signature,
because that export has no `insertions` key at all and AN ABSENT CHANNEL IS NOT AN EMPTY CHANNEL.
Ruling of 2026-11-15, item 5: check `glyph_signer.py` at the commit that built that console. If no
insertion UI existed there, record "insertions channel absent by construction, commit <sha>" and
admit the four rows on that. If it did exist, they stay out. No statement from Chris is needed.

This file decides that question from evidence and writes the record. It does not admit anything: the
record is an input to `diff_resigned`, which checks it by equality against the prior file it licenses.

HOW THE COMMIT IS IDENTIFIED, as a stated rule rather than a guess. The console's export record is
one `JSON.stringify({...})` literal in the generator's JavaScript. Its TOP-LEVEL KEY SET is therefore
a fingerprint of the build. So:

  1. the candidate set is DERIVED: every commit touching `glyph_signer.py` with a commit date at or
     before the day after the export's date -- not a list typed here;
  2. for each candidate, the record literal's top-level keys are parsed out of the JS by a
     brace-depth scan (nested objects like `points_shown_not_adjudicated` contribute no keys);
  3. the export's own key set is taken from ALL of its rows, and every row must agree;
  4. the match must be UNIQUE. Two candidates with the same key set would make the fingerprint
     useless and this file refuses rather than pick one;
  5. the non-matching candidates must each emit `insertions` -- otherwise the absence of the key in
     the export does not discriminate between builds and tells us nothing;
  6. only then is the matching commit's source searched for insertion machinery, by a rule that
     names what it allows: the token `insert` may appear ONLY as `sys.path.insert`.

WHAT THIS DOES NOT SOLVE. It identifies the build whose EMITTER matches, which is not the same as
witnessing the browser session: the console HTML itself is gone (only the sheet `.jsonl` survives),
so no artifact of the sitting can be inspected. A build that emitted the same key set while carrying
an unused insertion UI would defeat step 6 -- which is why step 6 is a search of the whole source for
the token, not a check of the emitter. The record licenses ONE prior file by hash; it is not a
blanket permission, and it says nothing about any other export.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys

from write_scope import assert_inside

sys.stdout.reconfigure(encoding="utf-8")

REPO = "C:/Users/cnogr/git/goatyard-laneB"
SIGNER = "pipeline/reextract/glyph_signer.py"
AUD = "C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits"
EXPORT = os.path.join(AUD, "glyphsign_signed_0401b636ffa7bf1a_20261004_pass1.jsonl")
EXPORT_DATE = "2026-10-04"            # from the export's own filename
UNTIL = "2026-10-05"                  # the day after: a console built that evening still counts
ALLOWED_INSERT_TOKENS = {"sys.path.insert"}

CHECKS = 0


def check(cond, msg):
    global CHECKS
    assert cond, msg
    CHECKS += 1


def git(*a):
    return subprocess.run(["git"] + list(a), cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def record_literal_keys(src):
    """Top-level keys of the console's export record: the `JSON.stringify({...})` inside `L.push(`.

    A brace-depth scan, so a nested object contributes none of its own keys. Returns None when the
    literal is not there at all, which is itself an answer about that build."""
    m = re.search(r"L\.push\(JSON\.stringify\(\{", src)
    if not m:
        return None
    i, depth, keys, buf = m.end() - 1, 0, [], []
    while i < len(src):
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        elif depth == 1:
            buf.append(c)
        i += 1
    else:
        return None
    flat = "".join(buf)
    # depth-1 text only; `a:b,c:d` -> the identifiers that are followed by a colon
    for part in re.split(r",", flat):
        mm = re.match(r"\s*([A-Za-z_][A-Za-z_0-9]*)\s*:", part)
        if mm:
            keys.append(mm.group(1))
    return sorted(set(keys))


def insert_tokens(src):
    return sorted(set(re.findall(r"[A-Za-z_.]*insert[A-Za-z_]*", src)))


# ---------------------------------------------------------------- the export's own fingerprint
rows = [json.loads(l) for l in io.open(EXPORT, encoding="utf-8") if l.strip()]
check(len(rows) > 0, "the export is empty")
keysets = set(tuple(sorted(r.keys())) for r in rows)
check(len(keysets) == 1, "the export's %d rows do not agree on a key set: %s" % (len(rows), keysets))
EXPORT_KEYS = sorted(keysets.pop())
check("insertions" not in EXPORT_KEYS,
      "the export HAS an insertions key -- this whole question does not arise")
EXPORT_SHA16 = hashlib.sha256(io.open(EXPORT, "rb").read()).hexdigest()[:16]

# ---------------------------------------------------------------- the candidate set, derived
log = [l.split(" ", 1) for l in git("log", "--format=%H %ad", "--date=short",
                                    "--until=" + UNTIL, "--", SIGNER).strip().split("\n") if l.strip()]
check(len(log) >= 2, "only %d candidate commit(s) -- a fingerprint cannot discriminate" % len(log))
cands = []
for sha, date in log:
    src = git("show", "%s:%s" % (sha, SIGNER))
    check(len(src) > 0, "%s: could not read %s" % (sha[:7], SIGNER))
    cands.append({"commit": sha, "commit_date": date.strip(),
                  "subject": git("log", "-1", "--format=%s", sha).strip(),
                  "record_keys": record_literal_keys(src),
                  "emits_insertions": "insertions" in (record_literal_keys(src) or []),
                  "insert_tokens": insert_tokens(src),
                  "source_lines": len(src.split("\n"))})

check(all(c["record_keys"] is not None for c in cands),
      "a candidate has no export record literal at all: %s"
      % [c["commit"][:7] for c in cands if c["record_keys"] is None])

# ---------------------------------------------------------------- the match, and it must be unique
matches = [c for c in cands if c["record_keys"] == EXPORT_KEYS]
check(len(matches) == 1,
      "the record-key fingerprint matched %d candidate(s), so it does not identify a build: %s"
      % (len(matches), [c["commit"][:7] for c in matches]))
BUILD = matches[0]
others = [c for c in cands if c is not BUILD]
check(all(c["emits_insertions"] for c in others),
      "a non-matching candidate also omits `insertions`, so the export's missing key does not "
      "discriminate between builds: %s"
      % [c["commit"][:7] for c in others if not c["emits_insertions"]])

# ---------------------------------------------------------------- step 6: the whole source, not the emitter
stray = [t for t in BUILD["insert_tokens"] if t not in ALLOWED_INSERT_TOKENS]
HAS_UI = bool(stray)
check(BUILD["record_keys"] == EXPORT_KEYS and "insertions" not in BUILD["record_keys"],
      "the matched build emits an insertions key after all")

verdict = ("insertions channel absent by construction" if not HAS_UI
           else "an insertion UI existed in this build: the four rows stay out")

doc = {
    "kind": "channel_absent_by_construction" if not HAS_UI else "channel_present_rows_stay_out",
    "verdict": verdict,
    "note": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88). Lane B. Derived by "
            "pass1_channel_provenance.py from git history and the export's own key set; no "
            "statement from a human is quoted or needed.",
    "channel": "insertions",
    "side": "prior",
    "licenses_prior_file": os.path.basename(EXPORT),
    "licenses_prior_file_sha16": EXPORT_SHA16,
    "licenses_nothing_else": "This record permits exactly one comparison: the prior file whose "
                             "sha16 is named above. diff_resigned checks it by equality.",
    "commit": BUILD["commit"],
    "commit_date": BUILD["commit_date"],
    "commit_subject": BUILD["subject"],
    "how_the_commit_was_identified":
        "The console's export record is one JSON.stringify({...}) literal; its top-level key set is "
        "a fingerprint of the build. The candidate set was derived as every commit touching "
        "%s with a commit date at or before %s. Exactly one candidate's key set equals the "
        "export's, over all %d rows, and every other candidate emits `insertions` -- so the missing "
        "key discriminates." % (SIGNER, UNTIL, len(rows)),
    "export_record_keys": EXPORT_KEYS,
    "insert_tokens_in_matched_build": BUILD["insert_tokens"],
    "insert_tokens_allowed": sorted(ALLOWED_INSERT_TOKENS),
    "insert_tokens_not_allowed_found": stray,
    "candidates": cands,
    "what_this_does_not_solve": [
        "It identifies the build whose EMITTER matches, not the browser session. The console HTML is "
        "gone; only the sheet glyphsign_0401b636ffa7bf1a.jsonl survives, so no artifact of the "
        "sitting can be inspected.",
        "Step 6 searches the WHOLE source for the token `insert`, not just the emitter, because a "
        "build could carry an unused insertion UI and still emit the matching key set.",
        "It says nothing about any other export, and nothing about whether the readings are right.",
    ],
}
body = json.dumps(doc, indent=1, ensure_ascii=True, sort_keys=True).encode("utf-8")
doc["record_sha16"] = hashlib.sha256(body).hexdigest()[:16]
doc["record_sha16_rule"] = ("sha256 of json.dumps(this document WITHOUT record_sha16 and "
                            "record_sha16_rule, indent=1, ensure_ascii=True, sort_keys=True), "
                            "UTF-8 bytes, first 16 hex")
# The count check comes BEFORE the write: a build that refuses must leave nothing behind. The
# expected total is DERIVED from a term this run measures -- eight fixed checks plus one per
# candidate commit read -- so it cannot go stale against a snapshot nobody re-derives.
EXPECTED = 9 + len(cands)
check(CHECKS + 1 == EXPECTED, "ran %d checks before the final count, expected %d (8 fixed + %d "
      "candidates + this one)" % (CHECKS + 1, EXPECTED, len(cands)))

dest = os.path.join(AUD, "CHANNELBASIS_pass1_insertions_%s.json" % doc["record_sha16"])
final = json.dumps(doc, indent=1, ensure_ascii=True).encode("utf-8")
assert_inside(dest, "the channel-basis record belongs in the audits directory")
if os.path.exists(dest) and io.open(dest, "rb").read() != final:
    sys.exit("REFUSING TO CLOBBER: %s exists and holds different bytes" % os.path.basename(dest))
io.open(dest, "wb").write(final)
print("VERDICT: %s" % verdict)
print("  build       %s  %s  %s" % (BUILD["commit"][:12], BUILD["commit_date"], BUILD["subject"]))
print("  fingerprint %d keys, matched 1 of %d candidates; the others emit `insertions`"
      % (len(EXPORT_KEYS), len(cands)))
print("  insert tokens in that build: %s" % (BUILD["insert_tokens"] or "(none)"))
print("  licenses    %s (%s), insertion axis, prior side only"
      % (os.path.basename(EXPORT), EXPORT_SHA16))
print("  wrote %s   (%d checks)" % (os.path.basename(dest), CHECKS))
