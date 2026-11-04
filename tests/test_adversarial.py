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
            # Round 5: only directional probes may carry a perturbed task.
            assert (p.task_override is not None) == (p.failure_class == "directional_shift")
            if p.task_override is not None:
                assert p.task_override.family == p.family
                assert p.task_override.task_id == p.task_id + "-dir"
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


def test_all_seven_failure_classes_are_covered_across_the_registry():
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
def test_code_patch_hardcoded_answers_are_now_rejected():
    """Round 4 fix: the verifier runs held-out inputs the table cannot answer."""
    pairs = _run("code_patch", "hardcoded_expected")
    assert pairs
    assert not any(v.passed for _, v in pairs)


def test_code_patch_stateful_output_is_now_caught():
    """Round 4 fix: the suite runs twice, so late-call degradation is visible.

    All four state probes (x02 first-five-calls-only, x03 second-call, x04
    alternation, x05 arity memo) are rejected; none is a known leak any more.
    """
    pairs = _run("code_patch", "resource")
    assert pairs
    known_leaks = {p.probe_id for p, v in pairs if v.passed}
    assert known_leaks == set(), known_leaks


def test_code_patch_overfit_rules_are_rejected_only_by_heldout_inputs():
    """Each OVF payload is correct on every visible case and wrong off-distribution.

    This is the construct-validity check: if a payload were also wrong on a
    visible case it would be a plain mutation, not an overfit, and the rejection
    could not be attributed to the held-out suite.
    """
    from vci.families.structural import _CODE_HOLDOUT, _CODE_TEMPLATES

    for tpl in _CODE_TEMPLATES:
        name = tpl["name"]
        ref = {}
        exec(compile(tpl["correct"], "<ref>", "exec"), ref)
        impl = adversarial._code_impl(name)[1].replace("def solve(", "def _impl(", 1)
        for tail, _note in adversarial._CODE_OVF[name]:
            ns = {}
            exec(compile(impl + tail, "<probe>", "exec"), ns)
            assert all(ns["solve"](*c) == ref["solve"](*c) for c in tpl["cases"]), name
            assert any(ns["solve"](*c) != ref["solve"](*c)
                       for c in _CODE_HOLDOUT[name]), name

    fam = registry.by_name("code_patch")
    task = fam.generate(1, random.Random(0))[0]
    pairs = [p for p in adversarial.probes_for("code_patch", task)
             if p.failure_class == "overfit_to_tests" and p.operator == "OVF"]
    assert len(pairs) >= 2
    for p in pairs:
        cand = Candidate(cand_id=p.probe_id, task_id=task.task_id,
                         family="code_patch", payload=p.payload,
                         defect=p.failure_class)
        assert not fam.verify(task, cand).passed, p.probe_id


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


def test_regex_overfit_patterns_are_rejected_by_heldout_strings():
    """Enumerating the labelled examples now fails on unseen strings.

    Construct validity: the x01 pattern classifies every labelled string that
    the prompt shows correctly, so its rejection is attributable to the held-out
    set, not to a plain error.  Equivalents of the canonical rule stay accepted.
    """
    fam = registry.by_name("regex_construct")
    task = fam.generate(1, random.Random(0))[0]
    pairs = [p for p in adversarial.probes_for("regex_construct", task)
             if p.failure_class == "overfit_to_tests"]
    assert pairs
    for p in pairs:
        cand = Candidate(cand_id=p.probe_id, task_id=task.task_id,
                         family="regex_construct", payload=p.payload,
                         defect=p.failure_class)
        assert not fam.verify(task, cand).passed, p.probe_id
    for payload, _why in fam.equivalents(task, random.Random(1)):
        cand = Candidate(cand_id="eq", task_id=task.task_id,
                         family="regex_construct", payload=payload,
                         defect="semantic_equivalent")
        assert fam.verify(task, cand).passed
    # The held-out strings are disjoint from what the prompt shows.
    for sp in task.meta["specs"]:
        assert set(sp["held_pos"]) - set(sp["pos"])
        assert set(sp["held_neg"]) - set(sp["neg"])


def test_only_the_code_patch_fixture_table_is_imported():
    """Only task data (inputs) may cross the module boundary, never a rule."""
    tree = ast.parse(inspect.getsource(adversarial))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            modules.add("vci." + (node.module or ""))
    assert modules == {"vci.schema", "vci.families.structural"}


# --- Round 5: positive directional probes on execution-derived verifiers -----
def _run_directional(family, n=3, seed=0):
    fam = registry.by_name(family)
    out = []
    for task in fam.generate(n, random.Random(seed)):
        for p in adversarial.probes_for(family, task):
            if p.failure_class != "directional_shift":
                continue
            eff = p.task_override or task
            cand = Candidate(cand_id=p.probe_id, task_id=task.task_id,
                             family=family, payload=p.payload,
                             defect=p.failure_class)
            out.append((p, fam.verify(eff, cand)))
    return out


@pytest.mark.parametrize("family", ["sql_result", "regex_construct", "code_patch"])
def test_every_task_has_a_directional_probe_pair(family):
    fam = registry.by_name(family)
    task = fam.generate(1, random.Random(3))[0]
    probes = [p for p in adversarial.probes_for(family, task)
              if p.failure_class == "directional_shift"]
    assert {p.expectation for p in probes} == {"accept", "reject"}
    assert all(p.checklist_category == "directional" and p.operator == "DIR"
               for p in probes)


@pytest.mark.parametrize("family", ["sql_result", "regex_construct", "code_patch"])
def test_directional_accept_probes_are_accepted(family):
    """The correct answer to the perturbed input must pass: a rejection is a
    false reject on new input -- the quantity the directional TPR measures."""
    pairs = [(p, v) for p, v in _run_directional(family) if p.expectation == "accept"]
    assert pairs
    bad = [p.probe_id for p, v in pairs if not v.passed]
    assert bad == [], f"{family} falsely rejects the shifted correct answer: {bad}"


@pytest.mark.parametrize("family", ["sql_result", "regex_construct", "code_patch"])
def test_directional_stale_answers_are_rejected(family):
    """The answer that was correct *before* the input shift must now fail."""
    pairs = [(p, v) for p, v in _run_directional(family) if p.expectation == "reject"]
    assert pairs
    leaked = [p.probe_id for p, v in pairs if v.passed]
    assert leaked == [], f"{family} accepts a stale answer after the shift: {leaked}"


def test_directional_override_changes_what_the_verifier_sees():
    """Guard against a vacuous override: the shifted-accept payload must fail
    on the *original* task, proving the verdict depends on the override."""
    fam = registry.by_name("code_patch")
    task = fam.generate(1, random.Random(0))[0]
    p = next(p for p in adversarial.probes_for("code_patch", task)
             if p.failure_class == "directional_shift" and p.expectation == "accept")
    cand = Candidate(cand_id=p.probe_id, task_id=task.task_id,
                     family="code_patch", payload=p.payload,
                     defect=p.failure_class)
    assert fam.verify(p.task_override, cand).passed
    assert not fam.verify(task, cand).passed
