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
