
# Canonical mapping for Bible books (Abbreviations -> WEAVIATE_CANONICAL_NAME)
# Based on common academic and standard abbreviations.

BIBLE_BOOK_MAP = {
    # OLD TESTAMENT
    "gen": "GENESIS", "ge": "GENESIS", "gn": "GENESIS", "genesis": "GENESIS",
    "ex": "EXODUS", "exo": "EXODUS", "exod": "EXODUS", "exodus": "EXODUS",
    "lev": "LEVITICUS", "le": "LEVITICUS", "lv": "LEVITICUS", "leviticus": "LEVITICUS",
    "num": "NUMBERS", "nu": "NUMBERS", "nm": "NUMBERS", "nb": "NUMBERS", "numbers": "NUMBERS",
    "deut": "DEUTERONOMY", "dt": "DEUTERONOMY", "de": "DEUTERONOMY", "deuteronomy": "DEUTERONOMY",
    "josh": "JOSHUA", "jos": "JOSHUA", "joshua": "JOSHUA",
    "judg": "JUDGES", "jdg": "JUDGES", "jg": "JUDGES", "judges": "JUDGES",
    "ruth": "RUTH", "ru": "RUTH",
    "1 sam": "1 SAMUEL", "1 sa": "1 SAMUEL", "1sam": "1 SAMUEL", "1 s": "1 SAMUEL", "1 samuel": "1 SAMUEL",
    "2 sam": "2 SAMUEL", "2 sa": "2 SAMUEL", "2sam": "2 SAMUEL", "2 s": "2 SAMUEL", "2 samuel": "2 SAMUEL",
    "1 kings": "1 KINGS", "1 kgs": "1 KINGS", "1 ki": "1 KINGS", "1kgs": "1 KINGS",
    "2 kings": "2 KINGS", "2 kgs": "2 KINGS", "2 ki": "2 KINGS", "2kgs": "2 KINGS",
    "1 chron": "1 CHRONICLES", "1 chr": "1 CHRONICLES", "1 ch": "1 CHRONICLES", "1 chronicles": "1 CHRONICLES",
    "2 chron": "2 CHRONICLES", "2 chr": "2 CHRONICLES", "2 ch": "2 CHRONICLES", "2 chronicles": "2 CHRONICLES",
    "ezra": "EZRA", "ezr": "EZRA",
    "neh": "NEHEMIAH", "ne": "NEHEMIAH", "nehemiah": "NEHEMIAH",
    "esth": "ESTHER", "es": "ESTHER", "esther": "ESTHER",
    "job": "JOB", "jb": "JOB",
    "ps": "PSALMS", "psa": "PSALMS", "psalm": "PSALMS", "psalms": "PSALMS",
    "prov": "PROVERBS", "pro": "PROVERBS", "pr": "PROVERBS", "proverbs": "PROVERBS",
    "eccl": "ECCLESIASTES", "ecc": "ECCLESIASTES", "ec": "ECCLESIASTES", "qoh": "ECCLESIASTES", "ecclesiastes": "ECCLESIASTES",
    "song": "SONG OF SOLOMON", "sos": "SONG OF SOLOMON", "cant": "SONG OF SOLOMON", "song of solomon": "SONG OF SOLOMON", "song of songs": "SONG OF SOLOMON",
    "isa": "ISAIAH", "is": "ISAIAH", "isaiah": "ISAIAH",
    "jer": "JEREMIAH", "je": "JEREMIAH", "jr": "JEREMIAH", "jeremiah": "JEREMIAH",
    "lam": "LAMENTATIONS", "la": "LAMENTATIONS", "lamentations": "LAMENTATIONS",
    "ezek": "EZEKIEL", "eze": "EZEKIEL", "ezk": "EZEKIEL", "ezekiel": "EZEKIEL",
    "dan": "DANIEL", "da": "DANIEL", "dn": "DANIEL", "daniel": "DANIEL",
    "hos": "HOSEA", "ho": "HOSEA", "hosea": "HOSEA",
    "joel": "JOEL", "jl": "JOEL",
    "amos": "AMOS", "am": "AMOS",
    "obad": "OBADIAH", "ob": "OBADIAH", "obadiah": "OBADIAH",
    "jonah": "JONAH", "jnh": "JONAH", "jon": "JONAH",
    "mic": "MICAH", "mc": "MICAH", "micah": "MICAH",
    "nah": "NAHUM", "na": "NAHUM", "nahum": "NAHUM",
    "hab": "HABAKKUK", "hb": "HABAKKUK", "habakkuk": "HABAKKUK",
    "zeph": "ZEPHANIAH", "zep": "ZEPHANIAH", "zephaniah": "ZEPHANIAH",
    "hag": "HAGGAI", "hg": "HAGGAI", "haggai": "HAGGAI",
    "zech": "ZECHARIAH", "zec": "ZECHARIAH", "zc": "ZECHARIAH", "zechariah": "ZECHARIAH",
    "mal": "MALACHI", "ml": "MALACHI", "malachi": "MALACHI",

    # NEW TESTAMENT
    "matt": "MATTHEW", "mat": "MATTHEW", "mt": "MATTHEW", "matthew": "MATTHEW",
    "mark": "MARK", "mk": "MARK", "mr": "MARK",
    "luke": "LUKE", "lk": "LUKE", "luk": "LUKE",
    "john": "JOHN", "jn": "JOHN", "jhn": "JOHN",
    "acts": "ACTS", "ac": "ACTS",
    "rom": "ROMANS", "ro": "ROMANS", "rm": "ROMANS", "romans": "ROMANS",
    "1 cor": "1 CORINTHIANS", "1 co": "1 CORINTHIANS", "1cor": "1 CORINTHIANS", "1 corinthians": "1 CORINTHIANS",
    "2 cor": "2 CORINTHIANS", "2 co": "2 CORINTHIANS", "2cor": "2 CORINTHIANS", "2 corinthians": "2 CORINTHIANS",
    "gal": "GALATIANS", "ga": "GALATIANS", "galatians": "GALATIANS",
    "eph": "EPHESIANS", "ep": "EPHESIANS", "ephesians": "EPHESIANS",
    "phil": "PHILIPPIANS", "php": "PHILIPPIANS", "philippians": "PHILIPPIANS",
    "col": "COLOSSIANS", "colossians": "COLOSSIANS",
    "1 thess": "1 THESSALONIANS", "1 th": "1 THESSALONIANS", "1thess": "1 THESSALONIANS", "1 thessalonians": "1 THESSALONIANS",
    "2 thess": "2 THESSALONIANS", "2 th": "2 THESSALONIANS", "2thess": "2 THESSALONIANS", "2 thessalonians": "2 THESSALONIANS",
    "1 tim": "1 TIMOTHY", "1 ti": "1 TIMOTHY", "1tim": "1 TIMOTHY", "1 timothy": "1 TIMOTHY",
    "2 tim": "2 TIMOTHY", "2 ti": "2 TIMOTHY", "2tim": "2 TIMOTHY", "2 timothy": "2 TIMOTHY",
    "titus": "TITUS", "tit": "TITUS",
    "philem": "PHILEMON", "phm": "PHILEMON", "philemon": "PHILEMON",
    "heb": "HEBREWS", "he": "HEBREWS", "hebrews": "HEBREWS",
    "jas": "JAMES", "jm": "JAMES", "james": "JAMES",
    "1 pet": "1 PETER", "1 pe": "1 PETER", "1pet": "1 PETER", "1 peter": "1 PETER",
    "2 pet": "2 PETER", "2 pe": "2 PETER", "2pet": "2 PETER", "2 peter": "2 PETER",
    "1 john": "1 JOHN", "1 jn": "1 JOHN", "1john": "1 JOHN",
    "2 john": "2 JOHN", "2 jn": "2 JOHN", "2john": "2 JOHN",
    "3 john": "3 JOHN", "3 jn": "3 JOHN", "3john": "3 JOHN",
    "jude": "JUDE", "jd": "JUDE",
    "rev": "REVELATION", "re": "REVELATION", "revelation": "REVELATION"
}

from typing import List

CANONICAL_BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
    "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther",
    "Job", "Psalms", "Proverbs", "Ecclesiastes", "Song Of Solomon", 
    "Isaiah", "Jeremiah", "Lamentations", "Ezekiel", "Daniel",
    "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum",
    "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
    "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians",
    "1 Thessalonians", "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon",
    "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation"
]

def format_book_ranges(books: List[str]) -> List[str]:
    """Sort books into canonical order and group consecutive books into ranges."""
    if not books:
        return []
        
    def get_sort_key(book_name: str):
        try:
            return (0, CANONICAL_BOOKS.index(book_name))
        except ValueError:
            return (1, book_name)

    # Dedup and sort books
    sorted_books = sorted(list(set(books)), key=get_sort_key)
    
    formatted_books = []
    i = 0
    n = len(sorted_books)
    
    while i < n:
        start_book = sorted_books[i]
        try:
            start_index = CANONICAL_BOOKS.index(start_book)
        except ValueError:
            formatted_books.append(start_book)
            i += 1
            continue
            
        j = i
        while j + 1 < n:
            next_book = sorted_books[j+1]
            try:
                next_index = CANONICAL_BOOKS.index(next_book)
                if next_index == start_index + (j + 1 - i):
                    j += 1
                else:
                    break
            except ValueError:
                break
                
        if j > i:
            formatted_books.append(f"{start_book}-{sorted_books[j]}")
        else:
            formatted_books.append(start_book)
            
        i = j + 1
        
    return formatted_books

