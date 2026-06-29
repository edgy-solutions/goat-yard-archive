"""Contamination guard for baml_src/query_router.baml.

Validation queries (Set B) are real launch-traffic queries that the prompt
must NOT contain — otherwise "validation" reduces to "did the model copy
the example?" rather than "did the model generalize the rule?"

Run as part of any pre-commit or validation flow. Returns non-zero if any
SET_B query appears as a substring (case-insensitive) inside the prompt
template.

The list is the empirical Set B from the post-launch fix sequence; add to
it whenever a new real query becomes a regression-class case.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT_SRC = ROOT / "baml_src" / "query_router.baml"

# Real launch-traffic queries reserved for VALIDATION. If any of these appears
# in the prompt template, the validation result is contaminated.
SET_B_VALIDATION_QUERIES = [
    "singing psalms",
    "the two thieves",
    "two thieves",                       # variant
    "aquinas",                            # any reference to the name
    "exclusive psalmody",
    "divorce of Israel",
    "circumcision",
    # Add new entries as real launch queries become validation cases.
]


def main() -> int:
    text = PROMPT_SRC.read_text(encoding="utf-8").lower()
    hits = []
    for q in SET_B_VALIDATION_QUERIES:
        if q.lower() in text:
            hits.append(q)

    if hits:
        print("=" * 72)
        print("CONTAMINATION DETECTED in baml_src/query_router.baml")
        print("=" * 72)
        print("The following validation queries appear in the prompt template:")
        for q in hits:
            print(f"  - {q!r}")
        print()
        print("Validation queries must NEVER appear in the prompt. If they do,")
        print("the 'validation' result is just the model copying from the prompt,")
        print("not generalizing the rule. Replace any contaminated example with a")
        print("synthetic phrase that teaches the same shape (e.g. for an unnamed-")
        print("figure example, use 'the Magi' or 'the rich man' instead of 'the")
        print("two thieves' so 'the two thieves' remains a valid test case).")
        return 1

    print(f"OK — none of the {len(SET_B_VALIDATION_QUERIES)} validation queries appear in the prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
