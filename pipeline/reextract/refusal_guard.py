"""REFUSAL-HONOR guard — the THIRD sibling of the "nothing here" law (crop_gate = intake gate,
escalation intake-gate = adjudication precondition, THIS = the model's OWN refusal honored).

p4 (frontispiece of Gill): the VLM answered truthfully — "The provided image is not a strip of
footnotes... It is a title page or frontispiece... There are no footnotes present... No output can be
generated" — and the pipeline wrapped that honest refusal as note [^1] and shipped it OK. The pipeline
had no slot for the answer "nothing here," so the model's honesty became a fabrication. This parser
gives the answer a slot: refusal-shaped output -> no_apparatus signal, not note content.

Detects MODEL meta-language a 1766 footnote could never contain (a real note is a Latin/Hebrew citation,
never "no output can be generated"). Deterministic; born-tested with p4 as the fixture.
"""
import re

# strong refusal signatures — unambiguous model meta-commentary, calibrated on p4
_SIGNATURES = [
    r"\bis not a strip of footnotes\b",
    r"\bprovided image is not\b",
    r"\b(?:there are |are )?no footnotes?(?: are)? present\b",
    r"\bno footnote lines?\b",
    r"\bno output can be generated\b",
    r"\bcannot (?:be )?generate(?:d)?\b",
    r"\bdoes not (?:match|contain)\b",
    r"\bit is a (?:title page|frontispiece)\b",
    r"\bno apparatus\b",
    r"\bunable to (?:transcribe|read|find)\b",
    r"\bimage (?:is|does not|contains no)\b",
]
_RX = re.compile("|".join(_SIGNATURES), re.I)

def is_refusal(text):
    """True iff the text is a MODEL refusal / meta-statement ('nothing here'), not footnote content."""
    return bool(_RX.search(text or ""))

def check_notes(notes):
    """(is_refusal, matched_phrase) for an extracted-notes list. A page whose 'notes' are really the
    model saying there's nothing to transcribe -> honor it as no_apparatus upstream."""
    joined = " ".join((n["text"] if isinstance(n, dict) else n) for n in (notes or []))
    m = _RX.search(joined)
    return bool(m), (m.group(0) if m else None)

if __name__ == "__main__":
    import sys, json
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    from pathlib import Path
    res = {r["page"]: r for r in json.loads((Path(__file__).parent / "truthset_review/truthset_results.json").read_text(encoding="utf-8"))}
    p4 = res[4]["extracted"][0]["text"]
    print("p4 refusal detected:", is_refusal(p4), "| matched:", check_notes(res[4]["extracted"])[1])
    real = "סגר עליהם clausit viam illis, Pagninus, præclusit sese illis, Vatablus."
    print("real footnote refusal? (want False):", is_refusal(real))
