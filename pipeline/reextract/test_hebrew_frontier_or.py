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
ran = []            # every check that actually EXECUTED -- see CHECK_FLOOR at the bottom of this file


def check(name, cond, detail=""):
    ran.append(name)
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
_MUTE_SPANS = {sid for sid, _m, _h in _MUTE}
# THE KEY IS THE READ. Keyed on (span, model) this muted a live read because a dead one shared its
# cell, and 52 approved, sent, paid-for reads on p423:n3 and p726:n3 were dropped from scoring while
# `run()` would have re-sent them. Asserted on the shape AND on the consequence.
check("the void is keyed on the read -- cell plus the pixels it was shown, not the cell alone",
      all(isinstance(k, tuple) and len(k) == 3 for k in _MUTE), sorted(_MUTE)[:2])
_LIVE = F.live_reads()
check("a cell holding a dead read AND a live read keeps the live one",
      all(F.read_key(o) not in _MUTE for o in _LIVE))
for _sid, _h in (("p423:n3", "7059fcf05ea87bf6"), ("p726:n3", "631456a69a2da6a2")):
    _n_live = sum(1 for o in _LIVE if o["span_id"] == _sid and o.get("crop_sha16") == _h)
    _n_mute = sum(1 for k in _MUTE if k[0] == _sid)
    check(f"{_sid}: reads at the approved hash survive the void beside {_n_mute} retired reads",
          _n_live == 26 and _n_mute == 26, f"live={_n_live} mute={_n_mute}")
# That they reach the SCORED rows is asserted below, against the approved hashes, once `_RS` exists.
# This was a literal set of span_ids, and it had to be edited on 2026-09-28 for p912:n2 and again the
# same day for p124:n4 -- twice in one day, both times because a box was redrawn, which is the
# mechanism WORKING. A check that must be hand-edited every time the thing it watches does its job
# teaches you to edit it without reading it. So it derives the expectation instead: the retired-read
# set is exactly the set of spans whose crop differs from the one their reads were taken on, and that
# is a question `crops_changed` already answers from the files.
_RECUT = set(diag.crops_changed(F.APERTURE))
check("the retired-read set is exactly the spans whose A2 crop was re-cut",
      _MUTE_SPANS == _RECUT, f"mute={sorted(_MUTE_SPANS)} recut={sorted(_RECUT)}")
check("and that set is not empty -- a check that passes on nothing is not watching anything",
      bool(_RECUT), "no crop has been re-cut, so the rule above is unexercised")
# Span-level void is "lost its reads AND has not got them back". A re-read repairs a span, so this set
# is the re-cut spans MINUS the ones re-read since -- derived for the same reason.
_ALIVE = {o["span_id"] for o in F.live_reads()}
_UNREPAIRED = _RECUT - _ALIVE
check("a span without a live read is exactly a re-cut span that has not been re-read",
      set(F.stale_spans()) == _UNREPAIRED, f"{sorted(F.stale_spans())} vs {sorted(_UNREPAIRED)}")
check("a pre-hash read on an UNCHANGED crop is still evidence (the rule is not 'distrust the old')",
      not (_MUTE_SPANS & {"p102:n0", "p138:n5", "p217:n2"}))
# p912:n2 was the fourth name on that list until its box was redrawn, and it is the span that shows the
# rule has TWO directions rather than one. Its crop moved, so its 36 pre-hash reads are muted -- and
# its 26 reads carrying the approved hash are untouched. An ABSENT hash is not a MISMATCHED one; what
# retires a read is the crop moving under it, never the read's age.
_p912_live = sum(1 for o in _LIVE if o["span_id"] == "p912:n2"
                 and o.get("crop_sha16") == "99a6bef43a0ba2de")
_p912_mute = sum(1 for k in _MUTE if k[0] == "p912:n2")
_p912_prehash = sum(1 for o in diag._lines(F.OUT) if o.get("kind") == "read"
                    and o["span_id"] == "p912:n2" and not o.get("crop_sha16"))
check("p912:n2 is muted and evidenced at once: 27 pre-hash reads retired, 26 at the approved hash kept",
      (_p912_prehash, _p912_live) == (27, 26), f"prehash={_p912_prehash} live={_p912_live}")
# 27 reads but 26 mute KEYS: one arm answered twice before hashing existed. The void is a set of cells,
# so it counts cells; the evidence is a list of reads, so it counts reads. Asserting both keeps the two
# from being quietly swapped -- the 36 quoted by `hebrew_bind` is a third number again, because bind
# pools this artifact with the local arms' and this suite reads only its own.
check("and the void counts CELLS while the evidence counts READS -- 27 reads on 26 arms",
      _p912_mute == 26, f"mute keys={_p912_mute}")
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
_VOIDED = (_SENDABLE & set(F.stale_spans())) - _SCORED   # reads retired and not yet retaken
_NEVER = _SENDABLE - _SCORED - _VOIDED                  # no reads at all
# A PARTITION, asserted as one. The count identity held on 2026-09-28 while the sets OVERLAPPED --
# `_VOIDED` still contained two spans that were also in `_SCORED`, and 17 + 2 + 0 = 19 came out right
# for the wrong reason. A decomposition check that only adds up cannot see a double-counted term.
check("the three terms are DISJOINT, not merely summing to the population",
      not ((_SENDABLE & _SCORED) & _VOIDED) and not (_VOIDED & _NEVER)
      and not ((_SENDABLE & _SCORED) & _NEVER),
      f"scored={sorted(_SENDABLE & _SCORED)} voided={sorted(_VOIDED)} never={sorted(_NEVER)}")
check("the sendable population decomposes with no remainder: scored + voided + never-run",
      len(_SENDABLE & _SCORED) + len(_VOIDED) + len(_NEVER) == len(_SENDABLE),
      f"{len(_SENDABLE & _SCORED)} + {len(_VOIDED)} + {len(_NEVER)} != {len(_SENDABLE)}")
# Chris's rerun scope of 2026-09-27 -- p138:n6, p423:n3, p596:n2, p726:n3 -- was SENT on 09-27 (104
# calls, 26 arms each, 0 errors). So the scope is empty now, and the durable claim is not "these four
# are pending" but "these four are scored, at the hashes he approved". Pinning the hashes is what
# keeps a later re-cut from quietly re-opening a spend he already signed off.
# "All 19 scored" was true between sends and false during one. It broke the moment Chris ratified
# p124:n4's redraw, because a redrawn box is UNSCORED until its 26 calls go -- which is the pipeline
# working, not a regression. The durable claim is the decomposition asserted just above (scored +
# voided + never-run, no remainder); what belongs here is that nothing is voided for a reason OTHER
# than an unsent redraw, and that a span awaiting its send is named rather than absorbed.
_AWAITING = _VOIDED & set(diag.crops_changed(F.APERTURE))
check("every voided span is voided because its box was redrawn and not yet re-sent",
      _VOIDED == _AWAITING, f"voided={sorted(_VOIDED)} explained-by-redraw={sorted(_AWAITING)}")
check("no sendable span has simply never been run",
      not _NEVER, f"never={sorted(_NEVER)}")
if _AWAITING:
    print(f"    note: {sorted(_AWAITING)} awaiting the send on a redrawn box -- unscored BY DESIGN")
_APPROVED_2609 = {"p138:n6": "292b179e978509d6", "p423:n3": "7059fcf05ea87bf6",
                  "p596:n2": "842abe52c2829e14", "p726:n3": "631456a69a2da6a2"}
for _sid, _h in sorted(_APPROVED_2609.items()):
    _live = [o for o in _RS if o["span_id"] == _sid]
    check(f"{_sid} is scored on the pixels Chris approved ({_h})",
          len(_live) == 26 and {o.get("crop_sha16") for o in _live} == {_h},
          f"n={len(_live)} hashes={sorted({o.get('crop_sha16') for o in _live})}")
# p900:n4 is the one that cannot be repaired by re-running: its crop moved AND its crop is refused, so
# its 26 reads go mute with no route back until the box is redrawn. That is the real cost of the
# denominator change and it must be visible, not folded into "unscorable".
check("p900:n4's reads are void AND it is unsendable -- a debt, not a re-run",
      "p900:n4" in _MUTE_SPANS and "p900:n4" not in {s["span_id"] for s, _c, _x in CS})

print("\n(9) the contact-sheet gate: approved pixels are the sent pixels")
import tempfile                                                            # noqa: E402
# This was the literal list of the four spans the 2026-09-27 sheet happened to carry, and it became a
# lie the moment the sheet was rebuilt for p124:n4's redraw -- at which point `sheet_gate` RAISED here
# and took the rest of the suite with it, the same shape of defect as the `src.index` abort below. The
# sheet is this section's SUBJECT, so its scope is read off the sheet rather than remembered: whatever
# the sheet approves is what the gate must pass, and a span the sheet does not carry is what it must
# refuse. Nothing about the current build's scope is asserted here; sections (7)/(8) own that.
_SHEET_REC = json.loads(F.SHEET.read_text(encoding="utf-8")) if F.SHEET.exists() else {"crop_sha16": {}}
_SC = sorted(set(_SHEET_REC.get("crop_sha16", {})) & {s["span_id"] for s, _c, _x in CS})
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


def _passes(fn, label):
    """Run a gate that is SUPPOSED to pass, and turn a refusal into a failing check, not an abort."""
    try:
        check(label, bool(fn()))
    except RuntimeError as e:
        check(label, False, "gate REFUSED: %s" % str(e)[:140])


check("the live sidecar exists and names the pixels it approved",
      F.SHEET.exists() and bool(_SHEET_REC.get("crop_sha16")),
      "sheet=%s scope=%s" % (F.SHEET.exists(), sorted(_SHEET_REC.get("crop_sha16", {}))))
check("its scope is sendable spans -- an approval for a span that cannot be sent is not an approval",
      set(_SHEET_REC.get("crop_sha16", {})) <= {s["span_id"] for s, _c, _x in CS},
      sorted(set(_SHEET_REC.get("crop_sha16", {})) - {s["span_id"] for s, _c, _x in CS}))
check("and it is not empty, so every refusal below is measured against a sheet that passes", bool(_SC),
      "no sendable span on the sheet -- the gate checks below prove nothing")
_passes(lambda: F.sheet_gate(_cs)["sheet"].endswith(".html"),
        "the gate PASSES on the real sheet (a gate that refuses everything protects nothing)")
_refuses(lambda: F.sheet_gate(_cs, pathlib.Path("no_such_sheet.json")),
         "no contact sheet", "no sheet at all -> refuse, and say to build one")
# Damaged one span at a time, and WHICH span comes off the derived scope -- naming `p596:n2` here was
# the same pin as the scope list, and would have started asserting nothing the day it left the sheet.
_VICTIM = _SC[0] if _SC else None
_refuses(lambda: F.sheet_gate(_cs, _sheet(lambda r: r["crop_sha16"].pop(_VICTIM))),
         "not on the contact sheet", "a span the sheet never showed -> refuse")
_refuses(lambda: F.sheet_gate(_cs, _sheet(lambda r: r["crop_sha16"].update({_VICTIM: "0" * 16}))),
         "crop changed since the sheet", "a crop re-cut after approval -> refuse, naming both hashes")
# The one thing no check can verify is that a human looked. So it is not dressed up as verification:
# the flag is REQUIRED, and the header records it as a claim.
_refuses(lambda: F.run(None, _SC or ["p124:n4"]), "pass --approved",
         "no --approved -> refuse before the catalog pull, so a refusal costs nothing")
check("the approval is recorded as a claim, never as a verification",
      "NOT machine-verifiable" in src and "RECORDED CLAIM" in src)
# `src.index` raised ValueError here when `--sheet` turned `sheet_gate(cs)` into
# `sheet_gate(cs, sheet_path or SHEET)`, and a raise in a test file is not a failing check: it ABORTS
# the run, so every assertion below this line silently stopped executing. A check that cannot see its
# own subject must say so and let the rest of the suite proceed.
def _before(a, b, why):
    ia, ib = src.find(a), src.find(b)
    if ia < 0 or ib < 0:
        check(why, False, f"anchor missing: {a!r}" if ia < 0 else f"anchor missing: {b!r}")
        return
    check(why, ia < ib, f"{a!r} at {ia}, {b!r} at {ib}")


_before("sheet = sheet_gate(", "cat = catalog(refresh=True)",
        "the gate runs BEFORE the catalog pull (a refusal must not look like a started run)")

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
      not (_MUTE_SPANS & set(_a1)))
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
# AND THEN THE BOX ITSELF WAS CORRECTED. Chris's decision 3 of 2026-09-27 set the ratified x0 to 0, so
# there is no -2 left for either mechanism to repair, and `canvas-slop-clamped` has dropped off the flag
# list while the mapped rect still starts at 0. That disappearance is the measurement worth keeping: the
# clamp was genuinely load-bearing before the ruling and is not now, and the PIXELS are identical in both
# worlds. Which is Chris's reason for ruling at all -- "the crop already looks right because two clamps
# agree, and the agent is correct that two clamps agreeing isn't a ratification". A crop that survives
# because something silently held it is not evidence about the box that produced it.
check("the mapped rect starts at 0 -- and now by the ratified box, with the slop clamp no longer firing",
      _p217["native_rects"][0][0] == 0 and _p217["rect_edges"][0] == ["band-clipped"],
      _p217["rect_edges"])
# The fault table was then down to one, which was a DIFFERENT fact about the same span. My `crop_fault`
# reports the ratified STRIP box, which began at -2; the clip repaired the MAPPED rect. One is an
# editorial debt against the box, the other is the geometry that cut the pixels, and conflating them
# would have retired a debt nobody paid. It has since been paid properly, by a human ruling on the box.
_a1f = diag.crop_faults("A1_notebox")
check("the five loud page-width refusals are gone: those five A1 crops exist now",
      not [k for k, f in _a1f.items() if "exceeds page width" in f]
      and all(MAN[s].get("A1_notebox") for s in
              ("p124:n4", "p200:n2", "p596:n2", "p726:n3", "p900:n4")), sorted(_a1f))
# ...and that last debt was PAID, on the box, by Chris's ruling. An emptied fault table is the one
# result a fault check cannot celebrate on its own: it looks the same whether the debt was settled or the
# detector went quiet. So both halves are asserted -- the live ratified truth now reads 0, which is where
# the fault came from, and the detector still holds the fault it should.
check("the A1 fault table is EMPTY because the ratified box was corrected to 0, not by rounding",
      _a1f == {} and _FULL["p217:n2"]["note_box"][0] == 0,
      (_a1f, _FULL["p217:n2"]["note_box"]))
check("and the detector is not quiet: p900:n4 is still faulted out-of-strip on A2",
      set(diag.crop_faults("A2_spanbox")) == {"p900:n4"}, diag.crop_faults("A2_spanbox"))
check("p900:n4 is flagged AND produced a crop, so a recorded fault is still not a refusal",
      bool((MAN["p900:n4"].get("A2_spanbox") or {}).get("path")),
      diag.crop_faults("A2_spanbox").get("p900:n4"))

print("\n(12) the manifest index cannot silently lose spans")
# BORN-TEST. `crops()` defaults to include_sealed=False and the CLI took that default, rewriting the
# manifest over 11 of 21 spans and dropping ten sealed ones -- p423:n3, p596:n2 and p726:n3 among them,
# three of the four spans in the send scope. Every PNG survived, which is exactly why it was silent:
# the bytes were fine and the INDEX was half a corpus, and every measurement downstream reads the index.
check("the manifest on disk holds the whole build set, sealed spans included",
      set(MAN) == {s["span_id"] for s in diag.build_set(include_sealed=True)},
      "manifest %d spans, build set %d" % (len(MAN), len(diag.build_set(include_sealed=True))))
check("the send scope is IN the manifest -- the exact spans the narrowing dropped",
      all(s in MAN for s in SH.scope()[0]), sorted(set(SH.scope()[0]) - set(MAN)))
_narrowed = None
try:
    diag.crops(save=True, include_sealed=False)          # the call that did the damage
except RuntimeError as e:
    _narrowed = str(e)
check("and a narrowing write REFUSES, naming the spans it would have lost",
      _narrowed and "would DROP" in _narrowed and "p726:n3" in _narrowed, _narrowed)
check("the refusal left the index alone: it still holds every span",
      set({m["span_id"] for m in json.loads((diag.CROPDIR / "manifest.json").read_text("utf-8"))})
      == set(MAN))

print("\n(13) the clip flag is acted on, not merely recorded")
# Lane A's point, and the real remaining gap: a clipped crop is a valid PNG, so until something acts on
# the flag an amputation is visible only to a reader who goes looking. The gate does NOT refuse clipped
# crops -- a box cut back to real page content may be the crop we want, and that is Chris's judgement.
# It refuses a crop whose cut is not the cut the sheet showed, in either direction.
_SHEETREC = json.loads(F.SHEET.read_text(encoding="utf-8"))
_live_clip = F.clip_status(CS)
# VACUITY, SAID OUT LOUD. No A2 rect is clipped today, so every check below that ranges over the
# population ranges over nothing. The gate is therefore exercised on a CONSTRUCTED record instead.
check("no crop in the send scope is clipped, so the gate's population is EMPTY today",
      _live_clip == {}, _live_clip)
check("the sheet on disk RECORDS the answer rather than omitting it -- {} is an answer, a missing "
      "key is silence", "clipped" in _SHEETREC, sorted(_SHEETREC))
check("the gate passes on the real sheet (a gate that refuses everything protects nothing)",
      F.clip_gate(CS, _SHEETREC) == _live_clip)
_sid = CS[0][0]["span_id"]
_doctored = dict(_SHEETREC, clipped={_sid: [{"rect_i": 0, "edge": ["band-clipped"], "over": 42.0}]})
try:
    F.clip_gate(CS, _doctored)
    check("a sheet that showed a cut which is no longer there -> REFUSE", False, "gate passed")
except RuntimeError as e:
    check("a sheet that showed a cut which is no longer there -> REFUSE, naming both",
          "clip gate REFUSED" in str(e) and _sid in str(e))
try:
    F.clip_gate(CS, {k: v for k, v in _SHEETREC.items() if k != "clipped"})
    check("an old sheet with no clip field passes only because nothing in scope is cut", True)
except RuntimeError as e:
    check("an old sheet with no clip field passes only because nothing in scope is cut", False, str(e))
check("and the nine clipped boxes are all A1, which is why this population is empty and not because "
      "the measurement is broken",
      {c["aperture"] for c in diag.clipped()} == {"A1_notebox"} and len(diag.clipped()) == 9,
      [(c["span_id"], c["aperture"]) for c in diag.clipped()])

print("\n(14) every run writes its own header, not one per artifact")
# BORN-TEST. The 104-call send appended to an existing artifact and wrote no header, so the only
# config_header in that file belongs to an earlier run: the send's git state, approval flag, truth
# digest and crop-hash map went unrecorded while every read still carried its own crop_sha16. The
# pixels stayed answerable and the RUN did not.
_src = pathlib.Path(F.__file__).read_text(encoding="utf-8")
check("the header is no longer conditioned on the artifact not existing",
      "first = not OUT.exists()" not in _src)
check("a run over an existing artifact records where its own reads begin",
      '"reads_before": _reads_before' in _src and "_reads_before = sum(" in _src)
if F.OUT.exists():
    _hdrs = [o for o in diag._lines(F.OUT) if o.get("kind") == "config_header"]
    _late = [o for o in diag._lines(F.OUT) if o.get("kind") == "config_header_late"]
    check("the 23:17 send of 2026-09-27 has an identity record, even if a late one",
          any(h.get("crop_sha16") for h in _hdrs + _late),
          "%d header(s), %d late" % (len(_hdrs), len(_late)))

print("\n(12) BORN-TEST -- the pixels are archived before the money is spent")
# Chris's ruling, 2026-09-28. The 26 calls on p912:n2 at 07:32 left reads whose `crop_sha16` resolved
# to exactly ONE file: the live crop, which the next re-cut of that span would have overwritten. The
# hash would have outlived the pixels it names. `AS_SENT` could not cover this -- it is a write-once
# 2026-09-20 snapshot, and the whole problem is a SECOND state of the same span.
_SHAS = {o["crop_sha16"] for _a in (F.OUT,) for o in diag._lines(_a)
         if o.get("kind") == "read" and o.get("crop_sha16")}
check("every crop_sha16 on a recorded read resolves to archived pixels",
      all(diag.sent_archive_has(h) for h in _SHAS),
      sorted(h for h in _SHAS if not diag.sent_archive_has(h)))
check("p912:n2's 07:32 state is in the archive, not only in the live crop",
      diag.sent_archive_has("99a6bef43a0ba2de"))
check("and so are the two states that had the same exposure (p423:n3, p726:n3)",
      diag.sent_archive_has("7059fcf05ea87bf6") and diag.sent_archive_has("631456a69a2da6a2"))

# The archive is content-addressed, so a put is idempotent and CANNOT overwrite: same bytes, same
# name, nothing written. That is the property that makes it evidence rather than a cache.
import os, tempfile as _tf, shutil as _sh                                        # noqa: E402
_any = sorted(diag.SENT_SHA.glob("*.png"))[0]
_n_before = len(list(diag.SENT_SHA.glob("*.png")))
_h1 = diag.sent_archive_put(_any, "test:n0", F.APERTURE, why="idempotence check")
check("re-putting an already-archived crop writes nothing and returns its hash",
      _h1 == _any.stem and len(list(diag.SENT_SHA.glob("*.png"))) == _n_before)
_tmpd = _tf.mkdtemp()
_miss = os.path.join(_tmpd, "absent.png")
try:
    diag.sent_archive_put(_miss, "test:n1", F.APERTURE)
    _bad = "archived a crop that does not exist"
except FileNotFoundError:
    _bad = None
check("a crop that does not exist cannot be archived -- and so cannot be silently sent", _bad is None,
      _bad or "")
check("the index holds one row per DISTINCT pixel state, not one per send",
      len({r["sha16"] for r in diag.sent_archive_index()}) == len(diag.sent_archive_index()))
check("every archived file hashes to its own name",
      all(diag._sha(p) == p.stem for p in sorted(diag.SENT_SHA.glob("*.png"))))

# And the send path must actually archive, before the catalog pull and before the header, or the
# guarantee is only true of the backfill.
check("run() archives before the catalog pull (a failure to archive must cost nothing)",
      src.find("diag.sent_archive_put(") < src.find("cat = catalog(refresh=True)"))
check("run() archives before the header, so recorded hashes name preserved pixels",
      src.find("diag.sent_archive_put(") < src.find("hdr = build_header("))
check("the header records what it archived", '"crops_archived": _arch' in src)

print("\n(15) the input-guard control reads PIXELS, and says so when it cannot")
# Chris's law, 2026-10-04: a read is evidence only about a crop that passed the input guard. The
# control that enforces it is cited in REPORT_laneB_20260928d, so it gets a watcher. The defect it
# replaced selected on `"crop-fault" in unscorable` -- a tag about a BOX -- and printed "these arms
# were shown nothing" over p900:n4, whose crop has ink. A control that asserts what was shown must
# derive it from what was shown.
_BLANKS = [r for r in diag.sent_archive_index()
           if F.crop_ink_state(r["sha16"]) == "BLANK"]
check("the archive still holds the blank sends, so the proof case has not been groomed away",
      len(_BLANKS) == 2, [r["sha16"][:16] for r in _BLANKS])
check("every archived blank is identified as BLANK from its own pixels, not from a fault tag",
      all(F.crop_ink_state(r["sha16"]) == "BLANK" for r in _BLANKS))
_INKED = [r for r in diag.sent_archive_index() if r["sha16"] not in {b["sha16"] for b in _BLANKS}]
check("and every other archived state reads INK -- the predicate discriminates, it does not just say BLANK",
      _INKED and all(F.crop_ink_state(r["sha16"]) == "INK" for r in _INKED),
      [r["sha16"][:16] for r in _INKED if F.crop_ink_state(r["sha16"]) != "INK"])

# The third state. An unknown hash must come back None, never a guess in either direction.
check("an unarchived hash is UNKNOWABLE, not BLANK and not INK",
      F.crop_ink_state("0" * 16) is None)
check("a hash-less read on a RE-CUT span is unknowable (its pixels are not recoverable)",
      all(F.crop_ink_state(None, sid) is None for sid in diag.crops_changed(F.APERTURE)),
      sorted(diag.crops_changed(F.APERTURE)))
_STABLE = [s["span_id"] for s, _c, _x in CS
           if s["span_id"] not in set(diag.crops_changed(F.APERTURE))]
check("but a hash-less read on a NEVER-re-cut span resolves against the live crop",
      _STABLE and all(F.crop_ink_state(None, sid) == "INK" for sid in _STABLE),
      [sid for sid in _STABLE if F.crop_ink_state(None, sid) != "INK"])
check("and that set is not empty -- the clause above would otherwise pass on nothing",
      bool(_STABLE))

# p900:n4 is the span the old control libelled. Name it, and assert the thing that was false.
_P900 = next((s for s in diag.build_set(include_sealed=True) if s["span_id"] == "p900:n4"), None)
if _P900:
    check("p900:n4's crop carries INK -- the old control called it 'shown nothing' on a box tag",
          F.crop_ink_state(None, "p900:n4") in ("INK", None))
    check("p900:n4 is unscorable for a BOX reason, which is not a statement about its pixels",
          "crop-fault" in (_P900["unscorable"] or ""), _P900["unscorable"])

# The stale_read_why blindness: support() must agree with score() about n.
_sup = src[src.index("def support():"):]
check("support() mutes void reads (it tallied 20 spans against score()'s 19 until 2026-10-04)",
      "if read_key(o) in mute:" in _sup)
check("support() reports the void reads it dropped rather than absorbing them",
      "VOID and excluded from the table above" in _sup)
check("the control is derived from crop_ink_state, and the fault-tag selector is gone",
      "crop_ink_state(" in _sup and 'if unsc and "crop-fault" in unsc:' not in _sup)

print("\n(16) item 6(a): the context-axes harness, before it produces a number")
import hebrew_context_axes as AX
from hebrew_recrop import _RECROP_PROMPT as _RP

# The cross-run null is only a null if `base` is the recorded config to the byte.
check("the base cell's prompt IS the recorded D prompt, byte for byte",
      AX.prompt_for(True, False, "ignored") == _RP)
check("base and base_rep are the same configuration (that is what makes one a null)",
      [c for c in AX.CELLS if c[0] == "base"][0][1:] ==
      [c for c in AX.CELLS if c[0] == "base_rep"][0][1:])
check("the four axis combinations are each present exactly once",
      sorted({(st, tx) for _c, st, tx in AX.CELLS}) ==
      [(False, False), (False, True), (True, False), (True, True)])

# The text channel is the FRONTIER's channel, or the two halves of item 6 are not comparable.
_p = AX.prompt_for(False, True, "a \u2022 b")
check("text ON carries the frontier's bullet wording and the ctx, text OFF carries neither",
      "each \u2022 marks" in _p and "a \u2022 b" in _p
      and "each \u2022 marks" not in AX.prompt_for(False, False, "a \u2022 b"))
check("the strip sentence appears only when a strip image is actually sent",
      "Image 1" in AX.prompt_for(True, False, "") and "Image 1" not in AX.prompt_for(False, False, ""))
check("and the bare prompt never refers to a second image",
      "image 2" not in AX.prompt_for(False, True, "x").lower())

# The send population: 19, not L._built's 20. This is the defect fixed in support(), not repeated here.
_pop = AX.built()
_un = {s["span_id"] for s in diag.build_set(include_sealed=True) if s["unscorable"]}
check("the axes population excludes unscorable spans (L._built returns 20 where score() tallies 19)",
      _pop and not ({s["span_id"] for s in _pop} & _un),
      sorted({s["span_id"] for s in _pop} & _un))
check("and it is exactly the population the frontier sends, so the two halves of item 6 compare",
      {s["span_id"] for s in _pop} == {s["span_id"] for s, _c, _x in CS},
      sorted({s["span_id"] for s in _pop} ^ {s["span_id"] for s, _c, _x in CS}))
check("every span in it has a context strip, or the strip axis would be silently uneven",
      all(s.get("context_strip") for s in _pop))

# Guards that must fire before the wire, not after it.
try:
    AX.run("192.168.1.179:11435", ["x"])
    _res = "NO RAISE"
except RuntimeError as e:
    _res = "RESERVED" if "RESERVED" in str(e) else str(e)[:60]
except Exception as e:
    _res = type(e).__name__
check("a run at the RESERVED production pair raises before any request is built", _res == "RESERVED",
      _res)
_axsrc = (HERE / "hebrew_context_axes.py").read_text(encoding="utf-8")
check("both channels route their base64 through the gated encoder, so neither can skip the input guard",
      _axsrc.count("L._b64(") == 2 and "base64.b64encode" not in _axsrc)
check("the ink state of EVERY channel is recorded beside the read, the strip's included",
      '"strip_ink"' in _axsrc and '"crop_ink"' in _axsrc)
check("N consecutive dead items faults the RUN, and a faulted artifact refuses to be scored",
      "dead >= DEAD_RUN_AT" in _axsrc and "cannot be scored" in _axsrc)
check("the footer records git at start AND end, and whether they matched",
      '"clean_run": clean' in _axsrc and "g0 == g1" in _axsrc)
# 2026-10-04: the tree was dirtied WHILE a run was in flight. Both halves of that accident are now
# guarded in code rather than in my memory of it.
check("a run refuses to resume onto an artifact that holds reads and no footer (never splice)",
      "NO footer -- its run never closed" in _axsrc and "raise RuntimeError" in _axsrc)
check("scoring refuses a footerless artifact, and a PROVISIONAL one unless it is named as such",
      "has no footer" in _axsrc and "allow_provisional" in _axsrc
      and "cannot be cited" in _axsrc)

print("\n(17) item 6, frontier half: the TEXT axis")
# The channel is removed by removing it. An empty paragraph would still say "a note surrounds this crop
# and its Hebrew was taken out", which is most of what the channel carries.
_on, _off = F._prompt_text("a \u2022 b"), F._prompt_text(None)
check("text OFF is head+tail exactly -- the told-about-the-note block is ABSENT, not empty",
      _off == F.PROMPT_HEAD + F.PROMPT_TAIL)
check("and it carries no bullet, no context sentence and no citation sentence",
      "\u2022" not in _off and "Context from" not in _off and "citation" not in _off)
check("text ON carries the ctx it was handed", "a \u2022 b" in _on and "Context from" in _on)

# The ablation must not be able to delete its own control.
check("the text-off run writes a DIFFERENT artifact (rows() keeps the last read per span+model)",
      F.OUT_NOTEXT != F.OUT and "notext" in F.OUT_NOTEXT.name)

# prompt_sha16 must keep meaning what it meant in the recorded artifact.
_hdr = next((o for o in diag._lines(F.OUT) if o.get("kind") == "config_header"), None)
if _hdr and _hdr.get("prompt_sha16"):
    check("prompt_sha16 still hashes head+tail, so the recorded run's header value is unchanged",
          _hdr["prompt_sha16"] == F.diag_sha(F.PROMPT_HEAD + F.PROMPT_TAIL), _hdr["prompt_sha16"])
check("the ASSEMBLED prompt gets its own hash, and the two variants differ under it",
      F.diag_sha(F._prompt_text("<CTX>")) != F.diag_sha(F._prompt_text(None)))

# astra: measured, recorded, and never called again.
check("astra is still in ARMS, so the recorded 19/19 keeps its meaning",
      "openai/gpt-6-astra" in F.ARMS)
check("astra is excluded from new spend, with the reason recorded rather than implied",
      "openai/gpt-6-astra" in F.EXCLUDED_ARMS
      and "Chris" in F.EXCLUDED_ARMS["openai/gpt-6-astra"])
_run = src[src.index("def run(only=None"):src.index("def diag_sha(")]
check("the excluded arm is skipped BEFORE the catalog status check, and records why",
      _run.index("if model in EXCLUDED_ARMS:") < _run.index('if c.get("status") != "ok":')
      and "EXCLUDED_ARMS[model]" in _run)

# The axis is applied at exactly one point, and it changes no pixel.
check("the channel is withheld at ONE call site, not scattered through the run",
      src.count("ctx if TEXT_CONTEXT else None") == 1)
check("--no-text is applied before dispatch, so score() reads the file run() wrote",
      src.index('if "--no-text" in a:') < src.index('if cmd == "catalog":'))
check("the text axis sends the same A2 crops through the same offnet gate -- no new pixel class",
      src.count('diag.b64_gated(cpath, what="frontier crop", offnet=True)') == 1)
check("the header says whether the channel was sent, in the hashed identity block",
      '"text_context_sent": TEXT_CONTEXT' in src)

print("\n(18) the contact sheet is an APPROVAL RECORD, not a report")
import hebrew_contact_sheet as SHEET   # NOT `CS` -- that name is the A2 cell list

# The defect that cost item 6 its approval: one fixed filename, so a later single-span build landed on
# the 19-span record and the gate had nothing left to check against.
_cssrc = (HERE / "hebrew_contact_sheet.py").read_text(encoding="utf-8")
# The literal still appears in the comment that explains the defect; what must be gone is any
# EXECUTABLE default. Comment lines stripped, then the name must not be there at all.
_cscode = chr(10).join(l for l in _cssrc.splitlines()
                       if not l.lstrip().startswith("#"))
check("no executable line names a fixed default sheet file any more",
      "contact_sheet_2" not in _cscode,
      [l.strip() for l in _cscode.splitlines() if "contact_sheet_2" in l][:2])
check("and the defect is still documented in a comment, so the naming rule has its reason attached",
      "contact_sheet_20260927.html" in _cssrc)
check("the default name is DERIVED from the scope, like scope() itself",
      "def derived_out(" in _cssrc and "out = out or derived_out(want, cells)" in _cssrc)

_c19 = {s["span_id"]: (s, c, x) for s, c, x in SHEET.F.cells()}
_w19 = sorted(_c19)
_n19 = SHEET.derived_out(_w19, _c19)
check("the name carries the span COUNT, so a 1-span sheet cannot be mistaken for the 19-span one",
      "_%dspan_" % len(_w19) in _n19.name, _n19.name)
check("same scope, same pixels -> same name (a rebuild is idempotent, not a second record)",
      SHEET.derived_out(_w19, _c19).name == _n19.name)
check("one span dropped from the scope moves the name",
      SHEET.derived_out(_w19[:-1], _c19).name != _n19.name)

# A re-cut crop must move the name, or an approval could silently cover pixels nobody saw.
class _FakeCrop(str):
    pass
_orig = SHEET.F.crop_sha
try:
    _flip = {"n": 0}
    def _shim(p):
        _flip["n"] += 1
        return "ffffffffffffffff" if _flip["n"] == 1 else _orig(p)
    SHEET.F.crop_sha = _shim
    _moved = SHEET.derived_out(_w19, _c19).name != _n19.name
finally:
    SHEET.F.crop_sha = _orig
check("one crop re-cut after approval moves the name, so it lands on a NEW file", _moved)

# And the assertion that watches the naming.
try:
    SHEET.refuse_to_clobber(str(_n19), {"zzz:n9": "deadbeefdeadbeef"})
    _r = "NO RAISE"
except RuntimeError as e:
    _r = "REFUSED" if "destroy the record" in str(e) else str(e)[:60]
check("a sidecar describing DIFFERENT pixels is never overwritten", _r == "REFUSED", _r)
check("and the refusal names the spans whose approval would have been lost",
      "' '.join(sorted(was))" in _cssrc)

# The spend figure Chris approves must not count arms that cannot be called.
check("excluded arms are out of the approved arm count (astra is the priciest arm in the set)",
      "m not in getattr(F, \"EXCLUDED_ARMS\", {})" in _cssrc)

print()
print("(19) the band-clip route out of the network -- item 6(b)")
print("-" * 92)

# Item 6(b) sends a crop that is not the A2 span box. A filename rule cannot tell a band-clip from
# any other PNG, so the clip carries a proof obligation instead: it must BE a full-width row range of
# a sendable A2 crop, checked against the pixels. These checks are the adversary -- each one builds a
# clip that lies in a different way and asserts the gate refuses it.
import tempfile                                                             # noqa: E402
from PIL import Image as _Im                                                # noqa: E402

_src = None
for _s, _c, _x in F.cells():
    if _s["span_id"] == "p912:n2":
        _src = _c
        break
check("the band-clip parent crop is present to test against", bool(_src), str(_src))

_td = tempfile.mkdtemp(prefix="bandclip_")


def _mk(name, img, parent=None, rows=None):
    p = os.path.join(_td, name)
    img.save(p)
    if parent is not None:
        rec = {"parent": str(parent), "rows": list(rows or [0, img.height - 1])}
        open(os.path.splitext(p)[0] + ".parent.json", "w", encoding="utf-8").write(json.dumps(rec))
    return p


if _src:
    _par = _Im.open(_src)
    _rows = (14, 72)
    _good = _par.crop((0, _rows[0], _par.width, _rows[1] + 1))

    _p = _mk("ok_A2_bandclip.png", _good, _src, _rows)
    check("a clip that IS a row range of its A2 parent passes the gate",
          diag.gate_outbound(_p, offnet=True)[1] is None, str(diag.gate_outbound(_p, offnet=True)[1]))

    _p = _mk("nosidecar_A2_bandclip.png", _good)
    check("a clip with no parent record is refused",
          "bandclip-has-no-parent-record" in (diag.gate_outbound(_p, offnet=True)[1] or ""))

    _bad = _good.copy()
    _px = _bad.load()
    _px[0, 0] = (0, 0, 0) if _bad.mode == "RGB" else 0
    _p = _mk("onepixel_A2_bandclip.png", _bad, _src, _rows)
    check("a clip altered by ONE pixel is refused -- the check is the bytes, not the sidecar",
          "not-a-slice-of-its-parent" in (diag.gate_outbound(_p, offnet=True)[1] or ""),
          str(diag.gate_outbound(_p, offnet=True)[1]))

    _p = _mk("wrongrows_A2_bandclip.png", _good, _src, (10, 68))
    check("a clip whose recorded rows do not produce it is refused",
          (diag.gate_outbound(_p, offnet=True)[1] or "").startswith("offnet:bandclip-"),
          str(diag.gate_outbound(_p, offnet=True)[1]))

    _p = _mk("notebox_A2_bandclip.png", _good, str(_src).replace("_A2_spanbox.png", "_A1_notebox.png"),
             _rows)
    check("a clip claiming a NOTE-BOX parent is refused -- the one aperture that may never leave",
          "parent-is-not-an-A2-span-box-crop" in (diag.gate_outbound(_p, offnet=True)[1] or ""))

    _p = _mk("missing_A2_bandclip.png", _good, os.path.join(_td, "gone_A2_spanbox.png"), _rows)
    check("a clip whose parent does not exist is refused",
          "bandclip-parent-missing" in (diag.gate_outbound(_p, offnet=True)[1] or ""))

    _wide = _Im.new(_good.mode, (_good.width + 4, _good.height), 255)
    _wide.paste(_good, (0, 0))
    _p = _mk("widened_A2_bandclip.png", _wide, _src, _rows)
    check("a clip that is WIDER than its parent slice is refused (rows may be dropped, pixels may not "
          "be added)", (diag.gate_outbound(_p, offnet=True)[1] or "").startswith("offnet:bandclip-"),
          str(diag.gate_outbound(_p, offnet=True)[1]))

    _p = _mk("chained_A2_bandclip.png", _good.crop((0, 2, _good.width, 20)),
             os.path.join(_td, "ok_A2_bandclip.png"), (2, 19))
    check("a clip OF a clip is refused -- the parent must be the ratified span box itself",
          "parent-is-not-an-A2-span-box-crop" in (diag.gate_outbound(_p, offnet=True)[1] or ""))

# The live item 6(b) pixel, as it sits on disk: it is the thing the contact sheet shows.
_LIVE = ("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/hebrew_pad_probe_20261004/"
         "p912_n2_A2_bandclip.png")
if os.path.exists(_LIVE):
    check("the item 6(b) clip on disk passes the gate",
          diag.gate_outbound(_LIVE, offnet=True)[1] is None, str(diag.gate_outbound(_LIVE, offnet=True)[1]))
    check("and it is 385x59, the full width of its parent",
          _Im.open(_LIVE).size == (385, 59), str(_Im.open(_LIVE).size))

# The suffix rule itself: the old refusal still stands for everything that is neither.
check("a PNG that is neither an A2 span box nor a band-clip is still refused",
      "not-an-A2-span-box-crop" in (diag.gate_outbound(os.path.join(_td, "x_A1_notebox.png"),
                                                    offnet=True)[1] or ""))

print()
# An abort is not a failure, so the count is the gate. Raise the floor when you add a section; never
# pin it to the exact number, or the suite starts failing on its own growth.
CHECK_FLOOR = 216
if len(ran) < CHECK_FLOOR:
    fails.append(f"only {len(ran)} checks executed, floor is {CHECK_FLOOR} -- a section was dropped or "
                 f"something raised mid-file. Last check to run: {ran[-1] if ran else '(none)'}")

if fails:
    print(f"FAIL: {len(fails)} assertion(s)")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"PASS: {len(ran)} checks, A2-only n={len(CS)}, {len(_ALL_LEAK)}/{len(CS)} context leaks blocked "
      f"({len(raw_leaks)} of them literal), no note-box crop reachable.")
sys.exit(0)
