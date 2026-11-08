"""USFM book code -> OSIS book code for the 66-book Protestant canon, plus a
fail-loud USFM verse counter.

Cite: lock dr-voluminous PREDICTION_versification_born_test_20261108.md (545b69e6).

The OSIS values are exactly the keys of Golden Chain's versification.py
CHAPTERS, in its order. The counter never normalises and never skips: any
irregularity (bridge, gap, duplicate, stray verse, missing id) raises
UsfmCountError naming source, book, chapter (and verse).
"""
import re
from pathlib import Path

_PAIRS = (
    ("GEN", "Gen"), ("EXO", "Exod"), ("LEV", "Lev"), ("NUM", "Num"), ("DEU", "Deut"),
    ("JOS", "Josh"), ("JDG", "Judg"), ("RUT", "Ruth"), ("1SA", "1Sam"), ("2SA", "2Sam"),
    ("1KI", "1Kgs"), ("2KI", "2Kgs"), ("1CH", "1Chr"), ("2CH", "2Chr"), ("EZR", "Ezra"),
    ("NEH", "Neh"), ("EST", "Esth"), ("JOB", "Job"), ("PSA", "Ps"), ("PRO", "Prov"),
    ("ECC", "Eccl"), ("SNG", "Song"), ("ISA", "Isa"), ("JER", "Jer"), ("LAM", "Lam"),
    ("EZK", "Ezek"), ("DAN", "Dan"), ("HOS", "Hos"), ("JOL", "Joel"), ("AMO", "Amos"),
    ("OBA", "Obad"), ("JON", "Jonah"), ("MIC", "Mic"), ("NAM", "Nah"), ("HAB", "Hab"),
    ("ZEP", "Zeph"), ("HAG", "Hag"), ("ZEC", "Zech"), ("MAL", "Mal"),
    ("MAT", "Matt"), ("MRK", "Mark"), ("LUK", "Luke"), ("JHN", "John"), ("ACT", "Acts"),
    ("ROM", "Rom"), ("1CO", "1Cor"), ("2CO", "2Cor"), ("GAL", "Gal"), ("EPH", "Eph"),
    ("PHP", "Phil"), ("COL", "Col"), ("1TH", "1Thess"), ("2TH", "2Thess"), ("1TI", "1Tim"),
    ("2TI", "2Tim"), ("TIT", "Titus"), ("PHM", "Phlm"), ("HEB", "Heb"), ("JAS", "Jas"),
    ("1PE", "1Pet"), ("2PE", "2Pet"), ("1JN", "1John"), ("2JN", "2John"), ("3JN", "3John"),
    ("JUD", "Jude"), ("REV", "Rev"),
)
USFM_TO_OSIS: dict[str, str] = dict(_PAIRS)


class UsfmCountError(ValueError):
    pass


# marker must be followed by whitespace: \v matches, \va \vp \cl \ca \cp do not
_ID = re.compile(r"\\id\s+(\S+)")
_MARK = re.compile(r"\\(c|v)\s+(\S+)")


def count_usfm_text(text: str, source: str = "<text>") -> tuple[str, tuple[int, ...]]:
    ids = _ID.findall(text)
    if len(ids) != 1:
        raise UsfmCountError(f"{source}: expected exactly one \\id, found {len(ids)} {ids}")
    book = ids[0]
    chapters: list[list[int]] = []
    for m in _MARK.finditer(text):
        kind, tok = m.group(1), m.group(2)
        if kind == "c":
            if not tok.isascii() or not tok.isdigit():
                raise UsfmCountError(f"{source}: {book}: non-integer chapter token {tok!r}")
            n = int(tok)
            if n != len(chapters) + 1:
                raise UsfmCountError(
                    f"{source}: {book}: chapter {n} follows chapter {len(chapters)} (gap or duplicate)")
            chapters.append([])
        else:
            if not chapters:
                raise UsfmCountError(f"{source}: {book}: \\v {tok} before any \\c")
            ch = len(chapters)
            if not tok.isascii() or not tok.isdigit():
                raise UsfmCountError(f"{source}: {book} {ch}: non-integer verse token {tok!r} (bridge?)")
            n = int(tok)
            if n != len(chapters[-1]) + 1:
                raise UsfmCountError(
                    f"{source}: {book} {ch}: verse {n} follows verse {len(chapters[-1])} (gap or duplicate)")
            chapters[-1].append(n)
    if not chapters:
        raise UsfmCountError(f"{source}: {book}: no chapters")
    for i, vs in enumerate(chapters, 1):
        if not vs:
            raise UsfmCountError(f"{source}: {book} {i}: chapter has 0 verses")
    return book, tuple(len(vs) for vs in chapters)


def count_usfm_dir(usfm_dir) -> dict[str, tuple[int, ...]]:
    out: dict[str, tuple[int, ...]] = {}
    seen: dict[str, str] = {}
    for p in sorted(Path(usfm_dir).glob("*.usfm")):
        uid, counts = count_usfm_text(p.read_text(encoding="utf-8"), str(p.name))
        if uid in out:
            raise UsfmCountError(f"duplicate \\id {uid} in {seen[uid]} and {p.name}")
        out[uid] = counts
        seen[uid] = p.name
    return out
