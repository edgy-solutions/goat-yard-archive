"""E-10 — is BAML's expansion net-positive as retrieval search_text?

The 2026-07-13 psalmist incident surfaced that the *success* path lands
MATTHEW 26:30 at rank 4/10-11 while the *punt* path lands it at rank 1.
The only difference is whether BAML's expansion is used as the retrieval
search_text. This experiment isolates that variable across query classes.

Method: for each query, hold the entity boost constant (the raw manifest
from get_relevant_entities), and compare where the known-right chunk
lands under two retrieval conditions:
  RAW  — search_gill(query=raw, original_query=raw). search_gill's
         include_original guard means the raw query is used once.
  EXP  — search_gill(query=baml_expansion, original_query=raw). Both
         the raw query AND the expansion contribute (search_gill adds
         both to BM25 and embedding sides). So EXP = raw + expansion.

Lower rank = better. Result (2026-07-13, gya-test, Gen-Num + Matt-John):

  query                        class            raw  exp  winner
  was gill an exclusive psalm* narrow-inflect    1    3   RAW
  should we sing only psalms   paraphrase        4    3   exp
  what does Gill say re Cain   plain             1    1   tie
  what does Gill say baptism   plain             1    1   tie
  who was Melchizedek          plain             1    1   tie
  the scapegoat ritual         compound          2    3   RAW
  the tower of Babel           plain             1    1   tie
  Noah and the flood           plain             1    1   tie
  the golden calf              plain             1    3   RAW
  monergism in salvation       narrow (ROMANS)  >12  >12  tie (corpus gap)

  RAW wins 3, expanded wins 1, ties 6 (n=10).

Conclusion: adding BAML's expansion on top of the raw query is
net-negative-or-neutral for 9/10 query classes. It HURTS narrow/
compound/named queries (dilutes the focused signal — 'psalmist' +
'songs of David' pulls retrieval toward David) and HELPS only
paraphrase-droughts where the raw query lacks vocabulary. The entity
boost (thesaurus anchors + two-pass) now carries the concept-bridging
that expansion-as-search-text used to be needed for.

This is decision evidence for ADR-0013 (c): retrieve on the raw query;
route BAML's expansion only to the two-pass entity lookup (where it
demonstrably helps — the paraphrase concept bridge) rather than to the
retrieval search_text (where it mostly hurts). NOT yet implemented —
gated on validation against the 28-case reference eval set.

Re-runnable: requires the debug backend at localhost:8001 and Weaviate
at 192.168.1.54. See the inline CASES list.
"""
import asyncio
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["WEAVIATE_URL"] = "http://192.168.1.54:80"
os.environ["WEAVIATE_GRPC_HOST"] = "192.168.1.53"
os.environ["WEAVIATE_GRPC_PORT"] = "50051"
os.environ["LITELLM_PROXY_URL"] = "http://localhost:4000"
os.environ.setdefault("APP_ENV", "e10-probe")

sys.path.insert(0, str(Path("C:/Users/cnogr/git/goat-yard-archive")))
from dotenv import load_dotenv
load_dotenv()
from backend.gill_search import GillSearchEngine  # noqa: E402


BACKEND = "http://localhost:8001/api/search"

CASES = [
    ("was gill an exclusive psalmist?", "MATTHEW 26:30", "narrow-inflect"),
    ("should we sing only psalms in worship?", "MATTHEW 26:30", "paraphrase"),
    ("what does Gill say about Cain", "GENESIS 4", "plain"),
    ("what does Gill say about baptism", "MATTHEW 3", "plain"),
    ("who was Melchizedek", "GENESIS 14", "plain"),
    ("the scapegoat ritual", "LEVITICUS 16", "compound"),
    ("the tower of Babel", "GENESIS 11", "plain"),
    ("Noah and the flood", "GENESIS 7", "plain"),
    ("the golden calf", "EXODUS 32", "plain"),
    ("monergism in salvation", "ROMANS", "narrow-term"),
]


def dbg(text: str, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            body = json.dumps({"query": text, "debug": True}).encode()
            req = urllib.request.Request(
                BACKEND, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(3)


async def main():
    engine = GillSearchEngine()
    await engine.connect()
    try:
        print(f'{"query":38} {"class":13} {"raw":>4} {"exp":>4} winner')
        print("-" * 74)
        raw_w = exp_w = tie = 0
        rows = []
        for query, target, cls in CASES:
            try:
                d = dbg(query)
            except Exception:
                print(f"{query[:38]:38} ERR")
                continue
            st = d.get("stages") or {}
            manifest = st.get("available_entities") or []
            baml_exp = st.get("baml_expansion") or st.get("lookup_query") or query

            def rk(res):
                for i, c in enumerate(res, 1):
                    if target in (c.get("verse_ref") or ""):
                        return i
                return None

            rr = rk(await engine.search_gill(query=query, entities=manifest, limit=12, original_query=query))
            re_ = rk(await engine.search_gill(query=baml_exp, entities=manifest, limit=12, original_query=query))
            rv, ev = rr or 99, re_ or 99
            w = "RAW" if rv < ev else ("exp" if ev < rv else "tie")
            if w == "RAW":
                raw_w += 1
            elif w == "exp":
                exp_w += 1
            else:
                tie += 1
            rows.append({"query": query, "class": cls, "target": target,
                         "raw_rank": rr, "exp_rank": re_, "winner": w})
            print(f"{query[:38]:38} {cls:13} {str(rr or '>12'):>4} {str(re_ or '>12'):>4} {w}")
        print("-" * 74)
        print(f"RAW wins:{raw_w}  exp wins:{exp_w}  ties:{tie}  n={len(CASES)}")

        out = Path(__file__).parent / "e10_raw_vs_expanded_results.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump({"rows": rows, "raw_wins": raw_w, "exp_wins": exp_w, "ties": tie}, f, indent=2)
        print(f"\nRaw: {out}")
    finally:
        await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
