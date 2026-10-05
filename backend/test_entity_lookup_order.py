"""The Tier-2 entity manifest must be a pure function of (query, corpus).

Regression cover for the 2026-09-28 incident: `candidates` was a set and was
iterated directly, so PYTHONHASHSEED decided which substring candidate spent
the 5-slot cap first. For "What is the spiritual meaning of the scapegoat?"
that flipped the manifest between [scape-goat, antitypical scape-goat, +3
spiritual*] and five spiritual* entities -- and with it whether Leviticus 16
ever reached the answer LM. Measured live over 7 processes x 10 calls: 30/30
with the good order, 0/30 with the bad one, zero variation inside any process.

These tests cover the two pure pieces. The end-to-end evidence is the live
7-seed probe recorded in docs/audits/; it needs the Weaviate cluster, so it is
not run here.

    python backend/test_entity_lookup_order.py
"""
import os
import subprocess
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.gill_search import GillSearchEngine  # noqa: E402

SCAPEGOAT_Q = "What is the spiritual meaning of the scapegoat?"


def _engine():
    return GillSearchEngine()


def test_candidates_are_a_list_in_first_appearance_order():
    got = _engine()._substring_candidates("scapegoat spiritual atonement")
    assert isinstance(got, list), type(got)
    assert got == ["scapegoat", "spiritual", "atonement"], got


def test_candidates_drop_stopwords_and_short_tokens():
    # "What"/"the" are short or stopwords; "meaning" is an explicit stopword.
    got = _engine()._substring_candidates(SCAPEGOAT_Q)
    assert got == ["spiritual", "scapegoat"], got


def test_candidates_dedupe_without_reordering():
    got = _engine()._substring_candidates("covenant covenant scapegoat covenant")
    assert got == ["covenant", "scapegoat"], got


def test_plural_stem_is_added_after_its_source_and_not_duplicated():
    got = _engine()._substring_candidates("psalms psalms")
    assert got == ["psalms", "psalm"], got


def test_rank_puts_the_distinctive_candidate_first():
    # The incident, in miniature: 2 exact matches must outrank 23 generic ones.
    per_candidate = {
        "spiritual": ["spiritual %d" % i for i in range(23)],
        "scapegoat": ["scape-goat", "antitypical scape-goat"],
    }
    assert GillSearchEngine._rank_candidates(per_candidate) == ["scapegoat", "spiritual"]


def test_rank_is_independent_of_input_insertion_order():
    a = {"spiritual": ["x"] * 23, "scapegoat": ["y"] * 2}
    b = {"scapegoat": ["y"] * 2, "spiritual": ["x"] * 23}
    assert GillSearchEngine._rank_candidates(a) == GillSearchEngine._rank_candidates(b)


def test_rank_breaks_equal_counts_alphabetically_so_the_order_is_total():
    per_candidate = {"zebra": ["a", "b"], "apple": ["c", "d"], "mango": ["e", "f"]}
    assert GillSearchEngine._rank_candidates(per_candidate) == ["apple", "mango", "zebra"]


def test_rank_of_nothing_is_nothing():
    assert GillSearchEngine._rank_candidates({}) == []


def test_a_candidate_with_zero_matches_ranks_first_and_contributes_nothing():
    # An empty match list must not raise and must not displace anything real,
    # because it adds no names downstream.
    per_candidate = {"generic": ["a", "b"], "nomatch": []}
    assert GillSearchEngine._rank_candidates(per_candidate) == ["nomatch", "generic"]


def test_candidate_order_is_identical_across_processes_with_different_hash_seeds():
    """The actual incident: a set's iteration order is per-PROCESS."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    snippet = (
        "import sys; sys.path.insert(0, %r);"
        "from backend.gill_search import GillSearchEngine as G;"
        "print(G()._substring_candidates(%r))" % (root, SCAPEGOAT_Q)
    )
    seen = set()
    for seed in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONIOENCODING="utf-8")
        out = subprocess.run([sys.executable, "-c", snippet], capture_output=True,
                             text=True, env=env, cwd=root)
        assert out.returncode == 0, out.stderr[-600:]
        seen.add(out.stdout.strip().splitlines()[-1])
    assert len(seen) == 1, "candidate order varies across processes: %s" % seen
    assert "scapegoat" in seen.pop()


# A hand-rolled suite reports what it happened to collect. If a test is renamed out of the
# test_ prefix, deleted, or shadowed by a duplicate name, the run still prints "N/N passed"
# and looks healthy. Assert the COUNT so a silently shrinking suite fails loudly.
EXPECTED_TESTS = 10

if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  ok    %s" % name)
        except Exception:
            failed += 1
            print("  FAIL  %s" % name)
            traceback.print_exc()
    print("")
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    if len(tests) != EXPECTED_TESTS:
        print("FAIL suite: collected %d tests, expected %d - a test was lost or added "
              "without updating EXPECTED_TESTS" % (len(tests), EXPECTED_TESTS))
        failed += 1
    sys.exit(1 if failed else 0)
