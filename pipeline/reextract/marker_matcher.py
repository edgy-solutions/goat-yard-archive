"""Confusable-margin marker matcher (config-v2). The sequence gate knows the EXPECTED letter at each position;
this is therefore a VERIFIER, not a 24-class classifier: 'is this crop the expected letter e?' The check is a
MARGIN, not a threshold on one template (Chris) — a single-template score false-confirms on confusable pairs at
~20px. So score the crop against e AND e's confusable set (c/e, n/u, h/b, f/s [long-s], o/e, i/l) and CONFIRM
only when e wins by a margin; equal-or-close => ABSTAIN. Separation between populations, not a bar on one.

Evaluation discipline (Chris):
  - HOLD OUT WHOLE RUNS, not exemplars — exemplars from one run share a compositor, a gathering, often a page;
    an exemplar-level split inflates accuracy with near-duplicates. Hold-out runs are spread across the volume.
  - The release gate is CONFIRMED-WRONG on hold-out == 0 (a wrong letter confirmed ships a mapping error).
  - Report overall abstain rate AND abstain rate ON THE CONFUSABLE PAIRS — that is where the margin is tightest
    and the bootstrap leans hardest.
Templates are nearest-neighbour over the TRAIN runs' exemplars (robust for tiny glyphs); the margin is chosen on
TRAIN only, then hold-out is reported at that margin (calibrating the margin on hold-out would be the named sin)."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

EX = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/marker_exemplars")
SEEDS_PATH = Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits/marker_seeds_human_20260913_FINAL.jsonl")
N = 32  # normalization box

# confusable sets (symmetric); f/s is the long-s problem in this type. Illegal twins j/v have no exemplars.
CONF = {"c": ["e", "o"], "e": ["c", "o"], "o": ["c", "e"],
        "n": ["u", "m"], "u": ["n"], "m": ["n"],
        "h": ["b", "k"], "b": ["h"], "k": ["h"],
        "f": ["s"], "s": ["f"],
        "i": ["l"], "l": ["i"]}
CONF_PAIR_LETTERS = set(CONF)                              # letters that HAVE a confusable — the hard set


def _vec(path):
    """A crop -> unit-L2 grayscale vector on an N x N box: ink=high, contrast-stretched, so cosine similarity
    compares glyph shape not exposure. Aspect preserved, centred on the box."""
    im = Image.open(path).convert("L")
    a = 255 - np.asarray(im, float)                        # ink high
    if a.max() > a.min():
        a = (a - a.min()) / (a.max() - a.min())
    im2 = Image.fromarray((a * 255).astype("uint8"))
    w, h = im2.size
    s = (N - 4) / max(w, h)
    im2 = im2.resize((max(1, round(w * s)), max(1, round(h * s))))
    canvas = Image.new("L", (N, N), 0)
    canvas.paste(im2, ((N - im2.size[0]) // 2, (N - im2.size[1]) // 2))
    v = np.asarray(canvas, float).ravel()
    n = np.linalg.norm(v)
    return v / n if n else v


def _load():
    rows = [json.loads(l) for l in (EX / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l).get("crop")]
    for r in rows:
        r["vec"] = _vec(EX / r["crop"]); r["run"] = tuple(r["run"])
    return rows


def _holdout_runs(rows):
    """Whole runs spread across the volume, chosen to cover the confusable letters. Deterministic."""
    picks = [(185, 185), (280, 282), (407, 409), (556, 558), (650, 650), (716, 716), (887, 890)]
    have = {r["run"] for r in rows}
    return [p for p in picks if p in have]


def score(vec, letter, templates):
    """Nearest-neighbour cosine of the crop to any TRAIN exemplar of `letter`. 0 if the letter is unseen."""
    T = templates.get(letter)
    if not T:
        return 0.0
    return float(max(vec @ t for t in T))


def verify(vec, expected, templates, margin):
    """CONFIRM (True) iff expected beats its confusable set by >= margin. Returns (confirm, margin_value)."""
    s_e = score(vec, expected, templates)
    conf = [score(vec, c, templates) for c in CONF.get(expected, [])]
    m = s_e - (max(conf) if conf else 0.0)
    return (m >= margin), m


def _templates(train):
    T = {}
    for r in train:
        T.setdefault(r["letter"], []).append(r["vec"])
    return T


def _confirmed_wrong(holdout, templates, margin):
    """The release-gate metric: a hold-out crop of TRUE letter L, asked 'is this e?' for every confusable e!=L,
    that the verifier CONFIRMS. Each such confirmation would ship a wrong mapping. Must be zero."""
    bad = []
    for r in holdout:
        L = r["letter"]
        for e in CONF.get(L, []):                          # the adversarial asks: a look-alike wrong letter
            if e == L:
                continue
            ok, m = verify(r["vec"], e, templates, margin)
            if ok:
                bad.append(dict(page=r["page"], true=L, confirmed_as=e, margin=round(m, 4), crop=r["crop"]))
    return bad


def _pick_margin(train):
    """Choose the margin on TRAIN ONLY: leave-one-run-out — the smallest margin at which no train crop is
    confirmed as a WRONG confusable across the folds (max coverage subject to zero train confirmed-wrong)."""
    runs = sorted({r["run"] for r in train})
    grid = [round(x, 3) for x in np.arange(0.0, 0.30, 0.01)]
    for margin in grid:
        wrong = 0
        for ho in runs:                                    # leave one train run out, template on the rest
            tr = [r for r in train if r["run"] != ho]
            te = [r for r in train if r["run"] == ho]
            T = _templates(tr)
            wrong += len(_confirmed_wrong(te, T, margin))
        if wrong == 0:
            return margin
    return grid[-1]


ALPHABET = "abcdefghiklmnopqrstuwxyz"


def open_read(vec, templates):
    """OPEN 24-class read (no expected letter) — what a SEED bootstrap would need. Returns (top1, margin, top2).
    This is the hard direction the scope warned about; measured here so the bootstrap decision is evidence-based,
    not assumed."""
    sc = sorted(((score(vec, L, templates), L) for L in ALPHABET), reverse=True)
    return sc[0][1], sc[0][0] - sc[1][0], sc[1][1]


def evaluate():
    rows = _load()
    ho_runs = set(_holdout_runs(rows))
    holdout = [r for r in rows if r["run"] in ho_runs]
    train = [r for r in rows if r["run"] not in ho_runs]
    templates = _templates(train)
    margin = _pick_margin(train)

    # hold-out coverage: ask the TRUE (expected) letter — confirm = mapped, else abstain
    confirmed = [r for r in holdout if verify(r["vec"], r["letter"], templates, margin)[0]]
    abstained = [r for r in holdout if r not in confirmed]
    conf_pair = [r for r in holdout if r["letter"] in CONF_PAIR_LETTERS]
    conf_pair_confirmed = [r for r in conf_pair if verify(r["vec"], r["letter"], templates, margin)[0]]
    wrong = _confirmed_wrong(holdout, templates, margin)

    # by-pair diagnosis of the residual confusions (are they one fixable pair, or the whole named set?)
    wrong_by_pair = {}
    for w in wrong:
        wrong_by_pair[f"{w['true']}->{w['confirmed_as']}"] = wrong_by_pair.get(f"{w['true']}->{w['confirmed_as']}", 0) + 1

    # OPEN-READ viability (the seed bootstrap's actual task): top-1 on hold-out, and each hold-out run's FIRST
    # marker vs its human seed. If this is not near-perfect, template matching CANNOT safely seed unseeded runs.
    seeds = {tuple(json.loads(l)["run"]): json.loads(l)["seed_letter"]
             for l in SEEDS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()} if SEEDS_PATH.exists() else {}
    open_top1 = sum(1 for r in holdout if open_read(r["vec"], templates)[0] == r["letter"])
    seed_reads = []
    for run in sorted(ho_runs):
        k0 = [r for r in holdout if r["run"] == run and r["k"] == 0]
        if not k0:
            continue
        t1, m, t2 = open_read(k0[0]["vec"], templates)
        seed_reads.append(dict(run=list(run), human=seeds.get(run), read=t1, second=t2,
                               margin=round(m, 4), correct=(t1 == seeds.get(run))))
    open_seed_correct = sum(1 for s in seed_reads if s["correct"])

    ho_letters = sorted({r["letter"] for r in holdout})
    missing_conf = sorted(CONF_PAIR_LETTERS - set(ho_letters))
    report = dict(
        margin=margin, train_runs=len({r["run"] for r in train}), train_exemplars=len(train),
        holdout_runs=[list(r) for r in sorted(ho_runs)], holdout_exemplars=len(holdout),
        holdout_letters=ho_letters, confusable_letters_missing_from_holdout=missing_conf,
        confirmed_wrong=wrong,                              # MUST be []
        overall_confirm=len(confirmed), overall_abstain=len(abstained),
        overall_abstain_rate=round(len(abstained) / max(1, len(holdout)), 3),
        confusable_pair_exemplars=len(conf_pair), confusable_pair_confirm=len(conf_pair_confirmed),
        confusable_pair_abstain_rate=round(1 - len(conf_pair_confirmed) / max(1, len(conf_pair)), 3),
        confirmed_wrong_by_pair=wrong_by_pair,
        open_read_top1=open_top1, open_read_top1_rate=round(open_top1 / max(1, len(holdout)), 3),
        open_seed_reads=seed_reads, open_seed_correct=open_seed_correct, open_seed_total=len(seed_reads),
        bootstrap_viable=(open_seed_correct == len(seed_reads) and len(seed_reads) > 0),
    )
    (EX / "matcher_eval.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"MARGIN (picked on TRAIN, leave-one-run-out): {margin}")
    print(f"train: {report['train_runs']} runs / {report['train_exemplars']} exemplars")
    print(f"hold-out: {len(ho_runs)} runs {report['holdout_runs']} / {len(holdout)} exemplars, "
          f"letters={''.join(ho_letters)}")
    if missing_conf:
        print(f"  WARN confusable letters absent from hold-out: {missing_conf}")
    print(f"CONFIRMED-WRONG on hold-out (release gate, must be 0): {len(wrong)}")
    for w in wrong:
        print(f"    p{w['page']} true={w['true']} confirmed_as={w['confirmed_as']} margin={w['margin']}")
    print(f"overall: confirm {len(confirmed)}/{len(holdout)}  abstain-rate {report['overall_abstain_rate']}")
    print(f"confusable-pair ({''.join(sorted(CONF_PAIR_LETTERS))}): confirm {len(conf_pair_confirmed)}/{len(conf_pair)}  "
          f"abstain-rate {report['confusable_pair_abstain_rate']}")
    print("--- OPEN-READ (the seed-bootstrap task) ---")
    print(f"open-read top-1 on hold-out: {open_top1}/{len(holdout)} = {report['open_read_top1_rate']}")
    print(f"held-out run first-marker vs human seed: {open_seed_correct}/{len(seed_reads)} correct")
    for s in seed_reads:
        print(f"    run {s['run']} human={s['human']} read={s['read']} (2nd={s['second']}) "
              f"margin={s['margin']}  {'OK' if s['correct'] else 'WRONG'}")
    print(f"BOOTSTRAP VIABLE (open-seed read is safe): {report['bootstrap_viable']}")
    print(f"wrote {EX/'matcher_eval.json'}")
    return report


if __name__ == "__main__":
    evaluate()
