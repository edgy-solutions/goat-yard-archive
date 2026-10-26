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
EXPECTED_CHECKS = None      # UNPINNED 2026-10-25: the law-8 send gate changed the call count,
                            # so 668 (run 501ab577a18a6785, 178 calls) no longer describes this
                            # path.  A guessed total coerces reality; the next full run prints
                            # the observed count and this gets pinned to what it measured.
EXPECTED_CHECKS_DRY = 356        # dry-run, re-measured 2026-10-25 after the law-8 send gate: 16
                                 # fewer payloads (4 refused spans x 2 arms x 2 channels, less the
                                 # ctx call p245:n1 never had) means 32 fewer per-payload checks,
                                 # and the gate itself adds 6

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


def build_payloads(calls):
    out = []
    for arm, channel, r in calls:
        b64 = diag.b64_gated(CROPDIR / r["crop_file"], what="score45 crop", offnet=True)
        body, ctx = build_body(arm, r, channel, b64)
        _no_hebrew_outbound(body)
        chk(True, "no Hebrew in outbound body")
        if channel == "context":
            text = body["messages"][0]["content"][1]["text"]
            chk(not HEB.search(text), f"GATE 8 Hebrew in channel-2 text for {r['span_id']}")
            chk(ctx == _ctx(ctx), f"channel-2 string for {r['span_id']} is not already masked")
        out.append({"arm": arm, "channel": channel, "row": r, "body": body,
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


# ------------------------------------------------------------------------------------------ calling
def _post(body, key):
    return httpx.post(H.URL, headers={"Authorization": f"Bearer {key}",
                                      "content-type": "application/json"}, json=body, timeout=300)


def do_call(p, key):
    """One read.  Returns a record.  Raises RunFault on a 429 that survives retries."""
    arm, row = p["arm"], p["row"]
    img_b64 = p["body"]["messages"][0]["content"][0]["image_url"]["url"].split(",", 1)[1]
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
           "arm": arm, "channel": p["channel"], "request_sha16": sent_sha, "crop_sha16": row["crop_sha16"],
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
        L.append(f"- {k}: registered {v['registered_pct']}% ({v['registered_n']}), measured {v['measured_pct']}% ({v['measured_n']}), delta {v['delta_pp']:+} pp (no band, no verdict)")
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
    L += ["", "## Subpopulations (primary; exact/nikud_only/wrong/abstain/error)", ""]
    for pn, v in tables["populations"].items():
        L.append(f"### {pn} (n ids {v['n_ids']})")
        for k, c in v["cells"].items():
            t = c["primary"]
            s = c["secondary"]
            L.append(f"- {k}: {t['exact']}/{t['nikud_only']}/{t['wrong']}/{t['abstain']}/{t['error']} of {t['n']}  (secondary {s['exact']}/{s['nikud_only']}/{s['wrong']}/{s['abstain']}/{s['error']})")
    L += ["", f"## p245:n1", f"Channel 2 absent. {ABSENT_BASIS}", "",
          "## Flags", f"- median output tokens per arm: {json.dumps(nik['median_out_tokens'])}; OUT_TOKEN_FLAG {OUT_TOKEN_FLAG}; flagged: {nik['out_token_flagged']}",
          "", "## What this does NOT solve", "",
          "- n=45 over a deliberately hard population; per-row differences between arms are not explained here, and no per-row prediction was registered.",
          "- The standard is the signed verdict. Six of twenty earlier signed truths were later found wrong the same way; a mismatch here can be the signature, not the read.",
          "- Context-channel gains cannot be told apart from canonical-verse recall by this run; no blank-crop control was run.",
          "- The 178-call run is a single draw per cell at temperature 0; no null replicate was run, so a delta smaller than the null spread is not evidence.",
          "- Nothing here promotes any arm to a production path.", ""]
    return "\n".join(L)


def write_new(path, text):
    chk(not path.exists(), f"refuse to clobber {path.name}; pass --attempt N (N>1) for a legitimate rerun")
    with open(path, "x", encoding="utf-8", newline="\n") as f:
        f.write(text)


# ---------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--attempt", type=int, default=1,
                    help="rerun number; N>1 appends _a<N> to output stems so a rerun is not a clobber")
    a = ap.parse_args()
    if a.self_test:
        self_test()
        return 0
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
    payloads = build_payloads(calls)
    gates_endpoint_aperture(payloads)
    gate_counts(payloads, sheet, plan)
    key = os.getenv(KEY_ENV)
    if dry:
        chk(True, "GATE 7 skipped in dry-run")
    else:
        chk(bool(key), f"GATE 7: {KEY_ENV} is not set")

    header = {"kind": "score45_run", "page_convention": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)",
              "git_start": g0, "prediction_sha16": g2["prediction_sha16"], "sheet_payload_sha16": pay_sha,
              "set_digest": SET_DIGEST, "crop_sha16_sent": {k: crop_shas[k] for k in sorted(crop_shas)},
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
              "crop_dir": str(CROPDIR), "aperture": APERTURE, "max_tokens": MAX_TOKENS,
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
    run_sha = sha16_bytes(canon(header).encode("utf-8"))

    if dry:
        print("DRY-RUN: all gates but the key and the network.  Writes NOTHING.")
        print("ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).")
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
        print(f"checks: {CHECKS} (EXPECTED_CHECKS_DRY {EXPECTED_CHECKS_DRY})")
        if CHECKS != EXPECTED_CHECKS_DRY:
            raise AssertionError(f"CHECKS {CHECKS} != EXPECTED_CHECKS_DRY {EXPECTED_CHECKS_DRY}")
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
    ev = evaluate(recs, pred)
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
    sfx = "" if a.attempt <= 1 else f"_a{a.attempt}"
    refused_rows = list(plan.refused_records())
    chk(len(refused_rows) == plan.report["n_refused"], "refused record count != n_refused")
    chk(not ({r["span_id"] for r in refused_rows} & {r["span_id"] for r in recs}),
        "a span is both refused and read")
    texts = {A / f"score45_reads_{run_sha}{sfx}.jsonl": "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
             # Beside the read rows, never among them: these never reached the wire, and
             # folding them into the reads file would put never-sent rows in a scorer
             # denominator.
             A / f"score45_refused_{run_sha}{sfx}.jsonl": "\n".join(json.dumps(r, ensure_ascii=False) for r in refused_rows) + "\n",
             A / f"SCORE45_{run_sha}{sfx}.json": json.dumps(out, ensure_ascii=False, indent=1) + "\n",
             A / f"SCORE45_{run_sha}{sfx}.md": md_report(header, run_sha, tables, ev, nik, recs, prov)}
    for pth, t in texts.items():
        chk(not pth.exists(), f"refuse to clobber {pth.name}; pass --attempt N (N>1) for a legitimate rerun")
        for h in FORBIDDEN_HOSTS:
            chk(h not in t, f"forbidden host in record {pth.name}")
    for pth, t in texts.items():
        write_new(pth, t)
    for pth in texts:
        chk("sk-or-" not in pth.read_text(encoding="utf-8"), f"key material in {pth.name}")
    print(f"checks observed: {CHECKS}")
    if EXPECTED_CHECKS is None:
        print("EXPECTED_CHECKS is unpinned: pin it to the observed count above")
    elif CHECKS != EXPECTED_CHECKS:
        raise AssertionError(f"CHECKS {CHECKS} != EXPECTED_CHECKS {EXPECTED_CHECKS}")
    print(f"wrote {run_sha}; cost ${cost}; provisional={bool(prov)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RunFault as e:
        print(f"RUN-LEVEL FAULT, nothing written: {e}", file=sys.stderr)
        sys.exit(3)
