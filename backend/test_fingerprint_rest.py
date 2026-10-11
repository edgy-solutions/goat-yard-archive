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

def _drive(pages, faults=None, include_vector=True):
    """Run stream_chunks against a fake transport with sleeps neutered. Returns (yielded, fake).

    `include_vector` is passed EXPLICITLY and defaults to True here, the opposite of the module's
    own default. Every assertion below is about the vector-bearing URL shape (`limit=20`,
    `&include=vector`) and about vectors arriving in the 3-tuple, so a helper that inherited the
    module default would silently turn all of them into tests of the text-only path. The module
    default is pinned by its own test instead."""
    real_http, real_sleep = FR.httpx, time.sleep
    FR.httpx, time.sleep = _FakeHTTP(pages), lambda *_a, **_k: None
    try:
        return (list(FR.stream_chunks("192.0.2.1", faults=faults,
                                      include_vector=include_vector)),
                FR.httpx)
    finally:
        FR.httpx, time.sleep = real_http, real_sleep

PAGE_1_URL = "http://192.0.2.1/v1/objects?class=CommentaryChunk&limit=20&include=vector"
NO_VECTOR_URL = "http://192.0.2.1/v1/objects?class=CommentaryChunk&limit=100"

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
    got, fake = _drive(pages)                          # this test is about the CURSOR
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

# --- the double read, RETIRED (ruling, 2026-10-04) --------------------------------------------
# These three tests used to assert the guard. They now assert its ABSENCE, with the loss named,
# because a retired guard whose tests were simply deleted leaves no record that the behaviour
# ever existed or what went away with it. The fault itself is open: docs/defects/D-002.

def test_every_vector_bearing_page_is_fetched_ONCE():
    # The retirement, stated as a count. The guard's cost was not CPU: it was that a full-corpus
    # vector sample refused about 99.5% of the time, so what it produced was the absence of a
    # sample rather than a verified one.
    got, fake = _drive(_one_page())
    urls = [u for _m, u in fake.calls]
    assert urls.count(PAGE_1_URL) == 1, urls
    assert urls[-1] == PAGE_1_URL + "&after=u2", urls
    assert len(got) == 2, got

def test_a_vector_that_reads_back_DIFFERENTLY_is_NO_LONGER_faulted():
    # The loss, named. Same fixture as the test this replaces: same length, different contents,
    # the signature measured on both attempt-5 arms. The sampler streams the first read and says
    # NOTHING, because it never takes a second one. An unverified vector read is now exactly what
    # it looks like -- unverified -- and the mid-run corpus check does not take one at all.
    faults = []
    first = _page([_obj("u1"), _obj("u2")])
    second = _page([_obj("u1"), _obj("u2")])
    second["objects"][1]["vector"] = [0.1, 0.1, 0.1, 0.9]      # same dim 4, one element moved
    got, fake = _drive({None: [first, second], "u2": [_page([])]}, faults)
    assert [m["id"] for _p, _v, m in got] == ["u1", "u2"], got  # the first read is what streams
    assert faults == [], faults                                # no detector, so no fault
    assert [u for _m, u in fake.calls].count(PAGE_1_URL) == 1, fake.calls

def test_vector_rounding_tolerates_float_noise():
    # LOAD-BEARING and still true, which is why it survives the retirement as a unit test of the
    # pure function instead of a test of the sampler. `vector_disagreement` decides on the
    # 6-decimal digest, so a difference in the 9th place is not a disagreement. Any future
    # consumer that re-reads vectors (the D-002 probe does) must compare this way: element-wise
    # equality would call every read unstable and bury the real fault in noise.
    assert FR.vector_disagreement([0.1, 0.1, 0.1, 0.1],
                                  [0.1, 0.1, 0.1, 0.1 + 1e-9]) is None
    d = FR.vector_disagreement([0.1, 0.1, 0.1, 0.1], [0.1, 0.1, 0.1, 0.9])
    assert d and d["reason"] == "elements" and d["n_differing"] == 1, d

def test_an_object_that_vanishes_from_a_second_read_is_not_noticed_by_the_sampler():
    # The other half of the loss. A page whose membership changes between two reads was a fault;
    # with one read there is no comparison to make, and the second page body is never fetched.
    # `vector_disagreement` still names the shape for a caller that does take two reads.
    faults = []
    first = _page([_obj("u1"), _obj("u2")])
    second = _page([_obj("u1")])
    got, _fake = _drive({None: [first, second], "u2": [_page([])]}, faults)
    assert [m["id"] for _p, _v, m in got] == ["u1", "u2"], got
    assert faults == [], faults
    assert FR.vector_disagreement([0.1] * 4, FR._ABSENT) == {"reason": "absent-on-reread"}

def test_include_vector_defaults_to_FALSE_and_pages_without_the_embedding():
    # The default is what a new consumer inherits, so the ruling's "no vector reads" had to land
    # on the default and not only on the eval's flag. A text-only page also carries 5x the rows.
    pages = {None: [_page([_obj("u1"), _obj("u2")])], "u2": [_page([])]}
    real_http, real_sleep = FR.httpx, time.sleep
    FR.httpx, time.sleep = _FakeHTTP(pages), lambda *_a, **_k: None
    try:
        got = list(FR.stream_chunks("192.0.2.1"))
        urls = [u for _m, u in FR.httpx.calls]
    finally:
        FR.httpx, time.sleep = real_http, real_sleep
    assert urls[0] == NO_VECTOR_URL, urls
    assert all("include=vector" not in u for u in urls), urls
    assert [m["id"] for _p, _v, m in got] == ["u1", "u2"], got

def test_vector_disagreement_is_silent_on_two_reads_that_agree():
    # The null. A detector that reported a disagreement for everything would satisfy every test
    # above and refuse every run ever made.
    assert FR.vector_disagreement([0.1] * 4, [0.1] * 4) is None
    assert FR.vector_disagreement(None, None) is None
    d = FR.vector_disagreement([0.1] * 4, None)
    assert d and d["reason"] == "one-read-had-no-vector" and d["first_read_had_one"] is True, d
    d = FR.vector_disagreement([0.1] * 4, [0.1] * 5)
    assert d and d["reason"] == "length" and (d["len_first"], d["len_second"]) == (4, 5), d

def test_the_module_issues_nothing_but_GET():
    _got, fake = _drive(_one_page())
    assert {m for m, _u in fake.calls} == {"GET"}, fake.calls
    assert not hasattr(fake, "post"), "the fake has no write verb; reaching for one must fail loud"

# A hand-rolled suite reports what it happened to collect. Assert the COUNT so a test that is
# renamed out of the prefix, deleted, or shadowed by a duplicate name fails loudly instead of
# printing a healthy-looking tally.
EXPECTED_TESTS = 17

if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    p = f = 0
    for fn in fns:
        try: fn(); p += 1; print(f"  PASS {fn.__name__}")
        except KeyboardInterrupt:
            raise
        # SystemExit is NOT an Exception, so `except Exception` let a test that reaches sys.exit
        # end the WHOLE run silently -- no summary line, which reads as a shorter suite. Witnessed
        # 2026-10-11 in evals/test_gate_paired.py (argparse exits 2 on an unrecognized flag).
        except BaseException: f += 1; print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{p} passed, {f} failed")
    if len(fns) != EXPECTED_TESTS:
        print(f"FAIL suite: collected {len(fns)} tests, expected {EXPECTED_TESTS} - a test was "
              f"lost or added without updating EXPECTED_TESTS")
        f += 1
    raise SystemExit(1 if f else 0)
