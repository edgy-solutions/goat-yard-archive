"""body_read born-tests: synthetic arrays and inline strings only, a fake client, no network.
Run: python test_body_read.py

EXPECTED_TESTS asserts the suite's OWN test count so a silently-dropped test fails the run.
"""
import numpy as np

import body_read as BR

EXPECTED_TESTS = 14


def page45():
    """45 printed lines, 10 px tall, pitch 18 (8 px gaps), on a 300-px-wide page."""
    g = np.full((900, 300), 255, np.uint8)
    tops = [20 + i * 18 for i in range(45)]
    for t in tops:
        g[t:t + 10, 10:250] = 0
    return g, tops


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {
            "message": {"content": "Line one"}, "done_reason": "stop", "eval_count": 7}

    def json(self):
        return self._body


class FakeClient:
    base_url = "http://192.168.1.169:11435"
    model = "fake-model"

    def __init__(self, resp=None):
        self.resp = resp or FakeResp()
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        return self.resp


def test_chunk_rect_45_lines_three_chunks():
    g, tops = page45()
    box = (0, 10, 300, 880)
    boxes, nls, flag = BR.chunk_rect(g, box)
    assert flag is None and nls == [20, 20, 5], (nls, flag)
    assert len(boxes) == 3
    assert boxes[0][1] == 10 and boxes[-1][3] == 880
    # boundary 1: midpoint of the gap between line 19 (idx) bottom and line 20 top
    e1 = ((tops[19] + 10) + tops[20]) // 2
    e2 = ((tops[39] + 10) + tops[40]) // 2
    assert boxes[0][3] == e1 == boxes[1][1], (boxes, e1)
    assert boxes[1][3] == e2 == boxes[2][1], (boxes, e2)
    assert all(b[0] == 0 and b[2] == 300 for b in boxes)


def test_chunk_rect_zero_lines_returns_box_and_marker():
    g = np.full((200, 100), 255, np.uint8)
    boxes, nls, flag = BR.chunk_rect(g, (0, 10, 100, 190))
    assert boxes == [(0, 10, 100, 190)] and nls == [0]
    assert flag == "no_lines_detected"


def test_chunk_rect_max_lines_validated():
    g, _ = page45()
    try:
        BR.chunk_rect(g, (0, 10, 300, 880), max_lines=0)
    except ValueError as e:
        assert "max_lines" in str(e)
    else:
        raise AssertionError("max_lines=0 must raise")


def test_core_at_edge_true_when_box_cuts_a_line():
    g, tops = page45()
    cut = (0, tops[3] + 4, 300, tops[10] - 4)     # top edge inside line 3's ink rows
    assert BR.core_at_edge(g, cut) is True
    cut_bottom = (0, tops[3] - 4, 300, tops[10] + 4)
    assert BR.core_at_edge(g, cut_bottom) is True


def test_core_at_edge_false_on_gap_edges_and_ink_tight_box():
    g, tops = page45()
    boxes, _n, _f = BR.chunk_rect(g, (0, tops[0], 300, tops[-1] + 10))
    for b in boxes:
        assert BR.core_at_edge(g, b) is False, b


def test_classify_read_every_branch():
    assert BR.classify_read("Some text", "stop", 3) is None
    assert BR.classify_read("", "stop", 3) == "empty"
    assert BR.classify_read("  \n ", "stop", 3) == "empty"
    assert BR.classify_read(None, "stop", 3) == "empty"
    assert BR.classify_read("Some text", "length", 3) == "truncated"
    assert BR.classify_read("ab" + "x" * 20 + "cd", "stop", 3) == "degenerate_repeat"
    assert BR.classify_read("ab" + "x" * 19 + "cd", "stop", 3) is None
    assert BR.classify_read("12345 ...", "stop", 2) == "degenerate_no_latin"
    assert BR.classify_read("12345 ...", "stop", 0) is None


def test_join_wordbreaks_joins_lowercase_continuation():
    assert BR.join_wordbreaks("the regene-\nration of") == "the regeneration of"


def test_join_wordbreaks_leaves_capital_and_em_dash_alone():
    assert BR.join_wordbreaks("the Lord-\nAnd he") == "the Lord-\nAnd he"
    assert BR.join_wordbreaks("so —\nand then") == "so —\nand then"
    assert BR.join_wordbreaks("one-\n two") == "one-\n two"   # leading space: not joined


def test_join_wordbreaks_chains_and_changes_nothing_else():
    assert BR.join_wordbreaks("a-\nb-\ncd\nEf") == "abcd\nEf"
    assert BR.join_wordbreaks("plain\ntext  here") == "plain\ntext  here"


def test_read_chunk_request_shape():
    c = FakeClient()
    res = BR.read_chunk(c, b"\x89PNGfake")
    url, payload, timeout = c.calls[0]
    assert url == "http://192.168.1.169:11435/api/chat"
    assert payload["think"] is False and payload["stream"] is False
    assert payload["options"] == {"temperature": 0, "num_predict": 2048}
    assert payload["messages"][0]["content"] == BR.BODY_PROMPT
    assert payload["model"] == "fake-model" and len(payload["messages"][0]["images"]) == 1
    assert res == {"text": "Line one", "done_reason": "stop", "eval_count": 7, "http_status": 200}


def test_read_chunk_429_and_5xx_raise_runfault():
    for st in (429, 500, 503):
        try:
            BR.read_chunk(FakeClient(FakeResp(st, {})), b"x")
        except BR.RunFault as e:
            assert str(st) in str(e)
        else:
            raise AssertionError(f"{st} must raise RunFault")


def test_read_chunk_other_non_200_also_runfault():
    try:
        BR.read_chunk(FakeClient(FakeResp(404, {})), b"x")
    except BR.RunFault:
        pass
    else:
        raise AssertionError("404 must raise RunFault (conservative: not an item)")


def test_body_prompt_is_the_locked_text():
    p = BR.BODY_PROMPT
    for needle in ("exactly as printed", "one output line per printed line", "^a^",
                   "do not correct or modernise", "Output only the text."):
        assert needle in p, needle


def test_read_chunk_missing_fields_do_not_invent_text():
    c = FakeClient(FakeResp(200, {"done_reason": "stop"}))
    res = BR.read_chunk(c, b"x")
    assert res["text"] == "" and BR.classify_read(res["text"], res["done_reason"], 2) == "empty"


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
