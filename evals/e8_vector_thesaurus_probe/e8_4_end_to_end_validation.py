"""E-8.4 — end-to-end validation of the ADR-0011 v2 exact→vector ladder.

Loads the modified backend/query_expansion.py, initializes the vector
thesaurus against real LiteLLM embeddings, and calls expand_query with
three query classes:

  CHRIS_TYPO_UI — Chris's original UI query that produced the 2026-07-12
                   drought. Must bridge via vector tier.
  SHOULD_MATCH  — additional typo/inflection/reordering shapes.
  SHOULD_NOT_MATCH — real other theological queries that must stay
                     silent (or land in near-miss log without firing).

Uses the LiteLLM proxy at localhost:4000 (same port-forward as E-8.1).
"""
import asyncio
import io
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path("C:/Users/cnogr/git/goat-yard-archive")))

from backend.query_expansion import (  # noqa: E402
    expand_query,
    init_vector_thesaurus,
    FUZZY_EDIT_DISTANCE,
    NEAR_MISS_LOG_MAX,
)

LITELLM_URL = "http://localhost:4000/embeddings"
MODEL = "qwen3-embedding"


async def embed(text: str) -> list[float]:
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(
        LITELLM_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer anything"},
    )
    # urllib is sync but we're using it under asyncio; run in thread-pool
    loop = asyncio.get_running_loop()
    def _blocking():
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    d = await loop.run_in_executor(None, _blocking)
    return d["data"][0]["embedding"]


CHRIS_UI_QUERY = "what was gill's opinion on the exlusive psalmody debate?"

SHOULD_MATCH = [
    ("exclusive psalmody", "exact"),          # bare — exact regex hits
    ("exlusive psalmody", "vector"),          # typo — Chris's UI form
    ("EXCLUSIVE PSALMODY", "exact"),          # case-insensitive
    ("exclusive psalms", "vector"),           # inflection
    ("psalmody exclusive position", "vector"), # reordering
    ("paktum salutis", "vector"),             # typo (may miss at 0.15 — 0.161 boundary)
    ("monergistic", "vector"),                # inflection
    ("regulative principle in worship", "vector"),  # inflection (0.167 — miss at 0.15)
]

SHOULD_NOT_MATCH = [
    "covenant of grace",
    "universal atonement in Christ",
    "what does Gill say about Cain",
    "did Esau eat pizza",
    "psalm singing in the Old Testament",     # adjacent, must not fire
    "justification by faith",                  # adjacent to imputation/monergism
    "who was Aquinas",
]


async def main():
    print("=" * 100)
    print(f"E-8.4 end-to-end — FUZZY_EDIT_DISTANCE={FUZZY_EDIT_DISTANCE} NEAR_MISS_LOG_MAX={NEAR_MISS_LOG_MAX}")
    print("=" * 100)

    print("\n[1] Initializing vector thesaurus...")
    await init_vector_thesaurus(embed)

    print("\n[2] Chris's original UI query — the incident case")
    print("-" * 100)
    expanded, matches, near_misses, _degraded = await expand_query(CHRIS_UI_QUERY, embed_fn=embed)
    print(f"  query:         {CHRIS_UI_QUERY!r}")
    print(f"  matches:       {matches}")
    print(f"  near_misses:   {near_misses}")
    print(f"  expanded:      {expanded!r}")
    chris_ok = any(m["term"] == "exclusive psalmody" for m in matches)
    print(f"  Chris's typo case BRIDGED?  {'YES' if chris_ok else 'NO'}")

    print("\n[3] SHOULD-MATCH cases")
    print("-" * 100)
    print(f"  {'query':50} {'expected':10} {'method':10} {'distance':>10} {'expanded?':>10}")
    smatch_pass = 0
    smatch_total = 0
    for q, expected_method in SHOULD_MATCH:
        smatch_total += 1
        expanded, matches, near, _degraded = await expand_query(q, embed_fn=embed)
        # Did we get any match?
        got_match = bool(matches)
        method = matches[0]["method"] if matches else "-"
        dist = matches[0]["distance"] if matches else float("nan")
        near_str = ", ".join(f"{n['term']}={n['distance']:.3f}" for n in near) or ""
        print(f"  {q[:44]:44} {expected_method:8} {method:8} {dist:>7.4f} {str(got_match):>5}  near:{near_str[:40]}")
        if got_match:
            smatch_pass += 1

    print(f"\n  SHOULD-MATCH pass rate: {smatch_pass}/{smatch_total}")

    print("\n[4] SHOULD-NOT-MATCH cases")
    print("-" * 100)
    print(f"  {'query':50} {'fired?':>8} {'near-misses':>50}")
    snot_pass = 0
    for q in SHOULD_NOT_MATCH:
        expanded, matches, near, _degraded = await expand_query(q, embed_fn=embed)
        fired = bool(matches)
        near_str = ", ".join(f"{n['term']}={n['distance']:.3f}" for n in near) or "(none)"
        print(f"  {q[:50]:50} {'YES' if fired else 'no':>8} {near_str[:50]:>50}")
        if not fired:
            snot_pass += 1

    print(f"\n  SHOULD-NOT-MATCH silence rate: {snot_pass}/{len(SHOULD_NOT_MATCH)}")

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    print(f"  Chris's typo case bridged: {chris_ok}")
    print(f"  SHOULD-MATCH: {smatch_pass}/{smatch_total} caught")
    print(f"  SHOULD-NOT-MATCH: {snot_pass}/{len(SHOULD_NOT_MATCH)} silenced")
    print()
    if chris_ok and snot_pass == len(SHOULD_NOT_MATCH):
        print("  PRIMARY WIN: Chris's incident case is fixed. No false-positives on should-not set.")
    else:
        print("  ATTENTION: check individual case results above.")


if __name__ == "__main__":
    asyncio.run(main())
