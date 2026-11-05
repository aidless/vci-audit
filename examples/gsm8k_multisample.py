#!/usr/bin/env python3
"""Run GSM8K with N samples per task on a local ollama model, then feed pass^k.

Usage::

    python3 examples/gsm8k_multisample.py --n-tasks 30 --samples 8 \
        --model qwen2.5-coder:14b --out outputs/gsm8k-multisample.jsonl

The dataset is the official GSM8K test split (MIT licence), downloaded once from
https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl
onto ``outputs/gsm8k-test.jsonl``.  Task ids are the file indices, so the selection is
recomputable with or without the local copy.

The run is resumable: attempts already present in ``--out`` are skipped.
"""
import argparse
import json
import os
import pathlib
import re
import statistics
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vci import gsm8k, passk  # noqa: E402

DATA = ROOT / "outputs" / "gsm8k-test.jsonl"
URL = ("https://raw.githubusercontent.com/openai/grade-school-math/master/"
       "grade_school_math/data/test.jsonl")


def ensure_dataset(path=DATA):
    if path.exists() and path.stat().st_size > 500_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL, timeout=120) as fh:
        path.write_bytes(fh.read())
    return path


def load_done(path):
    done = set()
    if not path.exists():
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            done.add((rec.get("task_id"), rec.get("seed")))
    return done


def generate(prompt, model, seed, timeout=900):
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 1.1, "top_p": 0.95, "num_predict": 16,
                    "seed": seed, "stop": ["\n"]},
    }).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        payload = json.load(fh)
    return payload, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-tasks", type=int, default=30)
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--model", default="qwen2.5-coder:14b")
    ap.add_argument("--seed-base", type=int, default=9000)
    ap.add_argument("--out", default=str(ROOT / "outputs" / "gsm8k-multisample.jsonl"))
    ap.add_argument("--summary", default=str(ROOT / "outputs" / "gsm8k-multisample.json"))
    ap.add_argument("--calibrate-from", default=None,
                    help="pilot jsonl; keep only tasks that passed at least once")
    args = ap.parse_args()

    rows = [json.loads(line) for line in
            ensure_dataset().read_text(encoding="utf-8").splitlines() if line.strip()]
    tasks = gsm8k.select_tasks(rows, args.n_tasks)
    if args.calibrate_from:
        pilot = [json.loads(line) for line in
                 pathlib.Path(args.calibrate_from).read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        keep = set(gsm8k.tasks_with_passes(pilot))
        tasks = [t for t in tasks if t["task_id"] in keep][:args.n_tasks]
        print(f"calibrated: {len(tasks)} tasks kept of {args.n_tasks}", flush=True)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out)

    started = time.time()
    calls = 0
    with open(out, "a", encoding="utf-8") as fh:
        for task in tasks:
            prompt = gsm8k.build_prompt(task["question"])
            for j in range(args.samples):
                seed = args.seed_base + j
                if (task["task_id"], seed) in done:
                    continue
                payload, wall = generate(prompt, args.model, seed)
                text = payload.get("response", "")
                pred = gsm8k.extract_prediction(text)
                rec = {
                    "task_id": task["task_id"], "index": task["index"],
                    "seed": seed, "attempt": j,
                    "question": task["question"], "gold": task["gold"],
                    "raw": text, "pred": pred,
                    "status": "pass" if gsm8k.is_correct(pred, task["gold"]) else "fail",
                    "wall_s": round(wall, 2),
                    "eval_count": payload.get("eval_count"),
                    "prompt_eval_count": payload.get("prompt_eval_count"),
                    "model": args.model,
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                calls += 1
                if calls % 20 == 0:
                    print(f"{calls} calls, {time.time()-started:.0f}s", flush=True)

    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    doc = {"tasks": []}
    by_task = {}
    for rec in records:
        by_task.setdefault(rec["task_id"], []).append(rec)
    # One task entry per (task_id, seed) so the summary records every seed that
    # was actually sampled instead of just the first one.
    for tid in sorted(by_task):
        by_task[tid].sort(key=lambda r: r["seed"])
        for rec in by_task[tid]:
            doc["tasks"].append({"task_id": tid, "seed": rec["seed"],
                                 "runs": [{"run": rec["attempt"],
                                           "status": rec["status"]}]})

    result = passk.compute(doc, k_max=args.samples, n_boot=2000, seed=0)
    walls = [r["wall_s"] for r in records]
    result["run"] = {
        "model": args.model, "n_tasks": len(by_task), "samples": args.samples,
        "wall_s_total": round(sum(walls), 1),
        "wall_s_median_per_call": round(statistics.median(walls), 2),
        "wall_s_mean_per_call": round(statistics.mean(walls), 2),
        "out_tokens_mean": round(statistics.mean(r["eval_count"] or 0 for r in records), 2),
        "temperature": 1.1, "top_p": 0.95, "num_predict": 16,
        "prompt": "answer-only", "seeds": [args.seed_base + j for j in range(args.samples)],
        "dataset": "GSM8K test split (MIT), 1319 rows, stride selection",
    }
    pathlib.Path(args.summary).write_text(json.dumps(result, indent=1, ensure_ascii=False),
                                          encoding="utf-8")
    print(passk.format_summary(result))
    print(f"{len(records)} attempts in {sum(walls):.0f}s "
          f"(median {statistics.median(walls):.1f}s/call)")
    print(f"wrote {out} and {args.summary}")


if __name__ == "__main__":
    main()
