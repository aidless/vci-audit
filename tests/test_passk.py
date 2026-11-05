"""Contract tests for the pass@k / pass^k calculator."""
import json
import os
import tempfile

import pytest

from vci import passk as P


def _tasks(*runs_per_task):
    return {"tasks": [{"task_id": f"t{i}", "seed": 0, "runs": list(runs)}
                      for i, runs in enumerate(runs_per_task)]}


def test_all_pass_is_one_at_every_k():
    out = P.compute(_tasks(["pass"] * 4, ["pass"] * 4, ["pass"] * 4),
                    k_max=4, n_boot=50, seed=7)
    for k in range(1, 5):
        at = out["curves"]["as_failure"]["pass@k"][k - 1]
        pw = out["curves"]["as_failure"]["pass^k"][k - 1]
        assert at["value"] == pytest.approx(1.0)
        assert pw["value"] == pytest.approx(1.0)
        assert at["ci"] == pytest.approx([1.0, 1.0])


def test_all_fail_is_zero_at_every_k():
    out = P.compute(_tasks(["fail"] * 3, ["fail"] * 3), k_max=3, n_boot=20, seed=1)
    for k in range(1, 4):
        assert out["curves"]["as_failure"]["pass@k"][k - 1]["value"] == pytest.approx(0.0)
        assert out["curves"]["as_failure"]["pass^k"][k - 1]["value"] == pytest.approx(0.0)


def test_unbiased_estimators_known_values():
    # n=4, c=2, k=2 -> pass@2 = 1 - C(2,2)/C(4,2) = 5/6 ; pass^2 = C(2,2)/C(4,2) = 1/6
    assert P.unbiased_pass_at_k(4, 2, 2) == pytest.approx(5.0 / 6.0)
    assert P.unbiased_pass_pow_k(4, 2, 2) == pytest.approx(1.0 / 6.0)
    # k=1 degenerates to the per-task pass rate
    assert P.unbiased_pass_at_k(4, 2, 1) == pytest.approx(0.5)
    assert P.unbiased_pass_pow_k(4, 2, 1) == pytest.approx(0.5)
    # k larger than n is not estimable
    assert P.unbiased_pass_at_k(2, 1, 3) is None
    assert P.unbiased_pass_pow_k(2, 1, 3) is None


def test_pass_at_1_equals_mean_per_task_success_rate():
    out = P.compute(_tasks(["pass", "fail", "fail", "fail"],
                           ["pass", "pass", "fail", "pass"],
                           ["fail", "fail", "fail", "fail"]),
                    k_max=1, n_boot=10, seed=0)
    expected = (1 / 4 + 3 / 4 + 0 / 4) / 3
    assert out["curves"]["as_failure"]["pass@k"][0]["value"] == pytest.approx(expected)


def test_k_beyond_run_count_is_not_estimable_and_reported():
    out = P.compute(_tasks(["pass", "fail"], ["pass", "fail", "pass"]),
                    k_max=4, n_boot=10, seed=0)
    pts = out["curves"]["as_failure"]["pass@k"]
    assert pts[1]["estimable"] is True          # k=2: both tasks have n>=2
    assert pts[2]["estimable"] is True          # k=3: one task still has n=3
    assert pts[2]["n_tasks"] == 1
    assert pts[3]["estimable"] is False         # k=4: no task has 4 runs
    assert pts[3]["value"] is None


def test_timeout_and_refusal_accounting_modes_differ():
    out = P.compute(_tasks(["pass", "timeout", "refusal"],
                           ["pass", "fail", "fail"]),
                    k_max=1, n_boot=20, seed=0)
    assert out["status_counts"]["timeout"] == 1
    assert out["status_counts"]["refusal"] == 1
    as_fail = out["curves"]["as_failure"]["pass@k"][0]["value"]
    excl = out["curves"]["exclude_nonattest"]["pass@k"][0]["value"]
    assert as_fail == pytest.approx((1 / 3 + 1 / 3) / 2)
    assert excl == pytest.approx((1 / 1 + 1 / 3) / 2)
    assert excl > as_fail


def test_duplicate_attempt_triples_raise():
    doc = {"tasks": [{"task_id": "t1", "seed": 0,
                      "runs": [{"run": 0, "status": "pass"},
                               {"run": 0, "status": "fail"}]}]}
    with pytest.raises(ValueError, match="duplicate attempt"):
        P.compute(doc, k_max=1, n_boot=10)

    flat = [{"task_id": "t1", "seed": 0, "run": 0, "passed": True},
            {"task_id": "t1", "seed": 0, "run": 0, "passed": False}]
    with pytest.raises(ValueError, match="duplicate attempt"):
        P.compute(flat, k_max=1, n_boot=10)


def test_multiple_seeds_count_as_independent_attempts():
    doc = [{"task_id": "t1", "seed": 1, "run": 0, "passed": True},
           {"task_id": "t1", "seed": 2, "run": 0, "passed": False}]
    out = P.compute(doc, k_max=1, n_boot=10, seed=0)
    assert out["n_tasks"] == 1
    assert out["n_attempts"] == 2
    assert out["run_counts"]["max"] == 2
    assert out["curves"]["as_failure"]["pass@k"][0]["value"] == pytest.approx(0.5)
    assert out["seeds"]["per_task"]["t1"] == [1, 2]


def test_bootstrap_interval_is_deterministic_and_brackets_estimate():
    doc = _tasks(["pass", "pass", "fail", "fail"], ["pass", "fail", "fail", "fail"],
                 ["pass", "pass", "pass", "fail"], ["fail", "fail", "fail", "fail"])
    a = P.compute(doc, k_max=2, n_boot=200, seed=11)
    b = P.compute(doc, k_max=2, n_boot=200, seed=11)
    for k_idx in range(2):
        pa = a["curves"]["as_failure"]["pass@k"][k_idx]
        pb = b["curves"]["as_failure"]["pass@k"][k_idx]
        assert pa["value"] == pytest.approx(pb["value"])
        assert pa["ci"] == pytest.approx(pb["ci"])
        lo, hi = pa["ci"]
        assert lo <= pa["value"] <= hi


def test_json_input_roundtrip():
    doc = {"tasks": [{"task_id": "t1", "seed": 0, "runs": ["pass", "fail"]},
                     {"task_id": "t2", "seed": 0, "runs": [True, True]}]}
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "attempts.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        out = P.compute_file(path, k_max=2, n_boot=20, seed=0)
    assert out["n_tasks"] == 2
    assert out["n_attempts"] == 4


def test_empty_input_is_refused():
    out = P.compute({"tasks": []}, k_max=1, n_boot=10)
    assert out["ok"] is False
    assert out["reason"] == "no_attempts"
