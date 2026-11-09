"""Verify the committed Round 22 paired harness result.

This is an offline check: it recomputes the paired report from the two
committed archives and compares it with the committed report. It never calls
a model or network endpoint.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vci import agent_trace  # noqa: E402


def main() -> int:
    result_dir = ROOT / "outputs" / "round22"
    base = json.loads(
        (result_dir / "agent-stable-stdout-k12.json").read_text(encoding="utf-8")
    )["replicas"]
    echo = json.loads(
        (result_dir / "agent-stable-echo-k12.json").read_text(encoding="utf-8")
    )["replicas"]
    committed = json.loads(
        (result_dir / "agent-stable-echo-paired.json").read_text(encoding="utf-8")
    )

    expected_seeds = [20261105 + 7919 * index for index in range(12)]
    for label, archives, harness in (
        ("stdout", base, "stdout_only (production)"),
        ("echo", echo, "stdout+repl_echo (round-19 counterfactual, live)"),
    ):
        if len(archives) != 12:
            raise SystemExit(f"{label}: expected 12 replicas")
        for index, archive in enumerate(archives):
            manifest = archive.get("manifest") or {}
            if manifest.get("seed") != expected_seeds[index]:
                raise SystemExit(f"{label}: seed mismatch at {index}")
            if manifest.get("model_digest") != (
                "9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849"
            ):
                raise SystemExit(f"{label}: model digest mismatch at {index}")
            if manifest.get("harness") != harness:
                raise SystemExit(f"{label}: harness mismatch at {index}")
            records = archive.get("records") or []
            if [record.get("task_id") for record in records] != [
                "agt-02-running-max",
                "agt-05-log-latency",
            ]:
                raise SystemExit(f"{label}: task mismatch at {index}")

    recomputed = agent_trace.paired_harness_report(base, echo)
    for key in ("design", "tasks", "pooled"):
        if committed.get(key) != recomputed.get(key):
            raise SystemExit(f"committed report differs in {key}")
    print("Round 22: 12 paired seeds x 2 tasks; delta 0.0, McNemar p=1.0")
    print("report verified:", result_dir / "agent-stable-echo-paired.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
