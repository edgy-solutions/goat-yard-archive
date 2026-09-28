"""Born-test: the frontier arm cannot leak the answer and cannot send a note-box crop off the network.

    python test_hebrew_frontier_or.py

No network call, no key, no spend. Pure CPU over the crops and the truth set already on disk.

THE TWO THINGS THIS EXISTS TO STOP, both of which were live defects in the obvious implementation:

  (1) **The answer leaking out in the prompt.** Chris asked for "the local extraction's English/Latin for
      that note" as text context. The extraction field that holds it, `latin_context`, is the footnote's
      candidate line -- and for **11 of the 18 spans it contains the signed truth verbatim**. A runner that
      passed that field through would have scored the arms on a prompt that told them the answer, and the
      resulting `exact` counts would have looked like frontier capability. This test asserts the count of
      leaking spans is what was measured (so the guard cannot be quietly retired as unnecessary), that
      `_ctx` removes every Hebrew character from all 18, and that `_no_hebrew_outbound` REFUSES a body
      built from the raw field.

  (2) **A note-box crop leaving the network.** Chris's scope is A2 only: "no note-box crops leave the
      network". Unused-by-convention is not a guarantee, so this asserts `cells()` emits only A2 paths,
      that every outbound body carries exactly one image, and that no A1 path from the manifest appears
      in any body -- checked against the manifest's own A1 entries, not against a naming convention.

ALSO ASSERTED. n=18 and no other number; temperature 0, reasoning off and `data_collection=deny` really
sit in the wire body; the header passes `require_endpoint` and records the privacy posture honestly,
including that the account toggle is NOT readable via the API. This does NOT assert the provider honoured
the filter, that the reading is right, or that the Latin gloss did not let a model back-translate --
that last one is a measured confound, reported as a split, not something a test can remove."""
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hebrew_aperture_diag as diag
import hebrew_frontier_or as F
from run_header import require_endpoint, HeaderMissingEndpoint

fails = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(f"{name}: {detail}")


def N(t):
    return unicodedata.normalize("NFC", (t or "").strip())


CS = F.cells()
SETS = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}
MAN = {m["span_id"]: m for m in json.load(open(diag.CROPDIR / "manifest.json", encoding="utf-8"))}

print("(1) the set is A2 and nothing else")
# MEMBERSHIP, not count. `len(CS) == 18` was true before AND after 2026-09-27, while two spans entered
# (p138:n6, p596:n2 signed) and two left (p423:n3, p726:n3 blank-crop faulted). The assertion held
# across a change to both halves of the set and reported nothing, which is what a parity proxy does.
_EXPECT = {"p102:n0", "p124:n4", "p138:n5", "p138:n6", "p200:n2", "p217:n2", "p219:n0", "p253:n2",
           "p293:n0", "p360:n0", "p362:n1", "p427:n4", "p491:n1", "p596:n2", "p895:n0", "p897:n4",
           "p900:n4", "p912:n2"}
_GOT = {s["span_id"] for s, _c, _x in CS}
check("cells() yields exactly the expected span set", _GOT == _EXPECT, sorted(_GOT ^ _EXPECT))
check(f"cells() yields {len(_EXPECT)} spans", len(CS) == len(_EXPECT), str(len(CS)))
check("the two blank-crop spans are NOT sendable",
      not ({"p423:n3", "p726:n3"} & _GOT), sorted({"p423:n3", "p726:n3"} & _GOT))
check("every cell is the A2 aperture", F.APERTURE == "A2_spanbox")
check("every span is scorable", all(not s["unscorable"] for s, _c, _x in CS))
check("every span has a ratified span box", all(s["span_box"] for s, _c, _x in CS))
check("p657:n0 is absent (no ratified span box, so not A2-scorable)",
      "p657:n0" not in {s["span_id"] for s, _c, _x in CS})
check("the A1-only span count is the difference (scorable - A2 sendable == 1, p657:n0)",
      sum(1 for s in SETS.values() if not s["unscorable"]) - len(CS) == 1,
      str(sum(1 for s in SETS.values() if not s["unscorable"]) - len(CS)))
check("every A2 crop exists on disk", all(Path(c).exists() for _s, c, _x in CS))

print("\n(2) the answer does NOT leave the network")
raw_leaks = [s["span_id"] for s, _c, _x in CS if N(s["truth"]) in N(s["latin_context"])]
# 11 -> 10 on 2026-09-27, and the membership is the point, not the tally: the two blank-crop spans
# that left (p423:n3, p726:n3) both leaked, and NEITHER of the two signed spans that arrived does.
# p138:n6's note reads "לך nidos, Pagninus, Montanus." and p596:n2's "See Buxtorf. in voce היה." --
# both carry Hebrew, but not the SIGNED Hebrew, so a literal-substring leak test correctly clears them.
#
# That makes p138:n6 the sharpest back-translation probe in the corpus and it must not be mistaken for
# a clean one: the gloss is *nidos*, "nests", and the signed answer קנים IS "nests". A model with Latin
# reaches it without reading a pixel. p596:n2 leans the other way -- its gloss names the WRONG headword
# (היה where the page has סנה), so back-translation actively misleads there. Recorded for item 6.
_LEAK = {"p102:n0", "p124:n4", "p138:n5", "p219:n0", "p360:n0", "p217:n2", "p293:n0", "p427:n4",
         "p491:n1", "p912:n2"}
check("the raw latin_context leaks the signed truth on exactly the known 10 spans",
      set(raw_leaks) == _LEAK, sorted(set(raw_leaks) ^ _LEAK))
check("neither newly signed span leaks its truth into the context",
      not ({"p138:n6", "p596:n2"} & set(raw_leaks)), sorted({"p138:n6", "p596:n2"} & set(raw_leaks)))
check("the guard is load-bearing: a majority of spans would leak unguarded",
      len(raw_leaks) >= len(CS) / 2, f"{len(raw_leaks)} of {len(CS)}")
check("_ctx leaves zero Hebrew characters on all 18",
      not any(F.HEB.search(x) for _s, _c, x in CS))
check("_ctx leaves usable Latin on all 18 (not blanked)",
      all(len(x.replace("•", "").strip()) >= 8 for _s, _c, x in CS))
check("_ctx keeps one bullet per Hebrew run it removed",
      all(x.count("•") == len(F.HEB.findall(s["latin_context"])) for s, _c, x in CS))

s0, c0, x0 = CS[0]
good = F._body("m", x0, "AAAA", False)
check("a body built from _ctx passes the outbound guard", F._no_hebrew_outbound(good) is True)
try:
    F._no_hebrew_outbound(F._body("m", s0["latin_context"], "AAAA", False))
    check("a body built from the RAW field is REFUSED", False, "the guard let the truth through")
except RuntimeError as e:
    check("a body built from the RAW field is REFUSED", "REFUSING" in str(e))
try:
    F._no_hebrew_outbound({"messages": [{"content": N(s0["truth"])}]})
    check("a bare truth string anywhere in the body is REFUSED", False, "guard missed it")
except RuntimeError:
    check("a bare truth string anywhere in the body is REFUSED", True)

print("\n(3) no note-box crop is reachable from here")
a1_paths = {(MAN[s["span_id"]].get("A1_notebox") or {}).get("path") for s, _c, _x in CS}
a1_paths = {p for p in a1_paths if p}
check("the manifest really does hold A1 note-box crops (so the check has teeth)", len(a1_paths) >= 15,
      str(len(a1_paths)))
cell_paths = {c for _s, c, _x in CS}
check("no cell path is an A1 note-box crop", not (cell_paths & a1_paths))
check("every cell path is the manifest's A2 path for that span",
      all(c == MAN[s["span_id"]][F.APERTURE]["path"] for s, c, _x in CS))
bodies = [F._body("m", x, "IMGB64", False) for _s, _c, x in CS]
check("every outbound body carries exactly ONE image",
      all(sum(1 for p in b["messages"][0]["content"] if p["type"] == "image_url") == 1 for b in bodies))
blob = json.dumps(bodies, ensure_ascii=False)
check("no A1 path string appears in any body", not any(Path(p).name in blob for p in a1_paths))
check("no context-strip path appears in any body",
      not any(Path(MAN[s["span_id"]]["context_strip"]).name in blob for s, _c, _x in CS))

print("\n(4) the run settings Chris specified are really on the wire")
b = F._body("openai/gpt-4o-mini", x0, "AAAA", True)
check("temperature 0", b["temperature"] == 0, str(b.get("temperature")))
check("reasoning disabled", b["reasoning"] == {"enabled": False}, str(b.get("reasoning")))
check("provider filter data_collection=deny", b["provider"]["data_collection"] == "deny",
      str(b.get("provider")))
check("usage accounting requested (cost per call comes back)", b["usage"]["include"] is True)
check("structured output requested when the model supports it",
      b.get("response_format") == {"type": "json_object"})
check("structured output NOT requested when it does not",
      "response_format" not in F._body("m", x0, "AAAA", False))
check("max_tokens is set and the >300 output flag exists",
      b["max_tokens"] == F.MAX_TOKENS and F.OUT_TOKEN_FLAG == 300)
check("the prompt forbids nikud, translation, reordering and modernising",
      all(w in F.PROMPT_HEAD for w in ("nikud", "Do not translate", "reorder", "modernise")))
check("the prompt offers ABSTAIN instead of a guess", "ABSTAIN" in F.PROMPT_HEAD)
check("the prompt states no verse citation is available (it is not invented)",
      "No scripture citation is recorded" in b["messages"][0]["content"][1]["text"])

print("\n(4b) reasoning: off where allowed, MINIMUM where the endpoint refuses off")
# WHY. Chris's setting is "reasoning off or minimum effort wherever the API allows, and record what
# was actually applied". `openai/gpt-6-astra` answers 400 "Reasoning is mandatory for this endpoint
# and cannot be disabled" -- 18 of 18 calls failed that way on the first pass. Dropping the arm would
# have reported a capability gap that is really a routing rule, so the ladder steps down and the row
# records the rung that carried the read plus the refusals collected on the way.
LAD = F.REASONING_LADDER
check("the ladder starts with reasoning OFF", LAD[0][0] == {"enabled": False}, str(LAD[0]))
check("the ladder's second rung is MINIMUM effort, not full", LAD[1][0] == {"effort": "minimal"},
      str(LAD[1]))
check("the ladder ends by omitting the parameter, never by raising effort",
      LAD[-1][0] is None and not any((sp or {}).get("effort") in ("high", "medium") for sp, _l in LAD))
check("every rung has a label that can be recorded", all(isinstance(l, str) and l for _sp, l in LAD))
check("_body honours the requested rung",
      F._body("m", x0, "A", False, reasoning={"effort": "minimal"})["reasoning"] == {"effort": "minimal"})
check("the omitted rung sends no reasoning key at all",
      "reasoning" not in F._body("m", x0, "A", False, reasoning=False))
check("the default body still asks for reasoning off",
      F._body("m", x0, "A", False)["reasoning"] == {"enabled": False})
SRC = (HERE / "hebrew_frontier_or.py").read_text(encoding="utf-8")
check("a read row records reasoning_applied, not only what was requested",
      chr(34) + "reasoning_applied" + chr(34) + ": applied" in SRC)
check("refusals on the way down are kept, not swallowed",
      chr(34) + "reasoning_ladder" + chr(34) + ": refusals" in SRC)
check("each arm header carries its own git_head and git_dirty (a resumed arm cannot lie)",
      "_git_head(), " + chr(34) + "git_dirty" + chr(34) + ": _git_dirty()" in SRC)

print("\n(4c) a token cap must not manufacture an abstention")
# WHY. Six arms cannot have reasoning disabled at all. At a 300-token cap `openai/gpt-6-astra` spent
# all 300 on reasoning for 4 of 18 spans and returned EMPTY content with finish_reason "length" --
# which classify() scores `abstain`, reporting a budget artifact as a model declining to guess.
SRC2 = (HERE / "hebrew_frontier_or.py").read_text(encoding="utf-8")
check("the cap leaves room for forced reasoning plus an answer", F.MAX_TOKENS >= 1000,
      str(F.MAX_TOKENS))
check("Chris's >300 median-output FLAG is unchanged by that", F.OUT_TOKEN_FLAG == 300)
check("a truncated read is not treated as done (it gets retried)",
      'o.get("finish_reason") != "length"' in SRC2)
check("an empty read is not treated as done either",
      'and (o.get("hebrew") or "").strip()' in SRC2)
check("scoring keeps the LAST row per (span, model) so a retry is not double-counted",
      'keep[(o["span_id"], o["model"])] = o' in SRC2)
check("scored rows carry a `truncated` flag so the artifact can be audited",
      '"truncated"' in SRC2)
check("retries are for transport and truncation only, never for a wrong answer",
      "never a retry on a wrong answer" in SRC2)

print("\n(5) the reply parser takes the Hebrew from JSON, and from prose when a model ignores JSON")
check("parses a clean JSON reply", F._parse('{"hebrew": "ABC"}') == ("ABC", "json"))
check("parses a fenced JSON reply", F._parse('```json\n{"hebrew": "ABC"}\n```')[0] == "ABC")
check("falls back to text and says so", F._parse("ABC")[1] == "text")
check("a list value is joined, not stringified as a list", "[" not in F._parse('{"hebrew": ["A","B"]}')[0])

print("\n(6) the header names the machine and is honest about the privacy posture")
hdr = F.build_header(host=F.HOST, port=F.PORT, model="multi:26-openrouter-arms",
                     digest_fn=lambda hp, mo, t=None: "n/a:hosted-api",
                     identity_extra={"aperture": F.APERTURE, "n_scorable": len(CS)},
                     extra={"privacy": {"request_filter": "provider.data_collection=deny",
                                        "account_toggle": "not-readable-via-api"}})
check("header passes require_endpoint", require_endpoint(hdr, "frontier") is True)
check("endpoint_host carries the real port", hdr["endpoint_host"] == "openrouter.ai:443",
      hdr.get("endpoint_host"))
check("hosted API is recorded as UNREGISTERED, not blank",
      str(hdr["endpoint_id"]).startswith("UNREGISTERED:"), hdr.get("endpoint_id"))
check("aperture and n are INSIDE the config hash", "aperture" in hdr and "n_scorable" in hdr)
check("git_dirty is recorded (a dirty frontier run is provisional)", "git_dirty" in hdr)
check("the account toggle is recorded as not verifiable, not as verified",
      hdr["privacy"]["account_toggle"] == "not-readable-via-api")
check("no API key appears anywhere in the header", "sk-or-" not in json.dumps(hdr))

print("\n(7) scoring is against the signed truth and nothing else")
src = (HERE / "hebrew_frontier_or.py").read_text(encoding="utf-8")
check("classification is diag.classify against s['truth']", "diag.classify(o[\"gated\"], s[\"truth\"])" in src)
check("no coherence or fluency term in the scorer", not re.search(r"fluen|coheren|plausib\w*\s*=", src))
check("build_set is called WITH the sealed carve-out (n=19/18, not n=10)",
      "build_set(include_sealed=True)" in src and "build_set()" not in src)
check("the C rows are labelled unrecorded-endpoint in the matrix",
      "C:unrecorded-endpoint" in src)
check("the key is read from the environment only, never embedded",
      "sk-or-" not in src and 'os.getenv(KEY_ENV)' in src)

print()
if fails:
    print(f"FAIL: {len(fails)} assertion(s)")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"PASS: A2-only n={len(CS)}, {len(raw_leaks)}/{len(CS)} raw-context leaks blocked, no note-box crop reachable.")
sys.exit(0)
