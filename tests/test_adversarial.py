"""Guards for the round-2 non-aligned probe module.

The point of ``vci.adversarial`` is that its candidates are *not* produced by
the code that judges them.  These tests enforce that mechanically (AST), check
the probe schema and determinism, and register the leaks we already know about
so that a verifier fix shows up as a test change instead of silently improving
the headline number.
"""
import ast
import inspect
import random

import pytest

from vci import adversarial, registry
from vci.schema import Candidate

FORBIDDEN = {
    "verify", "grade_item", "canonical", "equivalents", "wrongs",
    "corrupt_item", "extract_answers", "mutate", "partial",
}


def _called_names(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                names.add(fn.attr)
            elif isinstance(fn, ast.Name):
                names.add(fn.id)
    return names


def test_generator_never_calls_the_verifier_or_the_mutant_generator():
    src = inspect.getsourcefile(adversarial)
    assert FORBIDDEN - _called_names(src) == FORBIDDEN, (
        "adversarial.py calls verifier/generator internals: "
        f"{sorted(FORBIDDEN & _called_names(src))}")


def test_every_registered_family_has_a_probe_builder():
    missing = [m["family"] for m in registry.registry_metadata()
               if not adversarial.has_builder(m["family"])]
    assert missing == []


def test_probe_fields_are_valid_and_bound_to_the_task():
    for meta in registry.registry_metadata():
        fam = registry.by_name(meta["family"])
        task = fam.generate(1, random.Random(3))[0]
        probes = adversarial.probes_for(fam.name, task, heavy=True)
        assert probes, fam.name
        assert len({p.probe_id for p in probes}) == len(probes)
        classes = set()
        for p in probes:
            assert p.family == fam.name and p.task_id == task.task_id
            assert p.failure_class in adversarial.FAILURE_CLASSES
            assert p.expectation in adversarial.EXPECTATIONS
            assert p.note and p.basis
            assert p.label == {"accept": "correct", "reject": "incorrect",
                               "observe": None}[p.expectation]
            classes.add(p.failure_class)
            # Round 3: each record must be self-describing for a reviewer.
            assert p.checklist_category in adversarial.CHECKLIST_CATEGORIES
            assert p.operator in adversarial.OPERATORS
            assert p.generator_version == adversarial.GENERATOR_VERSION
        # Every family contributes at least one *reject* probe and at least one
        # equivalence or ambiguity probe: a family with only reject probes could
        # not measure false rejections.
        assert any(p.expectation == "reject" for p in probes)
        assert any(p.failure_class in ("semantic_equivalent", "spec_ambiguity")
                   for p in probes)


def test_all_three_checklist_categories_and_operators_are_covered():
    cats, ops = set(), set()
    for meta in registry.registry_metadata():
        fam = registry.by_name(meta["family"])
        task = fam.generate(1, random.Random(3))[0]
        probes = adversarial.probes_for(fam.name, task, heavy=True)
        cats |= {p.checklist_category for p in probes}
        ops |= {p.operator for p in probes}
    assert cats == set(adversarial.CHECKLIST_CATEGORIES)
    assert ops <= set(adversarial.OPERATORS)
    # The operator table in the module docstring must not drift from the code.
    doc = adversarial.__doc__
    missing = [op for op in ops if f"`{op}`" not in doc]
    assert missing == [], f"documented operators missing: {missing}"


def test_all_six_failure_classes_are_covered_across_the_registry():
    seen = set()
    for meta in registry.registry_metadata():
        fam = registry.by_name(meta["family"])
        task = fam.generate(1, random.Random(3))[0]
        seen |= {p.failure_class for p in adversarial.probes_for(fam.name, task, True)}
    assert seen == set(adversarial.FAILURE_CLASSES)


@pytest.mark.parametrize("seed", [0, 5])
def test_probe_generation_is_deterministic(seed):
    fam = registry.by_name("regex_construct")
    task = fam.generate(1, random.Random(seed))[0]
    a = [(p.probe_id, p.failure_class, p.expectation, repr(p.payload))
         for p in adversarial.probes_for(fam.name, task, heavy=True)]
    b = [(p.probe_id, p.failure_class, p.expectation, repr(p.payload))
         for p in adversarial.probes_for(fam.name, task, heavy=False)]
    assert a == b  # only the resource probes differ, and regex has none


def _run(family, expect_class, heavy=False):
    fam = registry.by_name(family)
    task = fam.generate(1, random.Random(0))[0]
    out = []
    for p in adversarial.probes_for(family, task, heavy=heavy):
        if p.failure_class != expect_class:
            continue
        cand = Candidate(cand_id=p.probe_id, task_id=task.task_id,
                         family=family, payload=p.payload,
                         defect=p.failure_class)
        out.append((p, fam.verify(task, cand)))
    return out


# --- Known leaks: the verifier disagrees with the independent label ---------
def test_code_patch_hardcoded_answers_are_accepted_known_leak():
    """A lookup table of the hidden-test answers passes the subprocess verifier."""
    pairs = _run("code_patch", "hardcoded_expected")
    assert pairs
    assert all(v.passed for _, v in pairs)


def test_code_patch_stateful_output_is_invisible_known_leak():
    """Round 3: only the *first-call-only* defect is still invisible.

    The one-shot subprocess verifier runs every case in a single import, so it
    does see "fails from the second invocation on", alternation and a
    arity-keyed memo -- those three are caught.  What it cannot see is a solver
    that is right exactly once: `x02` is correct for its first five calls, which
    covers the whole harness, and returns `None` afterwards.  That is the leak
    this test registers, by id, so a future fix shows up as a test change.
    """
    pairs = _run("code_patch", "resource")
    assert pairs
    known_leaks = {p.probe_id for p, v in pairs if v.passed}
    assert known_leaks == {"code_patch-001-x02"}, known_leaks


def test_log_equivalent_timestamps_are_rejected_known_over_strictness():
    """Same instant, three RFC-3339 spellings; the verifier compares strings."""
    pairs = _run("log_field_extraction", "semantic_equivalent")
    assert pairs
    assert not any(v.passed for _, v in pairs)


def test_unit_convert_precision_ambiguity_is_rejected_known_over_strictness():
    pairs = _run("unit_convert", "spec_ambiguity")
    assert pairs
    assert not any(v.passed for _, v in pairs)


# --- The other side: where the verifier is genuinely right ----------------
def test_independently_correct_implementations_are_accepted():
    pairs = _run("code_patch", "semantic_equivalent")
    assert pairs
    assert all(v.passed for _, v in pairs)


def test_only_the_code_patch_fixture_table_is_imported():
    """Only task data (inputs) may cross the module boundary, never a rule."""
    tree = ast.parse(inspect.getsource(adversarial))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            modules.add("vci." + (node.module or ""))
    assert modules == {"vci.schema", "vci.families.structural"}
