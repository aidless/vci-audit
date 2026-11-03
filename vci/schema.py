"""Fixed data model shared by every task family and verifier.

Nothing in the pipeline is allowed to invent a new return type: a verifier
always returns a :class:`Verdict`, and every evidence row has exactly the
keys ``unit``, ``ok`` and ``detail``.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

#: A defect label of ``correct`` or ``semantic_equivalent`` means the candidate
#: is a valid answer; everything else is a wrong answer.
CORRECT_DEFECTS = frozenset({"correct", "semantic_equivalent"})

#: The error taxonomy required by the audit protocol.  ``partial`` is generated
#: internally only (used to measure score fidelity / dense credit) and is not
#: part of the public taxonomy.
DEFECT_CLASSES = (
    "boundary",
    "off_by_one",
    "type_mismatch",
    "order",
    "missing",
    "extra",
    "semantic_wrong",
)

#: Synthetic candidates that keep j of k units correct.  Used only to measure
#: whether partial credit is faithful, never as a model output.
PARTIAL_DEFECT = "partial"


@dataclass
class Task:
    """A seed task: a prompt plus the ground truth for every graded unit."""

    family: str
    task_id: str
    prompt: str
    items: List[Dict[str, Any]]
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_items(self) -> int:
        return len(self.items)

    @property
    def units(self) -> List[str]:
        return [it["unit"] for it in self.items]


@dataclass
class Candidate:
    """A candidate answer produced by the synthetic mutant generator."""

    cand_id: str
    task_id: str
    family: str
    payload: Any
    defect: str
    note: str = ""

    @property
    def is_correct(self) -> bool:
        return self.defect in CORRECT_DEFECTS


@dataclass
class Verdict:
    """The one and only verifier return type.

    ``passed`` is full-credit acceptance (all graded units correct, no extra
    material).  ``score`` is the weighted fraction of units that passed, in
    [0, 1].  ``evidence`` is a list of ``{unit, ok, detail}`` rows.
    ``cost_ms`` is wall-clock verification latency measured inside the
    verifier.
    """

    passed: bool
    score: float
    evidence: List[Dict[str, Any]]
    cost_ms: float
