# -*- coding: utf-8 -*-
u"""The LOCALIZER presence draw's sender: does the stored box carry the Hebrew at all?

Lane B / session 50612c81.  ALL PAGE NUMBERS ARE FILE pages (printed = file - 88).

Chris, 2026-11-25 (item 4): "Dry-run the localizer draw end to end against a stub endpoint, so the
real run is one command after Chris approves the spend."

The draw itself is registered in PREDICTIONS_localizer45_bf942e009e51c71e.json, written 2026-11-22
and hashed before any of this existed.  EVERY RUN PARAMETER IS READ OUT OF THAT RECORD -- the arms,
the channel, the call count, the token cap, the required population digest -- because a sender that
carries its own copy of the numbers can drift from the lock it claims to run under, and the drift
would be invisible in the output.  The two things this module pins itself are the lock's own sha16
and the names of the files it reads; everything else is derived.

MODES, and what each one may touch:

  --self-test            the parser, the decision rule, the secondary and the falsifiers over
                         hand-made strings.  No files, no network, no money.
  --dry-run              every gate except the key and the network; builds all 90 payloads; writes
                         NOTHING; prints the pre-call check count, which is what `--send` must be
                         given.  A header-scoped guard must never be discovered by spending.
  --stub-run --out-dir D end to end against a LOCAL STUB on 127.0.0.1: the gates, the payloads, the
                         HTTP, the parse, the decision rule, the report and the write path.  The
                         stub's replies are scripted in this file, so the stub run proves the
                         WIRING and says nothing whatever about any box.  No key is read.
  --send --expect-checks N
                         the real paid run.  Needs the gates below to pass, and today it REFUSES:
                         the second sitting is not ingested and the 45-crop sheet has no approval.
                         The refusal names each missing thing, which is the point of item 4.

WHY A STUB AND NOT A --dry-run ALONE.  A dry-run builds payloads and stops, so it cannot exercise
the half of the run where the money has already been spent: the parse of a reply that does not obey
the shape, the retry counter, the run-level aborts, the decision rule, the report's first line, the
write.  Those are exactly the places a defect costs a paid run and not a free one.  The stub also
makes the abort paths demonstrable instead of asserted: `--stub-scenario fault-head` and
`dead-items` MUST abort and leave the output directory empty, and the run says so out loud.

WHAT THE STUB CANNOT DO.  It knows the signed strings, because its script is built from them -- a
stub that could not produce a plausible read could not exercise the scorer.  So no number from a
stub run is evidence about pixels, about boxes, or about any arm, and `scoreable: false` is written
into every stub artifact.  A verifier that calls the producer agrees by construction; this one
announces that it is one.

Interpreter: C:/Users/cnogr/git/goat-yard-archive/.venv/Scripts/python.exe, PYTHONIOENCODING=utf-8,
cwd = this directory.
"""
import argparse
import base64
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import httpx  # noqa: E402

import hebrew_aperture_diag as diag  # noqa: E402
import hebrew_frontier_or as H  # noqa: E402
import localizer45_lock as LOCK  # noqa: E402
import score45_run as S  # noqa: E402
import sealed_boundary as SB  # noqa: E402
import send_refusal as SR  # noqa: E402
import write_scope as WS  # noqa: E402

A = Path(str(diag.DATA))
LOCK_SHA = "bf942e009e51c71e"
LOCK_PATH = A / ("PREDICTIONS_localizer45_%s.json" % LOCK_SHA)
CLEAN_SHEET = A / LOCK.SHEET41
CLEAN_SHEET_BYTES_SHA = LOCK.SHEET41_SHA
CTRL_SHEET = A / "CONTACT_SHEET_controls4_e9132010ceda4a52.json"
CROPS = Path(str(LOCK.CROPS))
CUT = LOCK.CUT
CENSUS = A / "hebrew_span_census_20261004.json"
ATTEMPT = 1
PRINTED_OFFSET = 88

# The 45-crop sheet and its approval.  NAMED HERE AND NOT FOUND ON DISK: the four control crops are
# new disclosure (lock precondition P4), so the sheet Chris approves for this draw is a 45-row sheet
# that does not exist yet.  CONTACT_SHEET_controls4_e9132010ceda4a52.json is its new-disclosure half,
# built 2026-11-23 and not yet approved.  The gate wants the whole sheet and one yes over it, because
# two approvals over two populations is how a licence gets honoured on one axis and not the other.
SHEET45_PREFIX = "CONTACT_SHEET_localizer45_"
APPROVAL_FMT = "APPROVAL_localizer45_%s.json"

# The sitting-2 gate.  Chris's condition is "the second sitting is INGESTED"; the checkable form is
# the layer manifest that `sitting2_signed_layer.py` writes when accepted rows become a signed layer.
SITTING2_MANIFEST_PREFIX = "SITTING2LAYER_"

STUB_HOST = "127.0.0.1"
FORBIDDEN_HOSTS = S.FORBIDDEN_HOSTS          # one list, shared: .179 / .188 / .169
RETRY_CODES = S.RETRY_CODES
RETRIES = H.RETRIES
BACKOFF = H.BACKOFF
CONSECUTIVE_FAIL_ABORT = S.CONSECUTIVE_FAIL_ABORT
NIKUD = S.NIKUD
HEB = S.HEB

MUST_FAULT = ("fault-head", "dead-items")   # scenarios whose WHOLE POINT is the abort

VERDICTS = ("present", "absent_candidate", "disputed", "unmeasured")
STRATA = ("clean", "control")
# The three spans the signer marked `not-hebrew-or-blank`.  p677:n13 is in the control stratum too
# but is the MISLOCATION control, not an absence control, so F1 is scored over these three only.
NOT_HEBREW_CONTROLS = ("p257:n3", "p399:n5", "p426:n1")

PROMPT = (
    "This image is a tight crop from a page of an 18th-century printed English book.\n"
    "Some crops like this one contain a short word printed in the Hebrew alphabet. Others contain "
    "no Hebrew at all: only Latin-alphabet text, a printer's rule or ornament, or part of the line "
    "above or below.\n"
    "Answer about THIS image only. Do not guess at what a crop like this usually holds.\n"
    "1. Does the image contain text in the Hebrew alphabet?\n"
    "2. If it does, write the Hebrew consonants that are printed, in the order they appear on the "
    "page. Write only what you can see.\n"
    "If the image contains no Hebrew-alphabet text, answer no. `no` is a complete and correct "
    "answer and needs no transcription.\n"
    "Reply with one JSON object and nothing else:\n"
    '{"hebrew_present": "yes" or "no", "consonants": "the consonants, or an empty string", '
    '"reason": "one short line"}'
)

CHECKS = 0


def chk(cond, msg):
    u"""Every assertion in this run goes through here, so the counter is live and the pin can bite."""
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


def canon(o):
    return S.canon(o)


def sha16_bytes(b):
    return S.sha16_bytes(b)


def sha16(o):
    return S.sha16_bytes(canon(o).encode("utf-8"))


HASH_RULE = ("sha256[:16] over the UTF-8 bytes of json.dumps(obj, sort_keys=True, "
             "separators=(\",\",\":\"), ensure_ascii=False)")


def scan_for_leaks(text, what):
    u"""One predicate, two populations: the header before the calls and every record after them."""
    for h in FORBIDDEN_HOSTS:
        chk(h not in text, "forbidden host %s in %s" % (h, what))
    chk("sk-or-" not in text, "key material in %s" % what)


def _nfc(t):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t or "")).strip()


def bare_consonants(t):
    u"""The consonant skeleton: NFC, marks stripped, spaces collapsed.  The comparison unit for the
    SECONDARY analysis only -- nikud is a verdict of its own elsewhere and is never 'wrong' here."""
    return NIKUD.sub("", _nfc(t))


# --------------------------------------------------------------------------------- the registration
def load_lock():
    u"""GATE 0S: the lock recomputes to its own name, and nothing here is transcribed from it."""
    chk(LOCK_PATH.exists(), "GATE 0S: the methods lock %s is not on disk" % LOCK_PATH.name)
    rec = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    body = dict((k, v) for k, v in rec.items() if k != "self_sha16")
    got = sha16(body)
    chk(got == LOCK_SHA,
        "GATE 0S: %s recomputes to %s, not %s -- the registered lock has been edited"
        % (LOCK_PATH.name, got, LOCK_SHA))
    chk(rec.get("self_sha16") == LOCK_SHA, "GATE 0S: %s's own self_sha16 is not %s"
        % (LOCK_PATH.name, LOCK_SHA))
    chk(rec["run"]["attempt"] == ATTEMPT,
        "GATE 0S: the lock registers attempt %r and this sender is attempt %d"
        % (rec["run"]["attempt"], ATTEMPT))
    chk(rec["run"]["population_digest_required"] == LOCK.PINNED_DIGEST,
        "GATE 0S: the lock requires population digest %r, and localizer45_lock pins %r -- two "
        "numbers for one population" % (rec["run"]["population_digest_required"],
                                        LOCK.PINNED_DIGEST))
    return rec


def run_params(lock):
    u"""The arms, the channel, the cap and the call count, READ OUT OF THE LOCK.

    Not module constants.  A sender holding its own copy of `ARMS` can send a different draw under a
    lock's numbers, and no artifact would show it: the lock's hash would still check, the call count
    would still be 90, and the arm names would sit in the record looking registered."""
    r = lock["run"]
    arms = list(r["arms"])
    chk(len(arms) == len(set(arms)) and len(arms) == 2,
        "the lock registers %r as its arms" % (arms,))
    chk(all(":batch" not in a for a in arms),
        "no :batch variants this run -- the lock says so and so does the standing rule")
    chk(list(r["channels"]) == ["bare"],
        "the lock registers channels %r; this sender only knows bare" % (r["channels"],))
    chk(int(r["draws_per_item"]) == 1, "the lock registers %r draws per item" % r["draws_per_item"])
    cap = int(r["max_tokens"])
    chk(cap == LOCK.MAX_TOKENS_PINNED and cap < H.MAX_TOKENS,
        "the cap in the lock is %d, the module pins %d, and the sender default is %d"
        % (cap, LOCK.MAX_TOKENS_PINNED, H.MAX_TOKENS))
    return arms, cap, int(r["calls"])


# ----------------------------------------------------------------------------------- the population
def _row_clean(r):
    return {"span_id": r["span_id"], "stratum": "clean",
            "page_file": r["page_file"], "page_printed": r["page_printed"],
            "crop_file": r["crop_file"], "crop_sha16": r["crop_sha16"],
            "signature": r.get("signature"), "signature_full": r.get("signature_full"),
            "signer_fault_october": None, "candidate_shown_to_the_signer": None}


def _row_control(r):
    om = r.get("october_mark") or {}
    return {"span_id": r["span_id"], "stratum": "control",
            "page_file": r["file_page"], "page_printed": r["printed_page"],
            "crop_file": r["crop_file"], "crop_sha16": r["crop_sha16"],
            # NO SIGNED STRING, and the field says so rather than holding an empty string: pass 1
            # recorded `complete: false` for all four, so the secondary comparison is undefined for
            # them and must not quietly score as a miss against "".
            "signature": None, "signature_full": None,
            "signer_fault_october": om.get("fault") or om.get("note") or "marked 2026-10-04",
            "candidate_shown_to_the_signer": om.get("candidate_shown_to_the_signer")}


def population_rows():
    u"""The 45 rows: 41 from the approved scoring sheet, 4 from the controls sheet.

    DERIVED from the lock's own population() -- which derives the clean set from the sheet and the
    law-8 sidecar and asserts the refusal set has not moved -- and then matched against the two
    sheets.  A hand-copied list of 45 ids is a snapshot pin and a snapshot pin cannot tell a
    legitimate change from a mistake."""
    clean_ids, ctrl_ids = LOCK.population()
    sheet = json.loads(CLEAN_SHEET.read_text(encoding="utf-8"))
    chk(sha16_bytes(CLEAN_SHEET.read_bytes()) == CLEAN_SHEET_BYTES_SHA,
        "the approved scoring sheet's bytes are %s, not the approved %s"
        % (sha16_bytes(CLEAN_SHEET.read_bytes()), CLEAN_SHEET_BYTES_SHA))
    by_id = dict((r["span_id"], r) for r in sheet["rows"])
    chk(set(clean_ids) <= set(by_id), "law-8 sendable ids missing from the sheet: %r"
        % sorted(set(clean_ids) - set(by_id)))
    chk(CTRL_SHEET.exists(), "the controls sheet %s is not on disk" % CTRL_SHEET.name)
    csheet = json.loads(CTRL_SHEET.read_text(encoding="utf-8"))
    cby_id = dict((r["span_id"], r) for r in csheet["rows"])
    chk(sorted(cby_id) == sorted(ctrl_ids),
        "the controls sheet holds %r and the lock's control stratum is %r"
        % (sorted(cby_id), sorted(ctrl_ids)))
    rows = [_row_clean(by_id[i]) for i in clean_ids] + [_row_control(cby_id[i]) for i in ctrl_ids]
    for r in rows:
        chk(r["page_printed"] == r["page_file"] - PRINTED_OFFSET,
            "%s: printed %r is not file %r minus %d"
            % (r["span_id"], r["page_printed"], r["page_file"], PRINTED_OFFSET))
        chk(r["crop_file"].endswith(diag.OFFNET_SUFFIX),
            "%s: %s is not an A2 span-box crop" % (r["span_id"], r["crop_file"]))
        chk("A1_notebox" not in r["crop_file"], "%s: a note-box crop is in the plan" % r["span_id"])
    chk(len(rows) == len(set(x["span_id"] for x in rows)), "a span is in the population twice")
    return rows


def population_digest(rows):
    u"""sha16 over the REALIZED bytes of the crops, keyed by span.  The lock's own recipe, over the
    rows this sender built -- so a crop recut, renamed or re-padded moves it and the run aborts."""
    items = sorted([r["span_id"], S.stream_sha16(CROPS / r["crop_file"])] for r in rows)
    return sha16(items), items


def gate_population(rows, lock):
    dig, items = population_digest(rows)
    n_clean = sum(1 for r in rows if r["stratum"] == "clean")
    n_ctrl = sum(1 for r in rows if r["stratum"] == "control")
    chk(len(rows) == lock["population"]["n_spans"],
        "F5: %d spans in the plan, %d registered" % (len(rows), lock["population"]["n_spans"]))
    chk(n_clean == lock["population"]["strata"]["clean"]["n"]
        and n_ctrl == lock["population"]["strata"]["control"]["n"],
        "F5: strata are %d clean / %d control; the lock registers %d / %d"
        % (n_clean, n_ctrl, lock["population"]["strata"]["clean"]["n"],
           lock["population"]["strata"]["control"]["n"]))
    chk(dig == lock["run"]["population_digest_required"],
        "F5: the population digest is %s, not the registered %s.  Something about the 45 crops "
        "changed.  The run is UNSCOREABLE against this lock -- write a new lock, never repin."
        % (dig, lock["run"]["population_digest_required"]))
    # The sheet's row for each clean span claims a crop hash.  Compared against the file, because
    # the row's claim and the bytes an arm is shown are two different things.
    byid = dict(items)
    for r in rows:
        if r["stratum"] == "clean":
            chk(byid[r["span_id"]] == r["crop_sha16"],
                "%s: the file hashes to %s and the sheet says %s"
                % (r["span_id"], byid[r["span_id"]], r["crop_sha16"]))
    return dig


def gate_law8(rows, lock):
    u"""Law 8 twice over: the refusal set over the sheet is still the pinned four, and none of the 45
    is refused.  The lock's population() asserts the first; this asserts the second, over the rows
    actually planned, because the plan is what reaches the wire."""
    flags = SR.load_span_flags(str(A / SR.SIDECAR_NAME))
    ids = [r["span_id"] for r in rows]
    sendable, refused = SR.partition(ids, flags)
    chk(not refused,
        "law 8 refuses %r out of the planned population.  A refusal set that eats part of the "
        "draw moves the denominators: re-measure free, write a new lock." % sorted(refused))
    chk(sorted(sendable) == sorted(ids), "law 8's sendable set is not the planned set")
    chk(lock["population"]["law_8"]["refused_in_this_draw"] == 0,
        "the lock registers %r refusals in this draw"
        % lock["population"]["law_8"]["refused_in_this_draw"])
    return sorted(refused)


def gate_sealed(rows, lock):
    u"""0 of the 45 sit on a sealed page, measured 2026-11-22 and re-measured here.

    SEALED pages are spent: never re-scored, never opened.  This gate is not a formality -- it is
    the one check that keeps a presence draw from becoming a re-score of ratified work."""
    sealed = sealed_pages()
    on = sorted(r["span_id"] for r in rows if r["page_file"] in sealed)
    chk(not on, "sealed pages intersected by the draw: %r -- SEALED is spent, the run does not go"
                % on)
    chk(lock["population"]["sealed_pages_intersected"] == 0,
        "the lock registers %r sealed intersections"
        % lock["population"]["sealed_pages_intersected"])
    # The registered 0 above is a PREDICTION I wrote into the lock; the `chk` before it is the
    # measurement, and it is now taken over all fifteen pages rather than the ten a span table
    # knows about.  Both are kept and they are not the same claim.
    chk(len(sealed) == SB.PINNED_UNION,
        "the sealed union is %d pages, not the %d pinned in sealed_boundary"
        % (len(sealed), SB.PINNED_UNION))
    return sorted(sealed)


def sealed_pages():
    u"""Every page ANY record calls sealed -- fifteen -- from sealed_boundary.py.

    The first version of this function derived the boundary from the keys of SEALED_TRUTH, which is
    a SPAN table: ten pages, five short of the page-level record, and four of the five missing ones
    (129, 206, 478, 543) are pages the DRAW did not exclude either.  A boundary each consumer
    re-derives is one consumer away from a page being spent twice.  See sealed_boundary.py for the
    three records and why the union is not a compromise: over-excluding costs one unsent span,
    under-excluding re-opens ratified work, and those errors are not the same size.

    An unreadable record raises there.  An unreadable boundary is not an empty one."""
    return SB.union()


# ---------------------------------------------------------------------------------------- the gates
def gate_disclosure(dry):
    u"""The 45-crop sheet and the one yes over it.

    Reported in a dry run, FATAL for a send.  Two findings, named rather than counted, because the
    thing that is missing is what a human has to do next:
      - the 45-row sheet does not exist (the controls half does, unapproved);
      - no APPROVAL_localizer45_<sheet bytes>.json licenses attempt 1."""
    sheets = sorted(p for p in A.glob(SHEET45_PREFIX + "*.json"))
    state = {"sheet": None, "sheet_bytes_sha16": None, "approval": None, "by": None, "on": None,
             "controls_half": CTRL_SHEET.name if CTRL_SHEET.exists() else None,
             "controls_half_bytes_sha16":
                 sha16_bytes(CTRL_SHEET.read_bytes()) if CTRL_SHEET.exists() else None}
    if sheets:
        chk(len(sheets) == 1, "more than one 45-crop sheet on disk: %r" % [p.name for p in sheets])
        state["sheet"] = sheets[0].name
        state["sheet_bytes_sha16"] = sha16_bytes(sheets[0].read_bytes())
        srows = json.loads(sheets[0].read_text(encoding="utf-8")).get("rows") or []
        state["sheet_n_rows"] = len(srows)
        ap = A / (APPROVAL_FMT % state["sheet_bytes_sha16"])
        if ap.exists():
            rec = json.loads(ap.read_text(encoding="utf-8"))
            chk(rec.get("approves_sheet_bytes_sha16") == state["sheet_bytes_sha16"],
                "%s approves sheet bytes %r and its own name says %s"
                % (ap.name, rec.get("approves_sheet_bytes_sha16"), state["sheet_bytes_sha16"]))
            chk(rec.get("approves_cut_digest") == CUT,
                "%s approves cut %r, not %s -- the approved crops are not these crops"
                % (ap.name, rec.get("approves_cut_digest"), CUT))
            chk(bool(rec.get("by")) and bool(rec.get("on")),
                "%s names no approver or no date" % ap.name)
            chk(ATTEMPT in (rec.get("approves_attempts") or []),
                "%s licenses attempts %r and this is attempt %d.  A yes to one spend is not a yes "
                "to the next one on the same crops."
                % (ap.name, rec.get("approves_attempts"), ATTEMPT))
            state.update(approval=ap.name, by=rec.get("by"), on=rec.get("on"))
    want = A / (APPROVAL_FMT % (state["sheet_bytes_sha16"] or "<the sheet's bytes>"))
    if dry:
        chk(True, "disclosure gate evaluated (dry: reported, not fatal): sheet=%r approval=%r"
                  % (state["sheet"], state["approval"]))
    else:
        chk(state["sheet"] is not None,
            "NOT APPROVED: there is no %s*.json on disk.  The four control crops are new "
            "disclosure (lock P4), so this draw needs a 45-row sheet -- native size, each crop "
            "beside its signed text where one exists, the four controls marked as new disclosure "
            "-- and Chris approves the crops on what they SHOW.  %s is its unapproved half."
            % (SHEET45_PREFIX, CTRL_SHEET.name))
        chk(state["by"] is not None,
            "NOT APPROVED: %s does not exist or names no approver.  Nothing goes out before a "
            "human approves the crops." % want.name)
    return state


def gate_sitting2(dry):
    u"""Chris's own precondition: the second sitting is INGESTED before the first paid call.

    The checkable form is the layer manifest `sitting2_signed_layer.py` writes from accepted rows.
    Reported in a dry run, fatal for a send.  It is a real gate and not a formality: the sitting
    changes which spans carry a signed string, which is what the secondary analysis compares to."""
    mans = sorted(p for p in A.glob(SITTING2_MANIFEST_PREFIX + "*.json"))
    state = {"manifest": None, "layer": None, "layer_rows": None}
    if mans:
        chk(len(mans) == 1, "more than one sitting-2 layer manifest: %r" % [p.name for p in mans])
        rec = json.loads(mans[0].read_text(encoding="utf-8"))
        state["manifest"] = mans[0].name
        lay = rec.get("layer") or rec.get("layer_file")
        state["layer"] = lay
        p = A / lay if lay else None
        chk(p is not None and p.exists(),
            "%s names layer %r, which is not on disk" % (mans[0].name, lay))
        state["layer_rows"] = sum(1 for l in io.open(str(p), encoding="utf-8") if l.strip())
    if dry:
        chk(True, "sitting-2 gate evaluated (dry: reported, not fatal): manifest=%r"
                  % state["manifest"])
    else:
        chk(state["manifest"] is not None,
            "the second sitting is not ingested: no %s*.json in %s.  Chris's condition for this "
            "spend, and the honest order -- the sitting's verdicts change which spans carry a "
            "signed string." % (SITTING2_MANIFEST_PREFIX, A))
    return state


def gate_endpoint(mode, stub_url, payloads):
    u"""The endpoint is a ROLE and a hostport, and both are recorded.

    `mode` is a required argument with no default.  A sender that can infer its own endpoint can
    infer the wrong one, and the one artifact that would show it is the one the run writes."""
    chk(mode in ("send", "stub"), "endpoint mode %r" % mode)
    url = H.URL if mode == "send" else stub_url
    host = urlparse(url).hostname
    if mode == "send":
        chk(host == "openrouter.ai", "GATE 6: the send endpoint is %r" % host)
    else:
        chk(host == STUB_HOST, "GATE 6: the stub endpoint is %r, not %s" % (host, STUB_HOST))
        chk(urlparse(url).port not in (None, 0), "the stub endpoint has no port: %r" % url)
    # GATE 5, on the constant that actually exists.  The first version of this line read
    # `diag.APERTURE`, which is not an attribute of that module: it raised AttributeError on the
    # first stub run, after every gate had passed.  A check that names something that is not there
    # is not a weak check, it is no check -- and the only thing that found it was running the
    # module.  OFFNET_SUFFIX is the licence Chris gave in his own words ("A2 span-box crops only"),
    # so pinning its value pins the aperture that is allowed off the network.
    chk(diag.OFFNET_SUFFIX == "_A2_spanbox.png",
        "GATE 5: the only aperture licensed off the network is %r, which is not the A2 span box"
        % diag.OFFNET_SUFFIX)
    blob = "\n".join(canon(p["body"]) + p["row"]["crop_file"] for p in payloads)
    chk("A1_notebox" not in blob, "GATE 5: A1_notebox referenced in a constructed payload")
    scan_for_leaks(blob + url, "the constructed payloads and the endpoint")
    chk(all(p["row"]["crop_file"].endswith(diag.OFFNET_SUFFIX) for p in payloads),
        "a payload carries a crop that is not an A2 span box")
    return {"role": mode, "hostport": "%s:%s" % (host, urlparse(url).port or
                                                 (443 if url.startswith("https") else 80)),
            "url_host": host}


def gate_counts(payloads, rows, arms, lock):
    n_expected = len(rows) * len(arms)
    chk(len(payloads) == n_expected,
        "call count %d != %d spans x %d arms" % (len(payloads), len(rows), len(arms)))
    chk(len(payloads) == lock["run"]["calls"],
        "F5: %d calls planned, %d registered" % (len(payloads), lock["run"]["calls"]))
    per_arm = {}
    for p in payloads:
        per_arm[p["arm"]] = per_arm.get(p["arm"], 0) + 1
    chk(sorted(per_arm) == sorted(arms) and len(set(per_arm.values())) == 1,
        "the arms do not carry equal passes: %r" % per_arm)
    chk(len(set((p["arm"], p["row"]["span_id"]) for p in payloads)) == n_expected,
        "a (span, arm) pair is planned twice -- one draw per item is the registered design")
    return n_expected


def gate_ceiling(lock, n_calls, cap):
    u"""The ceiling is priced by the REGISTERED parameter, not by the expected case.

    An expected value is not a bound, and a bound computed from a cap nobody pinned is decoration.
    So: every call running to the cap, at the lock's own measured max prompt, against the ceiling
    the lock registers.  If the arithmetic exceeds what was registered, the run does not go."""
    cost = lock["cost"]
    m = cost["measured_bare_per_arm"]
    # list prices back out of the lock's own ceiling sentence: opus at $4e-6 prompt, $2e-5 out.
    opus = [k for k in m if "opus" in k][0]
    other = [k for k in m if k != opus][0]
    pmax = m[opus]["prompt_tokens_min_med_max"][2]
    per_arm_calls = n_calls // 2
    worst = per_arm_calls * (pmax * 4e-6 + cap * 2e-5) + m[other]["usd_total"]
    reg = float(cost["ceiling_usd"])
    chk(worst <= reg + 1e-9,
        "the priced ceiling is $%.4f (%d calls x cap %d) and the lock registers $%.4f.  A ceiling "
        "that is not the arithmetic of the registered parameters bounds nothing."
        % (worst, per_arm_calls, cap, reg))
    return {"expected_usd": float(cost["expected_usd"]), "ceiling_usd_registered": reg,
            "ceiling_usd_recomputed": round(worst, 4),
            "ceiling_basis": "%d calls per arm x cap %d at list price, plus %s's measured total"
                             % (per_arm_calls, cap, other)}


def git_state_both():
    return {"laneB": S.git_state(WS.LANE_B), "dr_voluminous": S.git_state(Path(str(A)).parents[1])}


def gate_clean_run(start, end, mode):
    u"""A run is clean only if git_state at start and at end are both clean and identical.

    Not fatal, and that is deliberate: the rule says such a run is PROVISIONAL and cannot be cited
    in an ADR or a tier change.  So the verdict is computed, written into the artifact, and the
    report's own first line carries it.  A rule enforced by silence is not enforced."""
    same = canon(start) == canon(end)
    clean = not (start["laneB"]["dirty"] or start["dr_voluminous"]["dirty"]
                 or end["laneB"]["dirty"] or end["dr_voluminous"]["dirty"])
    chk(isinstance(same, bool) and isinstance(clean, bool), "the clean-run verdict is not boolean")
    return {"identical": same, "clean_at_both_ends": clean,
            "provisional": not (same and clean),
            "why": ("" if same and clean else
                    "the tree moved mid-run or was dirty; this run is provisional and cannot be "
                    "cited in an ADR or a tier change"),
            "mode_note": ("a stub run is never citable anyway" if mode == "stub" else "")}


# ------------------------------------------------------------------------------------- the payloads
def build_body(arm, img_b64, cap):
    u"""One image, the question, the answer shape.  No note text, no candidate, no signed form, no
    verse, no page number, no neighbouring span -- and no reasoning ladder: presence is not a hard
    glyph read, and a ladder step would change the payload and the cost without moving the endpoint."""
    return {"model": arm, "temperature": 0, "max_tokens": cap,
            "provider": {"data_collection": "deny"},
            "usage": {"include": True},
            "messages": [{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64,%s" % img_b64}},
                {"type": "text", "text": PROMPT},
            ]}]}


def build_payloads(rows, arms, crop_dir, allow_fault, cap):
    u"""`crop_dir`, `allow_fault` and `cap` are REQUIRED arguments with no defaults.

    A function that derives its own input fails silently.  Had `crop_dir` defaulted, a control run
    that lost its flag between argparse and here would send the real crops and be written up as a
    floor -- the one failure no later reader could detect, because every byte of the output would
    look right."""
    out = []
    for arm in arms:
        for r in rows:
            src = crop_dir / r["crop_file"]
            b64 = diag.b64_gated(src, what="localizer45 crop", offnet=True,
                                 allow_fault=allow_fault)
            sent = sha16_bytes(base64.b64decode(b64))
            chk(sent == S.stream_sha16(src),
                "%s: the encoded bytes do not hash to the file on disk" % r["span_id"])
            body = build_body(arm, b64, cap)
            H._no_hebrew_outbound(body)
            chk(not HEB.search(PROMPT), "the prompt itself carries Hebrew")
            out.append({"arm": arm, "channel": "bare", "row": r, "body": body,
                        "crop_sha16_sent": sent,
                        "request_sha16": sha16_bytes(canon(body).encode("utf-8"))})
    return out


def payload_identity(payloads):
    u"""One digest over (span, arm, request) and the crops, so a rerun can prove it sent the same
    thing -- and so a rerun that did NOT can say which axis moved."""
    reqs = sorted([p["row"]["span_id"], p["arm"], p["request_sha16"]] for p in payloads)
    crops = sorted(set((p["row"]["span_id"], p["crop_sha16_sent"]) for p in payloads))
    return sha16({"requests": reqs, "crops": [list(c) for c in crops]})


# ----------------------------------------------------------------------------------------- the parse
def parse_presence(raw):
    u"""(present, consonants, reason, how) with present in True / False / None.

    None is a FIRST-CLASS outcome and not a silent false: a reply that does not answer the question
    is an item error, counted and named, never folded into `absent`.  A system with no way to say
    `nothing here` turns an honest component into a fabricator; a system with no way to say `I could
    not read this reply` turns a parse failure into a measurement."""
    t = (raw or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    m = re.search(r"\{.*\}", t, flags=re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            v = str(d.get("hebrew_present", d.get("present", ""))).strip().lower()
            cons = d.get("consonants", d.get("hebrew", "")) or ""
            if isinstance(cons, list):
                cons = " ".join(str(x) for x in cons)
            reason = str(d.get("reason", ""))[:200]
            if v in ("yes", "true", "y"):
                return True, str(cons).strip(), reason, "json"
            if v in ("no", "false", "n"):
                return False, str(cons).strip(), reason, "json"
            return None, str(cons).strip(), reason, "json-no-verdict"
        except Exception:
            pass
    low = t.lower()
    # THE BARE WORD HAS TO BE THE WHOLE REPLY.  The first version asked whether the reply STARTS
    # with "no", and "no idea" starts with it -- so a non-answer came back as `absent`, which on
    # this run is the consequential verdict (an absent_candidate is a claim that a signed span box
    # holds no Hebrew).  Caught by this module's own self-test on its first execution, 2026-11-25.
    # Anchored both directions, so there is no asymmetry to defend: a reply that says more than the
    # verdict word must carry the explicit field or it is unparsed.  The cost is real and taken on
    # purpose -- prose like "No Hebrew is present" now lands in `unmeasured`, which is counted and
    # named, rather than in a verdict, which is not.
    # Maximal RUNS, not characters: HEB is a one-character class, so joining its findall with a
    # space puts a word boundary between every letter.  Derived from HEB.pattern -- a second copy of
    # the class is a second thing to drift.
    heb = " ".join(re.findall("(?:%s)+" % HEB.pattern, t))
    if re.search(r"\bhebrew_present\b\s*[:=]\s*\"?yes", low):
        return True, heb, "", "text-field"
    if re.search(r"\bhebrew_present\b\s*[:=]\s*\"?no", low):
        return False, "", "", "text-field"
    if re.match(r"^yes[\s.!,:;]*$", low):
        return True, heb, "", "text-bare"
    if re.match(r"^no[\s.!,:;]*$", low):
        return False, "", "", "text-bare"
    return None, heb, t[:200], "unparsed"


# ------------------------------------------------------------------------------------------ the call
def _post(url, body, key, timeout=300):
    return httpx.post(url, headers={"Authorization": "Bearer %s" % key,
                                    "content-type": "application/json"},
                      json=body, timeout=timeout)


def do_call(p, key, url, endpoint):
    u"""One call.  Returns a record.  Raises RunFault on a 429 that survives the retries."""
    row, arm = p["row"], p["arm"]
    img = p["body"]["messages"][0]["content"][0]["image_url"]["url"].split(",", 1)[1]
    chk(sha16_bytes(base64.b64decode(img)) == p["crop_sha16_sent"],
        "%s %s: the image in the body is not the planned crop" % (row["span_id"], arm))
    chk(urlparse(url).hostname == endpoint["url_host"], "the host moved between the gate and the "
                                                        "send: %r" % urlparse(url).hostname)
    H._no_hebrew_outbound(p["body"])
    rec = {"span_id": row["span_id"], "stratum": row["stratum"],
           "page_file": row["page_file"], "page_printed": row["page_printed"],
           "arm": arm, "channel": "bare",
           "request_sha16": p["request_sha16"], "crop_sha16": row["crop_sha16"],
           "crop_sha16_sent": p["crop_sha16_sent"],
           "endpoint_role": endpoint["role"], "endpoint_hostport": endpoint["hostport"],
           "response_raw": None, "present": None, "consonants": None, "reason": None,
           "parse": None, "retries": 0, "cost_usd": None, "out_tokens": None,
           "finish_reason": None, "error": None, "provider": None, "model_returned": None,
           "gen_id": None}
    r, err = None, None
    try:
        r = _post(url, p["body"], key)
        for attempt in range(RETRIES):
            if r.status_code not in RETRY_CODES:
                break
            rec["retries"] += 1
            time.sleep(BACKOFF * (2 ** attempt) if endpoint["role"] == "send" else 0.01)
            r = _post(url, p["body"], key)
    except Exception as e:                                  # transport failure: an ITEM error
        err = "transport:%s:%s" % (type(e).__name__, str(e)[:100])
        r = None
    if r is not None and r.status_code == 429:
        raise S.RunFault("429 survived %d retries on %s %s" % (RETRIES, row["span_id"], arm))
    if err:
        rec["error"] = err
    elif r.status_code >= 400:
        rec["error"] = "http%d:%s" % (r.status_code, r.text[:160])
    else:
        try:
            d = r.json()
            raw = (d["choices"][0]["message"].get("content") or "").strip()
            u = d.get("usage") or {}
            present, cons, reason, how = parse_presence(raw)
            rec.update(response_raw=raw, present=present, consonants=cons, reason=reason,
                       parse=how, cost_usd=u.get("cost"), out_tokens=u.get("completion_tokens"),
                       finish_reason=d["choices"][0].get("finish_reason"),
                       provider=d.get("provider"), model_returned=d.get("model"),
                       gen_id=d.get("id"))
            if present is None:
                rec["error"] = "unparseable:%s" % how
        except Exception as e:
            rec["error"] = "malformed_body:%s:%s" % (type(e).__name__, str(e)[:100])
    chk(rec["present"] in (True, False, None), "%s: a presence verdict outside the three"
                                               % row["span_id"])
    return rec


def send_all(payloads, key, url, endpoint):
    u"""The loop, with the run-level faults the lock registers.

    A faulted HEAD poisons the load: if the FIRST call of an arm fails, that arm's whole pass is
    discarded, not patched around -- every later item of it would be unmeasured rather than fine.
    Four consecutive dead items is a run-level fault too.  Both abort and write nothing."""
    recs, consecutive, first_of_arm = [], 0, {}
    for i, p in enumerate(payloads):
        rec = do_call(p, key, url, endpoint)
        recs.append(rec)
        dead = bool(rec["error"])
        if p["arm"] not in first_of_arm:
            first_of_arm[p["arm"]] = dead
            if dead:
                raise S.RunFault(
                    "the FIRST call of arm %s faulted (%s).  A `done: false` at the head of a load "
                    "leaves every later item of it UNMEASURED, not fine: the arm's pass is "
                    "discarded and the run is rerun from the top, never spliced."
                    % (p["arm"], rec["error"]))
        consecutive = consecutive + 1 if dead else 0
        if consecutive >= CONSECUTIVE_FAIL_ABORT:
            raise S.RunFault("%d consecutive dead items ending at %s %s: run-level fault, the run "
                             "aborts and writes nothing"
                             % (consecutive, p["row"]["span_id"], p["arm"]))
    return recs


# ------------------------------------------------------------------------------------ the decisions
def census_by_page():
    u"""page -> [(span_id, consonants)] from the 2026-10-04 Hebrew span census.

    The SECONDARY analysis needs the Hebrew of the OTHER notes on a page: a read that matches
    another note's Hebrew is positive evidence of MISLOCATION, and a read that matches nothing is
    evidence of nothing in particular."""
    d = json.loads(CENSUS.read_text(encoding="utf-8"))
    out = {}
    for r in d["rows"]:
        out.setdefault(int(r["page"]), []).append((r["span_id"], bare_consonants(r.get("hebrew"))))
    return out


def decide(recs, rows, arms):
    u"""Per span: the pair of presence verdicts.

    both present -> present; both absent -> absent_candidate; disagree -> disputed; either arm
    unmeasured -> unmeasured.  AGREEMENT IS NOT CONFIDENCE and is not reported as any: two arms on
    the same pixels share priors.  Disagreement is the signal and its only use is the queue."""
    by = {}
    for r in recs:
        by.setdefault(r["span_id"], {})[r["arm"]] = r
    out = []
    for row in rows:
        got = by.get(row["span_id"], {})
        vals = [got.get(a, {}).get("present") if not got.get(a, {}).get("error") else None
                for a in arms]
        if any(v is None for v in vals):
            v = "unmeasured"
        elif all(v is True for v in vals):
            v = "present"
        elif all(v is False for v in vals):
            v = "absent_candidate"
        else:
            v = "disputed"
        out.append({"span_id": row["span_id"], "stratum": row["stratum"],
                    "page_file": row["page_file"], "page_printed": row["page_printed"],
                    "per_arm": dict((a, got.get(a, {}).get("present")) for a in arms),
                    "errors": dict((a, got.get(a, {}).get("error")) for a in arms
                                   if got.get(a, {}).get("error")),
                    "verdict": v,
                    "queued": v in ("absent_candidate", "disputed"),
                    "queue_as": {"absent_candidate": "candidate no_hebrew_on_crop (GEOMETRY5 "
                                                     "vocabulary), for a human sitting",
                                 "disputed": "disputed presence, for a human sitting"}.get(v, "")})
    chk(len(out) == len(rows), "the decision table is not the population")
    chk(all(o["verdict"] in VERDICTS for o in out), "a verdict outside the registered four")
    return out


def secondary(recs, rows, census):
    u"""Reported, NEVER primary: for `present` reads in the clean stratum, the consonant skeleton
    against the row's own signed signature, and on a miss against the other notes on the page.

    Undefined for the control stratum: pass 1 recorded `complete: false` for all four, so there is
    no signed string, and a comparison against "" would score a miss that means nothing."""
    byrow = dict((r["span_id"], r) for r in rows)
    out = []
    for r in recs:
        row = byrow[r["span_id"]]
        if row["stratum"] != "clean":
            out.append({"span_id": r["span_id"], "arm": r["arm"], "class": "undefined_no_signed_string",
                        "text": r["consonants"] or ""})
            continue
        if r["error"] or r["present"] is not True:
            out.append({"span_id": r["span_id"], "arm": r["arm"], "class": "not_a_present_read",
                        "text": r["consonants"] or ""})
            continue
        got = bare_consonants(r["consonants"])
        own = bare_consonants(row.get("signature"))
        if own and got == own:
            cls, who = "matches_own_signature", r["span_id"]
        else:
            others = [(sid, h) for sid, h in census.get(row["page_file"], [])
                      if sid != r["span_id"] and h]
            hit = [sid for sid, h in others if got and h == got]
            if hit:
                cls, who = "matches_another_note_on_the_page", ",".join(sorted(hit))
            else:
                cls, who = "unattributed", ""
        out.append({"span_id": r["span_id"], "arm": r["arm"], "class": cls, "matched": who,
                    "text": r["consonants"] or ""})
    chk(len(out) == len(recs), "the secondary table is not the record set")
    return out


def falsifiers(lock, decisions, recs, rows, pop_dig, refused, capped, arms):
    u"""F1..F6 as the lock registers them, evaluated and WRITTEN, fired or not.

    F1 is scored over the three not-Hebrew controls only -- p677:n13 is the mislocation control, and
    pooling it in would let a `present` read there satisfy a test about the absent channel."""
    byid = dict((d["span_id"], d) for d in decisions)
    byrow = dict((r["span_id"], r) for r in rows)
    clean = [d for d in decisions if d["stratum"] == "clean"]
    out = []

    three = [byid[s] for s in NOT_HEBREW_CONTROLS if s in byid]
    f1 = bool(three) and all(d["verdict"] == "present" for d in three)
    out.append({"id": "F1", "fired": f1,
                "measured": dict((d["span_id"], d["verdict"]) for d in three),
                "then": lock["falsifiers"][0]["then"]})

    # F2: a control read that returns the control's OWN candidate string -- fabrication on inked
    # non-Hebrew pixels.  The candidate is what the signer was shown in October; it is in the
    # controls sheet and never in a payload.
    f2rows = []
    for r in recs:
        row = byrow[r["span_id"]]
        if row["stratum"] != "control":
            continue
        cand = bare_consonants(row.get("candidate_shown_to_the_signer"))
        if cand and bare_consonants(r["consonants"]) == cand:
            f2rows.append({"span_id": r["span_id"], "arm": r["arm"], "returned": r["consonants"]})
    out.append({"id": "F2", "fired": bool(f2rows), "measured": f2rows,
                "then": lock["falsifiers"][1]["then"]})

    n_abs = sum(1 for d in clean if d["verdict"] == "absent_candidate")
    out.append({"id": "F3", "fired": n_abs > 6, "measured": {"clean_absent_both": n_abs},
                "then": lock["falsifiers"][2]["then"]})

    n_disp = sum(1 for d in decisions if d["verdict"] == "disputed")
    out.append({"id": "F4", "fired": n_disp > 10, "measured": {"disputed_all_strata": n_disp},
                "then": lock["falsifiers"][3]["then"]})

    f5 = (pop_dig != lock["run"]["population_digest_required"]
          or sorted(refused) != []
          or len(decisions) != lock["population"]["n_spans"])
    out.append({"id": "F5", "fired": f5,
                "measured": {"population_digest": pop_dig, "law8_refused_in_draw": sorted(refused),
                             "n_spans": len(decisions)},
                "then": lock["falsifiers"][4]["then"]})

    out.append({"id": "F6", "fired": len(capped) > 2, "measured": {"capped_calls": capped},
                "then": lock["falsifiers"][5]["then"]})

    chk(len(out) == len(lock["falsifiers"]),
        "%d falsifiers evaluated, %d registered" % (len(out), len(lock["falsifiers"])))
    chk([o["id"] for o in out] == [f["id"] for f in lock["falsifiers"]],
        "the falsifiers are evaluated in an order that does not match the lock")
    return out


def scoreability(fals, decisions):
    u"""What the run may be read as saying, decided by the falsifiers and not by the numbers.

    F1 or F2 fired -> the clean stratum is UNSCOREABLE, and no presence count from this run is a
    statement about boxes.  Written at the top of the report, so the first thing a reader sees is
    what the run is allowed to claim."""
    fired = [f["id"] for f in fals if f["fired"]]
    unmeasured = sum(1 for d in decisions if d["verdict"] == "unmeasured")
    if "F2" in fired:
        return {"clean_stratum": "WITHDRAWN", "why": "F2: a control returned its own candidate "
                "string on inked non-Hebrew pixels -- the draw measured priors, not pixels",
                "fired": fired}
    if "F1" in fired:
        return {"clean_stratum": "UNSCOREABLE", "why": "F1: the absent channel did not work on "
                "this corpus, so the clean stratum's presence count is not clean", "fired": fired}
    if unmeasured:
        return {"clean_stratum": "PARTIAL", "why": "%d span(s) unmeasured: an item with an error "
                "on either arm has no pair, and a pair is the unit" % unmeasured, "fired": fired}
    return {"clean_stratum": "a count over the unfaulted residual, one draw per item",
            "why": "", "fired": fired}


# ------------------------------------------------------------------------------------- the artifacts
def report_lines(header, decisions, sec, fals, score, recs, arms):
    L = []
    L.append("# Localizer presence draw -- %s" % header["mode"])
    L.append("")
    L.append("Lane B / session 50612c81.  ALL PAGE NUMBERS ARE FILE pages (printed = file - 88).")
    if header["mode"] != "send":
        L.append("")
        L.append("**NOT A MEASUREMENT.** This is a %s against %s. The replies are scripted in "
                 "localizer45_run.py from the signed strings, so every number below is the stub's "
                 "own script: it exercises the wiring and says nothing about any box, any arm or "
                 "any crop. `scoreable: false`." % (header["mode"], header["endpoint"]["hostport"]))
    L.append("")
    L.append("- run: `%s`  mode: %s  endpoint: %s (%s)"
             % (header["run_sha16"], header["mode"], header["endpoint"]["role"],
                header["endpoint"]["hostport"]))
    L.append("- lock: `%s` (self_sha16 %s), attempt %d" % (LOCK_PATH.name, LOCK_SHA, ATTEMPT))
    L.append("- population digest: `%s`; payload identity: `%s`"
             % (header["population_digest"], header["payload_identity"]))
    L.append("- scoreability of the clean stratum: **%s** %s"
             % (score["clean_stratum"], ("-- " + score["why"]) if score["why"] else ""))
    L.append("- falsifiers fired: %s" % (", ".join(score["fired"]) or "none"))
    L.append("- checks: %d (pre-call %d); calls %d; retries %d; cost $%s"
             % (header["checks_total"], header["checks_precall"], len(recs),
                sum(r["retries"] for r in recs),
                header["cost_usd_total"] if header["cost_usd_total"] is not None else "n/a"))
    L.append("- clean-run rule: %s" % ("PROVISIONAL -- " + header["clean_run"]["why"]
                                       if header["clean_run"]["provisional"]
                                       else "clean at both ends and identical"))
    L.append("")
    L.append("## Verdicts, by stratum, never pooled")
    L.append("")
    for st in STRATA:
        d = [x for x in decisions if x["stratum"] == st]
        counts = dict((v, sum(1 for x in d if x["verdict"] == v)) for v in VERDICTS)
        L.append("- **%s** (n=%d): %s" % (st, len(d),
                                          ", ".join("%s %d" % (k, counts[k]) for k in VERDICTS)))
    L.append("")
    L.append("## The queue (nothing here is a verdict)")
    L.append("")
    q = [d for d in decisions if d["queued"]]
    if not q:
        L.append("- empty")
    for d in q:
        L.append("- `%s` (printed p%d, %s): %s -- %s"
                 % (d["span_id"], d["page_printed"], d["stratum"], d["verdict"], d["queue_as"]))
    L.append("")
    L.append("## Falsifiers")
    L.append("")
    for f in fals:
        L.append("- **%s %s** %s" % (f["id"], "FIRED" if f["fired"] else "did not fire",
                                     canon(f["measured"])))
    L.append("")
    L.append("## Secondary (reported, never primary)")
    L.append("")
    cls = {}
    for s in sec:
        cls[s["class"]] = cls.get(s["class"], 0) + 1
    for k in sorted(cls):
        L.append("- %s: %d" % (k, cls[k]))
    ml = [s for s in sec if s["class"] == "matches_another_note_on_the_page"]
    for s in ml:
        L.append("  - `%s` %s matched `%s` -- positive evidence of MISLOCATION"
                 % (s["span_id"], s["arm"], s["matched"]))
    L.append("")
    L.append("## What this run cannot settle")
    L.append("")
    for w in header["what_this_cannot_settle"]:
        L.append("- %s" % w)
    return L


def write_artifacts(out_dir, header, recs, decisions, sec, fals, score, arms):
    out_dir = Path(WS.assert_inside(Path(out_dir), why="the run's artifacts"))
    out_dir.mkdir(parents=True, exist_ok=True)
    run = header["run_sha16"]
    # THE FILENAME TOKEN, sanitised.  "stub:normal" put all three artifacts into NTFS alternate
    # data streams on a zero-byte file: the sizes were real, the paths resolved, and the directory
    # was empty.  The header keeps the unsanitised mode, which is the truthful value of the field.
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", str(header["mode"]))
    chk(bool(slug) and re.match(r"^[A-Za-z0-9._-]+$", slug),
        "the mode slug %r is not a safe filename token" % slug)
    md = "\n".join(report_lines(header, decisions, sec, fals, score, recs, arms)) + "\n"
    scan_for_leaks(md, "the report")
    paths = {}
    p = out_dir / ("LOCALIZER45_%s_%s.md" % (slug, run))
    io.open(str(p), "w", encoding="utf-8", newline="\n").write(md)
    paths["report"] = p
    p = out_dir / ("LOCALIZER45_%s_%s.jsonl" % (slug, run))
    with io.open(str(p), "w", encoding="utf-8", newline="\n") as f:
        for r in recs:
            line = json.dumps(r, ensure_ascii=False, sort_keys=True)
            scan_for_leaks(line, "a record")
            f.write(line + "\n")
    paths["records"] = p
    p = out_dir / ("LOCALIZER45_%s_%s.json" % (slug, run))
    obj = dict(header, decisions=decisions, secondary=sec, falsifiers=fals, scoreability=score)
    txt = json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    scan_for_leaks(txt, "the header artifact")
    io.open(str(p), "w", encoding="utf-8", newline="\n").write(txt)
    paths["header"] = p
    # WITNESSED BY THE DIRECTORY, not by the path that wrote the file.  `exists()` and `stat()`
    # both answered yes about three data streams nobody can open by name, because they ask through
    # the same path the write used.  `os.listdir` does not list streams, so it is an independent
    # witness, and the size is compared with the bytes this function actually produced.
    listed = set(os.listdir(str(out_dir)))
    wrote = {"report": len(md.encode("utf-8")), "records": None, "header": None}
    for k, v in sorted(paths.items()):
        chk(v.name in listed,
            "the %s artifact is not in the directory listing of %s: the name %r did not become a "
            "file (on Windows a colon in a name writes an NTFS data stream, which exists(), "
            "stat() and the hash all agree about and nobody can open)" % (k, out_dir, v.name))
        chk(v.exists() and v.stat().st_size > 0, "the %s artifact was not written" % k)
        if wrote.get(k):
            chk(v.stat().st_size == wrote[k],
                "the %s artifact is %d bytes on disk and %d were written"
                % (k, v.stat().st_size, wrote[k]))
    return paths


# ------------------------------------------------------------------------------------- the stub
class _StubHandler(BaseHTTPRequestHandler):
    scenario = "normal"
    table = {}
    state = {}
    dead = set()     # (arm, crop_sha16) pairs that fail on EVERY attempt

    def log_message(self, *a):                                    # silence
        return

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        st = _StubHandler.state
        st["n"] = st.get("n", 0) + 1
        i = st["n"]
        arm = body.get("model")
        key = self.headers.get("Authorization") or ""
        if "sk-or-" in key:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"a real key reached the stub"}')
            return
        sc = _StubHandler.scenario
        # `retry` is the only scenario that may key on the request index, because a retry is a
        # property of the REQUEST: the same item is asked twice and answered the second time.
        if sc == "retry" and i == 1 and st.get("retried", 0) < 2:
            st["retried"] = st.get("retried", 0) + 1
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"error":"slow down"}')
            return
        # The image is the key the script is written against: the sender's own crop hashes.
        img = body["messages"][0]["content"][0]["image_url"]["url"].split(",", 1)[1]
        csha = sha16_bytes(base64.b64decode(img))
        # A DEAD ITEM IS DEAD EVERY TIME IT IS ASKED.  The first version of these two scenarios
        # returned a retryable code on request numbers 1 and 2..8; since the request counter
        # advances with each retry, the retry cured both and the two fault branches in `send_all`
        # had never run -- fault-head produced a normal run's artifacts and exited 0.  Keyed on the
        # item, the retries exhaust, the item errors, and the law fires.
        if (arm, csha) in (_StubHandler.dead or set()):
            st["dead_served"] = st.get("dead_served", 0) + 1
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"error":"upstream: this item is dead on every attempt"}')
            return
        spec = _StubHandler.table.get((arm, csha)) or {"raw": '{"hebrew_present":"no",'
                                                              '"consonants":"","reason":"stub"}',
                                                       "finish": "stop"}
        out = {"id": "stub-%d" % i, "model": arm, "provider": "stub",
               "choices": [{"message": {"content": spec["raw"]},
                            "finish_reason": ("length" if sc == "cap" and i <= 3
                                              else spec["finish"])}],
               "usage": {"cost": 0.0, "prompt_tokens": 240, "completion_tokens": 30}}
        raw = json.dumps(out, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def stub_table(rows, arms, census):
    u"""The scripted replies, keyed by (arm, crop sha16).

    BUILT FROM THE SIGNED STRINGS, which is why a stub run is not a measurement.  The script
    deliberately covers every branch the scorer has: a matching read, a read that matches ANOTHER
    note on the page (the mislocation branch), a read that matches nothing (unattributed), a reply
    that does not answer (an item error), a disagreement between the arms, and `no` on all four
    controls."""
    t, notes = {}, []
    clean = [r for r in rows if r["stratum"] == "clean"]
    for ai, arm in enumerate(arms):
        for i, r in enumerate(clean):
            csha = S.stream_sha16(CROPS / r["crop_file"])
            own = r.get("signature") or ""
            if i == 0:
                others = [h for sid, h in census.get(r["page_file"], [])
                          if sid != r["span_id"] and h]
                txt = others[0] if others else own
                why = "mislocation branch: another note's census Hebrew"
            elif i == 1:
                txt, why = "", "present with no consonants: the unattributed branch"
            elif i == 2:
                t[(arm, csha)] = {"raw": "I am not sure what this image shows.", "finish": "stop"}
                notes.append((r["span_id"], arm, "unparseable reply: an item error"))
                continue
            elif i == 3 and ai == 1:
                t[(arm, csha)] = {"raw": '{"hebrew_present":"no","consonants":"",'
                                         '"reason":"stub disagreement"}', "finish": "stop"}
                notes.append((r["span_id"], arm, "one arm says no: the disputed branch"))
                continue
            else:
                txt, why = own, "matches its own signature"
            t[(arm, csha)] = {"raw": json.dumps({"hebrew_present": "yes", "consonants": txt,
                                                 "reason": "stub"}, ensure_ascii=False),
                              "finish": "stop"}
            if i < 4:
                notes.append((r["span_id"], arm, why))
    for r in [x for x in rows if x["stratum"] == "control"]:
        csha = S.stream_sha16(CROPS / r["crop_file"])
        for arm in arms:
            t[(arm, csha)] = {"raw": '{"hebrew_present":"no","consonants":"",'
                                     '"reason":"stub control"}', "finish": "stop"}
    return t, notes


def start_stub(scenario, table, payloads):
    u"""The dead set is DERIVED from the planned payload order, never typed.

    `payloads` is a required argument: a function that derives its own notion of "the head" or "the
    next four" fails silently when the order changes under it."""
    chk(bool(payloads), "start_stub needs the planned payloads to know which item is the head")
    keys = [(p["arm"], p["crop_sha16_sent"]) for p in payloads]
    dead = set()
    if scenario == "fault-head":
        dead = {keys[0]}
    elif scenario == "dead-items":
        chk(len(keys) > CONSECUTIVE_FAIL_ABORT,
            "the population is too small to script %d consecutive dead items"
            % CONSECUTIVE_FAIL_ABORT)
        dead = set(keys[1:1 + CONSECUTIVE_FAIL_ABORT])
    _StubHandler.dead = dead
    _StubHandler.scenario = scenario
    _StubHandler.table = table
    _StubHandler.state = {}
    srv = ThreadingHTTPServer((STUB_HOST, 0), _StubHandler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, "http://%s:%d/v1/chat/completions" % (STUB_HOST, srv.server_address[1])


# ------------------------------------------------------------------------------------- the self-test
def self_test():
    u"""The parser, the decision rule, the secondary and the falsifier arithmetic over hand-made
    inputs.  No files, no network.  The check COUNT is asserted: an exception in a hand-rolled
    suite ends the run silently, and that has cost this lane 40 assertions once already."""
    before = CHECKS
    chk(not HEB.search(PROMPT), "the prompt carries Hebrew")
    chk("page" not in PROMPT.lower().replace("page of a", "").replace("on the page", ""),
        "the prompt names a page number or a note")
    # --- the parser, including the three outcomes of `present`
    for raw, want in [('{"hebrew_present":"yes","consonants":"\u05d0\u05d1","reason":"x"}', True),
                      ('{"hebrew_present":"no","consonants":"","reason":"x"}', False),
                      ('```json\n{"hebrew_present":"YES","consonants":"\u05d0"}\n```', True),
                      ('{"hebrew_present":"maybe"}', None),
                      ("no idea", None),
                      ("not sure", None),
                      ("No clear view of this crop.", None),
                      ("Yes, I think so, but the edge is cut.", None),
                      ("no", False),
                      ("Yes.", True),
                      ("hebrew_present: no", False),
                      ("", None)]:
        got = parse_presence(raw)[0]
        chk(got is want, "parse_presence(%r) -> %r, wanted %r" % (raw[:40], got, want))
    # The reply is never stored in the field the secondary reads as a transcription.
    chk(parse_presence("Yes, I see \u05d0\u05d1 here")[1] == "\u05d0\u05d1",
        "an unparsed reply's prose leaked into the consonants field")
    chk(parse_presence("no idea")[2] == "no idea",
        "an unparsed reply is not kept verbatim as the reason")
    chk(parse_presence('{"hebrew_present":"yes","consonants":["\u05d0","\u05d1"]}')[1]
        == "\u05d0 \u05d1", "a list of consonants is not joined")
    # --- bare_consonants: nikud is stripped for the SECONDARY only
    chk(bare_consonants("\u05d0\u05b8") == "\u05d0", "nikud is not stripped")
    chk(bare_consonants(None) == "", "None is not the empty skeleton")
    # --- the decision rule, all four outcomes, both orders of the pair
    arms = ["a1", "a2"]
    rows = [{"span_id": "p1:n0", "stratum": "clean", "page_file": 100, "page_printed": 12},
            {"span_id": "p2:n0", "stratum": "clean", "page_file": 101, "page_printed": 13},
            {"span_id": "p3:n0", "stratum": "control", "page_file": 102, "page_printed": 14},
            {"span_id": "p4:n0", "stratum": "clean", "page_file": 103, "page_printed": 15}]

    def rec(sid, arm, present, error=None):
        return {"span_id": sid, "arm": arm, "present": present, "error": error,
                "consonants": "", "retries": 0}

    recs = [rec("p1:n0", "a1", True), rec("p1:n0", "a2", True),
            rec("p2:n0", "a1", False), rec("p2:n0", "a2", False),
            rec("p3:n0", "a1", True), rec("p3:n0", "a2", False),
            rec("p4:n0", "a1", None, "unparseable:text"), rec("p4:n0", "a2", True)]
    d = dict((x["span_id"], x["verdict"]) for x in decide(recs, rows, arms))
    chk(d == {"p1:n0": "present", "p2:n0": "absent_candidate", "p3:n0": "disputed",
              "p4:n0": "unmeasured"}, "the decision rule: %r" % d)
    # the pair is unordered: swapping which arm disagreed must not change the verdict
    swapped = [rec("p3:n0", "a1", False) if r["span_id"] == "p3:n0" and r["arm"] == "a1"
               else (rec("p3:n0", "a2", True) if r["span_id"] == "p3:n0" else r) for r in recs]
    chk([x["verdict"] for x in decide(swapped, rows, arms) if x["span_id"] == "p3:n0"]
        == ["disputed"], "disputed is not symmetric in the arms")
    # an ERROR on one arm is not an `absent`: that is the whole point of the third outcome
    err = [rec("p1:n0", "a1", False, "http500"), rec("p1:n0", "a2", False)]
    chk([x["verdict"] for x in decide(err, rows[:1], arms)] == ["unmeasured"],
        "an item error on one arm scored as a pair")
    # --- the secondary's four classes
    srows = [{"span_id": "p1:n0", "stratum": "clean", "page_file": 100,
              "signature": "\u05d0\u05d1"},
             {"span_id": "p3:n0", "stratum": "control", "page_file": 102, "signature": None}]
    census = {100: [("p1:n0", "\u05d0\u05d1"), ("p1:n1", "\u05d2\u05d3")]}
    sr = [{"span_id": "p1:n0", "arm": "a1", "present": True, "error": None,
           "consonants": "\u05d0\u05d1"},
          {"span_id": "p1:n0", "arm": "a2", "present": True, "error": None,
           "consonants": "\u05d2\u05d3"},
          {"span_id": "p3:n0", "arm": "a1", "present": True, "error": None,
           "consonants": "\u05d0"}]
    got = secondary(sr, srows, census)
    chk([g["class"] for g in got] == ["matches_own_signature",
                                      "matches_another_note_on_the_page",
                                      "undefined_no_signed_string"],
        "the secondary classes: %r" % [g["class"] for g in got])
    chk(got[1]["matched"] == "p1:n1", "the mislocation match does not name the other note")
    sr2 = [{"span_id": "p1:n0", "arm": "a1", "present": True, "error": None,
            "consonants": "\u05d8\u05d8\u05d8"}]
    chk(secondary(sr2, srows, census)[0]["class"] == "unattributed",
        "a read matching nothing is not unattributed")
    # a present read whose consonants are empty is not a match to anything
    sr3 = [{"span_id": "p1:n0", "arm": "a1", "present": True, "error": None, "consonants": ""}]
    chk(secondary(sr3, srows, census)[0]["class"] == "unattributed",
        "an empty read matched a signature")
    # --- the falsifiers, with a synthetic lock
    lk = {"falsifiers": [{"id": "F%d" % i, "then": "t"} for i in range(1, 7)],
          "run": {"population_digest_required": "dig"},
          "population": {"n_spans": 3}}
    frows = [{"span_id": s, "stratum": "control", "page_file": 1, "page_printed": 1,
              "candidate_shown_to_the_signer": "\u05d0\u05d1"} for s in NOT_HEBREW_CONTROLS]
    fdec = [{"span_id": s, "stratum": "control", "verdict": "present"} for s in NOT_HEBREW_CONTROLS]
    frecs = [{"span_id": NOT_HEBREW_CONTROLS[0], "arm": "a1", "consonants": "\u05d0\u05d1",
              "present": True, "error": None}]
    f = dict((x["id"], x["fired"]) for x in
             falsifiers(lk, fdec, frecs, frows, "dig", [], [], arms))
    chk(f["F1"] and f["F2"] and not f["F3"] and not f["F4"] and not f["F5"] and not f["F6"],
        "the falsifiers on the synthetic all-present control set: %r" % f)
    # F1 must NOT fire when one of the three is absent, and p677:n13 must not be able to satisfy it
    fdec2 = list(fdec)
    fdec2[0] = dict(fdec2[0], verdict="absent_candidate")
    f2 = dict((x["id"], x["fired"]) for x in
              falsifiers(lk, fdec2, [], frows, "dig", [], [], arms))
    chk(not f2["F1"], "F1 fired with one control reading absent")
    fdec3 = fdec + [{"span_id": "p677:n13", "stratum": "control", "verdict": "present"}]
    chk(dict((x["id"], x["fired"]) for x in
             falsifiers(lk, [dict(d, verdict="absent_candidate") if d["span_id"]
                             == NOT_HEBREW_CONTROLS[0] else d for d in fdec3],
                        [], frows, "dig", [], [], arms))["F1"] is False,
        "p677:n13 reading present satisfied a test about the absent channel")
    # F5 on a moved digest, F3/F4/F6 on their thresholds
    chk(dict((x["id"], x["fired"]) for x in
             falsifiers(lk, fdec, [], frows, "moved", [], [], arms))["F5"],
        "F5 did not fire on a moved population digest")
    many = [{"span_id": "x%d" % i, "stratum": "clean", "verdict": "absent_candidate"}
            for i in range(7)]
    chk(dict((x["id"], x["fired"]) for x in
             falsifiers(lk, many, [], [], "dig", [], [], arms))["F3"],
        "F3 did not fire on 7 absent_both in the clean stratum")
    chk(not dict((x["id"], x["fired"]) for x in
                 falsifiers(lk, many[:6], [], [], "dig", [], [], arms))["F3"],
        "F3 fired at 6, which is the registered boundary")
    chk(dict((x["id"], x["fired"]) for x in
             falsifiers(lk, fdec, [], frows, "dig", [], ["c"] * 3, arms))["F6"],
        "F6 did not fire on 3 capped calls")
    # --- scoreability: F2 withdraws, F1 unscoreable, an unmeasured item is partial
    chk(scoreability([{"id": "F2", "fired": True}], [])["clean_stratum"] == "WITHDRAWN",
        "F2 did not withdraw the draw")
    chk(scoreability([{"id": "F1", "fired": True}], [])["clean_stratum"] == "UNSCOREABLE",
        "F1 did not make the clean stratum unscoreable")
    chk(scoreability([], [{"verdict": "unmeasured"}])["clean_stratum"] == "PARTIAL",
        "an unmeasured item did not make the run partial")
    chk(scoreability([], [{"verdict": "present"}])["clean_stratum"].startswith("a count"),
        "a clean run is not reported as a count")
    # --- the leak predicate fires on both populations
    for h in FORBIDDEN_HOSTS:
        try:
            scan_for_leaks("x %s y" % h, "a synthetic record")
            raise AssertionError("the leak scan passed %s" % h)
        except AssertionError as e:
            chk("forbidden host" in str(e), "the leak scan raised the wrong thing for %s" % h)
    try:
        scan_for_leaks("sk-or-v1-whatever", "a synthetic record")
        raise AssertionError("the leak scan passed key material")
    except AssertionError as e:
        chk("key material" in str(e), "the leak scan raised the wrong thing for a key")
    # MEASURED on 2026-11-25, the first execution of this module, and not estimated: the 44 that
    # stood here was a number I wrote while writing the suite and never ran.  It is a snapshot and
    # it says nothing about whether the checks are good -- its one job is that an exception cannot
    # end this hand-rolled suite quietly, which has cost this lane 40 assertions once already.
    # Changing a check means changing this number in the same commit, on purpose.  The 74 is the
    # count BEFORE the pin's own check, so the line the run prints reads 75; both numbers are real
    # and neither is a typo for the other.
    ran = CHECKS - before
    chk(ran == 74, "the self-test ran %d checks, not the 74 it asserts" % ran)
    return CHECKS - before


# ------------------------------------------------------------------------------------------- the run
def precall(mode, dry, lock):
    u"""Every gate that can run before a call, in one place, so `--dry-run` and `--send` cannot
    disagree about which gates ran.  Returns (rows, payloads, facts)."""
    arms, cap, n_reg = run_params(lock)
    rows = population_rows()
    pop_dig = gate_population(rows, lock)
    refused = gate_law8(rows, lock)
    sealed = gate_sealed(rows, lock)
    disc = gate_disclosure(dry)
    sit2 = gate_sitting2(dry)
    payloads = build_payloads(rows, arms, CROPS, None, cap)
    n_calls = gate_counts(payloads, rows, arms, lock)
    cost = gate_ceiling(lock, n_calls, cap)
    pid = payload_identity(payloads)
    return rows, payloads, {"arms": arms, "cap": cap, "n_calls": n_calls,
                            "population_digest": pop_dig, "law8_refused": refused,
                            "sealed_pages": sorted(sealed),
                            "sealed_sources": dict((k, sorted(v))
                                                   for k, v in SB.sources().items()),
                            "sealed_disagreement": [list(x) for x in SB.disagreement()],
                            "disclosure": disc, "sitting2": sit2,
                            "cost": cost, "payload_identity": pid}


def main():
    ap = argparse.ArgumentParser(description="the localizer presence draw's sender")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stub-run", action="store_true")
    ap.add_argument("--stub-scenario", default="normal",
                    choices=["normal", "retry", "fault-head", "dead-items", "cap"])
    ap.add_argument("--out-dir", default=None,
                    help="required for --stub-run; must be inside Lane B's write scope")
    ap.add_argument("--keep", action="store_true",
                    help="--stub-run: leave the artifacts on disk (default: verify, then remove, "
                         "so a wiring test does not leave data in the audits directory)")
    ap.add_argument("--send", action="store_true", help="the real paid run")
    ap.add_argument("--expect-checks", type=int, default=None,
                    help="required for --send: the pre-call check count a free --dry-run pinned")
    ap.add_argument("--expect-payload-digest", default=None)
    a = ap.parse_args()
    modes = [m for m in ("self_test", "dry_run", "stub_run", "send") if getattr(a, m)]
    if len(modes) != 1:
        print("pick exactly one of --self-test / --dry-run / --stub-run / --send")
        return 2

    if a.self_test:
        n = self_test()
        print("self-test: %d checks, all green" % n)
        return 0

    git_start = git_state_both()
    lock = load_lock()
    mode = "send" if a.send else ("stub" if a.stub_run else "dry")
    dry = not a.send
    rows, payloads, facts = precall(mode, dry, lock)
    precall_checks = CHECKS
    print("Lane B / session 50612c81 -- localizer presence draw, attempt %d" % ATTEMPT)
    print("  FILE pages throughout (printed = file - 88)")
    print("  lock            %s (self_sha16 %s)" % (LOCK_PATH.name, LOCK_SHA))
    print("  population      %d spans (%d clean + %d control), digest %s"
          % (len(rows), sum(1 for r in rows if r["stratum"] == "clean"),
             sum(1 for r in rows if r["stratum"] == "control"), facts["population_digest"]))
    print("  arms            %s, bare only, cap %d" % (", ".join(facts["arms"]), facts["cap"]))
    print("  calls           %d; payload identity %s" % (facts["n_calls"], facts["payload_identity"]))
    print("  cost            expected $%.3f, ceiling $%.3f (recomputed $%.3f: %s)"
          % (facts["cost"]["expected_usd"], facts["cost"]["ceiling_usd_registered"],
             facts["cost"]["ceiling_usd_recomputed"], facts["cost"]["ceiling_basis"]))
    print("  law 8           refuses %d of the planned population" % len(facts["law8_refused"]))
    print("  sealed pages    %d in the union of %d records, %d intersected (measured)"
          % (len(facts["sealed_pages"]), len(facts["sealed_sources"]),
             len(SB.intersects(r["page_file"] for r in rows))))
    for _k, _p in facts["sealed_disagreement"]:
        print("                  DISAGREEMENT: %s does not name page %s" % (_k, _p))
    print("  disclosure      sheet=%r approval=%r (controls half: %r)"
          % (facts["disclosure"]["sheet"], facts["disclosure"]["approval"],
             facts["disclosure"]["controls_half"]))
    print("  sitting 2       manifest=%r" % facts["sitting2"]["manifest"])
    print("  pre-call checks %d" % precall_checks)

    if a.dry_run:
        print("")
        print("DRY RUN: nothing was sent and nothing was written.")
        print("  pin this for the paid pass:  --send --expect-checks %d" % precall_checks)
        print("  payload identity to compare: --expect-payload-digest %s" % facts["payload_identity"])
        return 0

    if a.send:
        chk(a.expect_checks is not None,
            "--send needs --expect-checks N, the count a free --dry-run pinned.  A header-scoped "
            "guard must never be discovered by spending.")
        chk(a.expect_checks == precall_checks,
            "the pre-call check count is %d and the pin says %d.  Either a gate was added or one "
            "stopped running; find out which before spending." % (precall_checks, a.expect_checks))
        if a.expect_payload_digest:
            chk(a.expect_payload_digest == facts["payload_identity"],
                "payload identity %s, pinned %s" % (facts["payload_identity"],
                                                    a.expect_payload_digest))
        key = os.environ.get(H.KEY_ENV)
        chk(bool(key), "%s is not set" % H.KEY_ENV)
        out_dir = Path(a.out_dir) if a.out_dir else A
        url = H.URL
        srv = None
        census = census_by_page()
    else:
        chk(a.out_dir is not None,
            "--stub-run needs --out-dir: a run that picks its own output directory can write over "
            "something, and the directory is the one argument a stub run must state")
        out_dir = Path(a.out_dir)
        census = census_by_page()
        table, notes = stub_table(rows, facts["arms"], census)
        srv, url = start_stub(a.stub_scenario, table, payloads)
        key = "stub-not-a-key"
        chk(H.KEY_ENV not in os.environ or os.environ.get(H.KEY_ENV) != key,
            "the stub is using the real key's name")
        print("  stub            %s, scenario %s, %d scripted replies"
              % (url, a.stub_scenario, len(table)))
        for sid, arm, why in notes:
            print("      scripted   %-10s %-28s %s" % (sid, arm.split("/")[-1], why))

    endpoint = gate_endpoint(mode if mode != "dry" else "stub", url, payloads)
    t0 = time.time()
    try:
        recs = send_all(payloads, key, url, endpoint)
    except S.RunFault as e:
        print("")
        print("RUN-LEVEL FAULT: %s" % e)
        # The scenario's own expectation, asserted in BOTH directions.  fault-head and dead-items
        # once produced a normal run's three artifacts and exit 0, and nothing in this module said
        # a word: the only reader of the outcome was me, looking at a log.
        if mode == "stub":
            chk(a.stub_scenario in MUST_FAULT,
                "scenario %r faulted, and only %r are supposed to" % (a.stub_scenario, MUST_FAULT))
        print("  nothing was written.  The run is rerun from the top, never spliced.")
        left = sorted(p.name for p in Path(out_dir).glob("LOCALIZER45_*")) \
            if Path(out_dir).exists() else []
        print("  artifacts in %s: %s" % (out_dir, left or "none"))
        if srv is not None:
            srv.shutdown()
        return 3
    finally:
        if srv is not None and not srv.__dict__.get("_done"):
            pass
    wall = time.time() - t0
    if srv is not None:
        srv.shutdown()

    if mode == "stub":
        chk(a.stub_scenario not in MUST_FAULT,
            "scenario %r ran to completion: it exists to make the run-level fault fire, and a "
            "fault scenario that finishes is a probe that passed on nothing" % a.stub_scenario)
    chk(len(recs) == facts["n_calls"], "%d records for %d calls" % (len(recs), facts["n_calls"]))
    chk(CHECKS - precall_checks >= len(recs),
        "the call loop contributed %d checks over %d calls -- a per-call assertion went missing"
        % (CHECKS - precall_checks, len(recs)))
    decisions = decide(recs, rows, facts["arms"])
    sec = secondary(recs, rows, census)
    capped = [(r["span_id"], r["arm"]) for r in recs if r["finish_reason"] == "length"]
    fals = falsifiers(lock, decisions, recs, rows, facts["population_digest"],
                      facts["law8_refused"], capped, facts["arms"])
    score = scoreability(fals, decisions)
    git_end = git_state_both()
    costs = [r["cost_usd"] for r in recs if r["cost_usd"] is not None]
    header = {
        "kind": "localizer45_run",
        "mode": "send" if a.send else ("stub:%s" % a.stub_scenario),
        "scoreable": bool(a.send),
        "lane": "Lane B", "session": "50612c81",
        "page_convention": "FILE pages (printed = file - 88)",
        "hash_rule": HASH_RULE,
        "lock": LOCK_PATH.name, "lock_sha16": LOCK_SHA, "attempt": ATTEMPT,
        "arms": facts["arms"], "channel": "bare", "max_tokens": facts["cap"],
        "population_digest": facts["population_digest"],
        "payload_identity": facts["payload_identity"],
        "law8_refused_in_draw": facts["law8_refused"],
        # MEASURED, not the registered 0 copied into the record it is supposed to witness. A
        # written claim that restates the prediction it was meant to check witnesses nothing.
        "sealed_pages_intersected": len(SB.intersects(r["page_file"] for r in rows)),
        "sealed_pages_union": sorted(facts["sealed_pages"]),
        "sealed_sources": dict((k, len(v)) for k, v in facts["sealed_sources"].items()),
        "sealed_disagreement": facts["sealed_disagreement"],
        "disclosure": facts["disclosure"], "sitting2": facts["sitting2"],
        "cost": facts["cost"],
        "cost_usd_total": round(sum(costs), 6) if costs else None,
        "endpoint": endpoint,
        "wall_clock_s": round(wall, 1),
        "retries_total": sum(r["retries"] for r in recs),
        "checks_precall": precall_checks, "checks_total": None,
        "git_start": git_start, "git_end": git_end,
        "clean_run": gate_clean_run(git_start, git_end, mode),
        "what_this_cannot_settle": lock["what_this_cannot_settle"],
        "stub_note": None if a.send else
            "The replies were scripted in localizer45_run.stub_table from the signed strings. "
            "This run proves the wiring and is evidence about nothing else.",
    }
    header["run_sha16"] = sha16({"payload_identity": facts["payload_identity"],
                                 "mode": header["mode"], "endpoint": endpoint["hostport"],
                                 "started": int(t0)})
    header["checks_total"] = CHECKS
    paths = write_artifacts(out_dir, header, recs, decisions, sec, fals, score, facts["arms"])
    print("")
    print("  verdicts        %s" % ", ".join(
        "%s %d" % (v, sum(1 for d in decisions if d["verdict"] == v)) for v in VERDICTS))
    for st in STRATA:
        print("    %-8s      %s" % (st, ", ".join(
            "%s %d" % (v, sum(1 for d in decisions
                              if d["verdict"] == v and d["stratum"] == st)) for v in VERDICTS)))
    print("  falsifiers      %s" % (", ".join(f["id"] for f in fals if f["fired"]) or "none fired"))
    print("  scoreability    %s %s" % (score["clean_stratum"], score["why"]))
    print("  secondary       %s" % canon(dict(
        (k, sum(1 for s in sec if s["class"] == k)) for k in sorted(set(s["class"] for s in sec)))))
    print("  retries %d, capped %d, errors %d, wall %.1fs, cost $%s"
          % (header["retries_total"], len(capped), sum(1 for r in recs if r["error"]), wall,
             header["cost_usd_total"]))
    print("  checks          %d total (%d pre-call)" % (CHECKS, precall_checks))
    print("  clean-run       %s" % ("PROVISIONAL: " + header["clean_run"]["why"]
                                    if header["clean_run"]["provisional"] else "clean"))
    for k in sorted(paths):
        print("  %-15s %s  (%d bytes, sha16 %s)"
              % (k, paths[k], paths[k].stat().st_size, S.stream_sha16(paths[k])))
    if not a.send and not a.keep:
        for p in sorted(paths.values()):
            p.unlink()
        try:
            Path(out_dir).rmdir()
        except OSError:
            pass
        print("  removed         the stub artifacts (pass --keep to leave them); the audits "
              "directory is as it was")
    return 0


if __name__ == "__main__":
    sys.exit(main())
