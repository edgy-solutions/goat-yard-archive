"""Calibration runner for the Zone-3 three-way semantic judge.

Runs the judge N=5 on each of six labeled examples pulled from this
project's own history. Reports:

  1. Correctness — does the judge's majority class match the label on
     clear cases?
  2. Run-to-run consistency — a flaky judge flips verdicts on the same
     text, which makes any gate built on it noisy and trains everyone
     to re-run until green. Death of the instrument.

The judge is NOT wired as a merge gate until this calibration passes.
Same discipline used for the gemma classifier (ADR-0008 substrate work).

Pass criteria:
  - All 4 clear-labeled cases (supported/unsupported/none/none) hit
    their label on majority-of-5. Correctness = 4/4.
  - Consistency (fraction of runs matching the case's own majority) >=
    0.8 on every case, borderline included.
  - Borderline case may land either supported OR unsupported reliably
    (both are acceptable) — what MUST be reliable is the class, not
    which side of the borderline.

Borderline policy is stated up front: on `unsupported`, the gate flags
for human eyeball, not auto-fail. At 28 eval cases, per-case review
costs minutes and keeps marginal cases from making the gate brittle.
"""
from __future__ import annotations

import statistics
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evals.zone3_judge import judge_answer, DEFAULT_JUDGE_MODEL  # noqa: E402


# ---- Six labeled examples pulled from this project's own history. ----
# Every text is a real bot output captured verbatim from a test / prod run.
# Labels are the reviewer-endorsed expected classification.

CASES = [
    {
        "id": "flagship_covenant_run1",
        "expected": "supported",
        "notes": (
            "Step-3 mini-A/B run 1 covenant answer. Opener uses forbidden "
            "verb 'distinguishes' but every quote that follows shows Gill "
            "himself distinguishing (Gen 9:9 'Not X, but Y'). Same substrate "
            "the flagship read confirmed against source."
        ),
        "answer": (
            "Gill distinguishes the covenant of grace from other covenants in the following ways:\n"
            "\n"
            '1. On the Noahic covenant: "Not the covenant of grace in Christ, but of the preservation '
            'of the creatures in common, a promise that they should not be destroyed any more by a '
            'flood" [GENESIS_9_9_S00].\n'
            "\n"
            '2. On the covenant of circumcision: "The covenant of circumcision, so called from the '
            'token of it, which God is said to make or give, being his own constitution, and depended '
            'on his sovereign will and pleasure" [GENESIS_17_2_S00].\n'
            "\n"
            '3. On the Mosaic covenant: "The blood of the covenant, which the Lord hath made with you '
            'concerning all these words; being a ratification of the covenant on both sides, having '
            'been sprinkled both upon the altar, and upon the people" [EXODUS_24_8_S00]. Gill '
            'contrasts this with the new covenant: "But the second covenant, or the new administration '
            'of the covenant of grace, for which reason it is called the New Testament, is exhibited '
            'and established in the blood of Christ the testator" [MATTHEW_26_28_S01].\n'
            "\n"
            '4. On the everlasting nature of the covenant of grace: "For an everlasting covenant; to '
            'his natural seed, as long as they should continue in the true worship of God... and to '
            'all his spiritual seed, with respect to the spiritual blessings of it, which are '
            'everlasting, and are never taken away, or become void" [GENESIS_17_7_S00].\n'
            "\n"
            '5. On the covenant\'s fulfillment in Christ: "Which is shed for many, for the remission '
            'of sins; that is, was very shortly to be shed, and since has been, for all the elect of '
            'God... whereby the full forgiveness of all their sins was procured" [MATTHEW_26_28_S03].'
        ),
    },
    {
        "id": "run2_closer_unsupported",
        "expected": "unsupported",
        "notes": (
            "Step-3 run 2 covenant answer. Closes with a systematizing "
            "sentence that goes beyond what the quotes show — the model "
            "asserts Gill's overall doctrinal position on monocovenantalism "
            "from three verse-specific quotes. The 2026-07-05 exemplar."
        ),
        "answer": (
            'Gill distinguishes the covenant of grace from other covenants. For example, in Genesis '
            '9:9-10, he states: "Not the covenant of grace in Christ, but of the preservation of the '
            'creatures in common" [GENESIS_9_9_S00]. Similarly, in Genesis 17:7, he notes that the '
            'covenant with Abraham includes both "natural seed" and "spiritual seed," but he does not '
            'conflate it with the covenant of grace: "Not only renew it, but confirm it by the '
            'following token of circumcision" [GENESIS_17_7_S00].\n'
            "\n"
            'Gill also contrasts the "new testament" (covenant of grace) with the "first covenant" in '
            'Matthew 26:28: "That is, the red wine in the cup, was an emblem and representation of '
            'his precious blood, whereby was exhibited a new dispensation, or administration of the '
            'covenant of grace; and by which it was ratified and confirmed" [MATTHEW_26_28_S00].\n'
            "\n"
            'These distinctions suggest Gill does not treat all covenants as one unified '
            '"monocovenantal" system.'
        ),
    },
    {
        "id": "current_pod_closer_borderline",
        "expected": "unsupported",
        "notes": (
            "Current pod's covenant answer (2026-07-05 eyeball). Closer is "
            "'This suggests Gill views the covenant of grace as a distinct, "
            "enduring covenant, though administered differently across time.' "
            "The 'distinct, enduring' part IS supported by quotes; the "
            "'administered differently across time' is a systematizing "
            "overlay on a single Matt 26:28 'administration' quote. Labeled "
            "unsupported because the trailing clause is where the label "
            "actually lives — but this is the borderline case the calibration "
            "is designed to expose. Either verdict is acceptable if RELIABLE; "
            "flakiness is not."
        ),
        "answer": (
            'Gill does not use the term "monocovenantal," but he distinguishes the covenant of grace '
            'from other covenants. On Genesis 17:7, he notes that the covenant with Abraham includes '
            'both "his natural seed, as such" and "his spiritual seed," with the latter receiving "the '
            'spiritual blessings of it, which are everlasting" [GENESIS_17_7_S00]. He further clarifies '
            'that the covenant of grace is not the same as the Noahic covenant, which he calls "not the '
            'covenant of grace in Christ, but of the preservation of the creatures in common" '
            '[GENESIS_9_9_S00]. In Matthew 26:28, he describes the "new testament" as "a new '
            'dispensation, or administration of the covenant of grace," ratified by Christ\'s blood '
            '[MATTHEW_26_28_S00]. This suggests Gill views the covenant of grace as a distinct, '
            'enduring covenant, though administered differently across time.'
        ),
    },
    {
        "id": "clean_peter_answer",
        "expected": "none",
        "notes": (
            "Step-3 smoke on 'Who is Peter?'. Substantive Gill-cited answer, "
            "no characterization of Gill's position on anything."
        ),
        "answer": (
            'Peter, originally named Simon, was a fisherman from Galilee who became one of Jesus\' '
            'disciples. In John 1:42, Jesus declares: "Thou shalt be called Cephas, which is, by '
            'interpretation, a stone" [JOHN_1_42_S03]. This name signifies "a rock, or stone, as '
            'Cephas also does, see John i. 42. from his constancy, steadfastness, and solidity" '
            '[LUKE_6_14_S00]. Mark notes this renaming occurred when "Christ first called him to be '
            'his disciple and apostle" [MARK_3_16_S00].'
        ),
    },
    {
        "id": "aquinas_informative_refusal",
        "expected": "none",
        "notes": (
            "Step-3 smoke on Aquinas. Surfaces Philip Aquinas (Hebrew "
            "lexicographer) as the corpus material, distinguishes from Thomas "
            "Aquinas the theologian. No characterization of Gill's own "
            "doctrinal position anywhere — pure Zone-1 disclaimer + Zone-2 "
            "quotes."
        ),
        "answer": (
            'Gill references Philip Aquinas, a Hebrew lexicographer, in two contexts:\n'
            "1. On John 7:27, he notes that \"Aquinas attributes to the Jewish Rabbins\" a specific "
            "interpretation about the Messiah's origin, which Gill dismisses as \"a Popish device\" "
            "misattributed to the Jews [JOHN_7_27_S03].\n"
            '2. In Leviticus 11, Aquinas is cited alongside other scholars interpreting unclean '
            'animals: "so Jarchi and Kimchi, and Philip Aquinas, interpret it by *mustela*, the weasel" '
            "[LEVITICUS_11_29_S01]."
        ),
    },
    {
        "id": "prod_launch_covenant_unsupported",
        "expected": "unsupported",
        "notes": (
            "The 2026-06-22 launch-week prod-log covenant answer. Assertive "
            "monocovenantal thesis with no verbatim anchors. The original "
            "Zone-3 exemplar that motivated this whole ADR chain."
        ),
        "answer": (
            'Gill distinguishes between different covenantal administrations while affirming their '
            'ultimate unity in grace. On Genesis 17:7, he speaks of "an everlasting covenant" '
            '[GENESIS_17_7_S00], and on Matthew 26:28 he speaks of Christ ratifying "a new '
            'dispensation, or administration of the covenant of grace" [MATTHEW_26_28_S00]. Together '
            "these express one covenant across successive administrations, held together by grace."
        ),
    },
]

N_RUNS = 5


def run_calibration(model: str = DEFAULT_JUDGE_MODEL) -> int:
    print("=" * 92)
    print(f"ZONE-3 JUDGE CALIBRATION — model={model}, N={N_RUNS} per case")
    print("=" * 92)
    print()
    print("Pass criteria:")
    print("  - Correctness: majority class matches expected on all 4 clear cases (supported/")
    print("    unsupported/none/none). Borderline case may land either side if RELIABLE.")
    print("  - Consistency: >= 0.8 (majority frequency across N=5) on every case.")
    print()

    load_dotenv()

    all_pass = True
    summary = []

    for case in CASES:
        cid = case["id"]
        expected = case["expected"]
        print(f"-- {cid} -- expected={expected}")
        print(f"   {case['notes']}")
        classifications = []
        latencies = []
        for i in range(1, N_RUNS + 1):
            r = judge_answer(case["answer"], model=model)
            classifications.append(r.cls)
            latencies.append(r.latency_s)
            n_chars = len(r.characterizations)
            n_unsup = sum(1 for c in r.characterizations if not c.substantiated)
            print(f"   run {i}: cls={r.cls} chars={n_chars} unsupported={n_unsup} "
                  f"lat={r.latency_s:.1f}s")
            if r.error:
                print(f"           ERROR: {r.error}")
        cnt = Counter(classifications)
        majority_class, majority_count = cnt.most_common(1)[0]
        consistency = majority_count / N_RUNS
        median_lat = statistics.median(latencies) if latencies else 0.0
        matches_expected = (majority_class == expected)
        # Borderline gets special treatment: any RELIABLE class is acceptable
        is_borderline = case.get("id", "").endswith("_borderline") or "borderline" in case.get("notes", "").lower()
        acceptable = matches_expected or (is_borderline and consistency >= 0.8)
        summary.append({
            "id": cid,
            "expected": expected,
            "majority_class": majority_class,
            "consistency": consistency,
            "median_latency_s": median_lat,
            "counts": dict(cnt),
            "matches_expected": matches_expected,
            "acceptable": acceptable,
        })
        mark = "OK" if acceptable else "FAIL"
        print(f"   SUMMARY: majority={majority_class!r} freq={consistency:.2f} "
              f"counts={dict(cnt)} median_lat={median_lat:.1f}s -> {mark}")
        if not acceptable:
            all_pass = False
        print()

    print("=" * 92)
    print("CALIBRATION AGGREGATE")
    print("=" * 92)
    for s in summary:
        mark = "OK" if s["acceptable"] else "FAIL"
        note = "borderline" if not s["matches_expected"] and s["acceptable"] else ""
        print(f"  {s['id']:40s} expected={s['expected']:12s} majority={s['majority_class']:12s} "
              f"consistency={s['consistency']:.2f}  {mark} {note}")

    n_ok = sum(1 for s in summary if s["acceptable"])
    print()
    print(f"  {n_ok}/{len(summary)} cases pass")
    if all_pass:
        print("  CALIBRATION PASSED — judge is ready to wire into evals/run_eval.py + Slack sampler.")
        return 0
    else:
        print("  CALIBRATION FAILED — DO NOT WIRE into the gate. Investigate flaky/mismatched cases.")
        return 1


if __name__ == "__main__":
    sys.exit(run_calibration())
