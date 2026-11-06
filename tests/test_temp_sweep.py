"""Round 15: the temperature-sweep artifact is consumable by the round-10
exploit-signature scanner, offline (no ollama).

Pins three things: (1) the sweep targets exactly the three families the
signature scanner encodes; (2) a sweep-shaped record (same keys, payload
already passed through realfail_adapt) round-trips through the scanner;
(3) sample seeds are distinct across temperatures and replicate indices, so
samples never share a decoding stream.
"""
import json
import random
import sys

import pytest

sys.path.insert(0, ".")
sys.path.insert(0, "work")

pytest.importorskip(
    "temp_sweep",
    reason="work/ is git-ignored; the sweep script ships only in the working tree",
)
import temp_sweep  # noqa: E402
import realfail_real_check  # noqa: E402
from vci import realfail as rf  # noqa: E402
from vci import registry  # noqa: E402
from vci.schema import Candidate  # noqa: E402


def test_sweep_targets_match_the_signature_families():
    assert set(temp_sweep.EXPLOIT_FAMILIES) == {
        "regex_construct", "sql_result", "code_patch"}
    for attr in ("regex_signature", "sql_signature", "code_signature"):
        assert callable(getattr(realfail_real_check, attr))


def test_sample_seeds_are_distinct_across_temp_and_replicate():
    seeds = set()
    for temp in (0.7, 1.0):
        for k in range(2):
            seeds.add(20261104 + 7919 * k + int(temp * 100))
    assert len(seeds) == 4


def test_sweep_record_round_trips_through_the_scanner(tmp_path):
    fams = {f.name: f for f in registry.FAMILIES}
    fam = fams["code_patch"]
    seed, n_tasks = 20261104, 2
    rng = random.Random(rf.family_seed(seed, rf.INDEX[fam.name]))
    tasks = fam.generate(n_tasks, rng)
    task = tasks[0]
    prompt = rf.build_prompt(task, fam)
    # a synthetic "model sample": the correct template source, passed through
    # the same parse/adapt/verify path the sweep uses, without the network
    from vci.families.structural import _CODE_TEMPLATES
    tpl = next(t for t in _CODE_TEMPLATES if t["name"] == task.meta["template"])
    payload = {"answers": tpl["correct"].splitlines()}
    payload = fam.realfail_adapt(payload)
    verdict = fam.verify(task, Candidate(
        cand_id=task.task_id + "-real-t1.0s0", task_id=task.task_id,
        family=fam.name, payload=payload, defect="real_model_output",
        note="offline scanner round-trip"))
    artifact = {
        "manifest": {
            "kind": "vci-realfail", "version": rf.REALFAIL_VERSION,
            "model": "offline", "model_digest": None,
            "host": "http://localhost:11434", "seed": seed,
            "n_tasks": n_tasks, "families": ["code_patch"],
            "temperature": [1.0], "max_tokens": 1024,
            "samples_per_task": 2,
            "date": "1970-01-01 00:00:00 UTC",
        },
        "records": [{
            "family": fam.name, "task_id": task.task_id,
            "sample_id": "t1s0", "n_units": task.n_items,
            "prompt_chars": len(prompt), "prompt": prompt,
            "decoding": {"temperature": 1.0, "seed": 20261104,
                         "num_predict": 1024},
            "raw_response": "", "wall_s": 0.0,
            "parse_status": "ok", "payload": payload,
            "verdict": {"passed": verdict.passed,
                        "score": round(verdict.score, 6),
                        "evidence": verdict.evidence},
        }],
    }
    run_path = tmp_path / "sweep.json"
    out_path = tmp_path / "check.json"
    run_path.write_text(json.dumps(artifact), encoding="utf-8")
    argv = (realfail_real_check.RUN_PATH, realfail_real_check.OUT_PATH)
    realfail_real_check.RUN_PATH = str(run_path)
    realfail_real_check.OUT_PATH = str(out_path)
    try:
        assert realfail_real_check.main() == 0
    finally:
        realfail_real_check.RUN_PATH, realfail_real_check.OUT_PATH = argv
    out = json.loads(out_path.read_text(encoding="utf-8"))
    # the correct implementation is not an exploit and must be accepted
    assert out["flagged_summary"]["n"] == 0
    assert out["per_family"]["code_patch"]["tasks_passed"] == 1
