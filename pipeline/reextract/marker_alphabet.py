"""The 1766 24-letter marker alphabet (i/j and u/v merged): a b c d e f g h i k l m n o p q r s t u w x y z.
No j, no v. Gives the EXACT expected note count per column from the first→last marker, and makes j/v illegal
outputs in the marker-confirmation read. Sourced from the profile (compositor_conventions.marker_alphabet);
this module is the code that consumes it. See book_profile.gill.yaml for the convention + the after-z note."""

ALPHABET = "abcdefghiklmnopqrstuwxyz"   # 24 letters; also profile.compositor_conventions.marker_alphabet
_MERGE = {"j": "i", "v": "u"}           # i/j and u/v are one letter each

def normalize(letter):
    """Fold a marker letter to its canonical form (j→i, v→u), lowercased."""
    c = (letter or "").strip().lower()[:1]
    return _MERGE.get(c, c)

def is_legal(letter):
    """A marker-confirmation read must never emit j or v — those are illegal glyphs under the alphabet."""
    return (letter or "").strip().lower()[:1] not in ("j", "v")

def index(letter):
    """0-based position in the 24-letter alphabet, or -1 if not a marker letter."""
    c = normalize(letter)
    return ALPHABET.index(c) if c in ALPHABET else -1

def count_between(first, last):
    """Expected note count for a column running first→last marker (inclusive), under the alphabet. None if
    either marker is not a legal letter or they are out of order."""
    a, b = index(first), index(last)
    if a < 0 or b < 0 or b < a:
        return None
    return b - a + 1

def run(first, n):
    """The expected n-marker run from `first`, incrementing through the alphabet and WRAPPING z→a (the
    resolved after-z convention). The absolute start need not be 'a' (Gill pages start mid-run)."""
    a = index(first)
    if a < 0:
        return []
    L = len(ALPHABET)
    return [ALPHABET[(a + k) % L] for k in range(n)]

def count_run(first, last):
    """Count of a consecutive run first→last inclusive, WRAP-aware (z→a). None if either is not a marker."""
    a, b = index(first), index(last)
    if a < 0 or b < 0:
        return None
    return (b - a) % len(ALPHABET) + 1

def is_consecutive_run(markers):
    """True iff `markers` (in reading order) form a gapless consecutive run under the alphabet, WRAP-aware —
    no gaps, no repeats (except the single legal z→a step), no illegal j/v. This is the SEQUENCE-EQUALITY
    check the gate uses: cancellation (a false start + a missed real start) cannot produce a gapless run."""
    idx = []
    for m in markers:
        if not is_legal(m):
            return False
        i = index(m)
        if i < 0:
            return False
        idx.append(i)
    L = len(ALPHABET)
    return all(idx[k] == (idx[k - 1] + 1) % L for k in range(1, len(idx)))

def expected_segmented(segments):
    """The expected marker run for a page that crosses RESET boundaries. segments = [(first, n), …] — one
    per body segment (a book-intro / Chapter-I reset starts a new segment at 'a'; the continuing segment
    starts where the previous page's chain left off). Each segment is a wrap-aware run; the page's expected
    sequence is their concatenation. p2 = [('c',1),('a',4)] -> c,a,b,c,d. p315 = [('x',9),('a',1)] ->
    x,y,z,a,b,c,d,e,f,a. Reset points come from the body alignment (verse_ref), NOT the marker stream."""
    out = []
    for first, n in segments:
        out += run(first, n)
    return out

def is_valid_segmented(markers, segment_lengths):
    """markers in reading order; segment_lengths = notes per body segment (from the alignment resets). Each
    segment must be a gapless consecutive run (wrap-aware); segments reset independently. A duplicated letter
    ACROSS a reset (two 'c' on p2, two 'a' on p315) is legal; a duplicate or gap WITHIN a segment (a false
    start / a missed start — the cancellation class) is not. This is the reset-aware sequence gate."""
    if sum(segment_lengths) != len(markers):
        return False
    i = 0
    for L in segment_lengths:
        if not is_consecutive_run(markers[i:i + L]):
            return False
        i += L
    return True

def sequence_breaks(letters):
    """Return the list of problems in an observed marker sequence: any illegal j/v, or a gap/backstep that
    breaks consecutiveness under the alphabet. Empty list == the sequence obeys the convention."""
    problems = []
    idx = []
    for l in letters:
        if not is_legal(l):
            problems.append(f"illegal-marker:{l}")
        i = index(l)
        if i >= 0:
            idx.append(i)
    for k in range(1, len(idx)):
        if idx[k] != idx[k - 1] + 1:
            problems.append(f"non-consecutive:{ALPHABET[idx[k-1]]}->{ALPHABET[idx[k]]}")
    return problems
