"""build_body_shadow born-tests: a fake client, a synthetic stage-1 and synthetic page arrays served
through a monkeypatched loader. No network, no model, no private data.
Run: python test_build_body_shadow.py

EXPECTED_TESTS asserts the suite's OWN test count so a silently-dropped test fails the run.
"""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np

import body_read as BR
import build_body_shadow as BSB

EXPECTED_TESTS = 15

D_HOST = "192.168.1.169:11435"
PAGE_H, PAGE_W = 3500, 1000


def bars(g, box, n, pitch=20, thick=10):
    x0, y0, x1, y1 = box
    for i in range(n):
        t = y0 + 10 + i * pitch
        g[t:t + thick, x0 + 10:x1 - 10] = 0


def make_pages():
    pages = {fp: np.full((PAGE_H, PAGE_W), 255, np.uint8) for fp in (90, 91, 92, 126, 130)}
    # the two head-canary crops (verse_head_read.CANARY_CROPS): a bar well inside the pad margins
    pages[126][3390 + 30:3390 + 45, 100:800] = 0
    pages[130][3079 + 30:3079 + 45, 100:800] = 0
    bars(pages[90], (0, 100, 500, 300), 9)       # R0: 9 lines -> 3 chunks at max_lines 3
    bars(pages[90], (500, 350, 1000, 450), 4)    # R1 on p90 right: 2 chunks
    bars(pages[91], (0, 100, 500, 300), 5)       # R1 on p91 left: 2 chunks
    bars(pages[91], (500, 100, 1000, 200), 3)    # R2 chapter_intro: 1 chunk
    # p92 left (0,100,500,200) stays blank -> guard refusal (R3)
    return pages


def stage1_records():
    def rect(fp, col, box):
        return {"file_page": fp, "col": col, "box": list(box)}
    return [
        {"kind": "run_header", "config": {}},
        {"kind": "page", "file_page": 90},
        {"kind": "verse", "file_page_first": 90, "verse": [1], "head_status": "shipped",
         "head": {"col": "left", "y0": 90}, "rects": [rect(90, "left", (0, 100, 500, 300))]},
        {"kind": "verse", "file_page_first": 90, "verse": [2], "head_status": "shipped",
         "head": {"col": "right", "y0": 340},
         "rects": [rect(90, "right", (500, 350, 1000, 450)), rect(91, "left", (0, 100, 500, 300))]},
        {"kind": "chapter_intro", "file_page_first": 91, "verse": None,
         "head": {"col": "right", "y0": 90}, "rects": [rect(91, "right", (500, 100, 1000, 200))]},
        {"kind": "continuation_unanchored", "file_page_first": 92, "head": None,
         "rects": [rect(92, "left", (0, 100, 500, 200))]},
        {"kind": "region_without_rects", "file_page_first": 92, "rects": []},
    ]


class FakeResp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b


class FakeClient:
    base_url = "http://" + D_HOST
    model = BSB.VHR.DEFAULT_MODEL

    def __init__(self):
        self.log = []                 # ("get", url) | ("head",) | ("body", image_sha)
        self.body_calls = 0
        self.head_calls = 0
        self.header_seen_at_first_post = None
        self.tmp_path = None
        self.empty_from = None        # body call index from which replies are empty
        self.http_from = None         # (body call index, status)
        self.head_wrong_from = None   # head call index from which the canary mismatches
        self.canary_sha = None        # image sha whose reply varies per call (non-identical)
        self.degenerate_first = False

    def get(self, url, timeout=None):
        self.log.append(("get", url))
        if url.endswith("/api/tags"):
            return FakeResp({"models": [{"name": self.model, "digest": "digest-xyz"}]})
        return FakeResp({"models": []})

    def post(self, url, json=None, timeout=None):
        if self.header_seen_at_first_post is None:
            p = Path(self.tmp_path)
            first = p.read_text(encoding="utf-8").splitlines()[0] if p.exists() else ""
            self.header_seen_at_first_post = bool(first) and '"run_header"' in first
        msg = json["messages"][0]
        if msg["content"] == BR.BODY_PROMPT:
            idx = self.body_calls
            self.body_calls += 1
            sha = hashlib.sha256(msg["images"][0].encode()).hexdigest()
            self.log.append(("body", sha))
            if self.http_from and idx >= self.http_from[0]:
                return FakeResp({}, self.http_from[1])
            if self.degenerate_first and idx == 0:
                return FakeResp({"message": {"content": "12 34"}, "done_reason": "stop"})
            if self.empty_from is not None and idx >= self.empty_from:
                return FakeResp({"message": {"content": ""}, "done_reason": "stop"})
            text = f"Body {sha[:6]}"
            if sha == self.canary_sha:
                text += f" call{idx}"
            return FakeResp({"message": {"content": text}, "done_reason": "stop", "eval_count": 5})
        idx = self.head_calls
        self.head_calls += 1
        self.log.append(("head",))
        if self.head_wrong_from is not None and idx >= self.head_wrong_from:
            txt = "Ver. 99."
        else:
            txt = "Ver. 21." if idx % 2 == 0 else "Ver. 6."
        return FakeResp({"message": {"content": txt}, "done_reason": "stop"})


class Env:
    def __init__(self, stage1=None, max_lines=3, every=3):
        self.dir = Path(tempfile.mkdtemp(prefix="bbs_test_"))
        self.pages = make_pages()
        self.s1 = self.dir / "stage1.jsonl"
        recs = stage1 if stage1 is not None else stage1_records()
        self.s1.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
        self.out = self.dir / "out.jsonl"
        self.fake = FakeClient()
        self.fake.tmp_path = str(self.out) + ".tmp"
        self.max_lines = max_lines
        self.every = every
        self.saved = (BSB.make_client, BSB.load_page_gray, BSB.png_sha256, BSB.CANARY_EVERY)

    def run(self, pages=(91, 90, 92), host=D_HOST):
        BSB.make_client = lambda base_url, model: self.fake
        BSB.load_page_gray = lambda vd, fp: self.pages.get(fp)
        BSB.png_sha256 = lambda vd, fp: f"sha-page-{fp}"
        BSB.CANARY_EVERY = self.every
        argv = ["--stage1", str(self.s1), "--volume-dir", str(self.dir), "--out", str(self.out),
                "--host", host, "--pages", *[str(p) for p in pages],
                "--max-lines", str(self.max_lines)]
        return BSB.main(argv)

    def records(self):
        return [json.loads(l) for l in self.out.read_text(encoding="utf-8").splitlines() if l]

    def close(self):
        (BSB.make_client, BSB.load_page_gray, BSB.png_sha256, BSB.CANARY_EVERY) = self.saved
        shutil.rmtree(self.dir, ignore_errors=True)


def with_env(**kw):
    def deco(fn):
        def wrapper():
            env = Env(**kw)
            try:
                fn(env)
            finally:
                env.close()
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


@with_env()
def test_header_written_before_first_call(env):
    assert env.run() == 0
    assert env.fake.header_seen_at_first_post is True, "header must be on disk before the first POST"
    recs = env.records()
    h = recs[0]
    assert h["kind"] == "run_header" and h["tier"] == "best_effort" and h["config_hash"]
    c = h["config"]
    for k in ("git_head", "git_dirty", "stage1_sha256", "prompt_sha256", "model", "model_digest",
              "max_lines", "png_sha256", "pages", "host"):
        assert k in c, k
    assert c["model_digest"] == "digest-xyz" and c["pages"] == [91, 90, 92]
    assert c["prompt_sha256"] == hashlib.sha256(BR.BODY_PROMPT.encode()).hexdigest()
    assert recs[-1]["kind"] == "run_summary"


@with_env()
def test_guard_refusal_is_never_sent(env):
    assert env.run() == 0
    recs = env.records()
    blank = [r for r in recs if r["kind"] == "body_region" and r["stage1_kind"] == "continuation_unanchored"][0]
    assert blank["chunks"][0]["guard"] == "guard_refused:blank"
    assert blank["chunks"][0]["text"] is None and blank["body_status"] == "incomplete"
    # sent images: 8 non-refused chunks + one canary read per batch, nothing for the blank crop
    blank_png = BSB.crop_png_bytes(env.pages[92], blank["chunks"][0]["box"])
    import base64
    blank_sha = hashlib.sha256(base64.b64encode(blank_png)).hexdigest()
    sent = [e[1] for e in env.fake.log if e[0] == "body"]
    assert blank_sha not in sent
    n_canary = recs[-1]["counts"]["canary_batches"]
    assert len(sent) == 8 + n_canary, (len(sent), n_canary)
    assert recs[-1]["counts"]["guard_refusals"] == {"blank": 1}


@with_env()
def test_three_consecutive_empty_reads_is_run_fault(env):
    env.fake.empty_from = 1      # call 0 is the body canary; everything after is empty
    assert env.run() == 3
    assert not env.out.exists() and not Path(str(env.out) + ".tmp").exists()
    fault = json.loads(Path(str(env.out) + ".fault.json").read_text(encoding="utf-8"))
    assert "consecutive" in fault["cause"] and fault["item_errors"] == {"empty": 3}


@with_env()
def test_unexpected_failure_mid_run_leaves_nothing_behind(env):
    # page 92 missing: load() raises ValueError AFTER the header and the 91/90 reads
    del env.pages[92]
    try:
        env.run()
        assert False, "expected ValueError"
    except ValueError as e:
        assert "92" in str(e)
    assert not env.out.exists() and not Path(str(env.out) + ".tmp").exists()
    assert env.fake.body_calls > 0, "the failure must come after model calls to test the cleanup"


@with_env(every=100)
def test_two_empty_reads_are_item_errors_not_a_fault(env):
    env.fake.empty_from = None
    orig = env.fake.post
    state = {"n": 0}

    def post(url, json=None, timeout=None):
        if json["messages"][0]["content"] == BR.BODY_PROMPT:
            state["n"] += 1
            if state["n"] in (3, 6):      # call 1 is the canary; two non-consecutive empties among reads
                env.fake.body_calls += 1
                return FakeResp({"message": {"content": ""}, "done_reason": "stop"})
        return orig(url, json=json, timeout=timeout)
    env.fake.post = post
    assert env.run() == 0
    s = env.records()[-1]["counts"]
    assert s["item_errors"] == {"empty": 2}
    bad = [c for r in env.records() if r["kind"] == "body_region" for c in r["chunks"] if c["error"]]
    assert len(bad) == 2 and all(c["text"] == "" for c in bad)
    assert s["reads"] == 8, "an item error is never retried"


@with_env()
def test_head_canary_mismatch_at_batch0_aborts_before_any_read(env):
    env.fake.head_wrong_from = 0
    assert env.run() == 3
    assert env.fake.body_calls == 0 and not env.out.exists()
    fault = json.loads(Path(str(env.out) + ".fault.json").read_text(encoding="utf-8"))
    assert fault["type"] == "CanaryFault"


@with_env()
def test_head_canary_mismatch_at_later_batch_aborts(env):
    env.fake.head_wrong_from = 2     # batch 0 = head calls 0,1 pass; batch 1 mismatches
    assert env.run() == 3
    assert not env.out.exists()
    fault = json.loads(Path(str(env.out) + ".fault.json").read_text(encoding="utf-8"))
    assert fault["type"] == "CanaryFault" and "batch 1" in fault["cause"]
    assert fault["reads_before_fault"] == 3


@with_env()
def test_body_canary_byte_identity_is_recorded_and_not_an_abort(env):
    assert env.run() == 0
    s = env.records()[-1]
    # 8 reads, canary before reads 0, 3, 6 -> batches 0, 1, 2
    assert s["counts"]["canary_batches"] == 3 and s["counts"]["canary_identical"] == "2/2"
    assert [c["batch"] for c in s["canaries"]] == [0, 1, 2]
    assert all(c["identical"] for c in s["canaries"]) and len({c["sha"] for c in s["canaries"]}) == 1


@with_env()
def test_body_canary_mismatch_is_measured_not_an_abort(env):
    # the canary chunk is the first chunk of R0; learn its image sha from a first dry run
    assert env.run() == 0
    first_body = [e for e in env.fake.log if e[0] == "body"][0][1]
    env.out.unlink()
    env.fake.canary_sha = first_body
    env.fake.log, env.fake.body_calls, env.fake.head_calls = [], 0, 0
    env.fake.header_seen_at_first_post = None
    assert env.run() == 0
    s = env.records()[-1]
    assert s["counts"]["canary_identical"] == "0/2" and s["counts"]["canary_batches"] == 3
    assert [c["identical"] for c in s["canaries"]] == [True, False, False]


@with_env()
def test_degenerate_body_canary_aborts(env):
    env.fake.degenerate_first = True
    assert env.run() == 3
    assert not env.out.exists()
    fault = json.loads(Path(str(env.out) + ".fault.json").read_text(encoding="utf-8"))
    assert fault["type"] == "BodyCanaryFault" and "degenerate_no_latin" in fault["cause"]


@with_env()
def test_http_429_mid_run_is_run_fault(env):
    env.fake.http_from = (2, 429)
    assert env.run() == 3
    assert not env.out.exists() and not Path(str(env.out) + ".tmp").exists()
    fault = json.loads(Path(str(env.out) + ".fault.json").read_text(encoding="utf-8"))
    assert fault["type"] == "RunFault" and "429" in fault["cause"]


@with_env()
def test_non_D_host_refused_before_any_call(env):
    def boom(base_url, model):
        raise AssertionError("a client must not even be constructed for a non-D host")
    saved = BSB.make_client
    rc = None
    try:
        BSB.make_client = boom
        BSB.load_page_gray = lambda vd, fp: env.pages.get(fp)
        BSB.png_sha256 = lambda vd, fp: "x"
        rc = BSB.main(["--stage1", str(env.s1), "--volume-dir", str(env.dir), "--out", str(env.out),
                       "--host", "192.168.1.50:11434", "--pages", "90"])
    finally:
        BSB.make_client = saved
    assert rc == 2 and env.fake.log == []
    assert not env.out.exists() and not Path(str(env.out) + ".tmp").exists()


@with_env()
def test_closed_endpoint_E_is_refused(env):
    try:
        BSB.main(["--stage1", str(env.s1), "--volume-dir", str(env.dir), "--out", str(env.out),
                  "--host", "192.168.1.179", "--pages", "90"])
    except Exception as e:
        assert "179" in str(e) or "RESERVED" in str(e).upper() or "closed" in str(e).lower()
    else:
        raise AssertionError("the reserved endpoint must refuse")
    assert env.fake.log == [] and not env.out.exists()


@with_env()
def test_regions_spanning_pages_split_by_file_page(env):
    assert env.run(pages=(91, 90)) == 0
    regs = [r for r in env.records() if r["kind"] == "body_region"]
    # --pages order: page 91's units first (R1's p91 part, then R2), then page 90 (R0, R1's p90 part)
    assert [(r["file_page"], r["stage1_line"]) for r in regs] == [(91, 3), (91, 4), (90, 2), (90, 3)]
    r1_parts = [r for r in regs if r["stage1_line"] == 3]
    assert {c["file_page"] for r in r1_parts[:1] for c in r["chunks"]} == {91}
    assert {c["file_page"] for r in r1_parts[1:] for c in r["chunks"]} == {90}
    assert all(r["body_status"] == "complete" for r in regs)
    r0 = [r for r in regs if r["stage1_line"] == 2][0]
    assert [c["chunk_idx"] for c in r0["chunks"]] == [0, 1, 2] and r0["key"] == [90, "left", 90]
    assert r0["body_raw"] == "\n".join(c["text"] for c in r0["chunks"])


@with_env()
def test_out_exists_is_refused_and_untouched(env):
    env.out.write_text("keep", encoding="utf-8")
    assert env.run() == 2 and env.out.read_text(encoding="utf-8") == "keep"
    assert env.fake.log == []


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    if len(fns) != EXPECTED_TESTS:
        print(f"EXPECTED_TESTS mismatch: discovered {len(fns)}, expected {EXPECTED_TESTS}")
        raise SystemExit(1)
    p = f = 0
    for fn in fns:
        try:
            fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception:
            f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed")
    raise SystemExit(1 if f else 0)
