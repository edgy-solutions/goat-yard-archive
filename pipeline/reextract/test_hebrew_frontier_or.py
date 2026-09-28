"""Born-test: the frontier arm cannot leak the answer and cannot send a note-box crop off the network.

    python test_hebrew_frontier_or.py

No network call, no key, no spend. Pure CPU over the crops and the truth set already on disk.

THE TWO THINGS THIS EXISTS TO STOP, both of which were live defects in the obvious implementation:

  (1) **The answer leaking out in the prompt.** Chris asked for "the local extraction's English/Latin for
      that note" as text context. The extraction field that holds it, `latin_context`, is the footnote's
      candidate line -- and for **11 of the spans it contains the signed truth verbatim** (11 of 18 when
      the leak was measured, 11 of 19 in today's population). A runner that
      passed that field through would have scored the arms on a prompt that told them the answer, and the
      resulting `exact` counts would have looked like frontier capability. This test asserts the count of
      leaking spans is what was measured (so the guard cannot be quietly retired as unnecessary), that
      `_ctx` removes every Hebrew character from all 18, and that `_no_hebrew_outbound` REFUSES a body
      built from the raw field.

  (2) **A note-box crop leaving the network.** Chris's scope is A2 only: "no note-box crops leave the
      network". Unused-by-convention is not a guarantee, so this asserts `cells()` emits only A2 paths,
      that every outbound body carries exactly one image, and that no A1 path from the manifest appears
      in any body -- checked against the manifest's own A1 entries, not against a naming convention.

ALSO ASSERTED. The population as a SET, with every printed total derived from it -- n was 18 and is 19,
and the set is pinned because the two differ by a turnover in both directions, not by a net of one; temperature 0, reasoning off and `data_collection=deny` really
sit in the wire body; the header passes `require_endpoint` and records the privacy posture honestly,
including that the account toggle is NOT readable via the API. This does NOT assert the provider honoured
the filter, that the reading is right, or that the Latin gloss did not let a model back-translate --
that last one is a measured confound, reported as a split, not something a test can remove."""
import json
import pathlib
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hebrew_aperture_diag as diag
import nikud_gate                                                            # noqa: E402
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
# 27 Sept, after the re-cut on Lane A's fixed mapping (dc573ca): the set moved in BOTH directions
# again, which is why it is pinned as a set and the total derived from it.
#   + p423:n3, p726:n3  their A2 crops were blank:uniform=255 because the strip->native map was wrong.
#                       Same ratified box, same crop size, different pixels -- a pure translation
#                       fault, so the boxes were never at issue. Both now cut clean.
#   - p900:n4           its A2 box maps 2 rows past the bottom of its strip (out-of-strip:bottom2).
#                       A geometry fault, which is the only cause approved for a denominator change.
_EXPECT = {"p102:n0", "p124:n4", "p138:n5", "p138:n6", "p200:n2", "p217:n2", "p219:n0", "p253:n2",
           "p293:n0", "p360:n0", "p362:n1", "p423:n3", "p427:n4", "p491:n1", "p596:n2", "p726:n3",
           "p895:n0", "p897:n4", "p912:n2"}
_GOT = {s["span_id"] for s, _c, _x in CS}
check("cells() yields exactly the expected span set", _GOT == _EXPECT, sorted(_GOT ^ _EXPECT))
check(f"cells() yields {len(_EXPECT)} spans", len(CS) == len(_EXPECT), str(len(CS)))
# Reversed on 27 Sept, and the reversal is the point: these two were held out for a fault in OUR
# mapping, not in their boxes. A gate that refuses a crop must also be able to stop refusing it once
# the cause is fixed, or it silently becomes a permanent exclusion list.
_FULL = {s["span_id"]: s for s in diag.build_set(include_sealed=True)}
check("the two formerly-blank spans ARE sendable now that their crops cut clean",
      {"p423:n3", "p726:n3"} <= _GOT, sorted({"p423:n3", "p726:n3"} - _GOT))
check("p900:n4 is NOT sendable: its A2 box maps 2 rows past the bottom of its strip",
      "p900:n4" not in _GOT and "out-of-strip" in (_FULL["p900:n4"]["unscorable"] or ""),
      _FULL["p900:n4"]["unscorable"])
# The crops these two were read on are gone from the live folder and live only in the frozen archive,
# so every read on record for them is about pixels we no longer hold. They are re-run scope, not score.
check("both formerly-blank spans are flagged as re-run scope, their old reads void",
      set(diag.crops_changed()) >= {"p423:n3", "p726:n3"}, sorted(diag.crops_changed()))
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
# p726:n3 joined the leak set on 27 Sept purely by entering the population -- its gloss always leaked,
# there was simply no crop to send it with. p423:n3 entered too and does NOT leak.
# 2026-09-27, after Chris's re-sign batch: THE LITERAL TEST'S REACH SHRANK AND THE LEAKAGE DID NOT.
# `raw_leaks` fell from 11 to 9 and not one context became safer. Both departures are artifacts of
# asking for a literal substring of the SIGNED string:
#   p217:n2  the body layer transcribes the word as הימלא -- with the very MEM Chris overturned. Four of
#            five consonants and a plausible fifth are still handed over. (That the body layer carries
#            the overturned reading is a finding in its own right and is owed a standoff record; it is
#            NOT evidence for the mem, since it is one more reader of the same glyph.)
#   p726:n3  the context holds the pointed form and the signature is now bare, so the points sit between
#            the consonants. The whole word is present and no literal substring matches.
# And the measure was already understating BEFORE today: p253:n2 was depointed at an earlier sitting and
# has never been in this set, though its context gives the word away exactly as p726's does. So the
# historical 11 was an artifact too. Three measures, each claim attached to the one that supports it:
DEP = lambda t: nikud_gate.strip_nikud(N(t))
bare_leaks = [s["span_id"] for s, _c, _x in CS if DEP(s["truth"]) in DEP(s["latin_context"])]


def _unruled(sid, truth):
    """Every string one occurrence of the ruled letter away from the signature -- a SET, not "the"
    pre-batch string. Reversing a re-sign is ambiguous by construction (`diag._resign` refuses p423:n3,
    which now holds two gimels) and the ambiguity is real, so the test quantifies over all of them."""
    frm, to, _why = diag.GLYPH_RESIGN[sid]
    return {truth[:i] + frm + truth[i + 1:] for i, c in enumerate(truth) if c == to}


TRU = {s["span_id"]: s["truth"] for s, _c, _x in CS}
over_leaks = [s["span_id"] for s, _c, _x in CS
              if s["span_id"] in diag.GLYPH_RESIGN and s["span_id"] not in bare_leaks
              and any(DEP(a) in DEP(s["latin_context"]) for a in _unruled(s["span_id"], s["truth"]))]
_ALL_LEAK = set(raw_leaks) | set(bare_leaks) | set(over_leaks)
check("the literal test sees 9 of 19 -- and that is the reach of the TEST, not the leakage",
      len(raw_leaks) == 9 and set(raw_leaks) <= _ALL_LEAK, sorted(raw_leaks))
check("nikud-insensitively it is 11, and the two it adds are p253:n2 and p726:n3",
      set(bare_leaks) - set(raw_leaks) == {"p253:n2", "p726:n3"},
      sorted(set(bare_leaks) - set(raw_leaks)))
check("p253:n2 was never in the typed leak set, so the old figure was understated too",
      "p253:n2" in bare_leaks and "p253:n2" not in raw_leaks)
check("p217:n2 leaks a reading one ruled letter from the signature (the body layer's own mem)",
      over_leaks == ["p217:n2"], sorted(over_leaks))
check("p423:n3's re-sign is NOT reversible to one string, and it leaks under none of the two",
      len(_unruled("p423:n3", TRU["p423:n3"])) == 2 and "p423:n3" not in _ALL_LEAK)
check("so the population whose context gives the answer away is 12 of 19, not 9 and not 11",
      len(_ALL_LEAK) == 12 and len(CS) == 19, f"{len(_ALL_LEAK)} of {len(CS)}")
check("neither newly signed span leaks its truth into the context, by any of the three measures",
      not ({"p138:n6", "p596:n2"} & _ALL_LEAK), sorted({"p138:n6", "p596:n2"} & _ALL_LEAK))
check("the guard is load-bearing: a majority of spans would leak unguarded",
      len(_ALL_LEAK) >= len(CS) / 2, f"{len(_ALL_LEAK)} of {len(CS)}")
check("and the guard does not depend on any of that -- it strips Hebrew runs, not known strings",
      not any(F.HEB.search(x) for _s, _c, x in CS if _s["span_id"] in _ALL_LEAK))
check(f"_ctx leaves zero Hebrew characters on all {len(CS)}",
      not any(F.HEB.search(x) for _s, _c, x in CS))
check(f"_ctx leaves usable Latin on all {len(CS)} (not blanked)",
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

print("\n(8) --span bounds what is SENT; the crop hash bounds what is SCORED")
# These are two different jobs and the suite checks them separately on purpose. A scope filter is a
# spend control and a human types it, so it must fail loud. A hash is an evidence control and no human
# touches it, so it must be complete.
_SCOPE = ["p423:n3", "p726:n3", "p138:n6", "p596:n2"]
_sc = F.cells(_SCOPE)
check(f"--span returns exactly the {len(_SCOPE)} named spans, in the population's order",
      [s["span_id"] for s, _c, _x in _sc] == [x for x in (s["span_id"] for s, _c, _x in F.cells())
                                              if x in set(_SCOPE)],
      [s["span_id"] for s, _c, _x in _sc])
check("an empty scope is not the same as no scope: [] sends nothing",
      F.cells([]) == [] and len(F.cells()) == len(CS))

# Both directions of the fail-loud. An unknown id and a refused crop are different facts and the error
# has to say which, because one is a typo and the other is a box that needs redrawing.
for bad, want in (("p999:n9", "UNKNOWN span id"), ("p900:n4", "crop-fault")):
    try:
        F.cells([bad])
        check(f"--span {bad} refuses to silently send zero cells", False, "no exception raised")
    except RuntimeError as e:
        check(f"--span {bad} raises and names the cause ({want})", want in str(e), str(e)[:90])

check("every sendable crop has a hash, so the run header can never record a null",
      all(F.crop_sha(c) for _s, c, _x in F.cells()))
check("crop_sha of a path that does not exist is None, not a hash of nothing",
      F.crop_sha(diag.CROPDIR / "no_such_crop.png") is None)

# The evidence rule, measured against the real artifact rather than asserted about the source.
_MUTE = F.stale_reads()
_MUTE_SPANS = {sid for sid, _m in _MUTE}
check("the void-read set is exactly the 3 spans whose A2 crop was re-cut",
      _MUTE_SPANS == {"p423:n3", "p726:n3", "p900:n4"}, sorted(_MUTE_SPANS))
check("a pre-hash read on an UNCHANGED crop is still evidence (the rule is not 'distrust the old')",
      not (_MUTE_SPANS & {"p102:n0", "p138:n5", "p217:n2", "p912:n2"}))
check("every void read names its cause",
      all(v.startswith(("crop-sha-mismatch:", "pre-hash-read-on-recut-crop")) for v in _MUTE.values()))
_RS = F.rows()
check("no void read survives into the scored rows",
      not ({(o["span_id"], o["model"]) for o in _RS} & set(_MUTE)))
# The sendable population decomposes with no remainder, and the remainder IS the re-run scope. Every
# term is derived from the artifact: a span is scored, or its reads were taken on a crop we no longer
# hold, or it has no reads at all. A count alone would hide which.
_SENDABLE = {s["span_id"] for s, _c, _x in CS}
_SCORED = {o["span_id"] for o in _RS}
_VOIDED = _SENDABLE & _MUTE_SPANS                     # crop re-cut: reads exist but are mute
_NEVER = _SENDABLE - _SCORED - _VOIDED                # signed after the run: no reads at all
check("the sendable population decomposes with no remainder: scored + voided + never-run",
      len(_SENDABLE & _SCORED) + len(_VOIDED) + len(_NEVER) == len(_SENDABLE),
      f"{len(_SENDABLE & _SCORED)} + {len(_VOIDED)} + {len(_NEVER)} != {len(_SENDABLE)}")
check("the spans with byte-identical crops keep every read, re-scored and NOT re-sent",
      len(_SENDABLE & _SCORED) == 15 and not (_SENDABLE & _SCORED) & _MUTE_SPANS,
      sorted(_SENDABLE & _SCORED))
check("the re-run scope is exactly the 4 spans Chris named: 2 re-cut crops + 2 newly signed",
      _VOIDED | _NEVER == {"p423:n3", "p726:n3", "p138:n6", "p596:n2"}, sorted(_VOIDED | _NEVER))
check("and the two halves of that scope are there for DIFFERENT reasons",
      _VOIDED == {"p423:n3", "p726:n3"} and _NEVER == {"p138:n6", "p596:n2"},
      f"voided={sorted(_VOIDED)} never-run={sorted(_NEVER)}")
# p900:n4 is the one that cannot be repaired by re-running: its crop moved AND its crop is refused, so
# its 26 reads go mute with no route back until the box is redrawn. That is the real cost of the
# denominator change and it must be visible, not folded into "unscorable".
check("p900:n4's reads are void AND it is unsendable -- a debt, not a re-run",
      "p900:n4" in _MUTE_SPANS and "p900:n4" not in {s["span_id"] for s, _c, _x in CS})

print("\n(9) the contact-sheet gate: approved pixels are the sent pixels")
import tempfile                                                            # noqa: E402
_SC = ["p138:n6", "p423:n3", "p596:n2", "p726:n3"]
_cs = F.cells(_SC)


def _sheet(mutate=None):
    """A copy of the live sidecar, optionally damaged, written somewhere disposable."""
    rec = json.loads(F.SHEET.read_text(encoding="utf-8")) if F.SHEET.exists() else {"crop_sha16": {}}
    if mutate:
        mutate(rec)
    p = pathlib.Path(tempfile.mkdtemp()) / "sheet.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    return p


def _refuses(fn, want, label):
    try:
        fn()
        check(label, False, "no exception raised -- the gate did not fire")
    except RuntimeError as e:
        check(label, want in str(e), str(e)[:110])


check("the live sidecar exists and covers every span in the re-run scope",
      F.SHEET.exists() and set(_SC) <= set(json.loads(F.SHEET.read_text(encoding="utf-8"))["crop_sha16"]))
check("the gate PASSES on the real sheet (a gate that refuses everything protects nothing)",
      F.sheet_gate(_cs)["sheet"].endswith(".html"))
_refuses(lambda: F.sheet_gate(_cs, pathlib.Path("no_such_sheet.json")),
         "no contact sheet", "no sheet at all -> refuse, and say to build one")
_refuses(lambda: F.sheet_gate(_cs, _sheet(lambda r: r["crop_sha16"].pop("p596:n2"))),
         "not on the contact sheet", "a span the sheet never showed -> refuse")
_refuses(lambda: F.sheet_gate(_cs, _sheet(lambda r: r["crop_sha16"].update({"p423:n3": "0" * 16}))),
         "crop changed since the sheet", "a crop re-cut after approval -> refuse, naming both hashes")
# The one thing no check can verify is that a human looked. So it is not dressed up as verification:
# the flag is REQUIRED, and the header records it as a claim.
_refuses(lambda: F.run(None, _SC), "pass --approved",
         "no --approved -> refuse before the catalog pull, so a refusal costs nothing")
check("the approval is recorded as a claim, never as a verification",
      "NOT machine-verifiable" in src and "RECORDED CLAIM" in src)
check("the gate runs BEFORE the catalog pull (a refusal must not look like a started run)",
      src.index("sheet = sheet_gate(cs)") < src.index("cat = catalog(refresh=True)"))

print("\n(10) re-cut vs gone, and Chris's conditional A1 term")
import hebrew_contact_sheet as SH                                            # noqa: E402

_rc, _gone, _ch = diag.crops_recut(F.APERTURE), diag.crops_gone(F.APERTURE), diag.crops_changed(F.APERTURE)
check("the two causes partition 'changed' with no overlap and no remainder",
      set(_rc) | set(_gone) == set(_ch) and not (set(_rc) & set(_gone)),
      "recut %d + gone %d = changed %d" % (len(_rc), len(_gone), len(_ch)))
check("'gone' means no file: every one of them has a live sha of None",
      all(diag.crop_sha(sid, F.APERTURE) is None for sid in _gone),
      "gone: %s" % (sorted(_gone) or "none in this aperture"))
check("a vanished crop can never expand the send scope (nothing exists to send)",
      not (set(diag.crops_gone(F.APERTURE)) & set(SH.scope(include_a1=True)[0])))

# The sending path and the note-box aperture must not meet. Asserted structurally, not by reading
# ARMS or trusting a comment: every crop cells() hands out is an A2 file.
check("no note-box crop is reachable from the sending path",
      all(pathlib.Path(c).name.endswith("_%s.png" % F.APERTURE) for _s, c, _x in F.cells()),
      "apertures on the wire: %s" % sorted({pathlib.Path(c).name.split("_n")[-1][2:] for _s, c, _x in F.cells()}))

# RE-PINNED 2026-09-27 post-clip (laneB 2c8554a + da13758 = Lane A 4b2e0de + 36c36c4).
# This read "the A1 term is non-empty, so the exclusion below is a decision and not a vacuous pass"
# and it held these four: the spans whose A1 crop dc573ca had widened by the canvas filler. The clip
# emptied it, and the reason matters -- those four A1 crops are byte-identical to the 2026-09-20
# archive again, so there is nothing re-cut about them and their reads are evidence about the pixels
# on disk once more. Empty because the crops came back, not because a measurement died. The term
# stays in the code, with its vacuity stated, because the condition on it can still fire.
_A1_WAS = {"p217:n2", "p219:n0", "p293:n0", "p895:n0"}
_a1 = SH.a1_moved()
check("the A1 term is EMPTY post-clip: there is nothing for --include-a1 to fold in",
      _a1 == [], "%d span(s): %s" % (len(_a1), " ".join(_a1)))
check("empty because the crops came back: all four spans it held are byte-identical to as-sent",
      all(diag.crop_sha(s, "A1_notebox") == diag.crop_sha(s, "A1_notebox", as_sent=True)
          for s in _A1_WAS),
      {s: (diag.crop_sha(s, "A1_notebox"), diag.crop_sha(s, "A1_notebox", as_sent=True))
       for s in sorted(_A1_WAS)})
check("and not because the measurement died: crops_recut still names A1 re-cuts, they are simply "
      "not sendable-with-unchanged-A2",
      len(diag.crops_recut("A1_notebox")) > 0, sorted(diag.crops_recut("A1_notebox")))
# The three checks below are VACUOUS while the term is empty. Said out loud rather than left to look
# like passes: what they assert is true of no span, and the content moved to the two checks above.
check("every span in the A1 term has a byte-identical A2 crop -- it was sent the pixels it holds",
      all(diag.crop_sha(sid, F.APERTURE) == diag.crop_sha(sid, F.APERTURE, as_sent=True) for sid in _a1))
check("so none of its reads are void: an A1 re-cut mutes nothing",
      not ({sid for sid, _m in F.stale_reads()} & set(_a1)))
check("the A1 term is OUT of the default scope", not (set(_a1) & set(SH.scope()[0])))
check("and folding it in is one flag, not a code change",
      set(SH.scope(include_a1=True)[0]) == set(SH.scope()[0]) | set(_a1))
check("the sheet on disk was built WITHOUT it, and says so",
      json.loads(F.SHEET.read_text(encoding="utf-8"))["a1_term_folded_in"] is False)

# THE TRIPWIRE, still armed and now measured on the far side of the fix. Chris's condition was Lane
# A's x-origin fix landing; it landed on 2026-09-27 and it is not an x-origin change -- it clips the
# right edge to the band and clamps a left edge inside 2px of slop. So dx is still 0 everywhere, the
# widths moved the other way this time (dw -334 where dc573ca had given +300..+450), and the check
# keeps its job: if a future mapper change moves a page origin, the A1 term goes live and this fails
# with the instruction attached.
_shifts = diag.a1_x_shifts()
_livex = sorted(sid for sid, v in _shifts.items() if v and any(dx for dx, _dw in v))
check("no A1 rect has moved in x, so Chris's condition has NOT fired",
      not _livex,
      "x-origin shift now visible on %s -- Lane A's fix has landed, the A1 term is LIVE, fold it in "
      "with --include-a1 and rebuild the sheet before sending" % " ".join(_livex) if _livex
      else "dx=0 on all %d re-cut A1 rects; widths grew %s" % (
          len(_shifts), sorted({dw for v in _shifts.values() if v for _dx, dw in v})))
check("the x-shift measurement pairs rects or refuses to, never silently mispairs",
      all(v is None or len(v) >= 1 for v in _shifts.values()))

print()
# THE FAILURE GATE USED TO SIT HERE, above section 11, so section 11 ran only in a run where nothing
# else had failed -- silent in exactly the runs where the page geometry is most likely to be broken.
# A gate must be able to see the failure it is accountable for. It now sits below, where the last
# check is still inside it. Found by reading my own patch script, which anchored on the PASS line.
print("\n(11) the band clip -- Lane A's mechanism, measured here after the clip landed")
_BO = diag.band_overshoot()
_bo_a2 = [b for b in _BO if b["aperture"] == "A2_spanbox"]
_bo_a1 = {b["span_id"] for b in _BO if b["aperture"] == "A1_notebox"}
# THE CHECK THAT GATES THE SPEND. presplit's filler cannot reach a crop we are about to pay for unless
# an A2 box overshoots its band, and none does. Measured, not assumed -- and measured after the re-cut,
# because dc573ca stopped clamping and a clamp is what was hiding this.
check("no A2 span box overshoots its band, so no crop in the send scope is over filler",
      _bo_a2 == [], [(b["span_id"], b["over"]) for b in _bo_a2])
_exp_rects = sum(len(m[ap]["native_rects"]) for m in MAN.values()
                 for ap in ("A2_spanbox", "A1_notebox") if m.get(ap))
check("the measurement is not vacuous: it examined every rect the manifest holds",
      diag.band_overshoot.rects_examined == _exp_rects and _exp_rects >= len(CS),
      f"{diag.band_overshoot.rects_examined} examined, {_exp_rects} in the manifest")
# RE-PINNED 2026-09-27, post-clip. What these checks said pre-clip, kept because the history is the
# evidence: nine A1 note boxes were over the filler. Five were refused loudly (right column, mapped x1
# past the 3584px page) and four were SILENT (left column, overshoot inside the page, invisible to a
# page-width gate). p217:n2 was in both populations at once -- flagged out-of-strip and still producing
# a crop with 330px of filler in it. I wrote two of these to fail the day the clip landed. Both did.
_NINE_PRE_CLIP = {"p124:n4", "p200:n2", "p217:n2", "p219:n0", "p293:n0",
                  "p596:n2", "p726:n3", "p895:n0", "p900:n4"}
_CLIP = diag.clipped()
_clip_a1 = {c["span_id"] for c in _CLIP if c["aperture"] == "A1_notebox"}
_clip_a2 = {c["span_id"] for c in _CLIP if c["aperture"] == "A2_spanbox"}
# THE CHECK THAT GATES THE SPEND, now from the mapper's own flag and not only from my band arithmetic.
# Two independent measures, and they agree: no A2 rect overshot its band, and no A2 rect was cut.
check("not one A2 rect was CLIPPED either: the send scope's pixels are untouched by the fix",
      _clip_a2 == set(), sorted(_clip_a2))
check("the clip cut exactly the nine A1 boxes this lane counted pre-clip -- no more, no fewer",
      _clip_a1 == _NINE_PRE_CLIP,
      "cut %d: %s" % (len(_clip_a1), sorted(_clip_a1)))
check("every band overshoot is gone, so no box is outside its band any more",
      _BO == [], _BO)
# CORRECTING A PREDICTION OF MINE. This check used to read "p217:n2 is not merely an overshoot -- its
# rect starts left of every band, so a clip cannot fix it". False: Lane A's fix carries a 2px canvas
# slop clamp as well as the band clip, and -2 is inside the slop, so the mapped rect starts at 0 and
# the crop carries BOTH flags. I under-credited the fix and said so in the report.
_p217 = MAN["p217:n2"]["A1_notebox"]
check("p217:n2's -2 IS repaired -- by the 2px slop clamp, not by the band clip, and both are flagged",
      _p217["rect_edges"][0] == ["band-clipped", "canvas-slop-clamped"]
      and _p217["native_rects"][0][0] == 0, _p217["rect_edges"])
# And the fault table is down to one, which is a DIFFERENT fact about the same span. My `crop_fault`
# reports the ratified STRIP box, which still begins at -2; the clip repaired the MAPPED rect. One is
# an editorial debt against the box, the other is the geometry that cut the pixels. Conflating them
# would retire a debt nobody paid.
_a1f = diag.crop_faults("A1_notebox")
check("the five loud page-width refusals are gone: those five A1 crops exist now",
      not [k for k, f in _a1f.items() if "exceeds page width" in f]
      and all(MAN[s].get("A1_notebox") for s in
              ("p124:n4", "p200:n2", "p596:n2", "p726:n3", "p900:n4")), sorted(_a1f))
check("the one A1 fault left is p217:n2's ratified STRIP box at -2, not its mapped rect",
      set(_a1f) == {"p217:n2"} and "beyond=left2" in _a1f["p217:n2"]
      and _p217["native_rects"][0][0] == 0, _a1f)
check("p217:n2 is flagged AND produced a crop, so a recorded fault is still not a refusal",
      "p217:n2" in _a1f and MAN["p217:n2"].get("A1_notebox"), _a1f.get("p217:n2"))

print()
if fails:
    print(f"FAIL: {len(fails)} assertion(s)")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"PASS: A2-only n={len(CS)}, {len(_ALL_LEAK)}/{len(CS)} context leaks blocked "
      f"({len(raw_leaks)} of them literal), no note-box crop reachable.")
sys.exit(0)
