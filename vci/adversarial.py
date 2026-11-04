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
| `OVF` | a rule that only holds on the labelled examples | executable-oracle families only; two-plus per task where a held-out set exists |
| `HARD` | lookup table instead of an algorithm | obviously wrong in principle, yet invisible to a fixture-replaying harness |
| `STATE` | answer depends on history, not input | needs a second invocation; one-shot verifiers cannot see it |
| `NONDET` | same input, different answer | needs repeated calls; most harnesses call once |
| `INF` | non-termination / unbounded resource use | detectable by a watchdog, but the cost is wall-clock: observed, not scored |
| `EQUIV` | not a defect: same meaning, different spelling | authored, not decided; measures false rejects only where the author is right |
| `AMB` | not a defect: a defensible second reading of an under-specified prompt | a rejection here blames the task text, not the verifier |
| `DIR` | input changed, so the correct answer changed | only measurable where the verifier derives truth by executing the candidate against task-carried data; on fixture-replay verifiers a perturbed pair is accepted by construction and is therefore not authored |

Round-5/10 additions
--------------------
``directional_shift`` probes carry a ``task_override``: a perturbed copy of the
task whose input data changed in a known way.  ``audit._probe_record`` verifies
the candidate against the override, not the original task.  Positive probes
submit the independently recomputed correct answer to the perturbed input
(expectation ``accept``); negative probes submit the answer that was correct
*before* the change (expectation ``reject``).  They exist only for families
whose verifier re-derives truth from task-carried data instead of replaying a
stored expected value: round 5 covered ``sql_result``, ``regex_construct`` and
``code_patch``; round 10 added the constraint-shaped families
``grid_path`` (obstacles moved), ``csp_assign`` (node appended),
``schedule_slots`` (availability changed) and ``topo_order`` (node inserted).
For the remaining thirteen fixture-replay families a perturbed (input, truth)
pair would be accepted by construction and would manufacture a meaningless
TPR -- no such probe is authored.

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
``directional_shift``   the task input changed; the answer must change with it

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
    "directional_shift",
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
    "directional_shift": "directional",
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
    "directional_shift": "DIR",
}

#: The mutation operators a probe record may carry (see the module docstring).
OPERATORS = ("AOR", "ROR", "CR", "SDL", "TR", "OVF", "HARD", "STATE",
             "NONDET", "INF", "EQUIV", "AMB", "DIR")

#: Bumped whenever a probe payload changes, so a result file can be traced to
#: the sample that produced it.
GENERATOR_VERSION = "5.1"


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
    #: Round 5: when set, the verifier is run against this perturbed task
    #: instead of the original one (directional probes only).
    task_override: Any = None

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
        operator: Optional[str] = None, task_override: Any = None) -> Probe:
    assert cls in FAILURE_CLASSES and exp in EXPECTATIONS
    cat = category or CATEGORY_BY_CLASS[cls]
    op = operator or OPERATOR_BY_CLASS[cls]
    assert cat in CHECKLIST_CATEGORIES, cat
    return Probe(probe_id=f"{task.task_id}-x{idx:02d}", task_id=task.task_id,
                 family=task.family, failure_class=cls, checklist_category=cat,
                 operator=op, expectation=exp, payload=payload, note=note,
                 basis=basis, task_override=task_override)


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
    probes = [
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
    fresh_specs = _regex_fresh_specs(task)
    override = Task(family=task.family, task_id=task.task_id + "-dir",
                    prompt=task.prompt +
                    "\n[directional probe: labelled strings replaced by fresh ones]",
                    items=[dict(it) for it in task.items],
                    meta={"specs": fresh_specs})
    probes += [
        _mk(task, 3, "directional_shift", "accept", acc,
            "the general rule patterns, evaluated against a fresh set of "
            "positive/negative strings the probe author never saw labelled",
            "fresh strings generated here from the stated rule and self-checked "
            "against the own pattern; the verifier must classify them",
            operator="DIR", task_override=override),
        _mk(task, 4, "directional_shift", "reject", overfit,
            "alternation of the *original* positive strings, evaluated against the "
            "fresh string set: right answer to the old input",
            "the input changed, so the memorised alternation must fail on the "
            "fresh positives", operator="DIR", task_override=override),
    ]
    return probes


#: Candidate fresh strings per spec kind (round 5).  Positives must match the
#: own rule pattern, negatives must not; both are checked at build time.
_FRESH_STRINGS = {
    "hex_color": (
        ["#9C4f2A", "#0a1B2c", "#Ff00Aa", "#123aBc"],
        ["#9C4f2", "#9C4f2A1", "#9C4f2G", "9C4f2A", "#9C 4f2A"]),
    "ipv4_shape": (
        ["10.20.30.40", "1.2.3.4", "192.168.0.100", "255.0.127.9"],
        ["10.20.30", "10.20.30.40.50", "10.20.30.0400", "a.20.30.40",
         "10.20.30.40 "]),
    "identifier": (
        ["alpha_99", "z_123", "beta7_x", "q_w_e_r_1"],
        ["Alpha_99", "ab", "a_b", "9abc_", "a-b_c", "a_b_c_d_e_f_g_h_1_2"]),
    "iso_date_shape": (
        ["2026-11-04", "1999-01-01", "2030-12-31", "2024-02-29"],
        ["2026-1-4", "20261104", "2026/11/04", "26-11-0404", "2026-11-04 "]),
    "python_file": (
        ["utils.py", "my.module-v2.py", "_private.py", "UPPER.py"],
        ["utils.pyc", "utils.PY", "utils", "utils.py ", ".py"]),
    "hex_bytes": (
        ["de ad be ef", "00", "ff 00 aa 11", "0f"],
        ["DE AD", "de ad ", "dea d", "0g 00", "de  ad"]),
}


def _regex_fresh_specs(task: Task) -> List[Dict[str, Any]]:
    """Fresh pos/neg strings per spec, disjoint from the task's labelled set."""
    out = []
    for sp in task.meta["specs"]:
        kind = sp["kind"]
        pattern = re.compile(_GENERAL[kind])
        pos_c, neg_c = _FRESH_STRINGS[kind]
        seen = set(sp["pos"]) | set(sp["neg"])
        pos = [s for s in pos_c
               if s not in seen and pattern.fullmatch(s) is not None]
        neg = [s for s in neg_c
               if s not in seen and pattern.fullmatch(s) is None]
        assert len(pos) >= 2 and len(neg) >= 2, f"not enough fresh strings for {kind}"
        out.append({"kind": kind, "pos": pos[:2], "neg": neg[:2],
                    "loose": sp["loose"], "tight": sp["tight"]})
    return out


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
    probes = [
        _mk(task, 0, "semantic_equivalent", "accept", acc,
            "same result set expressed with aliases, ordinal ORDER BY and IN/H> forms",
            "own SQL rewrite per question, checked against no verifier code"),
        _mk(task, 1, "hardcoded_expected", "reject", consts,
            "constant SELECT ... UNION ALL rows copied from the visible primary result; "
            "the held-out probe dataset is ignored",
            "built from the task fixture's primary result rows, as a memorising solver "
            "would", operator="HARD"),
    ]
    shifted = _sql_shifted_task(task)
    if shifted is not None:
        probes += [
            _mk(task, 2, "directional_shift", "accept", acc,
                "correct general queries, submitted against a shifted dataset "
                "(amounts doubled, dept/region/status rotated)",
                "own pure-Python reference recomputed the shifted expected values; "
                "the verifier must execute on the shifted rows to agree",
                operator="DIR", task_override=shifted),
            _mk(task, 3, "directional_shift", "reject", consts,
                "constant rows memorising the original primary result, submitted "
                "after the dataset shift: right answer to the old input",
                "the input changed, so the memorised answer must fail; caught iff "
                "the verifier really executes on the shifted data",
                operator="DIR", task_override=shifted),
        ]
    return probes


# ------------------------------------------------- directional helpers (round 5)
_SQL_DEPT_ROT = {"ENG": "SLS", "SLS": "OPS", "OPS": "HR", "HR": "ENG"}
_SQL_REGION_ROT = {"NA": "EU", "EU": "APAC", "APAC": "NA"}
_SQL_STATUS_ROT = {"paid": "pending", "pending": "refund", "refund": "paid"}
_SQL_STATUS_SWAP = {"paid": "pending", "pending": "paid", "refund": "refund"}
#: Own copy of the constant depts fixture (task data; never read back from the
#: family module at decision time).
_SQL_DEPTS = [("ENG", "Ada", 900), ("SLS", "Grace", 700),
              ("OPS", "Linus", 500), ("HR", "Maria", 300)]


def _sql_ref(key: str, rows: List[List[Any]],
             depts: Optional[List[Tuple[str, str, int]]] = None) -> List[List[Any]]:
    """Pure-Python reference results for the six question templates."""
    if key == "sum_by_dept":
        tot: Dict[str, int] = {}
        for r in rows:
            tot[r[1]] = tot.get(r[1], 0) + r[3]
        return [[d, tot[d]] for d in sorted(tot)]
    if key == "count_paid":
        return [[sum(1 for r in rows if r[4] == "paid")]]
    if key == "top2_depts":
        tot = {}
        for r in rows:
            tot[r[1]] = tot.get(r[1], 0) + r[3]
        assert len(set(tot.values())) == len(tot), "top2 tie repair failed"
        return [[d, t] for d, t in sorted(tot.items(), key=lambda kv: (-kv[1], kv[0]))[:2]]
    if key == "regions_over_3":
        cnt: Dict[str, int] = {}
        for r in rows:
            cnt[r[2]] = cnt.get(r[2], 0) + 1
        return [[g] for g in sorted(cnt) if cnt[g] > 3]
    if key == "rich_depts":
        table = _SQL_DEPTS if depts is None else depts
        return [[n, h, b] for n, h, b in sorted(table) if b > 600]
    if key == "avg_by_region":
        sums: Dict[str, List[int]] = {}
        for r in rows:
            sums.setdefault(r[2], []).append(r[3])
        return [[g, sum(v) / len(v)] for g, v in sorted(sums.items())]
    raise KeyError(key)


def _sql_shift_rows(rows: List[List[Any]], mult: int,
                    status_map: Dict[str, str],
                    shrink_first_region: bool = False) -> List[List[Any]]:
    out = [[r[0], _SQL_DEPT_ROT[r[1]], _SQL_REGION_ROT[r[2]], r[3] * mult,
            status_map[r[4]]] for r in rows]
    if shrink_first_region:
        # Large but valid shift: keep only two rows of the lexicographically
        # first region, so a "all regions are over 3" answer must change.
        first = sorted({r[2] for r in out})[0]
        kept, seen = [], 0
        for r in out:
            if r[2] == first:
                seen += 1
                if seen > 2:
                    continue
            kept.append(r)
        out = kept
    # top2_depts is ordered by total: ties would make the reference order
    # engine-dependent, so bump amounts until every dept total is distinct.
    for _ in range(20):
        tot: Dict[str, int] = {}
        for r in out:
            tot[r[1]] = tot.get(r[1], 0) + r[3]
        dup = {d for d, t in tot.items() if list(tot.values()).count(t) > 1}
        if not dup:
            return out
        for r in out:
            if r[1] in dup:
                r[3] += 1
                break
    raise AssertionError("tie repair did not converge")


def _sql_shifted_task(task: Task) -> Optional[Task]:
    """A copy of the task on shifted data, with expected values recomputed here.

    Returns ``None`` when no deterministic shift changes any item's result
    (then a stale-answer probe would be accidentally correct).
    """
    variants = [
        (2, _SQL_STATUS_ROT, False), (2, _SQL_STATUS_SWAP, False),
        (3, _SQL_STATUS_ROT, False), (2, _SQL_STATUS_ROT, True),
        (2, _SQL_STATUS_SWAP, True), (3, _SQL_STATUS_SWAP, True),
        (2, _SQL_STATUS_ROT, "shrink"), (3, _SQL_STATUS_SWAP, "shrink"),
    ]
    for mult, status_map, drop_last in variants:
        shrink = drop_last == "shrink"
        rows = _sql_shift_rows(task.meta["rows"], mult, status_map, shrink)
        probe = _sql_shift_rows(task.meta["probe"], mult, status_map, shrink)
        if drop_last is True:
            rows, probe = rows[:-1], probe[:-1]
        items, changed = [], False
        for it in task.items:
            exp = {"primary": _sql_ref(it["key"], rows),
                   "probe": _sql_ref(it["key"], probe,
                                     task.meta.get("probe_depts"))}
            old = it["expected"]
            if exp["primary"] != old["primary"] or exp["probe"] != old["probe"]:
                changed = True
            items.append({"unit": it["unit"], "expected": exp,
                          "ordered": it["ordered"], "key": it["key"]})
        if changed:
            prompt = (task.prompt +
                      "\n[directional probe: dataset shifted -- amounts scaled, "
                      "dept/region/status relabelled]")
            meta = {"rows": rows, "probe": probe,
                    "probe_depts": task.meta.get("probe_depts"),
                    "questions": task.meta["questions"]}
            return Task(family=task.family, task_id=task.task_id + "-dir",
                        prompt=prompt, items=items, meta=meta)
    return None


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


def _grid_directional(task: Task) -> Optional[Tuple[List[Dict[str, Any]], Dict[str, Any],
                                                   List[Any], List[Any]]]:
    """Move the obstacles, then recompute every shortest path here.

    A wall is placed on each old path, so the old answer is wrong on the new
    grid while the independently recomputed answer is right.  Returns
    ``(items, meta, positive_payload, stale_payload)`` or ``None`` if the shift
    would disconnect a pair.
    """
    old_paths = [list(it["path"]) for it in task.items]
    protected = {tuple(it["expected"][k]) for it in task.items
                 for k in ("start", "goal")}

    def attempt(indices: Sequence[int]):
        grid = [list(row) for row in task.meta["grid"]]
        for i in indices:
            cell = next((c for c in old_paths[i][1:-1]
                         if tuple(c) not in protected and grid[c[0]][c[1]] == "."),
                        None)
            if cell is None:
                return None
            grid[cell[0]][cell[1]] = "#"
        shifted = ["".join(row) for row in grid]
        items, acc = [], []
        for it in task.items:
            path = _grid_bfs(shifted, it["expected"]["start"], it["expected"]["goal"])
            if not path:
                return None
            acc.append(path)
            items.append({"unit": it["unit"],
                          "expected": {"start": it["expected"]["start"],
                                       "goal": it["expected"]["goal"],
                                       "len": len(path)}})
        return items, {"grid": shifted}, acc, old_paths

    # Wall every old path when possible; otherwise wall a subset, which still
    # makes the stale answer wrong as long as one old path is blocked.
    for indices in ((0, 1, 2), (0,), (1,), (2,), (0, 1), (1, 2), (0, 2)):
        got = attempt(indices)
        if got is not None:
            return got
    return None


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
    shifted = _grid_directional(task)
    if shifted is not None:
        items, meta, acc_new, stale = shifted
        override = Task(family=task.family, task_id=task.task_id + "-dir",
                        prompt=task.prompt +
                        "\n[directional probe: obstacles added on the old paths]",
                        items=items, meta=meta)
        probes += [
            _mk(task, 3, "directional_shift", "accept", acc_new,
                "shortest paths recomputed on a grid with new obstacles",
                "own BFS on the perturbed grid; the verifier must read the shifted grid",
                operator="DIR", task_override=override),
            _mk(task, 4, "directional_shift", "reject", stale,
                "the paths that were shortest before the obstacles moved",
                "the input changed, so the old paths now cross a wall",
                operator="DIR", task_override=override),
        ]
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


def _csp_directional(task: Task) -> Optional[Tuple[List[Dict[str, Any]], Dict[str, Any],
                                                   List[Any], List[Any]]]:
    """Add a node joined to two differently coloured neighbours.

    The old colouring omits the new node, so it cannot satisfy the shifted
    constraint set; a fresh colouring is found with the independent search.
    """
    items, acc, stale = [], [], []
    for it in task.items:
        c = it["constraints"]
        nodes, edges = list(c["nodes"]), [list(e) for e in c["edges"]]
        pair = next(((u, v) for u, v in edges
                     if it["expected"][u] != it["expected"][v]), None)
        if pair is None:
            return None
        u, v = pair
        node = next(ch for ch in "WXYZ" if ch not in nodes)
        c2 = {"nodes": nodes + [node], "edges": edges + [[u, node], [node, v]],
              "pins": dict(c["pins"]), "colors": c["colors"]}
        sols = _csp_solution(c2, list(reversed(c2["nodes"])),
                             list(reversed(range(1, int(c2["colors"]) + 1)),), limit=2)
        if not sols:
            return None
        sol = {n: int(col) for n, col in sols[0].items()}
        acc.append(sol)
        stale.append(dict(it["expected"]))
        items.append({"unit": it["unit"], "expected": sol, "constraints": c2})
    return items, {}, acc, stale


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
    ] + _csp_dir_probes(task)


def _csp_dir_probes(task: Task) -> List[Probe]:
    shifted = _csp_directional(task)
    if shifted is None:
        return []
    items, meta, acc, stale = shifted
    override = Task(family=task.family, task_id=task.task_id + "-dir",
                    prompt=task.prompt +
                    "\n[directional probe: one node and two edges added]",
                    items=items, meta=meta)
    return [
        _mk(task, 2, "directional_shift", "accept", acc,
            "a colouring recomputed after a node was appended",
            "own search on the shifted constraints; the verifier must read them",
            operator="DIR", task_override=override),
        _mk(task, 3, "directional_shift", "reject", stale,
            "the colouring that satisfied the constraints before the node existed",
            "the answer ignores the new node, so it cannot satisfy the shifted set",
            operator="DIR", task_override=override),
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


def _schedule_directional(task: Task) -> Optional[Tuple[List[Dict[str, Any]],
                                                       Dict[str, Any],
                                                       List[Any], List[Any]]]:
    """Mark a slot used by the old schedule as busy, then reschedule.

    The old schedule conflicts with the new availability, so it must be
    rejected; a new schedule is found by an independent brute-force search.
    """
    items, acc, stale = [], [], []
    for it in task.items:
        prob, old = it["problem"], dict(it["expected"])
        found = None
        for m in prob["meetings"]:
            if found:
                break
            for person in m["who"]:
                slot = int(old[m["id"]])
                if slot in prob["busy"][person]:
                    continue
                busy = {p: list(v) for p, v in prob["busy"].items()}
                busy[person] = sorted(busy[person] + [slot])
                prob2 = {"meetings": prob["meetings"], "busy": busy}
                ids = [x["id"] for x in prob["meetings"]]
                for combo in itertools.product(range(_SLOTS), repeat=len(ids)):
                    starts = dict(zip(ids, combo))
                    if _sched_valid(prob2, starts):
                        found = (prob2, starts)
                        break
                if found:
                    break
        if found is None:
            return None
        prob2, sol = found
        acc.append(sol)
        stale.append(dict(old))
        items.append({"unit": it["unit"], "expected": sol, "problem": prob2})
    return items, {}, acc, stale


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
    ] + _schedule_dir_probes(task)


def _schedule_dir_probes(task: Task) -> List[Probe]:
    shifted = _schedule_directional(task)
    if shifted is None:
        return []
    items, meta, acc, stale = shifted
    override = Task(family=task.family, task_id=task.task_id + "-dir",
                    prompt=task.prompt +
                    "\n[directional probe: one previously free slot became busy]",
                    items=items, meta=meta)
    return [
        _mk(task, 2, "directional_shift", "accept", acc,
            "a schedule recomputed after an attendee became busy",
            "own search on the shifted availability; the verifier must read it",
            operator="DIR", task_override=override),
        _mk(task, 3, "directional_shift", "reject", stale,
            "the schedule that fitted the old availability",
            "it now puts a meeting into a busy slot",
            operator="DIR", task_override=override),
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


def _topo_directional(task: Task) -> Optional[Tuple[List[Dict[str, Any]], Dict[str, Any],
                                                   List[Any], List[Any]]]:
    """Insert a new node between an existing source and sink.

    The old order predates the node and therefore does not cover the shifted
    graph; the new order is recomputed with the independent Kahn pass.
    """
    items, acc, stale = [], [], []
    for it in task.items:
        g = it["graph"]
        nodes, edges = list(g["nodes"]), [list(e) for e in g["edges"]]
        node = next(ch for ch in "WXYZ" if ch not in nodes)
        indeg = {n: 0 for n in nodes}
        outdeg = {n: 0 for n in nodes}
        for u, v in edges:
            indeg[v] += 1
            outdeg[u] += 1
        source = sorted(n for n in nodes if indeg[n] == 0)[0]
        sink = sorted(n for n in nodes if outdeg[n] == 0)[-1]
        edges2 = edges + [[source, node], [node, sink]]
        order = _kahn_sorted(nodes + [node], edges2)
        if not order:
            return None
        acc.append(order)
        stale.append(list(it["expected"]))
        items.append({"unit": it["unit"], "expected": order,
                      "graph": {"nodes": nodes + [node], "edges": edges2}})
    return items, {}, acc, stale


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
    ] + _topo_dir_probes(task)


def _topo_dir_probes(task: Task) -> List[Probe]:
    shifted = _topo_directional(task)
    if shifted is None:
        return []
    items, meta, acc, stale = shifted
    override = Task(family=task.family, task_id=task.task_id + "-dir",
                    prompt=task.prompt +
                    "\n[directional probe: one node and two edges added]",
                    items=items, meta=meta)
    return [
        _mk(task, 2, "directional_shift", "accept", acc,
            "a topological order recomputed after a node was inserted",
            "own Kahn pass on the shifted graph; the verifier must read it",
            operator="DIR", task_override=override),
        _mk(task, 3, "directional_shift", "reject", stale,
            "the order that covered the graph before the node existed",
            "it omits the new node, so it is not a permutation of the shifted nodes",
            operator="DIR", task_override=override),
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
_TEMPLATES: Dict[str, Dict[str, Any]] = {}


def _code_cases() -> Dict[str, List[List[Any]]]:
    """Read the public fixture case inputs once (task data, not a decision rule)."""
    if not _CASES:
        from .families.structural import _CODE_TEMPLATES  # fixture table only

        for t in _CODE_TEMPLATES:
            _CASES[t["name"]] = [list(c) for c in t["cases"]]
    return _CASES


def _code_templates() -> Dict[str, Dict[str, Any]]:
    """The fixture rows themselves (spec text, buggy source, case inputs)."""
    if not _TEMPLATES:
        from .families.structural import _CODE_TEMPLATES  # fixture table only

        for t in _CODE_TEMPLATES:
            _TEMPLATES[t["name"]] = {"spec": t["spec"], "buggy": t["buggy"],
                                     "sig": list(t["sig"]),
                                     "cases": [list(c) for c in t["cases"]]}
    return _TEMPLATES


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


#: Overfit tails appended to the independent ``_impl``.  Each is correct on every
#: visible fixture case and wrong on the held-out inputs in
#: ``structural._CODE_HOLDOUT``; that is what makes ``OVF`` measurable here rather
#: than merely asserted.  Thresholds are read off the *visible* case set only.
_CODE_OVF: Dict[str, List[Tuple[str, str]]] = {
    "running_max": [
        ("\ndef solve(nums):\n    if len(nums) > 3:\n        return []\n"
         "    return _impl(nums)\n",
         "empty list for any input longer than the largest visible case (3 items)"),
        ("\ndef solve(nums):\n    if sum(1 for x in nums if x > 0) > 2:\n"
         "        return []\n    return _impl(nums)\n",
         "empty list whenever more than two positive values occur (visible max is 2)"),
    ],
    "count_vowels": [
        ("\ndef solve(s):\n    if len(s) > 12:\n        return 0\n    return _impl(s)\n",
         "zero for any string longer than the longest visible case (12 chars)"),
        ("\ndef solve(s):\n    if sum(1 for ch in s.lower() if ch == 'a') > 3:\n"
         "        return 0\n    return _impl(s)\n",
         "zero whenever a string contains more than three 'a' characters (visible max is 3)"),
    ],
    "chunk": [
        ("\ndef solve(items, k):\n    if len(items) > 5:\n        return []\n"
         "    return _impl(items, k)\n",
         "empty list for any input longer than the largest visible case (5 items)"),
        ("\ndef solve(items, k):\n    if k > 3:\n        return []\n"
         "    return _impl(items, k)\n",
         "empty list for any chunk size above the largest visible k (3)"),
    ],
    "safe_div": [
        ("\ndef solve(a, b):\n    if len(str(abs(a))) > 2:\n        return None\n"
         "    return _impl(a, b)\n",
         "None for any numerator outside the visible digit range (at most 2 digits)"),
        ("\ndef solve(a, b):\n    if abs(a) > 10:\n        return None\n"
         "    return _impl(a, b)\n",
         "None for any numerator above the largest visible magnitude (10)"),
    ],
    "dedupe": [
        ("\ndef solve(xs):\n    if len(xs) > 5:\n        return []\n    return _impl(xs)\n",
         "empty list for any input longer than the largest visible case (5 items)"),
        ("\ndef solve(xs):\n    if (max(xs) if xs else 0) > 9:\n        return []\n"
         "    return _impl(xs)\n",
         "empty list for any element above the largest visible value (9)"),
    ],
}


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
    # Round 5 (directional): the task's spec is swapped for the next template in
    # the fixture table.  The verifier derives truth by executing the candidate
    # against that template's hidden cases, so an input change it cannot track
    # would show up here.  ids x09/x10 stay fixed whether or not heavy probes run.
    names = list(_code_templates())
    other = names[(names.index(name) + 1) % len(names)]
    tpl_b = _code_templates()[other]
    override = Task(
        family=task.family, task_id=task.task_id + "-dir",
        prompt=(f"Fix the function below so that it satisfies: {tpl_b['spec']}.  "
                "Return the full module source defining solve.\n\n" + tpl_b["buggy"]),
        items=[{"unit": f"t{i + 1}", "expected": None, "case_index": i}
               for i in range(len(tpl_b["cases"]))],
        meta={"template": other, "sig": tpl_b["sig"]})
    probes += [
        _mk(task, 9, "directional_shift", "accept", _code_impl(other)[1],
            f"independent correct implementation of the shifted spec ({other})",
            "own implementation of the new spec; the verifier must execute it "
            "against the new template's hidden cases",
            operator="DIR", task_override=override),
        _mk(task, 10, "directional_shift", "reject", alt_src,
            f"correct implementation of the *original* spec ({name}), submitted "
            f"after the task shifted to {other}: right answer to the old input",
            "the input changed, so the old correct answer must fail the new "
            "hidden cases", operator="DIR", task_override=override),
    ]
    # Two overfit variants per template: both reproduce the reference answer on
    # every *visible* case and degrade on held-out shapes.  They are written
    # against the independent implementation, so their passing half is not the
    # fixture source.  x11/x12 stay fixed across templates; x06 is retained as
    # the historic chunk-only probe.
    ovf_tails = _CODE_OVF[name]
    for j, (tail, note) in enumerate(ovf_tails, start=11):
        probes.append(_mk(task, j, "overfit_to_tests", "reject", impl + tail,
                          note, "rule keyed to the visible case shapes/sizes only; "
                                "fails on inputs outside that range",
                          operator="OVF"))
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
