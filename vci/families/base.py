"""Base class for task families.

A family is simultaneously:
  * a parameterised seed-task generator,
  * a mutant generator (correct / paraphrase / defect classes / partials),
  * a verifier implementing the single fixed API
    ``verify(task, candidate) -> Verdict``.

Subclasses implement ``make_one``, ``canonical``, ``equivalents``,
``wrongs`` and ``grade_item``.  They must not return anything other than a
:class:`vci.schema.Verdict` from ``verify``.
"""
import copy
import time
from typing import Any, Dict, List, Optional, Tuple

from ..schema import PARTIAL_DEFECT, Candidate, Task, Verdict

_MISSING = object()


def _clip(s: str, limit: int = 140) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= limit else s[: limit - 3] + "..."


def _repr(v: Any, limit: int = 90) -> str:
    try:
        s = repr(v)
    except Exception:
        s = "<unrepr>"
    return _clip(s, limit)


class Family:
    name: str = ""
    domain: str = ""
    task_shape: str = ""
    premise: str = ""
    scoring: str = ""
    item_unit: str = ""
    payload_kind: str = "list"  # "list" or "mapping"
    default_tasks: int = 25
    round_unit_rel_tol: float = 1e-9

    # ------------------------------------------------------------------ tasks
    def make_one(self, rng, idx: int) -> Task:
        raise NotImplementedError

    def generate(self, n: int, rng) -> List[Task]:
        return [self.make_one(rng, i) for i in range(1, n + 1)]

    def task(self, task_id: str, prompt: str, items: List[Dict[str, Any]],
             meta: Optional[Dict[str, Any]] = None) -> Task:
        return Task(family=self.name, task_id=task_id, prompt=prompt,
                    items=items, meta=meta or {})

    # --------------------------------------------------------------- mutants
    def canonical(self, task: Task) -> Any:
        raise NotImplementedError

    def equivalents(self, task: Task, rng) -> List[Tuple[Any, str]]:
        return []

    def wrongs(self, task: Task, rng) -> List[Tuple[str, Any, str]]:
        raise NotImplementedError

    def corrupt_item(self, task: Task, item: Dict[str, Any], rng) -> Any:
        """A wrong answer for one unit, used to build partial-credit probes."""
        return None

    def set_units(self, task: Task, payload: Any, replacements: Dict[str, Any]) -> Any:
        out = copy.deepcopy(payload)
        if self.payload_kind == "list":
            units = task.units
            for unit, value in replacements.items():
                out[units.index(unit)] = value
        else:
            out.update(replacements)
        return out

    def partial(self, task: Task, j: int, rng) -> Any:
        """Payload that keeps exactly ``j`` of ``k`` units correct."""
        units = task.units
        keep = set(rng.sample(units, j))
        reps = {u: self.corrupt_item(task, it, rng)
                for u, it in zip(units, task.items) if u not in keep}
        return self.set_units(task, self.canonical(task), reps)

    def mutate(self, task: Task, rng) -> List[Candidate]:
        mk = lambda payload, defect, note="": Candidate(
            cand_id="", task_id=task.task_id, family=self.name,
            payload=payload, defect=defect, note=note)
        out = [mk(copy.deepcopy(self.canonical(task)), "correct", "reference answer")]
        for payload, note in self.equivalents(task, rng)[:2]:
            out.append(mk(copy.deepcopy(payload), "semantic_equivalent", note))
        for defect, payload, note in self.wrongs(task, rng):
            out.append(mk(copy.deepcopy(payload), defect, note))
        k = task.n_items
        if k > 1:
            for j in range(1, k):
                out.append(mk(self.partial(task, j, rng), PARTIAL_DEFECT,
                              f"{j}/{k} units correct"))
        for i, c in enumerate(out):
            c.cand_id = f"{task.task_id}-c{i:02d}"
        return out

    # -------------------------------------------------------------- verifier
    def extract_answers(self, task: Task, payload: Any):
        """Return ``(answers_by_unit, extra_units, parse_error)``."""
        units = task.units
        if self.payload_kind == "list":
            if isinstance(payload, dict) and set(payload) == {"answers"}:
                payload = payload["answers"]
            if not isinstance(payload, (list, tuple)):
                return {}, [], f"payload is {type(payload).__name__}, expected a list"
            answers = {u: payload[i] for i, u in enumerate(units) if i < len(payload)}
            extras = [f"extra[{i}]" for i in range(len(units), len(payload))]
            return answers, extras, None
        if not isinstance(payload, dict):
            return {}, [], f"payload is {type(payload).__name__}, expected an object"
        answers = {u: payload[u] for u in units if u in payload}
        extras = [str(k) for k in payload if k not in units]
        return answers, extras, None

    def grade_item(self, task: Task, item: Dict[str, Any], answer: Any) -> Tuple[bool, str]:
        raise NotImplementedError

    def verify(self, task: Task, candidate: Candidate) -> Verdict:
        t0 = time.perf_counter()
        try:
            answers, extras, err = self.extract_answers(task, candidate.payload)
        except Exception as ex:  # pragma: no cover - defensive
            answers, extras, err = {}, [], f"extract failed: {ex}"
        evidence: List[Dict[str, Any]] = []
        got = 0.0
        total = 0.0
        if err:
            for item in task.items:
                evidence.append({"unit": item["unit"], "ok": False, "detail": _clip(err)})
                total += item.get("weight", 1.0)
        else:
            for item in task.items:
                w = float(item.get("weight", 1.0))
                total += w
                ans = answers.get(item["unit"], _MISSING)
                if ans is _MISSING:
                    evidence.append({"unit": item["unit"], "ok": False,
                                     "detail": "missing answer for unit"})
                    continue
                try:
                    good, detail = self.grade_item(task, item, ans)
                except Exception as ex:  # a verifier bug must count as a failure
                    good, detail = False, f"verifier exception: {type(ex).__name__}: {ex}"
                if good:
                    got += w
                evidence.append({"unit": item["unit"], "ok": bool(good), "detail": _clip(detail)})
            for extra in extras:
                total += 1.0
                evidence.append({"unit": extra, "ok": False,
                                 "detail": "extra answer not defined by the task"})
        score = (got / total) if total else 0.0
        passed = bool(total and got >= total)
        cost_ms = (time.perf_counter() - t0) * 1000.0
        return Verdict(passed=passed, score=max(0.0, min(1.0, score)),
                       evidence=evidence, cost_ms=cost_ms)

    # ---------------------------------------------------------------- helpers
    def ok(self, cond: bool, good: str, bad: str) -> Tuple[bool, str]:
        return (bool(cond), good if cond else bad)
