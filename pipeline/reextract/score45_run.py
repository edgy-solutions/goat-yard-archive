"""score45_run.py -- score the 45 signed truth spans, two OpenRouter arms x two channels (178 calls).

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).  Every report this script writes says so too.

Arms:      anthropic/claude-opus-5.5, qwen/qwen3.7-plus   (both remote; no local arm in this run)
Channels:  bare     -- the A2 span-box crop only
           context  -- the crop plus the Latin note text with every Hebrew run masked to U+2022
Calls:     45 bare + 44 context per arm = 89 per arm = 178.  p245:n1 runs bare only.

Scoring basis (PREDICTIONS_scoring45_*.json `basis`): primary = the row's in-crop `signature`;
secondary = `signature_full`, reported beside it and never instead of it.  Classes per
(span, arm, channel): exact | nikud_only | wrong | abstain  (+ `error`, kept in the denominator).
`nikud_only` is a third state, not wrong.  Nikud is NEVER stripped to force an `exact`.

A local scorer is used rather than hebrew_aperture_diag.classify: classify has extra classes
(punct-only, contains, clipped, degenerate) that the registered basis does not define, and its
nikud-only branch is spelled `nikud-only`.  Reusing it would change the classes the predictions
were registered against.

Modes:
  --dry-run    every gate except the key and the network, builds all 178 payloads, writes NOTHING,
               exits 0 with the key unset.
  --self-test  scorer over hand-made strings.
  (neither)    the real run: spends money, needs OPENROUTER_API_KEY.  Do not use without approval.

Interpreter: C:/Users/cnogr/git/goat-yard-archive/.venv/Scripts/python.exe, PYTHONIOENCODING=utf-8,
cwd = this directory.  Never `python -I`.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import httpx  # noqa: E402
from PIL import Image  # noqa: E402

import hebrew_aperture_diag as diag  # noqa: E402
import hebrew_frontier_or as H  # noqa: E402
import send_refusal as SR  # noqa: E402
from hebrew_frontier_or import (APERTURE, BACKOFF, KEY_ENV, MAX_TOKENS, OUT_TOKEN_FLAG,  # noqa: E402
                                RETRIES, _ctx, _no_hebrew_outbound, _parse, _prompt_text,
                                REASONING_LADDER)

A = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
SHEET = A / "CONTACT_SHEET_scoring45_adb9a26835533dbc_c26745f4be489471bd.json"
PRED = A / "PREDICTIONS_scoring45_36122ad8eb06a9c2.json"
CROPDIR = A / "truthset74_crops_0401b636ffa7bf1a"      # the sheet's own cut (truthset74_cut_0401b636...)
REPO_B = Path("C:/Users/cnogr/git/goatyard-laneB")
REPO_DR = Path("C:/Users/cnogr/git/dr-voluminous")

ARMS = ["anthropic/claude-opus-5.5", "qwen/qwen3.7-plus"]
CHANNELS = {"bare": "A2 span crop alone",
            "context": "A2 span crop plus Latin note text, Hebrew runs masked to U+2022"}
PRED_SHA = "36122ad8eb06a9c2"
PAYLOAD_SHA = "6745f4be489471bd"
SET_DIGEST = "adb9a26835533dbc"
ABSENT = "p245:n1"
ABSENT_BASIS = ("the content witness disagrees with the region index; p245 is on A2's known "
                "two-notes-one-region list (p107, p245, p306, p377, p677)")
FORBIDDEN_HOSTS = ("192.168.1.179", "192.168.1.188", "192.168.1.169")
SIDECAR = Path(str(diag.DATA)) / SR.SIDECAR_NAME
UNGATED_CALLS = 178       # the population BEFORE law-8 refusal: 2 arms x (45 bare + 44 ctx)
EXPECTED_CALLS = None     # derived from the send plan at run time; see gate_counts
CLASSES = ("exact", "nikud_only", "wrong", "abstain", "error")
CONSECUTIVE_FAIL_ABORT = 4
RETRY_CODES = (429, 500, 502, 503, 504)
NIKUD = re.compile("[\u0591-\u05c7]")
HEB = re.compile("[\u0590-\u05ff]")

# Pinned to the count the first FULL run observes.  None until then: the real run prints the observed
# count and marks the header checks_pinned=false.  The dry-run has its own pinned count.
EXPECTED_CHECKS = 1603      # DERIVED 2026-11-08, not measured.  630 was MEASURED on run
                            # 6a2292bdb14d3c43, whose dry-run measured 356, so the real-run-only
                            # checks were 630 - 356 = 274 (mostly do_call's per-ladder-step host
                            # assertion, one per call because the ladder stepped once per call in
                            # that run).  The dry-run now MEASURES 1167, and this commit adds one
                            # further unconditional assertion per call in do_call, so
                            # 1167 + 274 + 162 = 1603.
                            #
                            # Two caveats a later reader needs.  The 274 is borrowed from a run
                            # under a condition that could change: if the reasoning ladder has to
                            # step twice on some call, this number is low by one per extra step.
                            # And the check runs AFTER the files are written, so a mismatch aborts
                            # a run that already spent.  Re-pin from the observed count when that
                            # happens; never relax it to None.
                            #
                            # PRECONDITION, because this total is not a constant of the code: it
                            # is a function of the CALL COUNT, and the call count is a function of
                            # law 8's refusal set, which was {p190:n0, p493:n3, p594:n0, p803:n0}
                            # -- 4 of 45 -- when this was measured.  Those refusals rest partly on
                            # sidecar fields DEFAULTED on 54 of 74 spans, so the set will move the
                            # day somebody adjudicates them.  When it does, this run ABORTS on the
                            # count rather than running: that is correct, and the fix is to
                            # re-measure with --dry-run (free) and re-pin, never to relax it to
                            # None.  A pin nobody can explain is how a lost assertion hides.
EXPECTED_CHECKS_DRY = 1167       # MEASURED 2026-11-08 in normal mode.  356 (measured 2026-10-25
                                 # after the law-8 send gate) + 162 (build_payloads: the encoded
                                 # bytes equal the file on disk) + 4*162 (GATE B1, per payload:
                                 # the payload hash has not drifted, the crop carries no fault,
                                 # it is the row's own crop, and the header records what is sent)
                                 # + 1 (GATE B2, run-level payload identity) = 1167.
                                 #
                                 # I predicted 518 here by counting only the first of those four
                                 # terms.  Left in view because the arithmetic is the point: the
                                 # number is only an assertion if somebody can restate how it is
                                 # reached, and mine was restatable enough to find the omission.

# ------------------------------------------------------------- the blank-crop control (blank45.py)
#
# This mode measures a FLOOR and reads nothing.  Run 6a2292bdb14d3c43 scored 32/41, 31/40, 25/41
# and 22/40 exact with ZERO abstentions in 162 calls, against no floor at all -- and this lane has
# a precedent of a zero-pixel crop returning the exact signed string.  78% against a floor of 0
# and 78% against a floor of 20 are different findings, and that run reported neither.
#
# The cut, the lock and the contact sheet are built by blank45.py and only CONSUMED here: this
# file derives none of them, and refuses to run if any of the three fails to recompute its own
# content address.
BLANKDIR = A / ("blank45_crops_%s" % SET_DIGEST)
BLANK_FAULT = "blank:uniform=255"
BLANK_CUT = A / "BLANK45_CUT_45c4cd25300f0989.json"
BLANK_PRED = A / "PREDICTIONS_blank45_302fb832585bba42.json"
BLANK_SHEET = A / "CONTACT_SHEET_blank45_4035ea8add73d217.json"
BLANK_CUT_DIGEST = "45c4cd25300f0989"
BLANK_PRED_SHA = "302fb832585bba42"
BLANK_SHEET_DIGEST = "4035ea8add73d217"
# The approval is its own record, named by the sheet digest it approves.  It is NOT a field in
# the sheet: the sheet is content-addressed over all of its contents, so answering inside it
# would change the name of the thing being approved.  A record of a human's yes must be named
# by what it describes.
BLANK_APPROVAL = A / ("APPROVAL_blank45_%s.json" % BLANK_SHEET_DIGEST)
BLANK_SIGNS = ("D1", "D2", "D3", "D4")      # the signs evaluate_blank knows how to score

# The run whose four rates this control puts a floor under, and that run's payload identity.
# The digest's recipe is `payload_identity` below; the VALUE was recovered from the committed
# artifact, not from this builder -- a verifier that calls the producer agrees by construction.
FLOORS_FOR = "6a2292bdb14d3c43"
FLOORS_FILE = A / ("SCORE45_%s.json" % FLOORS_FOR)
SCORED_PAYLOAD_DIGEST = "870bf99e65725534"

EXPECTED_CHECKS_BLANK = 1671       # DERIVED from the measured blank dry-run below, by the same
                                   # 274 + 162 real-run-only term as EXPECTED_CHECKS: 1235 + 436.
                                   # First MEASURED by the control's own run; re-pin if it aborts.
EXPECTED_CHECKS_BLANK_DRY = 1235   # MEASURED 2026-11-08 in blank mode: 1167 (normal) + 68 for
                                   # GATE B0, which re-hashes the cut, the lock and the contact
                                   # sheet, re-reads all 45 blanks off disk, and checks both of
                                   # the sheet's disclosure maps.  The two modes differ by GATE
                                   # B0 alone: GATE B1 runs the same number of assertions either
                                   # way, on opposite expectations.

CHECKS = 0


class RunFault(Exception):
    """A run-level fault: abort, write nothing."""


def chk(cond, msg):
    """Every assertion in the run goes through here so the CHECKS counter is live."""
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(msg)


# ----------------------------------------------------------------------------------------- scorer
def _nfc(t):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t or "")).strip()


def classify(read, truth):
    """exact | nikud_only | wrong | abstain.  `read` is the model's parsed Hebrew string.

    exact is tested on the NFC strings AS THEY ARE.  Marks are removed only AFTER that test has
    failed, and only to tell `nikud_only` from `wrong`; a pointed read of an unpointed truth is
    therefore `nikud_only`, never `exact`."""
    r, t = _nfc(read), _nfc(truth)
    if not r or r.upper() == "ABSTAIN" or not HEB.search(r):
        return "abstain"
    if r == t:
        return "exact"
    if NIKUD.sub("", r) == NIKUD.sub("", t):
        return "nikud_only"
    return "wrong"


def self_test():
    n = 0

    def eq(a, b, m):
        nonlocal n
        n += 1
        assert a == b, f"{m}: got {a!r} want {b!r}"

    truth = "\u05e9\u05e8\u05e5"                       # shin resh tsade
    eq(classify(truth, truth), "exact", "exact")
    eq(classify("\u05e9\u05b8\u05c1\u05e8\u05e5", truth), "nikud_only", "nikud-only pair")
    eq(classify(truth, "\u05e9\u05b8\u05e8\u05e5"), "nikud_only", "pointed truth, bare read")
    eq(classify("\u05e9\u05e8\u05e7", truth), "wrong", "one-letter substitution")
    eq(classify("ABSTAIN", truth), "abstain", "ABSTAIN")
    eq(classify("abstain", truth), "abstain", "abstain lowercase")
    eq(classify("", truth), "abstain", "empty")
    eq(classify("hello", truth), "abstain", "no Hebrew")
    # shortcut guard: a pointed read must NOT be exact, and must NOT be wrong
    pointed = "\u05e9\u05b8\u05e8\u05e5"
    eq(classify(pointed, truth) not in ("exact", "wrong"), True, "no nikud-stripping shortcut")
    eq(_parse('{"hebrew": "ABSTAIN"}')[0], "ABSTAIN", "parse abstain")
    eq(classify(_parse('{"hebrew": "%s"}' % truth)[0], truth), "exact", "parse json exact")
    eq(classify("\u05e9\u05e8 \u05e5", "\u05e9\u05e8\u05e5"), "wrong", "space is not folded away")
    # The payload-identity recipe, exercised against the COMMITTED artifact it did not produce.
    # GATE B2 asserts this value in both directions, so the recipe has to be code, not memory.
    _h = json.loads(FLOORS_FILE.read_text(encoding="utf-8"))["header"]
    eq(payload_identity(_h["predicted_request_sha16_before_send"], _h["crop_sha16_sent"]),
       SCORED_PAYLOAD_DIGEST, "payload identity recipe reproduces the committed run's digest")
    eq(len(_h["predicted_request_sha16_before_send"]), 162, "the floored run made 162 calls")
    print(f"self-test: {n} assertions passed")


# ------------------------------------------------------------------------------------------- utils
def sha16_bytes(b):
    return hashlib.sha256(b).hexdigest()[:16]


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def git_state(repo):
    try:
        head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"]).decode().strip()
        por = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]).decode()
    except Exception as e:
        return {"head": "unknown", "dirty": "unknown", "paths": [], "error": str(e)[:120]}
    paths = [l for l in por.splitlines() if l.strip()]
    return {"head": head, "dirty": bool(paths), "n": len(paths), "paths": paths[:12]}


def stream_sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 16), b""):
            h.update(blk)
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------------------------- plan
def load_inputs():
    sheet = json.loads(SHEET.read_text(encoding="utf-8"))
    pred = json.loads(PRED.read_text(encoding="utf-8"))
    return sheet, pred


def gate_prediction(pred):
    p = {k: v for k, v in pred.items() if k not in ("self_sha16", "self_sha16_rule")}
    c = hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]
    chk(c == PRED_SHA, f"GATE 2 prediction lock: self_sha16 recomputes to {c}, not {PRED_SHA}")
    chk(pred.get("self_sha16") == PRED_SHA, "GATE 2: file's own self_sha16 != expected")
    return {"prediction_sha16": c}


def gate_crops(sheet):
    bad, shas = [], {}
    for r in sheet["rows"]:
        p = CROPDIR / r["crop_file"]
        if not p.exists():
            bad.append((r["span_id"], "missing"))
            continue
        s = stream_sha16(p)
        shas[r["span_id"]] = s
        with Image.open(p) as im:
            wh = im.size
        if s != r["crop_sha16"]:
            bad.append((r["span_id"], f"sha {s} != {r['crop_sha16']}"))
        elif wh != (r["crop_w"], r["crop_h"]):
            bad.append((r["span_id"], f"size {wh} != {(r['crop_w'], r['crop_h'])}"))
    chk(not bad, f"GATE 3 disclosure: crops not matching what was shown: {bad}")
    chk(len(shas) == 45, "GATE 3: 45 crops")
    return shas


def gate_payload_identity(sheet):
    trip = sorted((r["span_id"], r["ch2_state"], r["ch2"] if r["ch2_state"] == "present" else "")
                  for r in sheet["rows"])
    got = sha16_bytes(json.dumps([list(t) for t in trip], ensure_ascii=False,
                                 separators=(",", ":")).encode("utf-8"))
    chk(got == PAYLOAD_SHA, f"GATE 4 channel-2 payload identity {got} != {PAYLOAD_SHA}")
    chk(sheet["channel2_payload_sha16"] == PAYLOAD_SHA, "GATE 4: sheet header sha")
    chk(sheet["set_digest"] == SET_DIGEST, "GATE 4: set_digest")
    return got


def build_body(arm, row, channel, img_b64):
    ctx = None if channel == "bare" else row["ch2"]
    return H._body(arm, ctx, img_b64, structured=False, reasoning=REASONING_LADDER[0][0]), ctx


def plan_calls(sheet, sendable):
    """Only `sendable` spans are planned.  A span law 8 refused is never built into a payload, so it
    cannot reach the wire by a later bug in the posting loop -- the refusal is in the PLAN, not a
    skip inside the sender."""
    allow = set(sendable)
    calls = []
    for arm in ARMS:
        for channel in CHANNELS:
            for r in sheet["rows"]:
                if r["span_id"] not in allow:
                    continue
                if channel == "context" and r["ch2_state"] != "present":
                    continue
                calls.append((arm, channel, r))
    return calls


def build_payloads(calls, crop_dir, allow_fault):
    """`crop_dir` and `allow_fault` are REQUIRED arguments, with no defaults.

    A function that derives its own input fails silently.  Had `crop_dir` defaulted to CROPDIR,
    a blank-crop run that lost its flag anywhere between argparse and here would post the REAL
    crops and be written up as a floor -- the one failure of this control no later reader could
    detect, because every byte of the output would look right.  A caller that cannot name the
    directory and the licence cannot call this.

    `allow_fault` is None for a read and the one licensed fault string for the control.  It
    makes the encode STRICTER, not looser -- see hebrew_aperture_diag.gate_outbound."""
    out = []
    for arm, channel, r in calls:
        src = crop_dir / r["crop_file"]
        b64 = diag.b64_gated(src, what="score45 crop", offnet=True, allow_fault=allow_fault)
        # The REALIZED bytes, hashed from what was encoded rather than taken from the row: in
        # blank mode the row's `crop_sha16` is NOT what goes on the wire, and a record that
        # cannot say which bytes were sent cannot witness the ablation.
        sent_sha = sha16_bytes(base64.b64decode(b64))
        chk(sent_sha == stream_sha16(src),
            f"{r['span_id']}: the encoded bytes do not hash to the file on disk")
        body, ctx = build_body(arm, r, channel, b64)
        _no_hebrew_outbound(body)
        chk(True, "no Hebrew in outbound body")
        if channel == "context":
            text = body["messages"][0]["content"][1]["text"]
            chk(not HEB.search(text), f"GATE 8 Hebrew in channel-2 text for {r['span_id']}")
            chk(ctx == _ctx(ctx), f"channel-2 string for {r['span_id']} is not already masked")
        out.append({"arm": arm, "channel": channel, "row": r, "body": body,
                    "crop_sha16_sent": sent_sha,
                    "request_sha16": sha16_bytes(canon(body).encode("utf-8"))})
    return out


def gates_endpoint_aperture(payloads):
    chk(APERTURE == "A2_spanbox", "GATE 5 aperture")
    chk(urlparse(H.URL).hostname == "openrouter.ai", "GATE 6 host")
    blob = "\n".join(canon(p["body"]) + p["row"]["crop_file"] for p in payloads)
    chk("A1_notebox" not in blob, "GATE 5: A1_notebox referenced in a constructed payload")
    for h in FORBIDDEN_HOSTS:
        chk(h not in blob, f"GATE 6: forbidden endpoint {h} in a constructed request")
    chk(all(p["row"]["crop_file"].endswith("_A2_spanbox.png") for p in payloads), "all crops A2")


def gate_counts(payloads, sheet, plan):
    """The call count is DERIVED from the sheet and the send plan, not pinned to a number.

    It was pinned to 178 when nothing was refused.  A pinned total and a live refusal gate fight each
    other, and the pin wins by aborting the run -- so the expected counts are computed from the same
    two inputs the plan was built from, and `UNGATED_CALLS` is asserted as the population the gate
    reduced, which keeps the 178 honest instead of stale."""
    send = set(plan.sendable)
    n_bare = sum(1 for r in sheet["rows"] if r["span_id"] in send)
    n_ctx = sum(1 for r in sheet["rows"] if r["span_id"] in send and r["ch2_state"] == "present")
    n_bare_all = len(sheet["rows"])
    n_ctx_all = sum(1 for r in sheet["rows"] if r["ch2_state"] == "present")
    chk(len(ARMS) * (n_bare_all + n_ctx_all) == UNGATED_CALLS,
        f"GATE 9: the ungated population is {len(ARMS) * (n_bare_all + n_ctx_all)}, not {UNGATED_CALLS}")
    chk(len(payloads) == len(ARMS) * (n_bare + n_ctx),
        f"GATE 9 call count {len(payloads)} != {len(ARMS)} x ({n_bare} bare + {n_ctx} ctx)")
    for arm in ARMS:
        chk(sum(p["arm"] == arm and p["channel"] == "bare" for p in payloads) == n_bare,
            f"{n_bare} bare per arm")
        chk(sum(p["arm"] == arm and p["channel"] == "context" for p in payloads) == n_ctx,
            f"{n_ctx} ctx per arm")
    # LAW 8, the half that is not a count: no refused span may appear in a built payload, checked
    # against the refusal report rather than against the list plan_calls filtered on.
    built = {p["row"]["span_id"] for p in payloads}
    leaked = sorted(built & set(plan.report["refused"]))
    chk(not leaked, f"GATE 9/law 8: refused span(s) built into a payload: {leaked}")
    chk(len(built) == n_bare, f"payloads cover {len(built)} spans, expected {n_bare}")
    chk(ABSENT not in plan.report["refused"], f"{ABSENT} is refused, so the bare/ctx asymmetry below is not the recorded one")
    chk(any(p["row"]["span_id"] == ABSENT and p["channel"] == "bare" for p in payloads), "p245:n1 bare")
    chk(not any(p["row"]["span_id"] == ABSENT and p["channel"] == "context" for p in payloads),
        "p245:n1 has no channel-2 call")
    chk(len({p["request_sha16"] for p in payloads}) == len(payloads), "request_sha16 unique")


def payload_identity(request_shas, crop_shas):
    """A run's payload identity: sha16 over its sorted request hashes and its sent-crop map.

    The recipe is the one run 6a2292bdb14d3c43 was hashed under, recovered from that committed
    artifact and written down here.  `self_test` reproduces that run's value through this
    function, so the recipe is checked against an artifact it did not produce.

    NAMING, carried from that run and deliberately not changed: `crop_sha16_sent` holds all 45
    of the sheet's crops, including the four law 8 refused and never sent.  The name overstates
    what it contains.  It is kept because the digest is a pin on the committed run and renaming
    the key would silently move it; the authoritative per-call record of what reached the wire
    is each read row's own `crop_sha16_sent`."""
    return sha16_bytes(canon({
        "crop_sha16_sent": {k: crop_shas[k] for k in sorted(crop_shas)},
        "predicted_request_sha16_before_send": sorted(request_shas),
    }).encode("utf-8"))


def gate_ablation(payloads, sheet, crop_dir, sent_shas, blank):
    """GATE B1/B2: what is in the payloads is what the mode says is in them.

    B1 is per crop and reads the BYTES on disk through the lane's own outbound gate.  The
    directory a caller passed is a claim; what is in the file is the evidence, and the thing
    this has to catch is a cut that wrote a real crop under a blank name.  In blank mode every
    crop must carry the licensed fault and must hash to none of the 45 real hashes; in normal
    mode every crop must have NO fault and must hash to its own row's recorded value.

    B2 is run-level and asserted in opposite directions.  Normal mode must still land on the
    committed run's payload identity -- adding this mode must not change what a read sends --
    and blank mode must NOT, because a control whose bytes equal the read run's bytes ablated
    nothing.  Equality alone would pass a run that forgot to swap the crops; inequality alone
    would pass a run that changed the prompt as well."""
    real = {r["span_id"]: r["crop_sha16"] for r in sheet["rows"]}
    real_set = set(real.values())
    for p in payloads:
        sid = p["row"]["span_id"]
        src = crop_dir / p["row"]["crop_file"]
        _raw, fault = diag.gate_outbound(src, offnet=True)
        chk(p["crop_sha16_sent"] == stream_sha16(src), f"GATE B1: {sid} payload hash drifted")
        if blank:
            chk(fault == BLANK_FAULT,
                f"GATE B1: {sid} is not blank on disk: the gate says {fault!r}")
            chk(p["crop_sha16_sent"] not in real_set,
                f"GATE B1: {sid} would send a REAL crop ({p['crop_sha16_sent']}) in blank mode")
        else:
            chk(fault is None, f"GATE B1: {sid} carries fault {fault!r} in a normal run")
            chk(p["crop_sha16_sent"] == real[sid],
                f"GATE B1: {sid} sends {p['crop_sha16_sent']}, row says {real[sid]}")
        chk(sent_shas[sid] == p["crop_sha16_sent"],
            f"GATE B1: {sid} is recorded in the header as {sent_shas[sid]} but sends "
            f"{p['crop_sha16_sent']}")
    digest = payload_identity([p["request_sha16"] for p in payloads], sent_shas)
    if blank:
        chk(digest != SCORED_PAYLOAD_DIGEST,
            "GATE B2: the blank run's payload identity EQUALS run %s's (%s).  Nothing was "
            "ablated." % (FLOORS_FOR, SCORED_PAYLOAD_DIGEST))
    else:
        chk(digest == SCORED_PAYLOAD_DIGEST,
            "GATE B2: a normal run now builds payload identity %s, not run %s's %s.  Adding "
            "the blank-crop mode changed what a READ sends." % (digest, FLOORS_FOR,
                                                               SCORED_PAYLOAD_DIGEST))
    return digest


def gate_blank_inputs(sheet, dry):
    """GATE B0: the control's three artifacts recompute, agree with each other, and are approved.

    Each of the cut, the lock and the contact sheet is content-addressed, so each is re-hashed
    from its own contents here rather than trusted by filename.  They are then checked against
    each other and against this file's pins, so a sheet built from one cut and a lock registered
    over another cannot be run together.

    The last clause is the standing contact-sheet gate, wired into the sender instead of living
    in a procedure: a real run refuses to spend while `approval.by` is null.  A dry-run reports
    it, because the dry-run is how the sheet gets checked before it is approved."""
    cut = json.loads(BLANK_CUT.read_text(encoding="utf-8"))
    lock = json.loads(BLANK_PRED.read_text(encoding="utf-8"))
    bsheet = json.loads(BLANK_SHEET.read_text(encoding="utf-8"))
    for obj, key, pin, name in ((cut, "digest", BLANK_CUT_DIGEST, "cut"),
                                (lock, "prediction_sha16", BLANK_PRED_SHA, "lock"),
                                (bsheet, "digest", BLANK_SHEET_DIGEST, "contact sheet")):
        got = sha16_bytes(canon({k: v for k, v in obj.items() if k != key}).encode("utf-8"))
        chk(got == pin, f"GATE B0: the blank {name} recomputes to {got}, not {pin}")
        chk(obj[key] == pin, f"GATE B0: the blank {name}'s own {key} is not {pin}")
    chk(lock["cut_digest"] == BLANK_CUT_DIGEST, "GATE B0: the lock registers another cut")
    chk(bsheet["cut_digest"] == BLANK_CUT_DIGEST, "GATE B0: the sheet shows another cut")
    chk(bsheet["prediction_sha16"] == BLANK_PRED_SHA, "GATE B0: the sheet names another lock")
    chk(lock["floors_run"] == FLOORS_FOR, "GATE B0: the lock floors another run")
    chk(lock["scored_payload_digest"] == SCORED_PAYLOAD_DIGEST, "GATE B0: lock payload digest")
    chk(lock["set_digest"] == SET_DIGEST == cut["set_digest"] == bsheet["set_digest"],
        "GATE B0: the control is registered over another span set")
    chk(sorted(lock["registered_cells"]) == sorted(f"{a}|{c}" for a in ARMS for c in CHANNELS),
        "GATE B0: the lock's cells are not this run's four arm/channel cells")
    chk(tuple(s["id"] for s in lock["registered_signs"]) == BLANK_SIGNS,
        "GATE B0: the lock registers signs %s and evaluate_blank scores %s.  An unscored "
        "registered sign is a prediction that quietly does not count."
        % ([s["id"] for s in lock["registered_signs"]], list(BLANK_SIGNS)))
    # The 45-entry sent-crop map, read off the cut and then verified against the files.
    blank_shas = {r["span_id"]: r["blank_sha16"] for r in cut["rows"]}
    byid = {r["span_id"]: r for r in sheet["rows"]}
    chk(set(blank_shas) == set(byid), "GATE B0: the cut and the sheet cover different spans")
    for sid, r in sorted(byid.items()):
        chk(stream_sha16(BLANKDIR / r["crop_file"]) == blank_shas[sid],
            f"GATE B0: {sid}'s blank on disk is not the one the cut recorded")
    # Both halves of the disclosure, from the sheet's two top-level maps.  The blanks must be
    # the crops that will be sent, AND the originals shown beside them must be the real crops
    # of record: a sheet showing the right blanks beside the wrong originals is a sheet nobody
    # can have approved on what it showed.
    shown = bsheet["crop_sha16_to_send"]
    replaced = bsheet["crop_sha16_replaced"]
    real_row = {r["span_id"]: r["crop_sha16"] for r in sheet["rows"]}
    bad_send = sorted(s for s, h in shown.items() if blank_shas.get(s) != h)
    bad_repl = sorted(s for s, h in replaced.items() if real_row.get(s) != h)
    chk(not bad_send,
        f"GATE B0 disclosure: crop(s) to be sent are not the ones the sheet showed: {bad_send}")
    chk(not bad_repl,
        f"GATE B0 disclosure: the sheet showed the wrong original beside the blank for "
        f"{bad_repl}")
    chk(set(shown) == set(replaced), "GATE B0: the sheet's two maps cover different spans")
    chk(len(shown) == bsheet["n_crops"] == 41, "GATE B0: the sheet showed 41 crops")
    chk(bsheet["calls"] == len(ARMS) * (41 + 40) == 162,
        "GATE B0: the sheet was approved for %d calls" % bsheet["calls"])
    # The four spans law 8 refused have a blank cut but no row on the sheet, because no call
    # will be made for them.  Stated as an assertion so the 45/41 gap stays a known quantity.
    chk(sorted(set(blank_shas) - set(shown)) == sorted(lock["population"]["refused"]),
        "GATE B0: the spans cut but not shown are not the four law 8 refused")
    inline = bsheet.get("approval") or {}
    # Refused by NAME, not left to fail on the digest: an operator who answered in the sheet
    # needs to be told where the yes belongs, not that a hash moved.
    chk(not inline.get("by"),
        "GATE B0: %s carries an inline approval by %r.  The sheet is content-addressed over "
        "its whole contents, so answering inside it renames the thing approved.  The yes goes "
        "in %s." % (BLANK_SHEET.name, inline.get("by"), BLANK_APPROVAL.name))
    appr = {"by": None, "on": None, "what": inline.get("what"), "record": None,
            "wanted": "a human approves the 41 crops on what they SHOW, not on the text "
                      "beside them"}
    if BLANK_APPROVAL.exists():
        rec = json.loads(BLANK_APPROVAL.read_text(encoding="utf-8"))
        # The name and the contents must agree.  A record that does not say which sheet it
        # approves is a yes to whatever happens to sit at that filename.
        chk(rec.get("approves_sheet_digest") == BLANK_SHEET_DIGEST,
            "GATE B0: %s approves sheet %r, and its own name says %s"
            % (BLANK_APPROVAL.name, rec.get("approves_sheet_digest"), BLANK_SHEET_DIGEST))
        chk(rec.get("approves_cut_digest") == BLANK_CUT_DIGEST,
            "GATE B0: %s approves cut %r, not %s -- the approved crops are not these crops"
            % (BLANK_APPROVAL.name, rec.get("approves_cut_digest"), BLANK_CUT_DIGEST))
        chk(bool(rec.get("by")) and bool(rec.get("on")),
            "GATE B0: %s names no approver or no date" % BLANK_APPROVAL.name)
        appr = dict(rec, record=BLANK_APPROVAL.name)
    if dry:
        chk(True, "GATE B0 approval evaluated (dry-run: reported, not fatal): by=%r"
                  % appr.get("by"))
    else:
        chk(bool(appr.get("by")),
            "GATE B0: contact sheet %s is not approved -- %s does not exist.  Nothing goes out "
            "before a human approves the crops on what they show."
            % (BLANK_SHEET.name, BLANK_APPROVAL.name))
    return lock, bsheet, blank_shas, appr


# ------------------------------------------------------------------------------------------ calling
def _post(body, key):
    return httpx.post(H.URL, headers={"Authorization": f"Bearer {key}",
                                      "content-type": "application/json"}, json=body, timeout=300)


def do_call(p, key):
    """One read.  Returns a record.  Raises RunFault on a 429 that survives retries."""
    arm, row = p["arm"], p["row"]
    img_b64 = p["body"]["messages"][0]["content"][0]["image_url"]["url"].split(",", 1)[1]
    # The image this call will actually post, hashed at the send site.  The reasoning ladder
    # rebuilds the body below, and `crop_sha16` on the record is the row's REAL crop -- which in
    # the blank-crop control is not the crop being sent.  A record that cannot say which bytes
    # reached the wire cannot witness an ablation.
    chk(sha16_bytes(base64.b64decode(img_b64)) == p["crop_sha16_sent"],
        f"{row['span_id']} {arm} {p['channel']}: the image in the body is not the planned crop")
    retries, applied, sent_sha, r, err = 0, None, p["request_sha16"], None, None
    for spec, label in REASONING_LADDER:
        body, _ = build_body(arm, row, p["channel"], img_b64)
        body = H._body(arm, None if p["channel"] == "bare" else row["ch2"], img_b64, False, reasoning=spec)
        _no_hebrew_outbound(body)
        chk(urlparse(H.URL).hostname == "openrouter.ai", "host at send")
        sent_sha = sha16_bytes(canon(body).encode("utf-8"))
        try:
            r = _post(body, key)
            for attempt in range(RETRIES):
                if r.status_code not in RETRY_CODES:
                    break
                retries += 1
                time.sleep(BACKOFF * (2 ** attempt))
                r = _post(body, key)
        except Exception as e:                                 # transport failure: an item error
            err = f"transport:{type(e).__name__}:{str(e)[:100]}"
            r = None
            break
        applied = label
        if not (r.status_code == 400 and "reasoning" in r.text.lower()):
            break
    rec = {"span_id": row["span_id"], "page_file": row["page_file"], "page_printed": row["page_printed"],
           "arm": arm, "channel": p["channel"], "request_sha16": sent_sha,
           # Two hashes, because in the blank-crop control they differ: `crop_sha16` is the
           # row's real crop (the thing this read is ABOUT) and `crop_sha16_sent` is what went
           # on the wire.  One field could not say both without lying in one mode.
           "crop_sha16": row["crop_sha16"], "crop_sha16_sent": p["crop_sha16_sent"],
           "response_raw": None, "hebrew": None, "class_primary": "error", "class_secondary": "error",
           "retries": retries, "cost_usd": None, "out_tokens": None, "finish_reason": None,
           "error": err, "reasoning_applied": applied,
           "predicted_request_sha16_before_send": p["request_sha16"],
           "provider": None, "model_returned": None, "gen_id": None}
    if r is not None and r.status_code == 429:
        raise RunFault(f"429 survived {RETRIES} retries on {row['span_id']} {arm} {p['channel']}")
    if r is not None and r.status_code >= 400:
        rec["error"] = f"http{r.status_code}:{r.text[:160]}"
    elif r is not None:
        try:
            d = r.json()
            raw = (d["choices"][0]["message"].get("content") or "").strip()
            u = d.get("usage") or {}
            heb, _how = _parse(raw)
            rec.update(response_raw=raw, hebrew=heb, cost_usd=u.get("cost"),
                       out_tokens=u.get("completion_tokens"),
                       finish_reason=d["choices"][0].get("finish_reason"),
                       provider=d.get("provider"), model_returned=d.get("model"),
                       gen_id=d.get("id"))
            rec["class_primary"] = classify(heb, row["signature"])
            rec["class_secondary"] = classify(heb, row["signature_full"])
        except Exception as e:
            rec["error"] = f"malformed_body:{type(e).__name__}:{str(e)[:100]}"
    return rec


# ------------------------------------------------------------------------------------------ tallies
def tally(recs, ids=None, which="class_primary"):
    c = {k: 0 for k in CLASSES}
    for r in recs:
        if ids is None or r["span_id"] in ids:
            c[r[which]] += 1
    c["n"] = sum(c.values())
    return c


def agreement(recs, channel):
    by = {}
    for r in recs:
        if r["channel"] == channel:
            by.setdefault(r["span_id"], {})[r["arm"]] = r
    aw, bwd = [], []
    for sid, d in sorted(by.items()):
        if len(d) == 2 and all(x["class_primary"] == "wrong" for x in d.values()):
            a, b = (d[ARMS[0]], d[ARMS[1]])
            (aw if _nfc(a["hebrew"]) == _nfc(b["hebrew"]) else bwd).append(sid)
    return {"agreement_and_wrong": aw, "both_wrong_disagree": bwd}


def nikud_rows(recs, arm, channel):
    return sorted(r["span_id"] for r in recs if r["arm"] == arm and r["channel"] == channel
                  and r["hebrew"] and NIKUD.search(r["hebrew"]))


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def evaluate(recs, pred):
    """Prediction-vs-outcome.  A 'hit' on a registered number is |measured pp - registered pp| <= 5."""
    P = pred["predictions"]
    cells = {"opus_bare": (ARMS[0], "bare"), "opus_ch2": (ARMS[0], "context"),
             "qwen_bare": (ARMS[1], "bare"), "qwen_ch2": (ARMS[1], "context")}
    res = {"registered_numbers": {}, "falsifiers": {}}
    ex = {}
    for k, (arm, ch) in cells.items():
        t = tally([r for r in recs if r["arm"] == arm and r["channel"] == ch])
        ex[k] = t
        reg = P["exact_in_crop"][k]
        m = pct(t["exact"], t["n"])
        same_of = (t["n"] == reg["of"])
        res["registered_numbers"][k] = {"registered_pct": reg["pct"], "registered_n": f'{reg["n"]}/{reg["of"]}',
                                        "measured_pct": m, "measured_n": f'{t["exact"]}/{t["n"]}',
                                        "same_denominator": same_of,
                                        "delta_pp": None if m is None else round(m - reg["pct"], 1),
                                        "delta_comparable": same_of,
                                        "denominator_note": None if same_of else (
                                            "the prediction was registered over %d spans and this "
                                            "run read %d: the law-8 send gate refused the "
                                            "difference, so delta_pp is NOT a hit-or-miss on the "
                                            "registered number." % (reg["of"], t["n"]))}
    common = {r["span_id"] for r in recs if r["channel"] == "context"}
    ar = {ch: agreement(recs, ch) for ch in CHANNELS}
    ar_bare44 = agreement([r for r in recs if r["span_id"] in common], "bare")
    d_exact = {}
    for arm in ARMS:
        b = tally([r for r in recs if r["arm"] == arm and r["channel"] == "bare" and r["span_id"] in common])
        c = tally([r for r in recs if r["arm"] == arm and r["channel"] == "context"])
        d_exact[arm] = {"bare_on_44": b["exact"], "ctx_on_44": c["exact"]}
    n44 = len(common)
    aw_b, aw_c = len(ar_bare44["agreement_and_wrong"]), len(ar["context"]["agreement_and_wrong"])
    dpp = {arm: round(100.0 * (v["ctx_on_44"] - v["bare_on_44"]) / n44, 1) for arm, v in d_exact.items()}
    raises = all(d > 0 for d in dpp.values())
    aw_delta_pp = round(100.0 * (aw_c - aw_b) / n44, 1)
    mean_exact_delta_pp = round(sum(dpp.values()) / len(dpp), 1)
    # Derived, not the literal "44": the law-8 send gate removes refused spans from both channels,
    # so the common denominator is whatever actually got read.  A label that says 44 over 40 rows is
    # the stale-precondition failure in miniature.
    basis44 = (f"common {n44} span(s) read in both channels ({ABSENT} has no channel-2 call; spans "
               f"refused at send are in neither). A rate over one denominator is not comparable to "
               f"a rate over another.")
    res["sign_predictions"] = {
        "P1_channel2_raises_exact_on_both_arms": {
            "hit": bool(raises), "exact_delta_pp_per_arm": dpp, "exact_on_common_44": d_exact, "basis": basis44},
        "P2_channel2_raises_agreement_and_wrong_MORE_than_exact": {
            "hit": bool(aw_delta_pp > mean_exact_delta_pp), "aw_delta_pp": aw_delta_pp,
            "mean_exact_delta_pp": mean_exact_delta_pp, "aw_bare_on_44": aw_b, "aw_ctx": aw_c, "basis": basis44},
    }
    nk = {f"{a}|{c}": len(nikud_rows(recs, a, c)) for a in ARMS for c in CHANNELS}
    res["sign_predictions"]["P3_nikud_on_at_most_3_rows_in_every_cell"] = {
        "hit": all(v <= 3 for v in nk.values()), "rows_with_nikud_marks_per_cell": nk,
        "nikud_only_class_per_cell": {k: ex[k]["nikud_only"] for k in ex}}
    res["falsifiers"]["F1_ctx_raises_exact_AND_lowers_agreement_and_wrong"] = {
        "fired": bool(raises and aw_c < aw_b), "exact_delta_pp_per_arm": dpp,
        "agreement_and_wrong_bare_on_44": aw_b, "agreement_and_wrong_ctx": aw_c, "basis": basis44}
    ob = pct(ex["opus_bare"]["exact"], ex["opus_bare"]["n"])
    res["falsifiers"]["F2_opus_bare_exact_over_80"] = {"fired": bool(ob is not None and ob > 80),
                                                        "measured_pct": ob}
    res["falsifiers"]["F3_either_arm_nikud_on_more_than_3_rows"] = {
        "fired": any(v > 3 for v in nk.values()), "rows_with_nikud_marks_per_cell": nk}
    gaps = {"bare": None, "context": None}
    for ch, (a, b) in (("bare", ("opus_bare", "qwen_bare")), ("context", ("opus_ch2", "qwen_ch2"))):
        pa, pb = pct(ex[a]["exact"], ex[a]["n"]), pct(ex[b]["exact"], ex[b]["n"])
        gaps[ch] = None if pa is None or pb is None else round(abs(pa - pb), 1)
    res["falsifiers"]["F4_qwen_matches_opus_within_5pp"] = {
        "fired": all(g is not None and g <= 5 for g in gaps.values()), "abs_gap_pp": gaps,
        "rule": "fired only if within 5pp in BOTH channels"}
    res["agreement"] = ar
    res["registered_agreement_and_wrong"] = {
        ch: {"registered": P["agreement_and_wrong"][k], "measured_n": len(ar[ch]["agreement_and_wrong"])}
        for ch, k in (("bare", "bare"), ("context", "ch2"))}
    return res


def populations(pred):
    pops = pred["basis"]["populations_reported_separately"]
    return {k: set(v["ids"]) for k, v in pops.items()}


def tally_tables(recs, pred):
    pops = populations(pred)
    out = {"all": {}, "populations": {}}
    for arm in ARMS:
        for ch in CHANNELS:
            sub = [r for r in recs if r["arm"] == arm and r["channel"] == ch]
            out["all"][f"{arm}|{ch}"] = {"primary": tally(sub), "secondary": tally(sub, which="class_secondary")}
    for pn, ids in pops.items():
        out["populations"][pn] = {"n_ids": len(ids), "cells": {}}
        for arm in ARMS:
            for ch in CHANNELS:
                sub = [r for r in recs if r["arm"] == arm and r["channel"] == ch]
                out["populations"][pn]["cells"][f"{arm}|{ch}"] = {
                    "primary": tally(sub, ids), "secondary": tally(sub, ids, "class_secondary")}
    return out


# ------------------------------------------------------------------------------------------- output
def md_report(header, run_sha, tables, ev, nik, recs, prov):
    L = [f"# SCORE45 {run_sha}", "",
         "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).", ""]
    if prov:
        L += [f"**PROVISIONAL**: {prov}", ""]
    L += [f"calls {header['call_count']}  retries {header['retry_total']}  cost ${header['cost_usd_measured']}  "
          f"prediction {header['prediction_sha16']}  set_digest {header['set_digest']}", "",
          "## Tallies (primary = in-crop signature; secondary = signature_full)", "",
          "| arm | channel | basis | exact | nikud_only | wrong | abstain | error | n |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in tables["all"].items():
        a, c = k.split("|")
        for b in ("primary", "secondary"):
            t = v[b]
            L.append(f"| {a} | {c} | {b} | {t['exact']} | {t['nikud_only']} | {t['wrong']} | {t['abstain']} | {t['error']} | {t['n']} |")
    L += ["", "Every nikud_only outcome is the MODEL adding points: 0 of 45 signed strings carry nikud.", "",
          "## Registered numbers (exact_in_crop)", ""]
    for k, v in ev["registered_numbers"].items():
        # The JSON carries `delta_comparable` and a `denominator_note`; the markdown used to print
        # a signed delta regardless, so the report asserted a comparison its own data denied. A
        # prediction registered over 45 spans and a run that read 41 do not share a denominator,
        # and the arithmetic difference of two rates over different populations is not a delta.
        head = (f"- {k}: registered {v['registered_pct']}% ({v['registered_n']}), "
                f"measured {v['measured_pct']}% ({v['measured_n']})")
        if v["delta_comparable"]:
            L.append(head + f", delta {v['delta_pp']:+} pp (no band, no verdict)")
        else:
            L.append(head + f", **NOT COMPARABLE** -- {v['denominator_note']}")
    L += ["", "## Sign / count predictions (hit or missed)", ""]
    for k, v in ev["sign_predictions"].items():
        L.append(f"- {k}: **{'hit' if v['hit'] else 'missed'}** -- {json.dumps({x: y for x, y in v.items() if x != 'hit'}, ensure_ascii=False)}")
    L += [""]
    for ch, v in ev["registered_agreement_and_wrong"].items():
        L.append(f"- agreement_and_wrong {ch}: registered {v['registered']['n']}/{v['registered']['of']}, measured {v['measured_n']}")
    L += ["", "## Falsifiers", ""]
    for k, v in ev["falsifiers"].items():
        L.append(f"- {k}: **{'FIRED' if v['fired'] else 'not fired'}** -- {json.dumps({x: y for x, y in v.items() if x != 'fired'}, ensure_ascii=False)}")
    L += ["", "## Agreement and wrong", ""]
    for ch, v in ev["agreement"].items():
        L.append(f"- {ch}: agreement_and_wrong {v['agreement_and_wrong']}; both_wrong_disagree {v['both_wrong_disagree']}")
    L += ["", "## Subpopulations (primary; exact/nikud_only/wrong/abstain/error)", "",
          "`n ids` is the population the LOCK named; the `of N` on each cell is how many of them "
          "this run actually read. Where they differ, law 8 refused the difference at send -- it is "
          "not an abstention and not a missing read. A population showing `of 0` was scored over "
          "nothing and this report says nothing about it.", ""]
    for pn, v in tables["populations"].items():
        L.append(f"### {pn} (n ids {v['n_ids']})")
        for k, c in v["cells"].items():
            t = c["primary"]
            s = c["secondary"]
            L.append(f"- {k}: {t['exact']}/{t['nikud_only']}/{t['wrong']}/{t['abstain']}/{t['error']} of {t['n']}  (secondary {s['exact']}/{s['nikud_only']}/{s['wrong']}/{s['abstain']}/{s['error']})")
    L += ["", f"## p245:n1", f"Channel 2 absent. {ABSENT_BASIS}", "",
          "## Flags", f"- median output tokens per arm: {json.dumps(nik['median_out_tokens'])}; OUT_TOKEN_FLAG {OUT_TOKEN_FLAG}; flagged: {nik['out_token_flagged']}",
          "", "## What this does NOT solve", ""]
    # DERIVED, not typed. These two sentences carried "n=45" and "the 178-call run" from the days
    # when nothing was refused; the executed run read fewer. A disclaimer that misstates the size
    # of what it disclaims is worse than none, because a reader calibrates on it.
    _n_read = len({r["span_id"] for r in recs})
    _n_calls = len(recs)
    _emptied = sorted(pn for pn, v in tables["populations"].items()
                      if v["n_ids"] and not any(c["primary"]["n"] for c in v["cells"].values()))
    L += [f"- n={_n_read} spans in {_n_calls} calls, over a population that is no longer the hard "
          f"one the lock describes (see the subpopulation note); per-row differences between arms "
          f"are not explained here, and no per-row prediction was registered.",
          "- The standard is the signed verdict. Six of twenty earlier signed truths were later found wrong the same way; a mismatch here can be the signature, not the read.",
          "- Context-channel gains cannot be told apart from canonical-verse recall by this run; no blank-crop control was run.",
          f"- {_n_calls} calls, a single draw per cell at temperature 0; no null replicate was run, "
          f"so a delta smaller than the null spread is not evidence. The channel-2 contrast moves "
          f"5 rows of {len({r['span_id'] for r in recs if r['channel'] == 'context'})}; nothing "
          f"here bounds the null.",
          "- Nothing here promotes any arm to a production path."]
    if _emptied:
        L += [f"- {len(_emptied)} of the lock's populations were scored over ZERO rows "
              f"({', '.join(_emptied)}): law 8 refused every member. No statement in this report "
              f"is evidence about them."]
    L += [""]
    return "\n".join(L)


def evaluate_blank(recs, lock, floored):
    """Score the control against its own registered lock, in the order its rule 1 fixes.

    `lock` is the lock FILE's contents, not blank45's live module: what was registered is what the
    content-addressed artifact says was registered.  `floored` is the committed result of the run
    whose rates this puts a floor under, so rule 3's citation strings are derived from that run's
    own tallies rather than typed.

    Nothing here re-scores a read.  No stored row is touched and no rate in run `floors_run` is
    recomputed; what this produces is the floor each of those four rates must be cited against.
    """
    cells, exact_ctx_ids = {}, {}
    for arm in ARMS:
        for ch in CHANNELS:
            k = f"{arm}|{ch}"
            sub = [r for r in recs if r["arm"] == arm and r["channel"] == ch]
            t = tally(sub)
            reg = lock["registered_cells"][k]
            st = floored["tallies"]["all"][k]["primary"]
            bounds = {}
            for name in ("abstain_min", "abstain_max", "exact_min", "exact_max"):
                if name not in reg:
                    continue
                m = t["abstain" if name.startswith("abstain") else "exact"]
                # RULE 5: a missed prediction is reported as a miss, on the same denominator.  No
                # band is widened here and no bound is dropped for being inconvenient.
                bounds[name] = {"registered": reg[name], "measured": m,
                                "hit": bool(m >= reg[name] if name.endswith("_min") else m <= reg[name])}
            cells[k] = {
                # RULE 1: abstention is the FIRST key, not just the first paragraph.
                "abstain": t["abstain"],
                "abstain_is_zero": t["abstain"] == 0,
                # RULE 8: nikud_only is an answer given without pixels, and is never in the floor.
                "answered_without_pixels": t["exact"] + t["nikud_only"] + t["wrong"],
                "nikud_only": t["nikud_only"],
                "exact_floor": t["exact"],
                "n": t["n"],
                "registered_n": reg["n"],
                "same_denominator": t["n"] == reg["n"],
                "bounds": bounds,
                "measured_on_real_pixels": {"exact": st["exact"], "n": st["n"],
                                            "abstain": st["abstain"], "run": lock["floors_run"]},
                # RULE 3: the only form in which that rate may be quoted from now on.
                "citation": "%d/%d (floor %d/%d)" % (st["exact"], st["n"], t["exact"], t["n"]),
            }
            if ch == "context":
                exact_ctx_ids[arm] = {r["span_id"] for r in sub if r["class_primary"] == "exact"}
    chk(len(cells) == 4, "the control has four cells")
    both = sorted(exact_ctx_ids[ARMS[0]] & exact_ctx_ids[ARMS[1]])

    def ex(a, c):
        return cells[f"{a}|{c}"]["exact_floor"]

    claims = {s["id"]: s["claim"] for s in lock["registered_signs"]}
    chk(tuple(sorted(claims)) == BLANK_SIGNS, "the lock's signs are not the four this scores")
    signs = {
        "D1": {"hit": all(ex(a, "context") > ex(a, "bare") for a in ARMS),
               "per_arm": {a: {"bare": ex(a, "bare"), "context": ex(a, "context")} for a in ARMS}},
        "D2": {"hit": any(c["abstain"] > 0 for c in cells.values()),
               "abstain_by_cell": {k: c["abstain"] for k, c in cells.items()}},
        "D3": {"hit": any(ex(a, "context") >= 2 for a in ARMS),
               "exact_context_by_arm": {a: ex(a, "context") for a in ARMS}},
        "D4": {"hit": len(both) >= 3, "exact_context_on_both_arms": both},
    }
    for k, v in signs.items():
        v["hit"] = bool(v["hit"])
        v["claim"] = claims[k]
    return {
        # RULE 1 again, as the record's own first key: whatever a reader opens this with, the
        # abstention counts are what they see before any accuracy number.
        "rule_1_abstention_first": {k: cells[k]["abstain"] for k in sorted(cells)},
        "cells": cells,
        "signs": signs,
        # RULE 2: an `exact` here is a fabrication witness, not a scoring event.  Each (span, arm)
        # listed is struck from the BARE channel's read-evidence for that run.
        "fabrication_witnesses_bare": {
            f"{a}|bare": sorted(r["span_id"] for r in recs if r["arm"] == a
                                and r["channel"] == "bare" and r["class_primary"] == "exact")
            for a in ARMS},
        # RULE 4, and PROVISIONAL at one draw per span.
        "no_pixel_recoverable": {
            "ids": both,
            "status": "PROVISIONAL -- one draw per span at temperature 0; a span that lands here "
                      "once has not been shown to land here reliably",
            "meaning": "the Latin note alone, with no span pixels, was enough for both arms to "
                       "produce the signed string.  These spans' context-channel `exact` in run "
                       "%s is not evidence about reading." % lock["floors_run"]},
        "not_rescored": "run %s is not re-scored by this control and no stored row was touched; "
                        "its four rates keep their measured values and gain a floor"
                        % lock["floors_run"],
        "scored_against": lock["prediction_sha16"],
    }


def md_blank_report(header, run_sha, tables, evb, nik, recs, prov):
    bc = header["blank_control"]
    L = [f"# BLANK45 {run_sha} -- blank-crop CONTROL for run {bc['floors_run']}", "",
         "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).", "",
         "**This is a control, not a read.** Every call in this run posted a uniform-255 rectangle "
         "of the span crop's own size and mode in place of the crop. Nothing below is a reading "
         "accuracy, and nothing here re-scores "
         f"run {bc['floors_run']}: its four rates keep their measured values and gain a floor.", ""]
    if prov:
        L += [f"**PROVISIONAL**: {prov}", ""]
    ap = bc["contact_sheet_approval"]
    L += [f"calls {header['call_count']}  retries {header['retry_total']}  "
          f"cost ${header['cost_usd_measured']}  lock {bc['blank_prediction_sha16']}  "
          f"cut {bc['cut_digest']}  sheet {bc['contact_sheet_digest']} "
          f"(approved by {ap.get('by')} on {ap.get('on')})  "
          f"payload identity {header['payload_identity_digest']} "
          f"!= {bc['floors_run']}'s {bc['scored_payload_digest']}", "",
          "## 1. Abstention, read first (rule 1)", "",
          "| arm | channel | abstain | answered without pixels | nikud_only | n |",
          "|---|---|---|---|---|---|"]
    for k in sorted(evb["cells"]):
        a, c = k.split("|")
        v = evb["cells"][k]
        L.append(f"| {a} | {c} | {v['abstain']} | {v['answered_without_pixels']} | "
                 f"{v['nikud_only']} | {v['n']} |")
    L += [""]
    zero = [k for k, v in evb["cells"].items() if v["abstain_is_zero"]]
    if zero:
        L += [f"**{len(zero)} of 4 cells abstained ZERO times with no pixels to read** "
              f"({', '.join(sorted(zero))}). In those cells every answer was produced from a white "
              f"rectangle, so the exact-rate below is a fabrication rate, not a floor on reading.", ""]
    else:
        L += ["Every cell abstained at least once, so each arm has some `nothing here` channel. "
              "What follows is how often it failed to use it.", ""]
    L += ["## 2. The floors, and how those four rates must be cited from now on (rule 3)", "",
          "| arm | channel | real pixels | blank floor | cite as |", "|---|---|---|---|---|"]
    for k in sorted(evb["cells"]):
        a, c = k.split("|")
        v = evb["cells"][k]
        m = v["measured_on_real_pixels"]
        L.append(f"| {a} | {c} | {m['exact']}/{m['n']} | {v['exact_floor']}/{v['n']} | "
                 f"`{v['citation']}` |")
    L += ["", "Rule 3: each of those four rates may be quoted only in the `measured/n (floor f/n)` "
              "form in the last column. A rate cited without its floor is a rate cited against "
              "nothing.", "",
          "## 3. Registered cells, hit or missed (rule 5)", ""]
    for k in sorted(evb["cells"]):
        for name, b in sorted(evb["cells"][k]["bounds"].items()):
            L.append(f"- {k} {name}: registered {b['registered']}, measured {b['measured']} -- "
                     f"**{'hit' if b['hit'] else 'MISSED'}**")
        v = evb["cells"][k]
        if not v["same_denominator"]:
            L.append(f"- {k}: **denominator moved** -- registered over {v['registered_n']}, "
                     f"measured over {v['n']}; these bounds are not comparable")
    L += ["", "No band above was widened after the numbers were seen, and no bound was dropped. A "
              "miss is a miss on the registered denominator.", "",
          "## 4. Registered signs", ""]
    for k in sorted(evb["signs"]):
        v = evb["signs"][k]
        rest = {x: y for x, y in v.items() if x not in ("hit", "claim")}
        L.append(f"- **{k} {'hit' if v['hit'] else 'MISSED'}** -- {v['claim']}")
        L.append(f"  - {json.dumps(rest, ensure_ascii=False)}")
    L += ["", "## 5. Fabrication witnesses in the bare channel (rule 2)", ""]
    for k, ids in sorted(evb["fabrication_witnesses_bare"].items()):
        if ids:
            L.append(f"- {k}: {len(ids)} span(s) returned the signed string from a white rectangle "
                     f"-- {', '.join(ids)}. Each is struck from that arm's bare-channel "
                     f"read-evidence in run {bc['floors_run']}: a correct string produced without "
                     f"pixels is not a read.")
        else:
            L.append(f"- {k}: none. No span's signed string came back from a white rectangle in "
                     f"this channel.")
    npr = evb["no_pixel_recoverable"]
    L += ["", "## 6. Spans recoverable without pixels (rule 4)", "",
          f"**{len(npr['ids'])} span(s)**, {npr['status']}.", "", npr["meaning"], ""]
    if npr["ids"]:
        L += ["", "| span | signature |", "|---|---|"]
        sigs = {r["span_id"]: r["signature"] for r in recs}
        for sid in npr["ids"]:
            L.append(f"| {sid} | `{sigs.get(sid, '')}` |")
    L += ["", "## 7. What this control cannot do", "",
          "Written before the run, in the lock, and not edited after seeing the numbers:", ""]
    for c in bc["cannot_do"]:
        L.append(f"- {c}")
    L += ["", "## 8. Raw tallies (descriptive only)", "",
          "| arm | channel | basis | exact | nikud_only | wrong | abstain | error | n |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k, v in tables["all"].items():
        a, c = k.split("|")
        for b in ("primary", "secondary"):
            t = v[b]
            L.append(f"| {a} | {c} | {b} | {t['exact']} | {t['nikud_only']} | {t['wrong']} | "
                     f"{t['abstain']} | {t['error']} | {t['n']} |")
    L += ["", f"Median output tokens: {json.dumps(nik['median_out_tokens'], ensure_ascii=False)}.",
          "", "## 9. Limits of this document", "",
          "- A floor is a floor on THIS population at ONE draw per cell. It bounds the prior, not "
          "the variance.",
          "- The control ablates the image channel only. The channel-2 Latin text was NOT ablated "
          "in the context cells, which is the point of those cells and the reason the two cells "
          "are never pooled.",
          f"- Every number here is about run {bc['floors_run']}'s population of "
          f"{header['call_count']} calls. Spans law 8 refused have no floor because they have no "
          f"read.",
          "- Nothing here promotes or demotes an arm, and nothing here is an ADR.", ""]
    return "\n".join(L)


def rescore(run_sha, attempt_sfx=""):
    """Rebuild the report from stored reads. No network, no key, no new reads, no clobber.

    The reads are what cost money; the report is a pure function of them plus the lock. Without
    this, correcting a sentence in a published report means re-spending or leaving the wrong
    sentence in place -- and the second is what actually happens.

    The recomputed tallies are asserted EQUAL to the stored ones. That is not a check of the
    scorer (same function, so it would agree by construction); it is a check of this path -- that
    it loaded the right reads file, kept every row, and split arm and channel the same way. A
    rescore that quietly dropped rows would otherwise publish a smaller run under the same sha.
    """
    sheet, pred = load_inputs()
    src = A / f"score45_reads_{run_sha}{attempt_sfx}.jsonl"
    old_p = A / f"SCORE45_{run_sha}{attempt_sfx}.json"
    # A blank-crop control is not rescorable by this path: `evaluate` below scores the
    # scoring45 lock, whose registered numbers are about reading real pixels.  The stems
    # already differ, so this would fail on a missing file -- it refuses by NAME instead, so
    # the reader is told why rather than left to read "no reads file" as a lost run.
    chk(not (A / f"BLANK45_{run_sha}{attempt_sfx}.json").exists(),
        f"{run_sha} is a blank-crop CONTROL, not a read: --rescore would score it against the "
        f"scoring45 prediction lock, which registers numbers about reading pixels")
    chk(src.exists(), f"no reads file for {run_sha}{attempt_sfx}: {src.name}")
    chk(old_p.exists(), f"no stored run json for {run_sha}{attempt_sfx}: {old_p.name}")
    recs = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    old = json.loads(old_p.read_text(encoding="utf-8"))
    chk(old["run_sha16"] == run_sha, "the stored json names a different run_sha16")
    tables = tally_tables(recs, pred)
    chk(tables["all"] == old["tallies"]["all"],
        "rescored tallies differ from the stored run: this path is not faithful")
    chk(len(recs) == old["header"]["call_count"],
        f'reads file holds {len(recs)} rows, header says {old["header"]["call_count"]}')
    ev = evaluate(recs, pred)
    chk(ev["sign_predictions"].keys() == old["evaluation"]["sign_predictions"].keys(),
        "rescored evaluation has different predictions than the stored run")
    hdr = dict(old["header"], rescored_from=old_p.name,
               rescore_note="report text rebuilt from the stored reads; no call was made and no "
                            "class was recomputed from pixels")
    out = dict(old, header=hdr, tallies=tables, evaluation=ev)
    md = md_report(hdr, run_sha, tables, ev, old["diagnostics"], recs,
                   old["header"].get("provisional_reason"))
    texts = {A / f"SCORE45_{run_sha}{attempt_sfx}_r2.json": json.dumps(out, ensure_ascii=False, indent=1) + "\n",
             A / f"SCORE45_{run_sha}{attempt_sfx}_r2.md": md}
    for pth, t in texts.items():
        for h in FORBIDDEN_HOSTS:
            chk(h not in t, f"forbidden host in record {pth.name}")
    for pth, t in texts.items():
        write_new(pth, t)
    print(f"rescored {run_sha}{attempt_sfx} from {len(recs)} stored reads; wrote _r2; "
          f"checks observed: {CHECKS}")
    return 0


def write_new(path, text):
    chk(not path.exists(), f"refuse to clobber {path.name}; pass --attempt N (N>1) for a legitimate rerun")
    with open(path, "x", encoding="utf-8", newline="\n") as f:
        f.write(text)


# ---------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--rescore", metavar="RUN_SHA16",
                    help="rebuild the report from that run's stored reads; no network, no spend")
    ap.add_argument("--attempt", type=int, default=1,
                    help="rerun number; N>1 appends _a<N> to output stems so a rerun is not a clobber")
    ap.add_argument("--blank-crop", action="store_true",
                    help="run the BLANK-CROP CONTROL: post blank45's uniform-255 crops instead "
                         "of the real ones to measure the floor under run %s's four rates. "
                         "Reads nothing; scored against PREDICTIONS_blank45_%s.json; writes to "
                         "BLANK45_* stems." % (FLOORS_FOR, BLANK_PRED_SHA))
    a = ap.parse_args()
    blank = a.blank_crop
    if a.self_test:
        self_test()
        return 0
    if a.rescore:
        return rescore(a.rescore, "" if a.attempt <= 1 else f"_a{a.attempt}")
    dry = a.dry_run

    # GATE 1
    g0 = {"goatyard-laneB": git_state(REPO_B), "dr-voluminous": git_state(REPO_DR)}
    for k, v in g0.items():
        chk(v["dirty"] != "unknown", f"GATE 1: cannot read git state of {k}")
    dirty0 = {k: v["paths"] for k, v in g0.items() if v["dirty"]}
    if dry:
        chk(True, "GATE 1 evaluated (dry-run: reported, not fatal)")
    else:
        chk(not dirty0, f"GATE 1: tree dirty at start: {dirty0}")

    sheet, pred = load_inputs()

    # GATE 0 (law 8, ruling B(4); wired 2026-10-25 on A2's substrate commit 6243756).
    #
    # BEFORE any payload is built.  `on_refused="record"` rather than `"fail"`: this is a scorer, and
    # the four refused spans are owed a recorded `unscorable:input-refused` row.  Dropping them with
    # no record would make an absence that a later reader cannot tell from "never drawn".
    #
    # The sidecar is built by span_send_flags_build.py from the three signing records.  Read its
    # `basis_counts` before reading this gate as a clean bill: partial_in_crop is MEASURED on 20 of
    # the 74 spans and DEFAULTED on 54, and box_fault is unverified on 63.  The refused set is a
    # FLOOR over the spans somebody adjudicated, not a count over the population.
    _side = json.loads(SIDECAR.read_text(encoding="utf-8")) if SIDECAR.exists() else None
    _flags = SR.load_span_flags(str(SIDECAR))
    plan = SR.refuse_at_send([r["span_id"] for r in sheet["rows"]], _flags, on_refused="record")
    chk(plan.report["n"] + plan.report["n_refused"] == len(sheet["rows"]),
        "GATE 0: the send plan does not account for every sheet row")
    chk(all(r["reached_wire"] is False for r in plan.refused_records()),
        "GATE 0: a refused record claims it reached the wire")
    g2 = gate_prediction(pred)
    crop_shas = gate_crops(sheet)
    pay_sha = gate_payload_identity(sheet)
    chk(pred["scored_over"]["set_digest"] == SET_DIGEST, "prediction scored_over set_digest")
    calls = plan_calls(sheet, plan.sendable)
    # The crop directory and the licence are passed down explicitly from the flag.  Nothing
    # below defaults to CROPDIR, so the mode cannot be lost on the way to the encoder.
    if blank:
        lock_b, sheet_b, sent_shas, appr_b = gate_blank_inputs(sheet, dry)
        crop_dir, allow_fault = BLANKDIR, BLANK_FAULT
    else:
        lock_b, sheet_b, sent_shas, appr_b = None, None, crop_shas, None
        crop_dir, allow_fault = CROPDIR, None
    payloads = build_payloads(calls, crop_dir, allow_fault)
    gates_endpoint_aperture(payloads)
    gate_counts(payloads, sheet, plan)
    pay_digest = gate_ablation(payloads, sheet, crop_dir, sent_shas, blank)
    key = os.getenv(KEY_ENV)
    if dry:
        chk(True, "GATE 7 skipped in dry-run")
    else:
        chk(bool(key), f"GATE 7: {KEY_ENV} is not set")

    header = {"kind": "blank45_control" if blank else "score45_run",
              "page_convention": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)",
              "git_start": g0, "prediction_sha16": g2["prediction_sha16"], "sheet_payload_sha16": pay_sha,
              "set_digest": SET_DIGEST, "crop_sha16_sent": {k: sent_shas[k] for k in sorted(sent_shas)},
              "payload_identity_digest": pay_digest,
              "arms": ARMS, "channels": CHANNELS, "call_count": len(payloads),
              "predicted_request_sha16_before_send": sorted(p["request_sha16"] for p in payloads),
              "predicted_request_sha16_note": "A PREDICTION of what would be sent, not a record of it.  The reasoning ladder rebuilds the body at send time, so the authoritative value is each row's request_sha16 (the sha of the bytes actually posted).  Never read this list as sent.",
              "refusal": plan.report,
              "refusal_law": ("law 8 / ruling B(4): a span with a ratified geometry fault is never "
                              "read. Refused spans are recorded `%s` with reached_wire false and "
                              "are absent from every payload." % SR.REFUSAL_CLASS),
              "refusal_sidecar": {"path": str(SIDECAR), "self_sha16": (_side or {}).get("self_sha16"),
                                  "basis_counts": (_side or {}).get("basis_counts"),
                                  "basis_warning": ("partial_in_crop is defaulted, not measured, on "
                                                    "the pass-1 spans; the refused set is a floor")},
              "ungated_call_count": UNGATED_CALLS,
              "crop_dir": str(crop_dir), "aperture": APERTURE, "max_tokens": MAX_TOKENS,
              "ch2_absent": {ABSENT: ABSENT_BASIS}, "attempt": a.attempt,
              "provider_policy": {
                  "no_retention_provider_filter": True,
                  "byok": "off",
                  "asserted_by": "Chris, relayed 2026-10-18",
                  "verifiable_via_api": False,
                  "basis": "account-level state asserted by Chris; this run neither sets nor "
                           "verifies it, and no response field can confirm it.  Recorded so a "
                           "later reader knows the claim and whose it is.",
              }}
    if blank:
        # The control's own provenance, all of it read out of the three content-addressed
        # artifacts rather than restated here: the lock is what was registered, and a header
        # that paraphrased it could drift from it.
        header.update(
            ablation=lock_b["ablation"],
            blank_control={
                "what": "the image channel is replaced by a uniform-255 rectangle of the "
                        "span crop's own size and mode; everything else is held constant.  "
                        "This measures a FLOOR and reads nothing.",
                "floors_run": FLOORS_FOR,
                "scored_payload_digest": SCORED_PAYLOAD_DIGEST,
                "blank_prediction_sha16": BLANK_PRED_SHA,
                "cut_digest": BLANK_CUT_DIGEST,
                "contact_sheet_digest": BLANK_SHEET_DIGEST,
                "contact_sheet_approval": appr_b,
                "fault_licensed": BLANK_FAULT,
                "gate_override": lock_b["gate_override"],
                "decision_rule": lock_b["decision_rule"],
                "cannot_do": lock_b["cannot_do"],
                "real_crop_sha16_replaced": {k: crop_shas[k] for k in sorted(crop_shas)},
            })
    run_sha = sha16_bytes(canon(header).encode("utf-8"))

    if dry:
        print("DRY-RUN: all gates but the key and the network.  Writes NOTHING.")
        print("ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).")
        if blank:
            _ap = appr_b
            print("MODE: BLANK-CROP CONTROL.  Posts uniform-255 crops, reads nothing, and "
                  "measures the floor under run %s." % FLOORS_FOR)
            print("gateB0 cut %s  lock %s  sheet %s (%d crops)"
                  % (BLANK_CUT_DIGEST, BLANK_PRED_SHA, BLANK_SHEET_DIGEST, sheet_b["n_crops"]))
            print("gateB0 approval: by=%r on=%r -- %s"
                  % (_ap.get("by"), _ap.get("on"),
                     "APPROVED" if _ap.get("by") else "NOT APPROVED: a real run refuses"))
            print("gateB1 %d payloads, every crop blank on disk per gate_outbound (%s), none "
                  "of them a real crop" % (len(payloads), BLANK_FAULT))
            print("gateB2 payload identity %s; run %s was %s -- the ablation moved it"
                  % (pay_digest, FLOORS_FOR, SCORED_PAYLOAD_DIGEST))
        else:
            print("MODE: read.  gateB2 payload identity %s == run %s (unregressed)"
                  % (pay_digest, FLOORS_FOR))
        for k, v in g0.items():
            print(f"gate1 {k}: head {v['head'][:10]} dirty={v['dirty']} n={v.get('n')} "
                  f"{'WOULD REFUSE a real run: ' + str(v['paths']) if v['dirty'] else ''}")
        print(f"gate2 prediction_sha16 {g2['prediction_sha16']}")
        print(f"gate3 45 crops match crop_sha16 and w/h  set_digest {SET_DIGEST}")
        print(f"gate4 channel2_payload_sha16 {pay_sha}")
        print(f"gate5/6 aperture {APERTURE}; host openrouter.ai; forbidden hosts absent; no A1_notebox")
        print(f"gate7 key: {'SET' if key else 'UNSET (expected in a dry-run)'}  [never printed]")
        print(f"gate8 no Hebrew in {sum(p['channel']=='context' for p in payloads)} channel-2 texts")
        print(f"gate0 law-8 refusal: n={plan.report['n']} n_refused={plan.report['n_refused']} "
              f"of {plan.report['n_population']}  refused={sorted(plan.report['refused'])}")
        print(f"gate0 sidecar basis (read this before trusting the gate): "
              f"{json.dumps((_side or {}).get('basis_counts'), ensure_ascii=False)}")
        print(f"gate9 calls {len(payloads)} = {len(ARMS)} x "
              f"({sum(p['channel'] == 'bare' for p in payloads) // len(ARMS)} bare + "
              f"{sum(p['channel'] == 'context' for p in payloads) // len(ARMS)} ctx); "
              f"ungated population {UNGATED_CALLS}; p245:n1 bare only")
        print(f"run_sha16 (of this header, before results) {run_sha}")
        for arm in ARMS:
            for ch in CHANNELS:
                n = sum(p['arm'] == arm and p['channel'] == ch for p in payloads)
                print(f"  {arm:28s} {ch:8s} n={n}  exact=_ nikud_only=_ wrong=_ abstain=_ error=_")
        for pn, ids in populations(pred).items():
            print(f"  population {pn}: {len(ids)} ids")
        print("  agreement_and_wrong bare=_ ctx=_   both_wrong_disagree bare=_ ctx=_")
        chk(True, "dry-run end")
        _pin = EXPECTED_CHECKS_BLANK_DRY if blank else EXPECTED_CHECKS_DRY
        _name = "EXPECTED_CHECKS_BLANK_DRY" if blank else "EXPECTED_CHECKS_DRY"
        print(f"checks: {CHECKS} ({_name} {_pin})")
        if _pin is None:
            print(f"{_name} is UNPINNED: pin it to the count above")
        elif CHECKS != _pin:
            raise AssertionError(f"CHECKS {CHECKS} != {_name} {_pin}")
        return 0

    # ---- real run: from here every abort writes nothing
    recs, consec, t_start = [], 0, time.time()
    for i, p in enumerate(payloads):
        rec = do_call(p, key)
        recs.append(rec)
        consec = consec + 1 if rec["class_primary"] == "error" else 0
        if consec >= CONSECUTIVE_FAIL_ABORT:
            raise RunFault(f"{CONSECUTIVE_FAIL_ABORT} consecutive failed items ending at {rec['span_id']}: {rec['error']}")
        print(f"[{i + 1}/{len(payloads)}] {rec['span_id']} {rec['arm']} {rec['channel']} {rec['class_primary']}", flush=True)
    chk(len(recs) == len(payloads), f"{len(payloads)} calls attempted (the gated plan), got {len(recs)}")
    chk(not any(r["span_id"] == ABSENT and r["channel"] == "context" for r in recs), "no p245:n1 ctx call")

    g1 = {"goatyard-laneB": git_state(REPO_B), "dr-voluminous": git_state(REPO_DR)}
    same = all(g0[k]["head"] == g1[k]["head"] and not g1[k]["dirty"] and not g0[k]["dirty"] for k in g0)
    prov = None if same else f"git moved or went dirty during the run: start {g0}, end {g1}"
    tables = tally_tables(recs, pred)
    if blank:
        # `evaluate` scores the scoring45 lock, whose registered numbers are predictions about
        # READING real pixels.  This run read none, so it is NOT RUN -- recorded with a cause,
        # because an absent evaluation and a failed one look the same to a later reader.
        ev = {"not_run": "evaluate() scores the scoring45 prediction lock, which registers "
                         "numbers about reading real pixels.  This run read no pixels.",
              "scored_against": BLANK_PRED_SHA}
        evb = evaluate_blank(recs, lock_b,
                             json.loads(FLOORS_FILE.read_text(encoding="utf-8")))
    else:
        ev = evaluate(recs, pred)
        evb = None
    meds = {a: statistics.median([r["out_tokens"] for r in recs if r["arm"] == a and r["out_tokens"] is not None] or [0])
            for a in ARMS}
    nik = {"median_out_tokens": meds, "out_token_flagged": [a for a, m in meds.items() if m > OUT_TOKEN_FLAG]}
    cost = round(sum(r["cost_usd"] or 0 for r in recs), 6)
    header.update(git_end=g1, retry_total=sum(r["retries"] for r in recs), cost_usd_measured=cost,
                  provisional=bool(prov), provisional_reason=prov, seconds=round(time.time() - t_start, 1))
    byid = {r["span_id"]: r for r in sheet["rows"]}
    pops = populations(pred)
    rows = []
    for sid in sorted(byid):
        r = byid[sid]
        row = {"span_id": sid, "page_file": r["page_file"], "page_printed": r["page_printed"],
               "crop_sha16_sent": sent_shas.get(sid),
               "signature": r["signature"], "signature_full": r["signature_full"],
               "populations": sorted(k for k, v in pops.items() if sid in v), "ch2_state": r["ch2_state"],
               "results": {f"{x['arm']}|{x['channel']}": {k: x[k] for k in ("hebrew", "class_primary", "class_secondary")}
                           for x in recs if x["span_id"] == sid}}
        if sid == ABSENT:
            row["ch2_absent_basis"] = ABSENT_BASIS
        if sid in plan.report["refused"]:
            # An empty `results` must not read as "no data, cause unknown".  The row says who
            # refused it and why, and that no call was made -- the record of a non-event.
            row["refused"] = plan.report["refused"][sid]
            row["class_primary"] = SR.REFUSAL_CLASS
            row["reached_wire"] = False
            row["refusal_basis"] = ((_side or {}).get("flags_by_span", {}).get(sid) or {}).get("basis")
            chk(not row["results"], f"{sid} is refused but carries read results")
        rows.append(row)
    out = {"header": header, "run_sha16": run_sha, "rows": rows, "tallies": tables, "evaluation": ev,
           "diagnostics": nik, "page_convention": header["page_convention"]}
    if blank:
        out["blank_control_evaluation"] = evb
    sfx = "" if a.attempt <= 1 else f"_a{a.attempt}"
    # Distinct stems, because a control that can be mistaken for a read is not a control.
    stem, lstem = ("BLANK45", "blank45") if blank else ("SCORE45", "score45")
    refused_rows = list(plan.refused_records())
    chk(len(refused_rows) == plan.report["n_refused"], "refused record count != n_refused")
    chk(not ({r["span_id"] for r in refused_rows} & {r["span_id"] for r in recs}),
        "a span is both refused and read")
    texts = {A / f"{lstem}_reads_{run_sha}{sfx}.jsonl": "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
             # Beside the read rows, never among them: these never reached the wire, and
             # folding them into the reads file would put never-sent rows in a scorer
             # denominator.
             A / f"{lstem}_refused_{run_sha}{sfx}.jsonl": "\n".join(json.dumps(r, ensure_ascii=False) for r in refused_rows) + "\n",
             A / f"{stem}_{run_sha}{sfx}.json": json.dumps(out, ensure_ascii=False, indent=1) + "\n",
             A / f"{stem}_{run_sha}{sfx}.md": (md_blank_report(header, run_sha, tables, evb, nik, recs, prov)
                                               if blank else
                                               md_report(header, run_sha, tables, ev, nik, recs, prov))}
    for pth, t in texts.items():
        chk(not pth.exists(), f"refuse to clobber {pth.name}; pass --attempt N (N>1) for a legitimate rerun")
        for h in FORBIDDEN_HOSTS:
            chk(h not in t, f"forbidden host in record {pth.name}")
    for pth, t in texts.items():
        write_new(pth, t)
    for pth in texts:
        chk("sk-or-" not in pth.read_text(encoding="utf-8"), f"key material in {pth.name}")
    print(f"checks observed: {CHECKS}")
    _pin = EXPECTED_CHECKS_BLANK if blank else EXPECTED_CHECKS
    _name = "EXPECTED_CHECKS_BLANK" if blank else "EXPECTED_CHECKS"
    if _pin is None:
        print(f"{_name} is unpinned: pin it to the observed count above")
    elif CHECKS != _pin:
        raise AssertionError(f"CHECKS {CHECKS} != {_name} {_pin}")
    print(f"wrote {run_sha} ({header['kind']}); cost ${cost}; provisional={bool(prov)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RunFault as e:
        print(f"RUN-LEVEL FAULT, nothing written: {e}", file=sys.stderr)
        sys.exit(3)
