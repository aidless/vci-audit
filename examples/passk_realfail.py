#!/usr/bin/env python3
"""Real-trace example: pass@1 on the two archived model batches.

Data used (already in the repository, nothing is fabricated):

* ``outputs/realfail-real.json``       -- 100 tasks, qwen2.5:7b, 1 greedy sample/task
* ``outputs/realfail-coder14b-100.json`` -- 100 identical tasks, qwen2.5-coder:14b

Each trace carries **one** sample per task, so ``pass@1`` is estimable and
``k >= 2`` is not.  The script asks for ``k_max=3`` on purpose: the output must
show ``n/a`` for k=2,3 instead of inventing repeats.  Supply N run files from
your own harness to get the full curve.

Run from anywhere::

    python3 examples/passk_realfail.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vci import passk as P  # noqa: E402

OUT = ROOT / "outputs"
RUNS = {
    "qwen2.5:7b": OUT / "realfail-real.json",
    "qwen2.5-coder:14b": OUT / "realfail-coder14b-100.json",
}


def attempts_of(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    seed = payload["manifest"]["seed"]
    rows = []
    for rec in payload["records"]:
        status = "pass" if rec["verdict"]["passed"] else "fail"
        rows.append({"task_id": f"{rec['family']}/{rec['task_id']}",
                     "seed": seed, "run": 0, "status": status})
    return {"tasks": [{"task_id": r["task_id"], "seed": r["seed"],
                       "runs": [r["status"]]} for r in rows]}


def main():
    for name, path in RUNS.items():
        doc = attempts_of(path)
        result = P.compute(doc, k_max=3, n_boot=1000, seed=0)
        print(f"== {name} — {result['n_tasks']} tasks, "
              f"{result['n_attempts']} attempts ==")
        print(P.format_summary(result))
        print()
        slug = "7b" if ":7b" in name else "14b"
        P.write_report(result, str(OUT / f"example-passk-{slug}.json"))
        with open(OUT / f"example-passk-input-{slug}.json", "w",
                  encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, ensure_ascii=False)
    print("wrote outputs/example-passk-{7b,14b}.json and their input files")
    print("same result from the CLI: vci passk "
          "--input outputs/example-passk-input-7b.json --k-max 3")


if __name__ == "__main__":
    main()
