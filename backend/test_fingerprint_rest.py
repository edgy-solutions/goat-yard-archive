"""fingerprint_rest.stream_chunks born tested against a FAKE transport -- the page-level structural
validation, the re-fetch, and the fault accounting. This is the code that actually touches the
measured defect (docs/audits/READFAULT_corpus_vector_sha_false_positive_20261004.md): a 1.1 MB page
body is occasionally reassembled client-side with an earlier block re-emitted over a later region,
preserving total length, so the vector array comes back malformed. The retry that was already here
caught the half that broke the JSON and counted nothing, which is why only the UNDETECTABLE half
ever reached the fingerprint. Every retry is asserted to be counted here.

Dims are tiny (4, not 4096) on purpose -- the modal-dim logic is dim-agnostic and a real-size
fixture would buy nothing. Run: python test_fingerprint_rest.py"""
import json, time
import fingerprint_rest as FR

PROPS = {"content": "In the beginning God created", "verse_ref": "GEN_1_1", "volume": 1,
         "page_number": 90}

def _obj(uuid, dim=4, lu=1748137658136, vector=True):
    o = {"id": uuid, "lastUpdateTimeUnix": lu, "properties": dict(PROPS)}
    o["vector"] = [0.1] * dim if vector else None
    return o

def _page(objs): return {"objects": objs}

def _after_of(url):
    """The cursor value in a page URL, or None for the first page -- the fake server page key."""
    return url.split("&after=")[1] if "&after=" in url else None

class _Resp:
    """A body is a dict (valid JSON), a str (parses as nothing -- the visible corruption), or the
    empty string (an empty body under load, which must NOT be read as the end of the stream)."""
    def __init__(self, body): self.body = body
    @property
    def text(self): return self.body if isinstance(self.body, str) else json.dumps(self.body)
    def json(self):
        if isinstance(self.body, str): raise ValueError("fake JSON decode error")
        return self.body

class _FakeHTTP:
    """Stands in for the httpx module inside fingerprint_rest. `pages` maps a cursor key to a LIST
    of bodies served in order; the last body is sticky, so [bad, good] means corrupt once then
    clean thereafter, and [bad] means corrupt on every attempt. Only `get` exists: if the module
    ever issues a write this blows up with AttributeError, which is the assertion we want."""
    def __init__(self, pages): self.pages, self.calls = pages, []
    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        bodies = self.pages[_after_of(url)]
        return _Resp(bodies.pop(0) if len(bodies) > 1 else bodies[0])

def _drive(pages, faults=None):
    """Run stream_chunks against a fake transport with sleeps neutered. Returns (yielded, fake)."""
    real_http, real_sleep = FR.httpx, time.sleep
    FR.httpx, time.sleep = _FakeHTTP(pages), lambda *_a, **_k: None
    try:
        return list(FR.stream_chunks("192.0.2.1", faults=faults)), FR.httpx
    finally:
        FR.httpx, time.sleep = real_http, real_sleep

PAGE_1_URL = "http://192.0.2.1/v1/objects?class=CommentaryChunk&limit=20&include=vector"

def _one_page():
    return {None: [_page([_obj("u1"), _obj("u2")])], "u2": [_page([])]}

def test_a_three_tuple_carries_the_servers_own_id_and_timestamp():
    got, _ = _drive(_one_page())
    assert len(got) == 2, got
    props, vec, meta = got[0]
    assert props == PROPS, props
    assert vec == [0.1] * 4, vec
    assert meta == {"id": "u1", "last_update_ms": 1748137658136}, meta   # read, not synthesised

def test_the_cursor_walks_pages_by_the_last_objects_id():
    pages = {None: [_page([_obj("u1"), _obj("u2")])],
             "u2": [_page([_obj("u3"), _obj("u4")])],
             "u4": [_page([])]}
    got, fake = _drive(pages)
    ids = [m["id"] for _p, _v, m in got]
    assert ids == ["u1", "u2", "u3", "u4"], ids              # no skip, no double-count
    assert [u for _m, u in fake.calls] == [PAGE_1_URL, PAGE_1_URL + "&after=u2",
                                           PAGE_1_URL + "&after=u4"], fake.calls

def test_an_empty_body_is_retried_not_read_as_the_end_of_the_stream():
    faults = []
    got, fake = _drive({None: ["", _page([_obj("u1")])], "u1": [_page([])]}, faults)
    assert [m["id"] for _p, _v, m in got] == ["u1"], got     # an empty body is not an empty corpus
    assert [f["kind"] for f in faults] == ["json_decode_retry"], faults
    assert len(fake.calls) == 3, fake.calls                  # empty, retry, terminator

def test_a_json_decode_failure_is_retried_and_counted():
    faults = []
    got, _ = _drive({None: ["{truncated", _page([_obj("u1")])], "u1": [_page([])]}, faults)
    assert len(got) == 1, got
    assert faults == [{"kind": "json_decode_retry", "attempt": 0, "url": PAGE_1_URL}], faults

def test_an_anomalous_page_is_refetched_and_the_clean_read_wins():
    faults = []
    bad = _page([_obj("u1"), _obj("u2"), _obj("u3", dim=5)])     # modal 4, one malformed array
    good = _page([_obj("u1"), _obj("u2"), _obj("u3")])
    got, _ = _drive({None: [bad, good], "u3": [_page([])]}, faults)
    assert [len(v) for _p, v, _m in got] == [4, 4, 4], got       # the clean re-read is what streams
    assert [f["kind"] for f in faults] == ["dim_anomaly_retry"], faults
    assert faults[0]["uuids"] == ["u3"] and faults[0]["attempt"] == 1, faults

def test_a_page_anomalous_on_every_attempt_is_yielded_whole_and_named():
    faults = []
    bad = _page([_obj("u1"), _obj("u2"), _obj("u3", dim=5)])
    got, _ = _drive({None: [bad], "u3": [_page([])]}, faults)
    assert [m["id"] for _p, _v, m in got] == ["u1", "u2", "u3"], got   # nothing silently dropped
    assert [len(v) for _p, v, _m in got] == [4, 4, 5], got            # and nothing zero-substituted
    kinds = [f["kind"] for f in faults]
    assert kinds == ["dim_anomaly_retry"] * 3 + ["dim_anomaly"], kinds  # 3 re-fetches, then named
    assert faults[-1]["uuids"] == ["u3"], faults[-1]

def test_a_uniform_corpus_is_never_flagged_whatever_its_dim():
    faults = []
    pages = {None: [_page([_obj("u1", dim=5), _obj("u2", dim=5)])], "u2": [_page([])]}
    got, _ = _drive(pages, faults)
    assert len(got) == 2 and faults == [], (got, faults)     # modal is observed, not hardcoded

def test_a_majority_corrupt_first_page_seeds_the_wrong_modal_dim():
    """A KNOWN WEAKNESS, asserted so it is a documented property and not a surprise: the modal dim
    is seeded from the first page, so if most of that page is corrupt the SOUND objects are the
    ones flagged. It still fails loud -- the sample is rejected and the remedy is a re-read either
    way -- but the uuids it names are wrong, which is why last_update_ms and not this check is the
    detector (two of the seven measured corruptions had the correct length anyway)."""
    faults = []
    bad = _page([_obj("u1", dim=5), _obj("u2", dim=5), _obj("u3", dim=4)])
    got, _ = _drive({None: [bad], "u3": [_page([])]}, faults)
    assert len(got) == 3, got
    assert faults[-1]["kind"] == "dim_anomaly" and faults[-1]["uuids"] == ["u3"], faults[-1]

def test_an_object_with_no_vector_is_yielded_and_is_not_an_anomaly():
    faults = []
    pages = {None: [_page([_obj("u1"), _obj("u2", vector=False)])], "u2": [_page([])]}
    got, _ = _drive(pages, faults)
    assert [v for _p, v, _m in got] == [[0.1] * 4, None], got
    assert faults == [], faults                              # absent is not malformed

def test_faults_is_optional_and_a_bad_page_still_streams():
    bad = _page([_obj("u1"), _obj("u2", dim=5)])
    got, fake = _drive({None: [bad], "u2": [_page([])]})
    assert [m["id"] for _p, _v, m in got] == ["u1", "u2"], got
    assert len(fake.calls) == 5, fake.calls                  # 1 + 3 re-fetches + terminator

def test_the_module_issues_nothing_but_GET():
    _got, fake = _drive(_one_page())
    assert {m for m, _u in fake.calls} == {"GET"}, fake.calls
    assert not hasattr(fake, "post"), "the fake has no write verb; reaching for one must fail loud"

# A hand-rolled suite reports what it happened to collect. Assert the COUNT so a test that is
# renamed out of the prefix, deleted, or shadowed by a duplicate name fails loudly instead of
# printing a healthy-looking tally.
EXPECTED_TESTS = 11

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except Exception: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed")
    if len(fns) != EXPECTED_TESTS:
        print(f"FAIL suite: collected {len(fns)} tests, expected {EXPECTED_TESTS} - a test was "
              f"lost or added without updating EXPECTED_TESTS")
        f += 1
    raise SystemExit(1 if f else 0)
