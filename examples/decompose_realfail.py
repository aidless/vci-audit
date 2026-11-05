#!/usr/bin/env python3
"""Real-trace example: decompose a harness change on the archived qwen2.5:7b run.

Data used (both already in the repository, nothing is fabricated):

* ``outputs/realfail-real.json``      -- 100 tasks, qwen2.5:7b, greedy, seed 20261104
* ``outputs/realfail-real-check.json`` -- the round-10 counterfactual replay of the
  *same archived replies* through the ``realfail_adapt`` envelope hook.  The model
  was not re-run; only the harness layer that hands the payload to the execution
  side changed.  That is exactly one mechanism: ``tool``.

Run from anywhere::

    python3 examples/decompose_realfail.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vci import harness_decomp as H  # noqa: E402

OUT = ROOT / "outputs"


def build_document():
    run = json.loads((OUT / "realfail-real.json").read_text(encoding="utf-8"))
    check = json.loads((OUT / "realfail-real-check.json").read_text(encoding="utf-8"))
    regrade = {r["task_id"]: r for r in check["code_patch_regrade"]["records"]}

    tasks = []
    for rec in run["records"]:
        tid = rec["task_id"]
        passed_a = bool(rec["verdict"]["passed"])
        if tid in regrade:
            # A: the archived reply was handed over as a JSON list of lines
            # B: the same reply is joined into module source before verification
            passed_b = bool(regrade[tid]["adapted_passed"])
            side_a = {"tool_sig": "json_list_envelope"}
            side_b = {"tool_sig": "joined_source"}
        else:
            passed_b = passed_a
            side_a = side_b = {"tool_sig": "native_payload"}
        tasks.append({"task_id": tid,
                      "a": {"passed": passed_a, **side_a},
                      "b": {"passed": passed_b, **side_b}})

    return {
        "benchmark": "vci-audit/realfail (20 families x 5 tasks, seed 20261104)",
        "model": run["manifest"]["model"],
        "harness_a": "archived payload envelope (strict JSON)",
        "harness_b": "round-10 realfail_adapt envelope (joined source)",
        "note": ("same model, same replies, same tasks; only the execution-layer "
                 "payload envelope differs on the 5 code_patch tasks"),
        "tasks": tasks,
    }


def main():
    doc = build_document()
    result = H.decompose(doc)

    print("== harness differential decomposition (real qwen2.5:7b traces) ==")
    print(H.format_summary(result))

    agg = {
        "harness_a": "qwen2.5:7b (100 tasks)",
        "harness_b": "qwen2.5-coder:14b (100 tasks)",
        "aggregate": {"a": 10 / 100, "b": 22 / 100},
        "note": "two different models: a harness decomposition would be invalid "
                "even with per-task rows",
    }
    refused = H.decompose(agg)
    print("\n== degraded input: aggregate scores only ==")
    print(H.format_summary(refused))

    H.write_report(result, str(OUT / "example-harness-decomp.json"))
    H.write_report(refused, str(OUT / "example-harness-decomp-refused.json"))
    with open(OUT / "example-decomp-input.json", "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
    print("\nwrote outputs/example-decomp-input.json, "
          "outputs/example-harness-decomp.json and "
          "outputs/example-harness-decomp-refused.json")
    print("same result from the CLI: vci harness-decomp "
          "--input outputs/example-decomp-input.json --out work/decomp.json")


if __name__ == "__main__":
    main()
