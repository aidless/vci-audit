"""Harness differential experiment: strategy B (repeat run) vs A (single pass).

These tests pin the behavioural contract of strategy B and the bookkeeping of
``vci.harness_diff``.  They deliberately do *not* assert the pooled numbers of
the full run; those live in work/harness_diff.json and the LOGBOOK.
"""
import random

from vci import adversarial, harness_diff
from vci.audit import family_seed
from vci.registry import INDEX, by_name
from vci.schema import Candidate

FAM = by_name("code_patch")
IDX = INDEX["code_patch"]


def _tasks(n=5, seed=0):
    return FAM.generate(n, random.Random(family_seed(seed, IDX)))


def _probe(task, suffix):
    probes = adversarial.probes_for("code_patch", task, heavy=False)
    hit = [p for p in probes if p.probe_id.endswith(suffix)]
    assert hit, f"no probe ending in {suffix} for {task.task_id}"
    return hit[0]


def _cand(task, probe):
    return Candidate(cand_id=probe.probe_id, task_id=task.task_id,
                     family="code_patch", payload=probe.payload,
                     defect=probe.failure_class, note=probe.note)


def test_strategy_b_catches_the_x02_stateful_leak():
    task = _tasks()[0]
    x02 = _probe(task, "-x02")
    assert x02.operator == "STATE"
    # Sanity: strategy A still accepts it (that is the known leak) ...
    assert FAM.verify(task, _cand(task, x02)).passed
    # ... and strategy B rejects it.
    assert not FAM.verify_twice(task, _cand(task, x02)).passed


def test_strategy_b_does_not_false_reject_correct_implementations():
    task = _tasks()[0]
    for cand in FAM.mutate(task, random.Random(0)):
        if cand.defect in ("correct", "semantic_equivalent"):
            assert FAM.verify_twice(task, cand).passed, cand.cand_id


def test_strategy_b_still_rejects_loud_defects():
    task = _tasks()[0]
    for cand in FAM.mutate(task, random.Random(0)):
        if cand.defect in ("boundary", "off_by_one", "type_mismatch", "order",
                           "missing", "extra", "semantic_wrong"):
            assert not FAM.verify_twice(task, cand).passed, cand.cand_id


def test_strategy_b_catches_every_history_dependent_probe():
    task = _tasks()[0]
    for suffix, op in (("-x03", "STATE"), ("-x04", "NONDET"), ("-x05", "STATE")):
        probe = _probe(task, suffix)
        assert probe.operator == op
        assert not FAM.verify_twice(task, _cand(task, probe)).passed, suffix


def test_strategy_b_still_kills_non_termination():
    task = _tasks()[0]
    probes = adversarial.probes_for("code_patch", task, heavy=True)
    inf = [p for p in probes if p.operator == "INF" and p.expectation == "reject"]
    assert inf
    for p in inf:
        assert not FAM.verify_twice(task, _cand(task, p)).passed


def test_differential_small_run_is_deterministic_and_consistent():
    r1 = harness_diff.run_differential(n_tasks=4, seed=0, n_seeds=2)
    r2 = harness_diff.run_differential(n_tasks=4, seed=0, n_seeds=2)

    def strip(node):  # latency is the only machine-dependent field
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items()
                    if k not in ("probe_rows", "p95_ms")}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    assert strip(r1) == strip(r2)
    p = r1["pooled"]
    assert p["A"]["n"] == p["B"]["n"] > 0
    # The flip matrix accounts for every probe.
    assert sum(p["flips"]["matrix"].values()) == len(r1["probe_rows"]["A"])
    # Every B-only catch is a defect A missed (A_pass_B_fail), never the reverse
    # for a reject-expected probe.
    for ra, rb in zip(r1["probe_rows"]["A"], r1["probe_rows"]["B"]):
        assert ra["probe_id"] == rb["probe_id"]
        if ra["expectation"] == "reject" and not ra["passed"]:
            assert not rb["passed"] or ra["passed"] != rb["passed"]
    # Aligned mutants: A and B agree everywhere.
    ag = r1["aligned_agreement_seed0"]
    assert ag["n"] > 0 and ag["n_disagree"] == 0, ag["disagreements"]


def test_differential_reports_x02_flips():
    r = harness_diff.run_differential(n_tasks=4, seed=0, n_seeds=1)
    x = r["pooled"]["x02"]
    assert x["A"]["accepted"] == x["A"]["n"] > 0  # the leak exists under A
    assert x["B"]["accepted"] == 0                # and is closed under B
