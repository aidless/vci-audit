"""Tests for the GSM8K answer handling used by the multi-sample run."""
import pytest

from vci import gsm8k


def test_gold_answer_takes_the_number_after_the_hash_marker():
    assert gsm8k.gold_answer("she sells 12 eggs. #### 18") == "18"
    assert gsm8k.gold_answer("... = 1,234.5 #### 1234.5") == "1234.5"
    assert gsm8k.gold_answer("no marker but 7") == "7"


def test_gold_answer_returns_none_without_a_number():
    assert gsm8k.gold_answer("nothing numeric here") is None
    assert gsm8k.gold_answer(None) is None


def test_extract_prediction_uses_the_last_number():
    assert gsm8k.extract_prediction("so the answer is 42") == "42"
    assert gsm8k.extract_prediction("12 then 34 then 7") == "7"
    assert gsm8k.extract_prediction("I cannot solve it") is None
    assert gsm8k.extract_prediction("1,200") == "1200"


def test_is_correct_is_numeric_not_string_exact():
    assert gsm8k.is_correct("42", "42")
    assert gsm8k.is_correct("42.0", "42")
    assert gsm8k.is_correct("-3", "-3.0")
    assert not gsm8k.is_correct("43", "42")
    assert not gsm8k.is_correct(None, "42")


def test_build_prompt_is_answer_only_and_contains_the_question():
    prompt = gsm8k.build_prompt("Tom has 3 apples.")
    assert "Tom has 3 apples." in prompt
    assert "only" in prompt.lower()
    assert prompt.rstrip().endswith("Answer:")


def test_select_tasks_is_deterministic_and_strided():
    rows = [{"question": f"q{i}", "answer": f"#### {i}"} for i in range(1319)]
    picked = gsm8k.select_tasks(rows, 30)
    assert len(picked) == 30
    assert [t["index"] for t in picked][:3] == [0, 43, 86]
    assert len({t["task_id"] for t in picked}) == 30
    again = gsm8k.select_tasks(rows, 30)
    assert picked == again


def test_select_tasks_handles_empty_and_short_inputs():
    assert gsm8k.select_tasks([], 5) == []
    rows = [{"question": "q0", "answer": "#### 0"}]
    assert len(gsm8k.select_tasks(rows, 5)) == 1


def test_tasks_with_passes_filters_by_pass_count():
    records = [
        {"task_id": "a", "status": "pass"},
        {"task_id": "a", "status": "fail"},
        {"task_id": "b", "status": "fail"},
        {"task_id": "b", "status": "fail"},
        {"task_id": "c", "status": "pass"},
        {"task_id": "c", "status": "pass"},
        {"task_id": None, "status": "pass"},
    ]
    assert gsm8k.tasks_with_passes(records) == ["a", "c"]
    assert gsm8k.tasks_with_passes(records, min_passes=2) == ["c"]
    assert gsm8k.tasks_with_passes(records, min_passes=3) == []
    assert gsm8k.tasks_with_passes([]) == []
