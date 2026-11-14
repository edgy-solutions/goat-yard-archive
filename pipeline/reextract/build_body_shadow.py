"""build_body_shadow -- stage 2 of the 20-page body shadow run (PREDICTION_shadow_run_20p_20261108.md).

Reads the BODY of every stage-1 region that has rects, one guarded chunk at a time, through the
native Ollama /api/chat of endpoint C only (192.168.1.169:11434; ruling 2026-11-14: C FIT on the fitness
protocol, D UNFIT, the shadow run goes on ONE endpoint). Output is private data and goes
through build_verse_regions.validate_out_path (never inside a repo).

Record order in OUT.jsonl: run_header (written FIRST, before any model call), then one body_region
per (stage-1 region, file page) in --pages order, then run_summary. The whole file is written to
OUT.tmp and renamed to OUT only on a clean finish.

Before the header the model is unloaded (keep_alive:0, /api/ps verified), so the first call of the
run is the first call of a fresh load, and that call is always a canary.

Pinned options (addendum 2, 2026-11-14): every /api/chat call -- head canary, body canary, body read --
goes through PinnedClient, which adds PINNED_OPTIONS (seed, num_ctx, num_batch) and KEEP_ALIVE, so the
body payload equals the fitness protocol's OPTIONS exactly and the server never chooses a load-time
option (11-12 load 5: n_batch 1024 vs 512 under identical undeclared options). It records every reply's
load_duration: the first call must trigger the load (> RELOAD_S), no later call may (a mid-run reload
is a RunFault). The options actually sent are recorded in the summary (realized, not requested).

Prompt echo (decision a, Chris 2026-11-12): every reply is passed through body_read.strip_echo; the
stored text is the remainder, echo_stripped records the copies removed, an echo-only reply is the
item error `echo`.

Run-level fault (RunFault = HTTP 429/5xx/non-200/transport, CanaryFault, a degenerate or echo-only
body canary, a body canary whose echo-stripped text differs from batch 0's, or 3 consecutive item
errors): write OUT.fault.json with the cause, delete the temp file, exit 3,
write NO OUT. A rerun starts from the top; nothing is spliced. Item errors (empty / truncated /
degenerate output) are recorded and never retried.

Guard: verse_head_read.guard_crop refuses a chunk on clamped / blank / uniform (the lock's list);
its straddle / too_short / blank_band statuses are NOT refusals here -- they test a head crop's
padded margin, which an ink-tight body chunk never has (the first chunk starts on the first line's
top row), so applying them refuses every chunk. core_at_edge replaces the straddle test. The raw
non-ok status is kept on the chunk as guard_raw.

Exit codes: 0 clean, 2 refused before any call (host not C, bad input, OUT exists), 3 run fault.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import body_read as BR  # noqa: E402
import build_verse_regions as BVR  # noqa: E402
import endpoint_guard  # noqa: E402
import verse_head_read as VHR  # noqa: E402

EXPECTED_HOST = "192.168.1.169:11434"   # C only (ruling 2026-11-14)
PINNED_OPTIONS = {"seed": 0, "num_ctx": 16384, "num_batch": 512}
KEEP_ALIVE = "5m"
RELOAD_S = 1.0
CANARY_EVERY = 20
UNIT_KINDS = ("verse", "chapter_intro", "continuation_unanchored")
GUARD_REFUSALS = ("clamped", "blank", "uniform")
BODY_CANARY_PAGE = 90
BODY_CANARY_COL = "left"
CONSECUTIVE_ITEM_ERRORS = 3
HTTP_TIMEOUT_S = 30


class BodyCanaryFault(RuntimeError):
    """The body canary read was degenerate/empty/truncated/echo-only, or its echo-stripped text
    differs from batch 0's (Chris 2026-11-12, A5 folded into decision a): the endpoint is suspect,
    abort."""


def unload_model(client, base_url, model):
    """keep_alive:0 unload, then /api/ps must no longer list `model`. The only reset known to clear
    D's request-history state (2026-11-08). Returns the /api/ps listing after the unload."""
    root = base_url.rstrip("/")
    client.post(root + "/api/generate", json={"model": model, "keep_alive": 0}, timeout=120)
    ps = client.get(root + "/api/ps", timeout=HTTP_TIMEOUT_S).json()
    left = [m.get("name") for m in ps.get("models", [])]
    if model in left:
        raise BR.RunFault(f"unload failed: {model} still listed by /api/ps ({left})")
    return ps


class _RequestsClient:
    def __init__(self, base_url, model):
        self.base_url = base_url
        self.model = model

    def post(self, url, json=None, timeout=None):
        import requests
        return requests.post(url, json=json, timeout=timeout)

    def get(self, url, timeout=None):
        import requests
        return requests.get(url, timeout=timeout)


_dumps = json.dumps


class PinnedClient:
    """Wraps the run's client. Every /api/chat payload is sent with PINNED_OPTIONS and KEEP_ALIVE (a
    caller value that differs is a RunFault, never overridden). Every 200 /api/chat reply's load_duration
    is recorded: the first must exceed RELOAD_S (the unload-verified load is triggered by the run's first
    call), no later one may (a mid-run reload). A violation is kept in .fault and raised as RunFault."""

    def __init__(self, inner):
        self.inner, self.base_url, self.model = inner, inner.base_url, inner.model
        self.load_durations_s = []
        self.options_sent = []
        self.fault = None

    def _fail(self, msg):
        if self.fault is None:
            self.fault = msg
        raise BR.RunFault(msg)

    def get(self, url, timeout=None):
        return self.inner.get(url, timeout=timeout)

    def post(self, url, json=None, timeout=None):
        if not url.endswith("/api/chat"):
            return self.inner.post(url, json=json, timeout=timeout)
        opts = dict(json.get("options") or {})
        for k, v in PINNED_OPTIONS.items():
            if k in opts and opts[k] != v:
                self._fail(f"caller option {k}={opts[k]!r} conflicts with the pinned {v!r}")
            opts[k] = v
        if json.get("keep_alive", KEEP_ALIVE) != KEEP_ALIVE:
            self._fail(f"caller keep_alive {json.get('keep_alive')!r} conflicts with the pinned {KEEP_ALIVE!r}")
        sent = _dumps(opts, sort_keys=True)
        if sent not in self.options_sent:
            self.options_sent.append(sent)
        resp = self.inner.post(url, json=dict(json, options=opts, keep_alive=KEEP_ALIVE), timeout=timeout)
        if getattr(resp, "status_code", 200) == 200:
            n = len(self.load_durations_s)
            ld = resp.json().get("load_duration")
            if not isinstance(ld, (int, float)) or isinstance(ld, bool):
                self._fail(f"chat call {n}: reply carries no load_duration ({ld!r})")
            sec = ld / 1e9
            self.load_durations_s.append(round(sec, 3))
            if n == 0 and sec <= RELOAD_S:
                self._fail(f"chat call 0 did not trigger the load: load_duration {sec:.3f}s <= {RELOAD_S}s")
            if n > 0 and sec > RELOAD_S:
                self._fail(f"mid-run reload at chat call {n}: load_duration {sec:.3f}s > {RELOAD_S}s")
        return resp

    def load_trace(self):
        later = self.load_durations_s[1:]
        return {"chat_calls": len(self.load_durations_s),
                "first_load_s": self.load_durations_s[0] if self.load_durations_s else None,
                "max_later_load_s": max(later) if later else None, "fault": self.fault}


def make_client(base_url, model):
    return _RequestsClient(base_url, model)


def load_page_gray(volume_dir, file_page):
    return BVR.load_page_gray(volume_dir, file_page)


def png_sha256(volume_dir, file_page):
    path = Path(volume_dir) / f"page{file_page}_image1.png"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_stage1(path):
    """Stage-1 records in file order. (Programs read the JSONL; nothing prints it.)"""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def region_key(rec):
    """(file_page_first, col, y0): the head's col/y0, else the first rect's."""
    head = rec.get("head")
    if head:
        return [rec["file_page_first"], head.get("col"), head.get("word_y0", head.get("y0"))]
    r0 = rec["rects"][0]
    return [rec["file_page_first"], r0["col"], r0["box"][1]]


def build_units(stage1, pages):
    """[(stage1_line, record, [(rect_idx, rect), ...], file_page)] grouped by --pages order, in
    stage-1 record order within a page. A region spanning pages yields one unit per page."""
    units = []
    for fp in pages:
        for line_no, rec in enumerate(stage1):
            if rec.get("kind") not in UNIT_KINDS or not rec.get("rects"):
                continue
            rects = [(i, r) for i, r in enumerate(rec["rects"]) if r["file_page"] == fp]
            if rects:
                units.append((line_no, rec, rects, fp))
    return units


def crop_png_bytes(gray, box):
    from PIL import Image
    x0, y0, x1, y1 = box
    buf = io.BytesIO()
    Image.fromarray(gray[y0:y1, x0:x1]).save(buf, format="PNG")
    return buf.getvalue()


def chunk_guard(gray, box, rect_box):
    """None if the chunk may be sent, else the refusal reason. rect_box (the stage-1 rect the chunk
    was cut from) is required: core_at_edge judges edges on the rect's banding, never the chunk's."""
    H, W = gray.shape
    raw = VHR.guard_crop(gray, tuple(box), (H, W))
    if raw in GUARD_REFUSALS:
        return raw, raw
    if BR.core_at_edge(gray, box, rect_box):
        return "core_at_edge", raw
    return None, raw


def _emit(fh, rec):
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    fh.flush()


def build_arg_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage1", required=True)
    ap.add_argument("--volume-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--host", required=True)
    ap.add_argument("--model", default=VHR.DEFAULT_MODEL)
    ap.add_argument("--pages", type=int, nargs="+", required=True)
    ap.add_argument("--max-lines", type=int, default=BR.MAX_LINES)
    return ap


def _refuse(msg):
    print(f"REFUSED: {msg}", file=sys.stderr)
    return 2


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    t_start = time.monotonic()
    try:
        out_path = BVR.validate_out_path(args.out)
    except BVR.OutputPathRefused as e:
        return _refuse(str(e))
    tmp_path = Path(str(out_path) + ".tmp")
    fault_path = Path(str(out_path) + ".fault.json")
    if out_path.exists():
        return _refuse(f"{out_path} exists; never clobbered")

    # Host first: nothing is sent anywhere unless it resolves to endpoint C.
    base_url = endpoint_guard.resolve_ollama_base_url(args.host, purpose="build_body_shadow")
    if urlparse(base_url).netloc != EXPECTED_HOST:
        return _refuse(f"host resolves to {base_url!r}; endpoint C ({EXPECTED_HOST}) only")

    pages = list(args.pages)
    stage1 = read_stage1(args.stage1)
    units = build_units(stage1, pages)
    if not units:
        return _refuse("no stage-1 units on the requested pages")

    gray_cache = {}

    def load(fp):
        if fp not in gray_cache:
            g = load_page_gray(args.volume_dir, fp)
            if g is None:
                raise ValueError(f"page image missing for file_page {fp}")
            gray_cache[fp] = g
        return gray_cache[fp]

    # The body canary chunk: chunk 0 of the first verse region's rect on page 90, left column.
    canary_png = canary_n_lines = None
    for rec in stage1:
        if rec.get("kind") != "verse":
            continue
        hit = [r for r in (rec.get("rects") or [])
               if r["file_page"] == BODY_CANARY_PAGE and r["col"] == BODY_CANARY_COL]
        if hit:
            g = load(BODY_CANARY_PAGE)
            boxes, nls, _flag = BR.chunk_rect(g, hit[0]["box"], args.max_lines)
            reason, _raw = chunk_guard(g, boxes[0], hit[0]["box"])
            if reason is not None:
                raise ValueError(f"body canary chunk refused by the guard: {reason}")
            canary_png, canary_n_lines = crop_png_bytes(g, boxes[0]), nls[0]
            canary_box = list(boxes[0])
            break
    if canary_png is None:
        raise ValueError(f"no stage-1 verse region has a rect on page {BODY_CANARY_PAGE} "
                         f"column {BODY_CANARY_COL!r}: no body canary")

    client = PinnedClient(make_client(base_url, args.model))
    base_url, digest = VHR.resolve_and_check(args.host, args.model, client=client)
    ps_before = client.get(base_url.rstrip("/") + "/api/ps", timeout=HTTP_TIMEOUT_S).json()
    try:
        ps = unload_model(client, base_url, args.model)
    except BR.RunFault as e:
        return _refuse(str(e))

    repo_root = Path(__file__).resolve().parents[2]
    config = {
        "git_head": BVR.get_git_head(repo_root),
        "git_dirty": BVR.get_git_dirty(repo_root),
        "stage1_sha256": sha256_file(args.stage1),
        "prompt_sha256": sha256_text(BR.BODY_PROMPT),
        "model": args.model,
        "model_digest": digest,
        "max_lines": args.max_lines,
        "num_predict": BR.NUM_PREDICT,
        "png_sha256": {str(fp): png_sha256(args.volume_dir, fp)
                       for fp in sorted(set(pages) | {BODY_CANARY_PAGE})},
        "pages": pages,
        "host": base_url,
        "canary_every": CANARY_EVERY,
        "body_canary": {"file_page": BODY_CANARY_PAGE, "col": BODY_CANARY_COL, "box": canary_box},
        "guard_refusals": list(GUARD_REFUSALS),
        "echo_rule": "strip every leading BODY_PROMPT copy; echo-only = item error 'echo'; "
                     "body canary echo-only or not identical to batch 0 = BodyCanaryFault",
        "unloaded_before": True,
        "pinned_options": dict(PINNED_OPTIONS), "keep_alive": KEEP_ALIVE, "reload_s": RELOAD_S,
        "body_read_sha256": sha256_file(BR.__file__),
        "builder_sha256": sha256_file(__file__),
    }
    chash = BVR.config_hash(config)
    header = {"kind": "run_header", "tier": "best_effort", "config": config,
              "config_hash": chash, "api_ps_before_unload": ps_before, "api_ps": ps,
              "started_utc": BVR.now_utc_iso()}

    fh = open(tmp_path, "w", encoding="utf-8")
    _emit(fh, header)  # HEADER-WRITE: before the first model call

    counts = Counter()
    refusals = Counter()
    item_errors = Counter()
    canaries = []
    state = {"ref_sha": None}
    counter = VHR.ConsecutiveErrorCounter(limit=CONSECUTIVE_ITEM_ERRORS)

    def transport(fn, *a):
        try:
            return fn(*a)
        except (BR.RunFault, VHR.ConsecutiveReadErrorFault, VHR.CanaryFault):
            raise
        except Exception as e:  # a timeout or connection failure is a run fault, never an item
            raise BR.RunFault(f"transport failure: {type(e).__name__}: {e}")

    def canary(batch, at_read):
        try:
            head = VHR.run_canary(client, load, batch, at_read)  # CanaryFault aborts
        except VHR.CanaryFault:
            if client.fault:  # a load-trace fault inside a head crop is the run's fault, not a mismatch
                raise BR.RunFault(client.fault)
            raise
        res = transport(BR.read_chunk, client, canary_png)
        kept, n_echo, err = BR.classify_body_reply(res["text"], res["done_reason"], canary_n_lines)
        if err:
            raise BodyCanaryFault(f"body canary batch {batch}: {err}")
        sha = sha256_text(kept)
        if state["ref_sha"] is None:
            state["ref_sha"] = sha
        canaries.append({"batch": batch, "at_read": at_read, "identical": sha == state["ref_sha"],
                         "sha": sha, "raw_sha": sha256_text(res["text"] or ""),
                         "echo_stripped": n_echo, "head_ok": bool(head.get("ok"))})
        if sha != state["ref_sha"]:
            raise BodyCanaryFault(f"body canary batch {batch}: echo-stripped text differs from "
                                  f"batch 0 ({sha[:8]} vs {state['ref_sha'][:8]})")

    try:
        for line_no, rec, rects, fp in units:
            gray = load(fp)
            chunks = []
            for rect_idx, rect in rects:
                boxes, nls, flag = BR.chunk_rect(gray, rect["box"], args.max_lines)
                for ci, (box, nl) in enumerate(zip(boxes, nls)):
                    counts["chunks"] += 1
                    c = {"file_page": fp, "col": rect["col"], "rect_idx": rect_idx,
                         "chunk_idx": ci, "box": list(box), "n_lines": nl, "guard": "ok",
                         "guard_raw": None, "text": None, "sha256": None, "done_reason": None,
                         "eval_count": None, "error": None}
                    if flag:
                        c["flags"] = [flag]
                    reason, raw = chunk_guard(gray, box, rect["box"])
                    if raw != "ok":
                        c["guard_raw"] = raw
                    if reason is not None:
                        c["guard"] = f"guard_refused:{reason}"
                        refusals[reason] += 1
                        chunks.append(c)
                        continue
                    if counts["reads"] % CANARY_EVERY == 0:
                        canary(counts["reads"] // CANARY_EVERY, counts["reads"])
                    res = transport(BR.read_chunk, client, crop_png_bytes(gray, box))
                    counts["reads"] += 1
                    kept, n_echo, err = BR.classify_body_reply(res["text"], res["done_reason"], nl)
                    c["text"], c["done_reason"], c["eval_count"] = (
                        kept, res["done_reason"], res["eval_count"])
                    c["echo_stripped"] = n_echo
                    c["sha256"] = sha256_text(kept or "")
                    c["raw_sha256"] = sha256_text(res["text"] or "")
                    c["error"] = err
                    chunks.append(c)
                    if err:
                        item_errors[err] += 1
                        counter.record_error()  # 3 consecutive -> ConsecutiveReadErrorFault
                    else:
                        counter.record_success()
            usable = [c["text"] for c in chunks if c["guard"] == "ok" and not c["error"]]
            body_raw = "\n".join(usable)
            complete = bool(chunks) and len(usable) == len(chunks)
            _emit(fh, {
                "kind": "body_region", "tier": "best_effort", "config_hash": chash,
                "file_page": fp, "key": region_key(rec), "stage1_line": line_no,
                "stage1_kind": rec["kind"], "verse": rec.get("verse"),
                "head_status": rec.get("head_status"), "chunks": chunks,
                "body_raw": body_raw, "body_text": BR.join_wordbreaks(body_raw),
                "body_status": "complete" if complete else "incomplete"})
        n_ident = sum(1 for c in canaries[1:] if c["identical"])
        _emit(fh, {"kind": "run_summary", "tier": "best_effort", "config_hash": chash,
                   "counts": {"chunks": counts["chunks"], "reads": counts["reads"],
                              "guard_refusals": dict(refusals),
                              "item_errors": dict(item_errors),
                              "canary_batches": len(canaries),
                              "canary_identical": f"{n_ident}/{max(0, len(canaries) - 1)}",
                              "elapsed_s": round(time.monotonic() - t_start, 1)},
                   "canaries": canaries,
                   "options_sent": [json.loads(o) for o in client.options_sent],
                   "load_trace": client.load_trace()})
    except (BR.RunFault, VHR.ConsecutiveReadErrorFault, VHR.CanaryFault, BodyCanaryFault) as e:
        fh.close()
        os.remove(tmp_path)
        fault_path.write_text(json.dumps({
            "kind": "run_fault", "cause": str(e), "type": type(e).__name__,
            "config_hash": chash, "reads_before_fault": counts["reads"],
            "item_errors": dict(item_errors), "canaries": canaries,
            "options_sent": [json.loads(o) for o in client.options_sent],
            "load_trace": client.load_trace()}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print(f"RUN FAULT: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    except BaseException:
        # any other failure (missing page, bad record, ^C): leave nothing behind, then fail loud
        fh.close()
        os.remove(tmp_path)
        raise
    fh.close()
    os.replace(tmp_path, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
