"""Verifier contract tests: one interface, honest answers, no crash on garbage."""
import copy
import random

import pytest

from vci import registry
from vci.families import numeric
from vci.schema import Candidate, Verdict


def _first_task(fam, seed=0):
    return fam.generate(1, random.Random(seed))[0]


def _cand(task, payload, defect="correct"):
    return Candidate(cand_id="probe", task_id=task.task_id, family=task.family,
                     payload=payload, defect=defect, note="")


def test_verdict_shape_is_fixed():
    import dataclasses

    fam = numeric.ArithExpression()
    task = _first_task(fam)
    verdict = fam.verify(task, _cand(task, fam.canonical(task)))
    assert isinstance(verdict, Verdict)
    assert {f.name for f in dataclasses.fields(verdict)} == {
        "passed", "score", "evidence", "cost_ms"}
    assert isinstance(verdict.passed, bool)
    assert 0.0 <= verdict.score <= 1.0
    assert verdict.cost_ms >= 0.0
    assert isinstance(verdict.evidence, list)


def test_arith_expression_accepts_the_reference_answer():
    fam = numeric.ArithExpression()
    task = _first_task(fam)
    verdict = fam.verify(task, _cand(task, fam.canonical(task)))
    assert verdict.passed is True
    assert verdict.score == pytest.approx(1.0)
    assert all(e["ok"] for e in verdict.evidence)


def test_arith_expression_rejects_a_wrong_value():
    fam = numeric.ArithExpression()
    task = _first_task(fam)
    payload = copy.deepcopy(fam.canonical(task))
    # Break exactly one unit: the other units stay right, so this is a
    # partial-credit probe rather than a total miss.
    expected = payload[0]
    payload[0] = expected + 1 if isinstance(expected, int) else str(expected) + "9"
    verdict = fam.verify(task, _cand(task, payload, "semantic_wrong"))
    assert verdict.passed is False
    assert verdict.score < 1.0
    assert sum(1 for e in verdict.evidence if not e["ok"]) == 1


def test_arith_expression_accepts_a_paraphrase():
    fam = numeric.ArithExpression()
    task = _first_task(fam)
    rng = random.Random(3)
    alts = fam.equivalents(task, rng)
    assert alts, "family must publish at least one semantically equivalent form"
    for payload, _note in alts:
        assert fam.verify(task, _cand(task, payload, "semantic_equivalent")).passed


def test_arith_expression_reference_matches_the_printed_expression():
    """Invariant (round-7): every reference value must equal the value a reader
    gets by evaluating the rendered expression under standard precedence.
    Uses Python's own evaluator as an independent implementation."""
    fam = numeric.ArithExpression()
    for seed in range(30):
        for task in fam.generate(25, random.Random(seed)):
            for it in task.items:
                expr = it["expr"]
                assert set(expr) <= set("0123456789+-*/() ."), expr
                got = eval(expr, {"__builtins__": {}})  # noqa: S307 - charset-checked above
                assert float(it["expected"]) == got, (expr, it["expected"], got)


@pytest.mark.parametrize("payload", [
    None, "not-a-list", {"answers": []}, 42, [None] * 20, {"unexpected": 1},
])
def test_garbage_payload_fails_without_raising(payload):
    fam = numeric.ArithExpression()
    task = _first_task(fam)
    verdict = fam.verify(task, _cand(task, payload, "type_mismatch"))
    assert isinstance(verdict, Verdict)
    assert verdict.passed is False
    assert verdict.score < 1.0


def test_missing_unit_is_graded_as_failure():
    fam = numeric.ArithExpression()
    task = _first_task(fam)
    payload = list(fam.canonical(task))[:-1]  # drop one answer
    verdict = fam.verify(task, _cand(task, payload, "missing"))
    assert verdict.passed is False
    assert any("missing answer" in e["detail"] for e in verdict.evidence)


def test_extra_unit_is_graded_as_failure():
    fam = numeric.ArithExpression()
    task = _first_task(fam)
    payload = list(fam.canonical(task)) + [12345]
    verdict = fam.verify(task, _cand(task, payload, "extra"))
    assert verdict.passed is False
    assert any(e["unit"].startswith("extra[") for e in verdict.evidence)


@pytest.mark.parametrize("fam_cls", registry.FAMILY_CLASSES, ids=lambda c: c.name)
def test_every_family_honours_the_contract(fam_cls):
    """Every family: reference passes, paraphrases pass, every defect fails."""
    fam = fam_cls()
    task = fam.generate(1, random.Random(2024))[0]
    rng = random.Random(2025)
    candidates = fam.mutate(task, rng)
    for cand in candidates:
        verdict = fam.verify(task, cand)
        assert isinstance(verdict, Verdict)
        assert 0.0 <= verdict.score <= 1.0
        if cand.defect in ("correct", "semantic_equivalent"):
            assert verdict.passed, f"{fam.name}: rejected a valid answer ({cand.defect})"
        else:
            assert not verdict.passed, f"{fam.name}: accepted a {cand.defect} mutant"


def test_families_declare_a_complete_premise_and_scoring_function():
    for fam_cls in registry.FAMILY_CLASSES:
        assert fam_cls.name and fam_cls.domain and fam_cls.task_shape
        assert fam_cls.premise and fam_cls.scoring and fam_cls.item_unit
        assert fam_cls.payload_kind in ("list", "mapping")
