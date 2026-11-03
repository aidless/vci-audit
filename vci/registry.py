"""The task-family registry.

Every family is a single object that is simultaneously a seed-task generator, a
mutant generator and a verifier.  The registry fixes the audit's unit of
analysis: one family -> one VCI number.

Inclusion criteria for a family (see SPEC.md, section 2):
 1. It has a decidable ground truth that does not require a trained judge.
 2. It admits at least ``min_units >= 2`` independently gradeable units per
    task, so dense credit is at all measurable.
 3. It has at least one legal answer that differs textually from the reference
    answer, so "accepts paraphrases" is testable.
 4. Its verifier can be expressed in pure Python + stdlib (no network, no
    proprietary model, no human in the loop).
 5. It exists in the wild as an open-domain task shape (not an artificial
    puzzle invented to make the numbers look good).
"""
from .families import (ArithExpression, BaseConvert, CodePatch, CspAssign, DateArith,
                       GridPath, IntervalMerge, JsonSchemaExtract, LifeStep,
                       LogFieldExtraction, MatrixOps, RegexConstruct, ScheduleSlots,
                       SortMultikey, SqlResult, StatsSummary, TableAggregate, TemplateRender,
                       TopoOrder, UnitConvert)

FAMILY_CLASSES = [
    # numeric (6)
    ArithExpression, UnitConvert, StatsSummary, BaseConvert, MatrixOps, DateArith,
    # text / structured output (4)
    JsonSchemaExtract, LogFieldExtraction, RegexConstruct, TemplateRender,
    # data (4)
    SqlResult, TableAggregate, SortMultikey, IntervalMerge,
    # structural / search (6)
    GridPath, CspAssign, ScheduleSlots, TopoOrder, LifeStep, CodePatch,
]

FAMILIES = [cls() for cls in FAMILY_CLASSES]
_BY_NAME = {f.name: f for f in FAMILIES}
INDEX = {f.name: i for i, f in enumerate(FAMILIES)}


def by_name(name):
    if name not in _BY_NAME:
        raise KeyError(f"unknown family {name!r}; known: {sorted(_BY_NAME)}")
    return _BY_NAME[name]


def resolve(spec):
    """``"all"`` or a comma separated list of family names."""
    if not spec or spec.strip().lower() == "all":
        return list(FAMILIES)
    names = [s.strip() for s in spec.split(",") if s.strip()]
    return [by_name(n) for n in names]


def registry_metadata():
    return [{
        "family": f.name,
        "domain": f.domain,
        "task_shape": f.task_shape,
        "premise": f.premise,
        "scoring": f.scoring,
        "item_unit": f.item_unit,
        "payload_kind": f.payload_kind,
        "default_tasks": f.default_tasks,
    } for f in FAMILIES]
