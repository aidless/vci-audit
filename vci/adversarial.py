"""Round-2/3 non-aligned probes.

Why this module exists
----------------------
Round 1 generated mutants with the family's own generators, so every mutant was
labelled by the same code that judged it.  That construction makes TPR/TNR look
perfect by definition.  This module builds a *second* sample source whose labels
do not come from the verifier.

Round-3 additions
-----------------
* every probe carries a CheckList category (``minimum_functionality`` /
  ``invariance`` / ``directional``), the mutation operator that produced it,
  its true label (derived from ``expectation``, never from the verifier) and a
  generator version.  The category split is what makes the per-family TPR/TNR
  meaningful: a verifier can be good at minimum functionality and bad at
  invariance, and collapsing the two hides that.
* probes named ``EQUIV`` (same meaning, different spelling) are kept apart from
  probes named ``AMB`` (a defensible reading of an under-specified prompt).
  Both are labelled "should be accepted", but only the first is a verifier
  defect; the second is a task-text defect.  ``audit._probe_record`` writes that
  verdict basis into ``attribution``.

Mutation operators: what each one stands for, and its representative weakness
-----------------------------------------------------------------------------
Orthodox names follow Jia & Harman 2011; ``OVF``/``HARD``/``STATE`` have no
program-mutation analogue and are the three that a fixture-replaying harness
cannot see.

| operator | real defect it stands for | representative weakness |
|---|---|---|
| `AOR` | wrong formula | loud: any value check kills it, so acceptance says nothing |
| `ROR` | boundary error | one inequality per family; a happy-path check is blind |
| `CR` | stale constant / off-by-one | easy to kill with exact fixtures; over-weights small numeric errors |
| `SDL` | a missing step / dropped functionality | only visible if the verifier asserts that step at all |
| `TR` | transposed operands or wrong emission order | looks equivalent whenever the checker sorts or compares sets |
| `OVF` | a rule that only holds on the labelled examples | at most one per family: cannot represent the overfitting space |
| `HARD` | lookup table instead of an algorithm | obviously wrong in principle, yet invisible to a fixture-replaying harness |
| `STATE` | answer depends on history, not input | needs a second invocation; one-shot verifiers cannot see it |
| `NONDET` | same input, different answer | needs repeated calls; most harnesses call once |
| `INF` | non-termination / unbounded resource use | detectable by a watchdog, but the cost is wall-clock: observed, not scored |
| `EQUIV` | not a defect: same meaning, different spelling | authored, not decided; measures false rejects only where the author is right |
| `AMB` | not a defect: a defensible second reading of an under-specified prompt | a rejection here blames the task text, not the verifier |

Representative weakness of the whole sample (Just et al., FSE 2014): mutants are
correlated with real faults but their *distribution* is not the distribution of
real faults, and they are easier to kill.  Therefore TPR/TNR measured on these
probes is an optimistic upper bound on deployment behaviour, not an estimate of
it -- synthetic mutants are not a sample of real defects, and this round's
validity is capped by that (see ``outputs/first-run-memo.md``, "validity
ceiling").  Equivalence is not decided by a general algorithm (the problem is
undecidable; Offutt & Pan 1997), so ``EQUIV`` probes are authored arguments,
one basis line each, not a solved equivalence oracle.

Independence contract (enforced by ``tests/test_adversarial.py``)
----------------------------------------------------------------
1. This module never calls ``verify``, ``grade_item``, ``canonical``,
   ``equivalents``, ``wrongs``, ``corrupt_item``, ``extract_answers``, ``mutate``
   or ``partial`` on a family object.
2. Expected answers are recomputed here from first principles: the prompt rule,
   the task's public fixture data (``Task.items`` / ``Task.meta``), and small
   reference implementations written below.  Where a different code path is
   possible we take it (own BFS, own brute-force scheduler, own Kahn, own
   interval merge, own formatter), so a shared bug between generator and
   verifier would show up as a disagreement instead of cancelling out.
3. The only import from a family module is the *fixture table* of code-patch
   cases (inputs and function names).  It is task data, not a decision rule; the
   expected values are produced by ``_CODE_IMPL`` here, never by the fixture's
   own "correct" source string.
4. ``expectation`` records what a correct verifier should do with this
   candidate.  It is a measurement target, not a fallback: a probe whose
   expectation is ``reject`` and which the verifier accepts is a leak that is
   reported as such.

Failure classes
---------------
``hardcoded_expected``  answers memorised for the visible cases only
``overfit_to_tests``    implementation/pattern valid only on the labelled inputs
``spec_ambiguity``      a defensible second reading that the verifier refuses
``silent_partial``      runs fine, locally right, wrong at a boundary
``semantic_equivalent`` same meaning, different spelling
``resource``            timeout / state-dependent (non-deterministic) output

``expectation`` is one of ``accept`` / ``reject`` / ``observe``.  ``observe``
probes are measured (cost, outcome) but excluded from TPR/TNR because the
verifier contract has no policy for them (e.g. a memory budget); they are
reported separately instead of silently deflating or inflating trust.
"""
from __future__ import annotations

import datetime as _dt
import html
import itertools
import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .schema import Task

FAILURE_CLASSES = (
    "hardcoded_expected",
    "overfit_to_tests",
    "spec_ambiguity",
    "silent_partial",
    "semantic_equivalent",
    "resource",
)
EXPECTATIONS = ("accept", "reject", "observe")

#: CheckList (Ribeiro et al., ACL 2020) test types, applied to candidate answers.
CHECKLIST_CATEGORIES = ("minimum_functionality", "invariance", "directional")

#: Which CheckList question a failure class is asking.
CATEGORY_BY_CLASS = {
    "hardcoded_expected": "minimum_functionality",
    "overfit_to_tests": "minimum_functionality",
    "spec_ambiguity": "minimum_functionality",
    "silent_partial": "directional",
    "semantic_equivalent": "invariance",
    "resource": "invariance",
}

#: Default mutation operator per failure class (overridden per probe where a
#: sharper operator applies).
OPERATOR_BY_CLASS = {
    "hardcoded_expected": "HARD",
    "overfit_to_tests": "OVF",
    "spec_ambiguity": "AMB",
    "silent_partial": "CR",
    "semantic_equivalent": "EQUIV",
    "resource": "STATE",
}

#: The mutation operators a probe record may carry (see the module docstring).
OPERATORS = ("AOR", "ROR", "CR", "SDL", "TR", "OVF", "HARD", "STATE",
             "NONDET", "INF", "EQUIV", "AMB")

#: Bumped whenever a probe payload changes, so a result file can be traced to
#: the sample that produced it.
GENERATOR_VERSION = "3.0"


@dataclass
class Probe:
    """One independently constructed candidate plus its expected treatment."""

    probe_id: str
    task_id: str
    family: str
    failure_class: str
    checklist_category: str
    operator: str
    expectation: str
    payload: Any
    note: str
    basis: str
    generator_version: str = GENERATOR_VERSION

    @property
    def label(self) -> Optional[str]:
        """Ground truth derived from ``expectation``, never from the verifier."""
        if self.expectation == "accept":
            return "correct"
        if self.expectation == "reject":
            return "incorrect"
        return None

    @property
    def attribution_kind(self) -> str:
        """What a disagreement with the verifier would be evidence of.

        ``verifier_too_strict``      a correct answer under the stated value is
                                     rejected because of its spelling.
        ``task_under_specified``     a defensible second reading is rejected;
                                     the prompt, not the verifier, is incomplete.
        ``true_defect``              the candidate really is wrong; a pass is a
                                     verifier miss, a rejection is a correct catch.
        ``observe``                  no policy in the verifier contract.
        """
        if self.expectation == "accept":
            return ("task_under_specified" if self.failure_class == "spec_ambiguity"
                    else "verifier_too_strict")
        if self.expectation == "reject":
            return "true_defect"
        return "observe"



# --------------------------------------------------------------------- helpers
def _frac(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        raise TypeError("bool is not a quantity")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(Decimal(repr(value)))
    return Fraction(Decimal(str(value)))


def _exact(value: Any) -> str:
    """Render a value exactly, choosing between a reduced fraction and a decimal.

    Independently written from the family formatter: terminate test first, then
    decimal expansion, otherwise ``n/d``.
    """
    fr = _frac(value)
    if fr.denominator == 1:
        return str(fr.numerator)
    d = fr.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d != 1:
        return f"{fr.numerator}/{fr.denominator}"
    with __import__("decimal").localcontext() as ctx:
        ctx.prec = 60
        s = format(Decimal(fr.numerator) / Decimal(fr.denominator), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _digits(value: int, base: int) -> str:
    chars = "0123456789ABCDEF"
    if value == 0:
        return "0"
    out = []
    while value:
        out.append(chars[value % base])
        value //= base
    return "".join(reversed(out))


def _mk(task: Task, idx: int, cls: str, exp: str, payload: Any,
        note: str, basis: str, category: Optional[str] = None,
        operator: Optional[str] = None) -> Probe:
    assert cls in FAILURE_CLASSES and exp in EXPECTATIONS
    cat = category or CATEGORY_BY_CLASS[cls]
    op = operator or OPERATOR_BY_CLASS[cls]
    assert cat in CHECKLIST_CATEGORIES, cat
    return Probe(probe_id=f"{task.task_id}-x{idx:02d}", task_id=task.task_id,
                 family=task.family, failure_class=cls, checklist_category=cat,
                 operator=op, expectation=exp, payload=payload, note=note,
                 basis=basis)


def _record_key(task: Task) -> Dict[str, Dict[str, Any]]:
    """Rebuild the record->field->value view from item units ``L<r>.<field>``."""
    out: Dict[str, Dict[str, Any]] = {}
    for it in task.items:
        r, field = it["unit"].split(".", 1)
        out.setdefault(r.lstrip("L"), {})[field] = it["expected"]
    return out


# ---------------------------------------------------------------- numeric probes
def _arith(task: Task, heavy: bool) -> List[Probe]:
    vals = [it["expected"] for it in task.items]
    exact = [_exact(v) for v in vals]
    bad = list(exact)
    shifted = _frac(vals[0]) + Fraction(1, 2)
    bad[0] = _exact(shifted if shifted != _frac(vals[0]) else _frac(vals[0]) + 1)
    return [
        _mk(task, 0, "semantic_equivalent", "accept", exact,
            "all values re-spelled as reduced fractions or terminating decimals",
            "own rational formatter; no call into fmt_num"),
        _mk(task, 1, "silent_partial", "reject", bad,
            f"first value moved by +1/2 ({_exact(vals[0])} -> {bad[0]})",
            "reference value + an independent offset", operator="CR"),
    ]


def _unit(task: Task, heavy: bool) -> List[Probe]:
    vals = [it["expected"] for it in task.items]
    exact = [_exact(v) for v in vals]
    six = [f"{float(v):.6g}" for v in vals]
    bad = list(exact)
    bad[0] = _exact(_frac(vals[0]) * 1000)
    return [
        _mk(task, 0, "semantic_equivalent", "accept", exact,
            "exact value as a fraction (engineering notation avoided)",
            "own exact formatter"),
        _mk(task, 1, "spec_ambiguity", "accept", six,
            "six significant digits: the prompt never states a precision requirement",
            "defensible second reading of an under-specified prompt"),
        _mk(task, 2, "silent_partial", "reject", bad,
            "first conversion off by a factor of 1000",
            "reference value scaled independently", operator="AOR"),
    ]


def _stats(task: Task, heavy: bool) -> List[Probe]:
    base = {it["unit"]: _exact(it["expected"]) for it in task.items}
    bad = dict(base)
    std = next(it["expected"] for it in task.items if it["unit"] == "std_sample")
    for nd in (2, 4, 6):
        cand = f"{float(std):.{nd}f}"
        if cand != base["std_sample"]:
            bad["std_sample"] = cand
            break
    return [
        _mk(task, 0, "semantic_equivalent", "accept", base,
            "statistics re-spelled exactly (fractions for rational moments)",
            "own exact formatter; Python's math.sqrt is not reused for re-derivation"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "sample std rounded to a few decimals, violating the stated 1e-6 tolerance",
            "independent rounding of the reference std", operator="CR"),
    ]


def _base(task: Task, heavy: bool) -> List[Probe]:
    acc = []
    bad = []
    for it in task.items:
        v, b = int(it["expected"]), int(it["base"])
        digits = _digits(v, b)
        acc.append("0" * (len(digits) + 2) + digits)
        bad.append(_digits(v + 1, b))
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "zero-padded digit strings: same integer, different spelling",
            "own base encoder + explicit padding"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "each value incremented by one in its own base",
            "own base encoder; no shared helper with the family", operator="CR"),
    ]


def _matrix(task: Task, heavy: bool) -> List[Probe]:
    n = 1 + max(it["row"] for it in task.items)
    grid = [[0] * n for _ in range(n)]
    for it in task.items:
        grid[it["row"]][it["col"]] = it["expected"]
    acc = [[str(cell) for cell in row] for row in grid]
    transposed = [[grid[c][r] for c in range(n)] for r in range(n)]
    bad = [row[:] for row in transposed]
    if bad == grid:  # a symmetric result would make the transpose indistinguishable
        bad[0][0] = bad[0][0] + 1
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "cells as decimal strings of the same integers",
            "own matrix reconstruction from row/col items"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "result transposed: valid matrix shape, wrong entry positions",
            "own transpose, applied without consulting the operation label",
            operator="TR"),
    ]


def _date(task: Task, heavy: bool) -> List[Probe]:
    vals = [it["expected"] for it in task.items]
    acc = [f"{v}T00:00:00" for v in vals]
    bad = list(vals)
    last = _dt.date.fromisoformat(vals[-1]) + _dt.timedelta(days=1)
    bad[-1] = last.isoformat()
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "midnight datetime spelling of the same calendar day",
            "own ISO rendering via datetime"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "last date advanced by one day (boundary wrong, rest right)",
            "own date arithmetic", operator="CR"),
    ]


# ------------------------------------------------------------------- text probes
def _json_extract(task: Task, heavy: bool) -> List[Probe]:
    base = {it["unit"]: it["expected"] for it in task.items}
    acc = dict(base)
    acc["tags"] = list(reversed(base["tags"]))
    acc["total_usd"] = f"{Decimal(repr(float(base['total_usd']))):.4f}"
    bad = dict(base)
    bad["priority"] = int(base["priority"]) + 1
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "tags reversed (documented order-insensitive) and total as a 4-decimal string",
            "own re-serialisation of the field values"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "priority off by one, every other field correct",
            "independent field perturbation", operator="CR"),
    ]


def _log_extract(task: Task, heavy: bool) -> List[Probe]:
    recs = _record_key(task)
    keys = list(recs)

    def same_instant_ms(ts: str) -> str:
        return ts.replace("Z", ".000Z")

    def same_instant_lower(ts: str) -> str:
        return ts.replace("T", "t").replace("Z", "z")

    def same_instant_offset(ts: str) -> str:
        dt = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + _dt.timedelta(hours=8)
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+08:00"

    a = {k: dict(v) for k, v in recs.items()}
    b = {k: dict(v) for k, v in recs.items()}
    c = {k: dict(v) for k, v in recs.items()}
    for v in a.values():
        v["ts"] = same_instant_ms(v["ts"])
    for v in b.values():
        v["ts"] = same_instant_lower(v["ts"])
    for v in c.values():
        v["ts"] = same_instant_offset(v["ts"])

    d = {k: dict(v) for k, v in recs.items()}
    code = d[keys[0]]["code"]
    d[keys[0]]["code"] = code[0] + f"{(int(code[1:]) + 7) % 1000:03d}"
    return [
        _mk(task, 0, "semantic_equivalent", "accept", a,
            "timestamps with explicit millisecond precision (.000Z): the same instant",
            "own datetime rendering, ISO-8601 fractional seconds"),
        _mk(task, 1, "semantic_equivalent", "accept", b,
            "lower-case t/z designators: RFC 3339 allows them, the instant is unchanged",
            "own RFC 3339 re-spelling"),
        _mk(task, 2, "semantic_equivalent", "accept", c,
            "same instant written as +08:00 wall-clock time",
            "own timezone arithmetic (datetime.timedelta), not string replacement"),
        _mk(task, 3, "silent_partial", "reject", d,
            "first record code changed by +7; every other field correct",
            "independent field perturbation", operator="CR"),
    ]


_GENERAL = {
    "hex_color": r"^#[0-9A-Fa-f]{6}$",
    "ipv4_shape": r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$",
    "identifier": r"^[a-z][a-z0-9_]{3,16}$",
    "iso_date_shape": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    "python_file": r"^(?:[A-Za-z0-9_.-]+)\.py$",
    "hex_bytes": r"^[0-9a-f]{2}(?: [0-9a-f]{2})*$",
}


def _regex(task: Task, heavy: bool) -> List[Probe]:
    specs = task.meta["specs"]
    acc = [_GENERAL[sp["kind"]] for sp in specs]
    overfit = ["^(?:" + "|".join(re.escape(p) for p in sp["pos"]) + ")$"
               for sp in specs]
    # A degenerate overfit that memorises *both* positive and negative strings:
    # the verifier notices this one, which isolates "positive-only overfit".
    all_labels = ["^(?:" + "|".join(re.escape(s) for s in sp["pos"] + sp["neg"])
                  + ")$" for sp in specs]
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "patterns re-derived from the stated rule with a different spelling",
            "own rule->regex derivation; no access to the family's pattern strings"),
        _mk(task, 1, "overfit_to_tests", "reject", overfit,
            "alternation of the listed positive strings; matches no held-out member "
            "of the rule (e.g. a fresh #RRGGBB colour)",
            "built from the prompt's example strings only, as an overfitting solver would"),
        _mk(task, 2, "overfit_to_tests", "reject", all_labels,
            "alternation of positive *and* negative strings: memorises every label, "
            "generalises to nothing (this should be caught)",
            "built from the full labelled set"),
    ]


def _template(task: Task, heavy: bool) -> List[Probe]:
    base = [it["expected"] for it in task.items]
    acc_money = list(base)
    acc_money[1] = "$" + base[1]
    acc_ws = [line + "  " for line in base]
    bad = list(base)
    note = str(task.meta["data"]["note"])
    bad[2] = html.escape(note, quote=False)  # type: ignore[arg-type]
    return [
        _mk(task, 0, "spec_ambiguity", "accept", acc_money,
            'money with a "$" prefix: the prompt says "money" but never says '
            "whether the symbol belongs to the formatted value",
            "defensible reading of an under-specified format rule"),
        _mk(task, 1, "semantic_equivalent", "accept", acc_ws,
            "trailing spaces: same rendered line",
            "own whitespace-only edit"),
        _mk(task, 2, "silent_partial", "reject", bad,
            'html-escaped with quote=False, so " in the note stays raw',
            "stdlib html.escape with a different flag; only the escaping boundary moves",
            operator="SDL"),
    ]


# ------------------------------------------------------------------- data probes
_REWRITES = {
    "sum_by_dept": "SELECT dept AS d, SUM(amount) AS s FROM orders GROUP BY dept ORDER BY 1",
    "count_paid": "SELECT COUNT(*) FROM orders WHERE status IN ('paid')",
    "top2_depts": "SELECT dept, SUM(amount) FROM orders GROUP BY dept ORDER BY 2 DESC LIMIT 2",
    "regions_over_3": "SELECT region FROM orders GROUP BY region HAVING COUNT(*) > 3",
    "rich_depts": "SELECT name, head, budget FROM depts WHERE budget >= 601 ORDER BY 1",
    "avg_by_region": "SELECT region, AVG(amount) FROM orders GROUP BY 1 ORDER BY 1",
}


def _sql_lit(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    return repr(value)


def _sql(task: Task, heavy: bool) -> List[Probe]:
    acc = [_REWRITES[it["key"]] for it in task.items]
    consts = []
    for it in task.items:
        rows = it["expected"]["primary"]
        selects = ["SELECT " + ", ".join(_sql_lit(c) for c in row) for row in rows]
        consts.append(" UNION ALL ".join(selects) if selects else "SELECT NULL LIMIT 0")
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "same result set expressed with aliases, ordinal ORDER BY and IN/H> forms",
            "own SQL rewrite per question, checked against no verifier code"),
        _mk(task, 1, "hardcoded_expected", "reject", consts,
            "constant SELECT ... UNION ALL rows copied from the visible primary result; "
            "the held-out probe dataset is ignored",
            "built from the task fixture's primary result rows, as a memorising solver "
            "would", operator="HARD"),
    ]


def _table(task: Task, heavy: bool) -> List[Probe]:
    base = {it["unit"]: it["expected"] for it in task.items}
    acc: Dict[str, Dict[str, Any]] = {}
    for (unit, value) in base.items():
        d, m = unit.split(".", 1)
        acc.setdefault(d, {})[m] = _exact(value) if m == "mean" else value
    # Recompute the median independently; if it equals the mean, nudge by one.
    bad: Dict[str, Dict[str, Any]] = {}
    for d in {u.split(".", 1)[0] for u in base}:
        amounts = sorted(r[2] for r in task.meta["rows"] if r[0] == d)
        n = len(amounts)
        med = Fraction(amounts[n // 2]) if n % 2 else Fraction(amounts[n // 2 - 1] + amounts[n // 2], 2)
        mean = Fraction(sum(amounts), n)
        alt = med if med != mean else mean + 1
        bad[d] = {"count": len(amounts), "sum": sum(amounts), "mean": _exact(alt)}
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "mean as an exact fraction; count and sum unchanged",
            "own exact formatter over the item values"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "mean column replaced by the median of the same group",
            "own median from the raw rows; no shared aggregation helper", operator="AOR"),
    ]


def _sort(task: Task, heavy: bool) -> List[Probe]:
    ids = [it["expected"] for it in task.items]
    return [
        _mk(task, 0, "semantic_equivalent", "accept", [str(i) for i in ids],
            "record ids as strings: same records, same positions",
            "own JSON re-spelling of the id list"),
        _mk(task, 1, "silent_partial", "reject", list(reversed(ids)),
            "positions reversed: every id is present, none is in the right place",
            "own permutation of the reference list", operator="TR"),
    ]


def _merge_touching(raw: Sequence[Sequence[int]]) -> List[List[int]]:
    out: List[List[int]] = []
    for a, b in sorted(raw):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _interval(task: Task, heavy: bool) -> List[Probe]:
    acc = [[float(it["expected"][0]), float(it["expected"][1])] for it in task.items]
    bad = _merge_touching(task.meta["raw"])
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "endpoints as JSON floats instead of integers",
            "own re-typing of the reference pairs"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "touching endpoints merged (a <= end instead of a < end)",
            "own half-open merge written with the wrong inequality", operator="ROR"),
    ]


# -------------------------------------------------------------- structural probes
def _grid_bfs(grid: Sequence[str], start: Sequence[int], goal: Sequence[int]) -> List[List[int]]:
    from collections import deque

    start, goal = tuple(start), tuple(goal)
    rows, cols = len(grid), len(grid[0])
    dirs = ((1, 0), (0, 1), (-1, 0), (0, -1))
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for dr, dc in dirs:
            rr, cc = cur[0] + dr, cur[1] + dc
            if 0 <= rr < rows and 0 <= cc < cols and grid[rr][cc] != "#" and (rr, cc) not in prev:
                prev[(rr, cc)] = cur
                q.append((rr, cc))
    if goal not in prev:
        return []
    path = []
    node: Optional[Tuple[int, int]] = goal
    while node is not None:
        path.append(list(node))
        node = prev[node]
    return list(reversed(path))


def _grid(task: Task, heavy: bool) -> List[Probe]:
    grid = task.meta["grid"]
    acc = [_grid_bfs(grid, it["expected"]["start"], it["expected"]["goal"])
           for it in task.items]
    bad = [list(p) for p in acc]
    bad[0] = bad[0][:-1]
    probes = [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "an alternative shortest path found with a different neighbour order",
            "own BFS (deque, fixed direction order) that shares no code with the family"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "first path stops one cell before the goal; other paths optimal",
            "own path truncation", operator="SDL"),
    ]
    if heavy and acc and acc[0]:
        huge = [acc[0][0]] * 5000
        probes.append(_mk(task, 2, "resource", "reject", [huge] + acc[1:],
                          "oversized path payload (5000 cells): must be rejected by the "
                          "length check without allocating an unbounded structure",
                          "payload-size probe; cost is measured separately"))
    return probes


def _csp_solution(c: Dict[str, Any], nodes: Sequence[str],
                  colours: Sequence[int], limit: int = 2) -> List[Dict[str, int]]:
    """Own backtracking search, independent of the family's solver."""
    out: List[Dict[str, int]] = []

    def ok(node: str, colour: int, cur: Dict[str, int]) -> bool:
        for u, v in c["edges"]:
            if (u == node and cur.get(v) == colour) or (v == node and cur.get(u) == colour):
                return False
        pin = c["pins"].get(node)
        return pin is None or int(pin) == colour

    def rec(i: int, cur: Dict[str, int]) -> None:
        if len(out) >= limit:
            return
        if i == len(nodes):
            out.append(dict(cur))
            return
        node = nodes[i]
        for colour in colours:
            if ok(node, colour, cur):
                cur[node] = colour
                rec(i + 1, cur)
                del cur[node]

    rec(0, {})
    return out


def _csp(task: Task, heavy: bool) -> List[Probe]:
    acc = []
    for it in task.items:
        c = it["constraints"]
        sols = _csp_solution(c, list(reversed(c["nodes"])), list(reversed(
            range(1, int(c["colors"]) + 1))), limit=2)
        alt = next((s for s in sols if s != it["expected"]),
                   sols[0] if sols else dict(it["expected"]))
        acc.append({n: int(col) for n, col in alt.items()})
    bad = []
    for it in task.items:
        c, sol = it["constraints"], dict(it["expected"])
        edge = c["edges"][0]
        cand = dict(sol)
        cand[edge[1]] = sol[edge[0]]
        bad.append(cand)
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "a different valid colouring (cyclic colour relabelling, pins preserved)",
            "own permutation argument, not the family's backtracking search"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "one edge given the same colour on both endpoints",
            "own edge selection from the stated constraints", operator="SDL"),
    ]


_SLOTS = 16


def _sched_valid(prob: Dict[str, Any], starts: Dict[str, int]) -> bool:
    cells = {}
    for m in prob["meetings"]:
        s = starts.get(m["id"])
        if not isinstance(s, int) or isinstance(s, bool) or s < 0 or s + m["dur"] > _SLOTS:
            return False
        block = set(range(s, s + m["dur"]))
        for person in m["who"]:
            if block & set(prob["busy"][person]):
                return False
        cells[m["id"]] = block
    ids = [m["id"] for m in prob["meetings"]]
    for a, b in itertools.combinations(ids, 2):
        if cells[a] & cells[b]:
            return False
    return set(starts) == set(ids)


def _schedule(task: Task, heavy: bool) -> List[Probe]:
    acc = []
    for it in task.items:
        prob = it["problem"]
        ids = list(reversed([m["id"] for m in prob["meetings"]]))
        sol = None
        for combo in itertools.product(range(_SLOTS), repeat=len(ids)):
            starts = dict(zip(ids, combo))
            if _sched_valid(prob, starts):
                sol = starts
                break
        acc.append(sol if sol is not None else it["expected"])
    bad = []
    for it in task.items:
        prob, sol = it["problem"], dict(it["expected"])
        cand = None
        for mid in [m["id"] for m in prob["meetings"]]:
            for delta in (1, -1, 2, -2, 3):
                trial = dict(sol)
                trial[mid] = sol[mid] + delta
                if not _sched_valid(prob, trial):
                    cand = trial
                    break
            if cand:
                break
        bad.append(cand if cand else {k: -1 for k in sol})
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "an alternative valid schedule found by an independent brute-force search",
            "own constraint check and search order (meeting ids reversed)"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "one meeting shifted into a conflict; the rest of the schedule stays valid",
            "own perturb-and-check loop", operator="CR"),
    ]


def _kahn_sorted(nodes: Sequence[str], edges: Sequence[Sequence[str]]) -> List[str]:
    indeg = {n: 0 for n in nodes}
    for u, v in edges:
        indeg[v] += 1
    ready = sorted(n for n in nodes if indeg[n] == 0)
    out: List[str] = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for u, v in edges:
            if u == n:
                indeg[v] -= 1
                if indeg[v] == 0:
                    ready.append(v)
                    ready.sort()
    return out


def _topo(task: Task, heavy: bool) -> List[Probe]:
    acc = [_kahn_sorted(it["graph"]["nodes"], it["graph"]["edges"]) for it in task.items]
    bad = [list(reversed(o)) for o in acc]
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "a different valid topological order (lexicographically smallest ready node)",
            "own Kahn implementation with a sorted queue, not the family's randomised one"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "order reversed: every node listed once, every edge violated",
            "own reversal of the independent order", operator="TR"),
    ]


def _life_wrap(board: Sequence[Sequence[int]]) -> List[str]:
    rows, cols = len(board), len(board[0])
    out = []
    for r in range(rows):
        line = []
        for c in range(cols):
            n = sum(board[(r + dr) % rows][(c + dc) % cols]
                    for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0))
            line.append("1" if (n == 3 or (n == 2 and board[r][c])) else "0")
        out.append("".join(line))
    return out


def _life(task: Task, heavy: bool) -> List[Probe]:
    rows = [it["expected"] for it in task.items]
    acc = [" ".join(ch for ch in row) for row in rows]
    bad = _life_wrap([[int(ch) for ch in row] for row in task.meta["board"]])
    return [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "rows as space-separated binary strings",
            "own row re-spelling"),
        _mk(task, 1, "silent_partial", "reject", bad,
            "toroidal (wrapping) neighbourhood instead of a dead border",
            "own Life step with wrap=True; boundary rule differs, interior usually agrees",
            operator="ROR"),
    ]


# ---------------------------------------------------------------- code-patch probes
_CASES: Dict[str, List[List[Any]]] = {}


def _code_cases() -> Dict[str, List[List[Any]]]:
    """Read the public fixture case inputs once (task data, not a decision rule)."""
    if not _CASES:
        from .families.structural import _CODE_TEMPLATES  # fixture table only

        for t in _CODE_TEMPLATES:
            _CASES[t["name"]] = [list(c) for c in t["cases"]]
    return _CASES


def _code_impl(name: str) -> Tuple[Callable[..., Any], str]:
    """Independent reference implementations, written here, different from ``alt``."""
    impls: Dict[str, Tuple[Callable[..., Any], str]] = {
        "running_max": (
            lambda nums: [max(nums[:i + 1]) for i in range(len(nums))],
            "def solve(nums):\n    out = []\n    for i in range(len(nums)):\n"
            "        out.append(max(nums[:i + 1]))\n    return out\n",
        ),
        "count_vowels": (
            lambda s: sum(1 for ch in s.lower() if ch in "aeiou"),
            "def solve(s):\n    return sum(1 for ch in s.lower() if ch in 'aeiou')\n",
        ),
        "chunk": (
            lambda items, k: [items[i:i + k] for i in range(0, len(items), k)],
            "def solve(items, k):\n    out = []\n    i = 0\n"
            "    while i < len(items):\n        out.append(items[i:i + k])\n        i += k\n"
            "    return out\n",
        ),
        "safe_div": (
            lambda a, b: None if b == 0 else a / b,
            "def solve(a, b):\n    if b == 0:\n        return None\n    return float(a) / b\n",
        ),
        "dedupe": (
            lambda xs: [x for i, x in enumerate(xs) if x not in xs[:i]],
            "def solve(xs):\n    out = []\n    for i, x in enumerate(xs):\n"
            "        if x not in xs[:i]:\n            out.append(x)\n    return out\n",
        ),
    }
    return impls[name]


def _code(task: Task, heavy: bool) -> List[Probe]:
    name = task.meta["template"]
    cases = _code_cases()[name]
    fn, alt_src = _code_impl(name)
    table = {repr(tuple(c)): fn(*c) for c in cases}

    hardcoded = ("def solve(*args):\n    table = " + repr(table)
                 + "\n    return table.get(repr(args))\n")
    stateful = ("_calls = [0]\ndef solve(*args):\n    _calls[0] += 1\n"
                "    if _calls[0] > 5:\n        return None\n    table = " + repr(table)
                + "\n    return table.get(repr(args))\n")
    # Variants below are built from the independent implementation, not from the
    # fixture's own source, so their correct half is never shared with the verifier.
    impl = alt_src.replace("def solve(", "def _impl(", 1)
    second_call = (impl + "\n_calls = [0]\ndef solve(*args):\n"
                   "    _calls[0] += 1\n    if _calls[0] >= 2:\n        return None\n"
                   "    return _impl(*args)\n")
    alternating = (impl + "\n_calls = [0]\ndef solve(*args):\n"
                   "    _calls[0] += 1\n    if _calls[0] % 2 == 0:\n        return None\n"
                   "    return _impl(*args)\n")
    # A module-level memo keyed by call arity: the first answer for an arity is
    # replayed for every later call with that arity.  Inside one task it corrupts
    # a second case of the same arity; across tasks it would return the previous
    # task's answer.  A one-shot verifier sees whichever case ordering it uses.
    cross_task = (impl + "\n_memo = {}\ndef solve(*args):\n    key = len(args)\n"
                  "    if key in _memo:\n        return _memo[key]\n"
                  "    out = _impl(*args)\n    _memo[key] = out\n    return out\n")

    probes = [
        _mk(task, 0, "semantic_equivalent", "accept", alt_src,
            "independent correct implementation of the stated spec",
            "own implementation, different control flow from the fixture's alt",
            operator="EQUIV"),
        _mk(task, 1, "hardcoded_expected", "reject", hardcoded,
            "lookup table of the visible hidden-test answers; correct on every case it "
            "was built for, meaningless on any other input",
            "expected values recomputed here from case inputs, then frozen",
            operator="HARD"),
        _mk(task, 2, "resource", "reject", stateful,
            "state-dependent output: the first five invocations pass, a later one "
            "fails; a single-shot verifier cannot see this",
            "module-level invocation counter, no randomness",
            operator="STATE"),
        _mk(task, 3, "resource", "reject", second_call,
            "fails from the second invocation on (a harness that runs every case in "
            "one process sees it; a harness that starts a fresh process per case "
            "would not)",
            "first-call-only correctness, counter in module state",
            operator="STATE"),
        _mk(task, 4, "resource", "reject", alternating,
            "output alternates between correct and None: the answer depends on call "
            "history, not on the input",
            "deterministic alternation stands in for non-determinism so the audit "
            "stays reproducible; genuinely random output would make the verifier's "
            "own verdict unstable, which is the defect being demonstrated",
            operator="NONDET"),
        _mk(task, 5, "resource", "reject", cross_task,
            "memoised answer replayed for a later call of the same arity; within one "
            "task it corrupts same-arity cases, across tasks it returns another "
            "task's answer",
            "module-level memo keyed by arity only, deliberately not keyed by input",
            operator="STATE"),
    ]
    if name == "chunk":
        probes.append(_mk(task, 6, "overfit_to_tests", "reject",
                          "def solve(items, k):\n    if len(items) > 5:\n        return []\n"
                          "    return [items[i:i + k] for i in range(0, len(items), k)]\n",
                          "correct for every fixture case (all lists have <= 5 items), "
                          "empty for any longer input",
                          "shape-overfit built from the fixture's case sizes",
                          operator="OVF"))
    if heavy:
        mem = ("def solve(*args):\n    junk = [0] * 2000000\n    table = "
               + repr(table) + "\n    return table.get(repr(args))\n")
        probes.append(_mk(task, 7, "resource", "observe", mem,
                          "~16 MB allocation for a five-element input; outcome is correct, "
                          "no memory budget is part of the verifier contract",
                          "resource observation, excluded from TPR/TNR",
                          operator="INF"))
        probes.append(_mk(task, 8, "resource", "reject",
                          "def solve(*args):\n    while True:\n        pass\n",
                          "non-terminating implementation: must be killed by the "
                          "subprocess timeout and rejected",
                          "timeout probe, run once per family",
                          operator="INF"))
    return probes


_BUILDERS: Dict[str, Callable[[Task, bool], List[Probe]]] = {
    "arith_expression": _arith,
    "unit_convert": _unit,
    "stats_summary": _stats,
    "base_convert": _base,
    "matrix_ops": _matrix,
    "date_arith": _date,
    "json_schema_extract": _json_extract,
    "log_field_extraction": _log_extract,
    "regex_construct": _regex,
    "template_render": _template,
    "sql_result": _sql,
    "table_aggregate": _table,
    "sort_multikey": _sort,
    "interval_merge": _interval,
    "grid_path": _grid,
    "csp_assign": _csp,
    "schedule_slots": _schedule,
    "topo_order": _topo,
    "life_step": _life,
    "code_patch": _code,
}


def has_builder(family: str) -> bool:
    return family in _BUILDERS


def probes_for(family: str, task: Task, heavy: bool = False) -> List[Probe]:
    """Return the non-aligned probes for one task.  Deterministic, no RNG."""
    fn = _BUILDERS.get(family)
    if fn is None:
        return []
    return fn(task, heavy)
