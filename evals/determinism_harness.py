"""
Stage-by-stage determinism harness.

For each question in gill_reference_set.jsonl, hits POST /api/search with
{"debug": true} N times and captures the per-stage I/O snapshot (`stages` dict)
that the API returns when debug=True. Then compares stage outputs across runs
to isolate exactly which stage introduces variance.

Stages captured (in pipeline order):
  question                  -> the user query (sanity check, always identical)
  available_entities        -> entities surfaced by BM25 entity lookup (input to BAML)
  baml_expansion            -> BAML OptimizeSearchQuery `expanded_search_terms` output
  baml_entities             -> BAML OptimizeSearchQuery `official_entities` output
  embedding_input           -> string passed to qwen3-embedding
  enhanced_query            -> bm25-side string used in Weaviate hybrid query
  embedding_hash            -> sha256 of the embedding vector (16 hex chars)
  retrieval_sids_set        -> sorted unique SIDs in retrieved chunks (set equality)
  retrieval_sids_ordered    -> SIDs in retrieved/ranked order (sequence equality)
  retrieval_chunk_ids_ordered -> chunk UUIDs in retrieved/ranked order
  bot_raw_answer            -> pred.answer BEFORE verifier (deepseek raw output)
  bot_final_answer          -> answer AFTER verifier (what user sees)
  bot_citations             -> sorted citation IDs
  bot_reasoning             -> model's CoT reasoning (DSPy)

For each stage we count how many DISTINCT outputs were seen across N runs of
the same question. unique==1 means deterministic; unique>1 means that stage
introduced variance. The per-question table prints `STAGE=K` cells so the
exact handoff point where determinism breaks is visible at a glance.

Usage:
    python evals/determinism_harness.py \\
        --endpoint http://localhost:8000/api/search \\
        --runs 3 \\
        --out-dir evals/output/determinism-2026-06-14
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


STAGES_IN_PIPELINE_ORDER = [
    "available_entities",
    "baml_expansion",
    "baml_entities",
    "embedding_input",
    "enhanced_query",
    "embedding_hash",
    "retrieval_sids_set",
    "retrieval_sids_ordered",
    "retrieval_chunk_ids_ordered",
    "bot_raw_answer",
    "bot_final_answer",
    "bot_citations",
    "bot_reasoning",
]


def stable_hash(obj: Any) -> str:
    """Deterministic short hash of any JSON-serializable value."""
    if obj is None:
        return "NULL"
    if isinstance(obj, str):
        payload = obj
    else:
        payload = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def call_endpoint(endpoint: str, question: str, timeout: float, auth: Optional[str]) -> Dict[str, Any]:
    headers = {}
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    with httpx.Client(timeout=timeout) as client:
        r = client.post(endpoint, headers=headers, json={"query": question, "debug": True})
        r.raise_for_status()
        return r.json()


def load_questions(ref_path: Path) -> List[Dict[str, Any]]:
    qs: List[Dict[str, Any]] = []
    with ref_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            if q.get("_skip"):
                continue
            qs.append(q)
    return qs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True,
                        help="POST endpoint for /api/search (must support debug=true).")
    parser.add_argument("--runs", type=int, default=3, help="Repeat each question N times.")
    parser.add_argument("--ref-set", default="evals/gill_reference_set.jsonl")
    parser.add_argument("--out-dir", default="evals/output/determinism")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--auth-token", default=None)
    parser.add_argument("--ids", nargs="*", default=None,
                        help="Optional subset of question IDs to run.")
    args = parser.parse_args()

    ref_path = Path(args.ref_set)
    if not ref_path.is_file():
        print(f"Reference set not found: {ref_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    questions = load_questions(ref_path)
    if args.ids:
        questions = [q for q in questions if q["id"] in args.ids]

    if not questions:
        print("No questions to run.", file=sys.stderr)
        sys.exit(1)

    total_calls = len(questions) * args.runs
    print(f"Endpoint  : {args.endpoint}")
    print(f"Questions : {len(questions)} (runs={args.runs})  -> {total_calls} total requests")
    print()

    # runs_data[q_id] = list of {stages, error?, elapsed_s} per run, run-major order
    runs_data: Dict[str, List[Dict[str, Any]]] = {q["id"]: [] for q in questions}

    for run_idx in range(args.runs):
        print(f"=== Run {run_idx + 1}/{args.runs} ===")
        for q in questions:
            q_id = q["id"]
            q_text = q["question"]
            t0 = time.time()
            try:
                resp = call_endpoint(args.endpoint, q_text, args.timeout, args.auth_token)
                stages = resp.get("stages") or {}
                runs_data[q_id].append({
                    "stages": stages,
                    "elapsed_s": time.time() - t0,
                })
                marker = "OK" if stages else "NO_STAGES"
                print(f"  [{run_idx + 1}/{args.runs}] {q_id:<40} {marker:<10} {time.time() - t0:5.1f}s")
            except Exception as e:
                runs_data[q_id].append({
                    "error": str(e),
                    "elapsed_s": time.time() - t0,
                })
                print(f"  [{run_idx + 1}/{args.runs}] {q_id:<40} ERROR     {e}")

    # ------------------------------------------------------------------ analysis
    # For each question, for each stage: how many distinct outputs were seen
    # across (successful) runs? unique==1 deterministic; >1 = flake source.
    print()
    print("=" * 100)
    print("STAGE-BY-STAGE DETERMINISM SUMMARY")
    print("=" * 100)

    per_q: Dict[str, Dict[str, Any]] = {}
    stage_questions_with_variance: Dict[str, int] = {s: 0 for s in STAGES_IN_PIPELINE_ORDER}

    for q in questions:
        q_id = q["id"]
        runs = runs_data[q_id]
        successful = [r for r in runs if "error" not in r]
        stage_unique: Dict[str, int] = {}
        stage_examples: Dict[str, List[str]] = {}
        for s in STAGES_IN_PIPELINE_ORDER:
            hashes = [stable_hash((r.get("stages") or {}).get(s)) for r in successful]
            uniq = sorted(set(hashes))
            stage_unique[s] = len(uniq)
            stage_examples[s] = uniq
            if len(uniq) > 1:
                stage_questions_with_variance[s] += 1
        per_q[q_id] = {
            "successful_runs": len(successful),
            "errored_runs": len(runs) - len(successful),
            "stage_unique": stage_unique,
            "stage_hashes": stage_examples,
        }

    n_q = len(questions)
    print(f"Questions: {n_q}  Runs per question: {args.runs}")
    print()
    print(f"{'Stage':<30} {'#Q with variance':>20} {'%':>8}")
    print("-" * 60)
    for s in STAGES_IN_PIPELINE_ORDER:
        c = stage_questions_with_variance[s]
        print(f"{s:<30} {c:>20} {100.0 * c / n_q:>7.1f}%")
    print()
    print("Per-question stage breakdown (only rows with ANY stage variance):")
    print(f"{'question_id':<40} | " + " ".join(f"{s[:4]}" for s in STAGES_IN_PIPELINE_ORDER))
    print("-" * 100)
    flaky_count = 0
    for q in questions:
        q_id = q["id"]
        su = per_q[q_id]["stage_unique"]
        if any(v > 1 for v in su.values()):
            flaky_count += 1
            cells = " ".join(f"{su[s]:>4}" for s in STAGES_IN_PIPELINE_ORDER)
            err = per_q[q_id]["errored_runs"]
            err_marker = f" (errored={err})" if err else ""
            print(f"{q_id:<40} | {cells}{err_marker}")
    print()
    print(f"Flaky questions (any stage varied): {flaky_count} / {n_q}")

    # ------------------------------------------------------------------ persistence
    raw_path = out_dir / "raw_runs.json"
    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(runs_data, f, indent=2, ensure_ascii=False)

    summary_path = out_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({
            "endpoint": args.endpoint,
            "n_questions": n_q,
            "n_runs_per_question": args.runs,
            "stages_in_pipeline_order": STAGES_IN_PIPELINE_ORDER,
            "stage_questions_with_variance": stage_questions_with_variance,
            "per_question": per_q,
        }, f, indent=2, ensure_ascii=False)

    print()
    print(f"Written:")
    print(f"  {raw_path}")
    print(f"  {summary_path}")


if __name__ == "__main__":
    main()
