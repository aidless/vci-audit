"""Contract tests for the harness differential decomposer."""
import csv
import json
import os
import tempfile

import pytest

from vci import harness_decomp as H


def _doc(tasks):
    return {"benchmark": "toy", "model": "m", "harness_a": "A", "harness_b": "B",
            "tasks": tasks}


def test_single_factor_attribution_sums_to_total_delta():
    tasks = [
        # three tasks flip because only the tool envelope differs
        {"task_id": "t1", "a": {"passed": False, "tool_sig": "raw"},
         "b": {"passed": True, "tool_sig": "joined"}},
        {"task_id": "t2", "a": {"passed": False, "tool_sig": "raw"},
         "b": {"passed": True, "tool_sig": "joined"}},
        {"task_id": "t3", "a": {"passed": False, "tool_sig": "raw"},
         "b": {"passed": True, "tool_sig": "joined"}},
        {"task_id": "t4", "a": {"passed": True, "tool_sig": "raw"},
         "b": {"passed": True, "tool_sig": "joined"}},
    ]
    out = H.decompose(_doc(tasks))
    assert out["decomposable"] is True
    assert out["scores"]["a"] == pytest.approx(0.25)
    assert out["scores"]["b"] == pytest.approx(1.0)
    assert out["scores"]["delta"] == pytest.approx(0.75)
    assert out["sources"]["tool"]["n_tasks"] == 4
    assert out["sources"]["tool"]["delta"] == pytest.approx(0.75)
    assert out["sources"]["state"]["delta"] == pytest.approx(0.0)
    assert out["attribution_sums_to_total_delta"] is True
    # buckets must partition the total delta exactly
    buckets = sum(v["delta"] for v in out["sources"].values()) \
        + out["ambiguous"]["delta"] + out["unexplained"]["delta"]
    assert buckets == pytest.approx(out["scores"]["delta"])


def test_multiple_differing_factors_are_ambiguous_not_guessed():
    tasks = [
        {"task_id": "t1",
         "a": {"passed": False, "state_retained": False, "retries": 0},
         "b": {"passed": True, "state_retained": True, "retries": 1}},
    ]
    out = H.decompose(_doc(tasks))
    assert out["ambiguous"]["n_tasks"] == 1
    assert out["ambiguous"]["delta"] == pytest.approx(1.0)
    for f in H.FACTORS:
        assert out["sources"][f]["delta"] == pytest.approx(0.0)


def test_no_factor_difference_but_outcome_changes_is_unexplained():
    tasks = [
        {"task_id": "t1", "a": {"passed": True, "retries": 0, "tool_sig": "x"},
         "b": {"passed": False, "retries": 0, "tool_sig": "x"}},
        {"task_id": "t2", "a": {"passed": True, "retries": 0, "tool_sig": "x"},
         "b": {"passed": True, "retries": 0, "tool_sig": "x"}},
    ]
    out = H.decompose(_doc(tasks))
    assert out["unexplained"]["n_tasks"] == 2
    assert out["unexplained"]["delta"] == pytest.approx(-0.5)
    assert out["scores"]["delta"] == pytest.approx(-0.5)


def test_aggregate_only_is_refused_with_explicit_reason():
    out = H.decompose({"harness_a": "A", "harness_b": "B",
                       "aggregate": {"a": 0.10, "b": 0.22}})
    assert out["decomposable"] is False
    assert out["reason"] == "aggregate_only"
    assert out["observed_delta"] == pytest.approx(0.12)
    assert out["required"]


def test_outcomes_without_factor_flags_are_refused():
    tasks = [{"task_id": "t1", "a": {"passed": True}, "b": {"passed": False}},
             {"task_id": "t2", "a": {"passed": True}, "b": {"passed": True}}]
    out = H.decompose(_doc(tasks))
    assert out["decomposable"] is False
    assert out["reason"] == "no_factor_flags"


def test_empty_document_is_refused():
    out = H.decompose({"tasks": []})
    assert out["decomposable"] is False
    assert out["reason"] == "no_records"


def test_unmatched_tasks_are_reported_and_excluded():
    a = {"harness": "A", "records": [
        {"task_id": "t1", "passed": True, "retries": 0},
        {"task_id": "t2", "passed": True, "retries": 0}]}
    b = {"harness": "B", "records": [
        {"task_id": "t1", "passed": True, "retries": 1},
        {"task_id": "t3", "passed": False, "retries": 1}]}
    out = H.decompose(a, b)
    assert out["n_tasks"] == 1
    assert out["n_unmatched"] == 2
    assert out["sources"]["retry"]["n_tasks"] == 1


def test_top_divergence_ranks_by_absolute_delta():
    tasks = [
        {"task_id": "small", "a": {"score": 0.9, "retries": 0},
         "b": {"score": 1.0, "retries": 1}},
        {"task_id": "big", "a": {"score": 0.2, "retries": 0},
         "b": {"score": 1.0, "retries": 1}},
    ]
    out = H.decompose(_doc(tasks), top_n=2)
    assert [r["task_id"] for r in out["top_divergence"]] == ["big", "small"]


def test_csv_input_is_supported():
    rows = [
        {"task_id": "t1", "a_passed": "false", "b_passed": "true",
         "a_tool_sig": "raw", "b_tool_sig": "joined"},
        {"task_id": "t2", "a_passed": "true", "b_passed": "true",
         "a_tool_sig": "raw", "b_tool_sig": "joined"},
    ]
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "in.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        out = H.decompose_file(path)
    assert out["decomposable"] is True
    assert out["n_tasks"] == 2
    assert out["sources"]["tool"]["delta"] == pytest.approx(0.5)
