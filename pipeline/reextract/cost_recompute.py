"""Recompute run 501ab577a18a6785's cost as measured tokens x live list price (ruling 1, 2026-10-18).

The run recorded only `completion_tokens` per call, so the INPUT side -- which dominates a vision
call -- is not in the record.  It is recoverable: every one of the 178 rows carries the generation id,
and OpenRouter's generation endpoint returns the native prompt/completion counts for each.  So this
script makes 1 + 178 METADATA GETs.  It sends no image, no prompt and no crop; it starts no read; it
costs nothing.  It is not a scoring run and nothing here may be cited as one.

Two figures come out, and they are not the same kind of thing:

  cost_law      = sum over calls of (prompt_tokens * input_list_price + completion_tokens * output_list_price)
                  -- the figure the cost law uses: measured tokens x live list price.
  cost_witness  = sum of the per-call `cost` field the API returned at read time
                  -- a witness, which can embed discounts, cache pricing, rounding or a provider's
                  own accounting, and therefore cannot stand in for the law's figure.

Both are recorded, with the per-arm breakdown and the divergence.  A disagreement is not an error in
either one; it is the thing worth knowing.

ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88).

Run:  PYTHONIOENCODING=utf-8 <venv>/python.exe cost_recompute.py [--dry-run]
      Key is read from a path given by --key-file, outside both repos.  It is never written or echoed.
"""
import argparse
import hashlib
import io
import json
import pathlib
import sys
import time
from urllib.parse import urlparse

import httpx

A = pathlib.Path("C:/Users/cnogr/git/dr-voluminous/reextract_vol1/audits")
RUN = "501ab577a18a6785"
READS = A / ("score45_reads_%s.jsonl" % RUN)
HOST = "openrouter.ai"
GEN = "https://openrouter.ai/api/v1/generation"
MODELS = "https://openrouter.ai/api/v1/models"
FORBIDDEN = ("192.168.1.179", "192.168.1.188", "192.168.1.169")
ARMS = ("anthropic/claude-opus-5.5", "qwen/qwen3.7-plus")
RETRY_CODES = (429, 500, 502, 503, 504)
RETRIES, BACKOFF = 4, 2.0

CHECKS = 0


def chk(cond, what):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError("CHECK FAILED: %s" % what)
    return True


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha16(b):
    return hashlib.sha256(b).hexdigest()[:16]


def get(url, key, params=None):
    """A metadata GET with counted retries.  Raises on a 429 that survives them."""
    tries = 0
    while True:
        r = httpx.get(url, headers={"Authorization": "Bearer %s" % key}, params=params, timeout=60)
        if r.status_code not in RETRY_CODES or tries >= RETRIES:
            break
        tries += 1
        time.sleep(BACKOFF * (2 ** (tries - 1)))
    if r.status_code == 429:
        raise RuntimeError("429 survived %d retries on %s" % (RETRIES, url))
    return r, tries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--key-file", default="C:/tmp/key-hebrew.txt")
    a = ap.parse_args()

    chk(urlparse(GEN).hostname == HOST, "generation host is openrouter.ai")
    chk(urlparse(MODELS).hostname == HOST, "models host is openrouter.ai")
    for h in FORBIDDEN:
        chk(h not in GEN and h not in MODELS, "forbidden host %s absent" % h)

    rows = [json.loads(l) for l in io.open(READS, encoding="utf-8")]
    chk(len(rows) == 178, "178 rows in the read record")
    chk(all(r.get("gen_id") for r in rows), "every row carries a generation id")
    chk(sorted({r["arm"] for r in rows}) == sorted(ARMS), "exactly the two recorded arms")
    witness = {m: 0.0 for m in ARMS}
    for r in rows:
        witness[r["arm"]] += r["cost_usd"] or 0.0

    if a.dry_run:
        print("DRY-RUN: %d rows, %d generation ids, 1 models call -- nothing fetched, nothing written."
              % (len(rows), len({r["gen_id"] for r in rows})))
        print("witness totals per arm:", {k: round(v, 6) for k, v in witness.items()})
        print("checks: %d" % CHECKS)
        return 0

    key = io.open(a.key_file, encoding="utf-8").read().strip()
    chk(bool(key), "key file is not empty")
    chk(key.startswith("sk-or-"), "key has the expected prefix")

    r, _ = get(MODELS, key)
    chk(r.status_code == 200, "models endpoint returned 200, got %s" % r.status_code)
    cat = {m["id"]: m for m in r.json()["data"]}
    price = {}
    for m in ARMS:
        chk(m in cat, "list price present for %s" % m)
        p = cat[m]["pricing"]
        price[m] = {"prompt": float(p["prompt"]), "completion": float(p["completion"]),
                    "fetched_from": MODELS}
        chk(price[m]["prompt"] > 0 and price[m]["completion"] > 0, "nonzero list price for %s" % m)

    law = {m: 0.0 for m in ARMS}
    toks = {m: {"prompt": 0, "completion": 0} for m in ARMS}
    per_call, retry_total, missing = [], 0, []
    for i, row in enumerate(rows, 1):
        g, tries = get(GEN, key, params={"id": row["gen_id"]})
        retry_total += tries
        if g.status_code != 200:
            missing.append({"span_id": row["span_id"], "arm": row["arm"], "channel": row["channel"],
                            "gen_id": row["gen_id"], "http": g.status_code})
            continue
        d = g.json().get("data") or {}
        pt = d.get("native_tokens_prompt")
        ct = d.get("native_tokens_completion")
        if pt is None or ct is None:
            missing.append({"span_id": row["span_id"], "arm": row["arm"], "channel": row["channel"],
                            "gen_id": row["gen_id"], "why": "no native token counts in the response"})
            continue
        m = row["arm"]
        c = pt * price[m]["prompt"] + ct * price[m]["completion"]
        law[m] += c
        toks[m]["prompt"] += pt
        toks[m]["completion"] += ct
        per_call.append({"span_id": row["span_id"], "arm": m, "channel": row["channel"],
                         "gen_id": row["gen_id"], "prompt_tokens": pt, "completion_tokens": ct,
                         "out_tokens_recorded_at_read": row["out_tokens"],
                         "cost_law_usd": round(c, 8), "cost_witness_usd": row["cost_usd"],
                         "provider": row["provider"]})
        if i % 40 == 0:
            print("  %d/%d" % (i, len(rows)))

    chk(not missing, "every generation resolved; unresolved: %s" % json.dumps(missing)[:400])
    chk(len(per_call) == 178, "178 calls costed, got %d" % len(per_call))
    # the out-token count recorded at read time must match what the generation endpoint reports,
    # or one of the two is not describing this run
    mismatch = [c for c in per_call
                if c["out_tokens_recorded_at_read"] is not None
                and c["completion_tokens"] != c["out_tokens_recorded_at_read"]]
    out = {
        "kind": "cost_recompute",
        "page_convention": "ALL PAGE NUMBERS ARE FILE PAGES (printed = file - 88)",
        "run": RUN,
        "basis": {
            "cost_law": "sum over calls of measured native tokens x live list price; THIS is the figure "
                        "the cost law uses",
            "cost_witness": "sum of the per-call `cost` field returned at read time; a witness only -- "
                            "it can embed discounts, cache pricing, rounding or provider accounting",
            "input_tokens_were_not_recorded_at_read":
                "the run stored completion_tokens only, so prompt tokens were recovered afterwards "
                "from the generation endpoint by gen_id; the recovery is a metadata fetch and sent no "
                "prompt, image or crop",
        },
        "list_price_per_token": price,
        "tokens_measured": toks,
        "cost_law_usd": {m: round(v, 6) for m, v in law.items()},
        "cost_law_usd_total": round(sum(law.values()), 6),
        "cost_witness_usd": {m: round(v, 6) for m, v in witness.items()},
        "cost_witness_usd_total": round(sum(witness.values()), 6),
        "divergence_usd": round(sum(law.values()) - sum(witness.values()), 6),
        "out_token_cross_check": {"compared": len(per_call), "mismatched": len(mismatch),
                                  "rows": mismatch[:10]},
        "metadata_calls": 1 + len(rows),
        "retries": retry_total,
        "spend_of_this_script_usd": 0.0,
    }
    out["self_sha16_rule"] = ("sha256 over canonical JSON of this object with self_sha16 and "
                              "self_sha16_rule removed, sort_keys=True, separators=(',',':'), "
                              "ensure_ascii=False, encoded UTF-8; first 16 hex")
    body = dict(out)
    out["self_sha16"] = sha16(canon(body).encode("utf-8"))

    dest = A / ("COST_RECOMPUTE_%s_%s.json" % (RUN, out["self_sha16"]))
    chk(not dest.exists(), "refusing to clobber %s" % dest.name)
    io.open(dest, "w", encoding="utf-8", newline="\n").write(
        json.dumps({"header": out, "per_call": per_call}, indent=1, ensure_ascii=False) + "\n")
    chk("sk-or-" not in io.open(dest, encoding="utf-8").read(), "no key material in the output")

    print("\nlist price per token:")
    for m in ARMS:
        print("  %-28s prompt %.10f  completion %.10f" % (m, price[m]["prompt"], price[m]["completion"]))
    print("tokens measured:", json.dumps(toks))
    print("COST (law: measured tokens x list price) $%.6f" % out["cost_law_usd_total"],
          json.dumps(out["cost_law_usd"]))
    print("COST (witness: per-call cost field)      $%.6f" % out["cost_witness_usd_total"],
          json.dumps(out["cost_witness_usd"]))
    print("divergence (law - witness) $%.6f" % out["divergence_usd"])
    print("out-token cross-check: %d compared, %d mismatched" % (len(per_call), len(mismatch)))
    print("wrote", dest.name, "| metadata calls", out["metadata_calls"], "| retries", retry_total)
    print("checks: %d" % CHECKS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
