# AS-RUN PROBE, committed so the numbers in
# docs/audits/FLIP_PROPOSAL_adr0009_laneA_20261004.md are checkable. Read-only: it touches nothing
# but recorded eval output under evals/output/. No model call, no endpoint, no network.
#
# KNOWN LIMITS, so nobody reads more out of it than it measured:
#   1. It reads the REPRESENTATIVE run's answer only. The other four runs of each question keep
#      answer_sha16, answer_chars and verification_failure but NOT `verified`, so this cannot say
#      which gate failed on run 3. Every per-run claim in the report is an inference, and is
#      labelled as one there.
#   2. QUOTE_WITH_CITE_RE is REPRODUCED from backend/bot.py:61, not imported, because importing
#      bot.py pulls the whole server. If that regex changes, this copy goes stale silently.
#   3. The recorded `answer` is POST-repair. For a no_gill_quote_for_citation failure no repair is
#      spliced, so the text is unchanged for the cases examined -- but that is an argument, not a
#      guarantee for other failure reasons.
#
# Do not edit in place to ask a new question; copy it. The report cites these numbers.

"""Is the span the ON answer attached to an UNPAIRED citation actually verbatim Gill?

If it is, the verifier's `no_gill_quote_for_citation` is a false positive and the eval's
must_be_verified gate is penalising a faithful answer. The pairing regex is reproduced from
backend/bot.py:61 rather than imported, because importing bot.py pulls the whole server.

My first version of this probe shared the blind spot it was measuring: it took the span between
the LAST TWO quote marks, which a doubled closing mark makes empty, and so it reported "no quote
found" for all six cases. It now walks back pairs until a non-empty span appears.
"""
import io, json, re

R = re.compile(r'["“”]([^"“”]+)["“”][^"“”\n\[\]]{0,80}\[([A-Z0-9_]+_S\d+)\]')
ANY = re.compile(r'\[([A-Z0-9_]+_S\d+)\]')
MARK = re.compile(r'["“”]')
WS = re.compile(r"\s+")
norm = lambda s: WS.sub(" ", s or "").strip()

CASES = [("off_vs_on_rerun2_20261004", "day_of_atonement_001"),
         ("off_vs_on_rerun2_20261004", "real_election_001"),
         ("off_vs_on_rerun2_20261004", "real_garden_genesis_3_24_misattribution_001"),
         ("off_vs_on_rerun3_20261004", "day_of_atonement_001"),
         ("off_vs_on_rerun3_20261004", "real_election_001"),
         ("off_vs_on_rerun3_20261004", "real_garden_genesis_3_24_misattribution_001")]

rows = []
for pair, q in CASES:
    r = json.load(io.open("evals/output/%s/on/%s.json" % (pair, q), encoding="utf-8"))
    a = r["score"]["answer"] or ""
    resp = r.get("response") or {}
    sents = {}
    for ev in resp.get("evidence") or []:
        for sd in ev.get("sentence_data") or []:
            if sd.get("sentence_id"):
                sents[sd["sentence_id"]] = sd.get("text") or ""
    unpaired = sorted({m.group(1) for m in ANY.finditer(a)} - {m.group(2) for m in R.finditer(a)})
    print("=== %s / %s" % (pair[12:18], q))
    for sid in unpaired:
        i = a.find("[%s]" % sid)
        before = a[max(0, i - 2000):i]
        marks = [m.start() for m in MARK.finditer(before)]
        cand, k = "", len(marks) - 1
        while k >= 1 and not cand:
            cand = norm(before[marks[k - 1] + 1:marks[k]])
            k -= 1
        src = norm(sents.get(sid, ""))
        if not cand:
            print("   %-22s cited BARE -- no quoted span at all before the SID" % sid)
            rows.append((pair, q, sid, None, None, None))
            continue
        lo, hi = 0, len(cand)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if cand[:mid] in src:
                lo = mid
            else:
                hi = mid - 1
        dbl = '""' in before[-500:]
        print("   %-22s len=%4d exact=%-5s longest_prefix=%d/%d doubled_quote=%s"
              % (sid, len(cand), cand in src, lo, len(cand), dbl))
        if cand not in src:
            print("        candidate head: %r" % cand[:140])
            print("        source  head  : %r" % src[:140])
        rows.append((pair, q, sid, cand in src, lo == len(cand), dbl))

print()
ok = [r for r in rows if r[3] is True]
print("verbatim-and-unpaired: %d of %d unpaired citations" % (len(ok), len(rows)))
print("of those, preceded by a doubled quote mark: %d" % sum(1 for r in ok if r[5]))
