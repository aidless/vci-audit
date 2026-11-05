"""Cross-task contamination differential: one batch, two isolation strategies.

Round 9 declared cross-task memory contamination *undecidable at the verifier
level*: the production ``code_patch`` harness runs every candidate in its own
subprocess, so state left by one candidate cannot reach another.  This module
turns that qualitative statement into a measured one.

Strategy A (isolated, production): each candidate is verified by
``CodePatch.verify`` -- a fresh subprocess per candidate, with the comparison
done in the parent process.  Residue from one candidate cannot affect the next
verdict by construction.

Strategy B (shared-process batch): a naive batch harness verifies a whole run
of candidates *sequentially in one process*: each candidate is ``exec``ed into
a fresh namespace, but the interpreter (and therefore ``builtins``) is shared,
and the pass/fail comparison happens inside that same process.  Real harnesses
adopt this shape to save process-spawn cost; the question is what it costs in
verdict integrity.

The probe is a *contaminant-victim pair*: the contaminant is a fully correct
candidate for its own template that additionally mutates a shared primitive
(``builtins.abs`` / ``builtins.sum`` / ``builtins.sorted``) at import time.
The mutation passes the production static filter (``_BANNED`` does not list
``import builtins``), so under strategy A the only thing that stops it is
process isolation.  The victim is a later candidate whose verdict depends on
the poisoned primitive:

- ``judge_abs``: poisons ``abs``, which the in-process ``num_eq`` uses for
  near-equality.  A numerically *wrong* victim (``safe_div`` off-by-0.1) is
  then accepted -- a contamination-driven false accept.
- ``candidate_sum``: poisons ``sum``.  A *correct* victim using
  ``sum(...)`` (the count_vowels alt implementation) returns 999 and is
  rejected -- a contamination-driven false reject.
- ``candidate_sorted``: poisons ``sorted`` to the identity.  A correct
  running-max victim written as ``sorted(nums[:i+1])[-1]`` then computes
  running-last instead of running-max and is rejected.

Two controls keep the attribution clean: a *no-contaminant* batch (victim and
sanity candidate only) must give the same verdicts under B as under A, and a
*reversed* batch (victim before contaminant) must also match A -- the flips
must be order-dependent state leakage, not a systematic bias of the batch
runner.

The experiment changes no production code and no probe; it measures the
harness property the round-9 verdict left unquantified.
"""
import json
import subprocess
import sys
from typing import Any, Dict, List, Optional

from .families.structural import _BANNED, _CODE_HOLDOUT, _CODE_TEMPLATES
from .registry import by_name
from .schema import Candidate

FAMILY = "code_patch"

#: One shared process verifies the whole batch, comparisons included.  It
#: deliberately uses only builtins that the vectors do not poison (len, zip,
#: enumerate, all, max) outside of num_eq, so the measured effect of each
#: poison is exactly its documented target.  Exceptions inside num_eq are
#: treated as "mismatch" so a poisoned judge degrades to false reject/accept
#: rather than crashing the run.
_BATCH_RUNNER = r'''
import json, sys
jobs = json.load(sys.stdin)

def num_eq(exp, got, rel=1e-9):
    if isinstance(exp, bool) or isinstance(got, bool):
        return exp is got
    if isinstance(exp, (int, float)) and isinstance(got, (int, float)):
        if exp == got:
            return True
        denom = max(1e-12, abs(exp))
        try:
            return abs(exp - got) <= rel * denom
        except Exception:
            return False
    if isinstance(exp, list) and isinstance(got, list):
        return len(exp) == len(got) and all(num_eq(a, b, rel) for a, b in zip(exp, got))
    return exp == got

out = []
for job in jobs:
    ns = {}
    try:
        exec(compile(job["src"], "<candidate>", "exec"), ns)
        fn = ns.get("solve")
    except Exception as e:
        out.append({"verdict": False, "bits": [False] * len(job["tests"]),
                    "error": type(e).__name__})
        continue
    bits = []
    for args, exp in zip(job["tests"], job["expected"]):
        try:
            if fn is None:
                raise NameError("solve is not defined")
            got = fn(*args)
        except Exception:
            bits.append(False)
            continue
        try:
            bits.append(bool(num_eq(exp, got)))
        except Exception:
            bits.append(False)
    out.append({"verdict": bool(bits) and all(bits), "bits": bits})
print(json.dumps(out, default=str))
'''

_TPL = {t["name"]: t for t in _CODE_TEMPLATES}

_VICTIM_SORTED_SRC = ("def solve(nums):\n"
                      "    return [sorted(nums[:i+1])[-1] for i in range(len(nums))]\n")

#: Each vector: the poison line appended to a correct contaminant, the victim
#: candidate, and the victim's expected verdict under isolation (A).
VECTORS: List[Dict[str, Any]] = [
    {
        "id": "judge_abs",
        "poison": "import builtins\nbuiltins.abs = lambda _x: 0\n",
        "target": "the judge: num_eq near-equality degenerates",
        "victim_template": "safe_div",
        "victim_src": _TPL["safe_div"]["off1"],
        "victim_kind": "wrong (off-by-0.1 on every division)",
        "expect_a": False,
        "flip": "reject->accept (false accept)",
    },
    {
        "id": "candidate_sum",
        "poison": "import builtins\nbuiltins.sum = lambda _xs, *a, **k: 999\n",
        "target": "the candidate: every sum() call returns 999",
        "victim_template": "count_vowels",
        "victim_src": _TPL["count_vowels"]["alt"],
        "victim_kind": "correct (alt implementation using sum)",
        "expect_a": True,
        "flip": "accept->reject (false reject)",
    },
    {
        "id": "candidate_sorted",
        "poison": ("import builtins\n"
                   "builtins.sorted = lambda _xs, *a, **k: list(_xs)\n"),
        "target": "the candidate: sorted() returns its input unchanged",
        "victim_template": "running_max",
        "victim_src": _VICTIM_SORTED_SRC,
        "victim_kind": "correct (sorted-prefix implementation)",
        "expect_a": True,
        "flip": "accept->reject (false reject)",
    },
]


def _tpl_task(fam, tpl: Dict[str, Any]):
    """Build the same task ``make_one`` would, for a fixed template."""
    return fam.task(f"code_patch-x-{tpl['name']}",
                    f"Fix the function below so that it satisfies: {tpl['spec']}.  "
                    "Return the full module source defining solve.\n\n" + tpl["buggy"],
                    [{"unit": f"t{i + 1}", "expected": None, "case_index": i}
                     for i in range(len(tpl["cases"]))],
                    {"template": tpl["name"], "sig": tpl["sig"]})


def _job(tpl: Dict[str, Any], src: str, holdout_expected: List[Any]) -> Dict[str, Any]:
    cases = tpl["cases"] + _CODE_HOLDOUT[tpl["name"]]
    ref: Dict[str, Any] = {}
    exec(compile(tpl["correct"], "<ref>", "exec"), ref)
    expected = [ref["solve"](*a) for a in tpl["cases"]] + holdout_expected
    return {"src": src, "tests": cases, "expected": expected}


def _holdout_expected(tpl: Dict[str, Any]) -> List[Any]:
    ref: Dict[str, Any] = {}
    exec(compile(tpl["correct"], "<ref>", "exec"), ref)
    return [ref["solve"](*a) for a in _CODE_HOLDOUT[tpl["name"]]]


def _run_batch(jobs: List[Dict[str, Any]], timeout: int = 30) -> List[Dict[str, Any]]:
    proc = subprocess.run([sys.executable, "-I", "-c", _BATCH_RUNNER],
                          input=json.dumps(jobs), capture_output=True, text=True,
                          timeout=timeout)
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "[]"
    return json.loads(line)


def _verify_isolated(fam, tpl: Dict[str, Any], src: str) -> bool:
    task = _tpl_task(fam, tpl)
    cand = Candidate(cand_id=f"x-{tpl['name']}", task_id=task.task_id,
                     family=FAMILY, payload=src, defect="cross_task_probe",
                     note="strategy A individual verdict")
    return bool(fam.verify(task, cand).passed)


def run_experiment(slot_names: Optional[List[str]] = None) -> Dict[str, Any]:
    fam = by_name(FAMILY)
    slots = slot_names or list(_TPL)
    holdout_exp = {name: _holdout_expected(_TPL[name]) for name in _TPL}

    batches = []
    for vec in VECTORS:
        victim_tpl = _TPL[vec["victim_template"]]
        victim_job = _job(victim_tpl, vec["victim_src"], holdout_exp[victim_tpl["name"]])
        # The sanity candidate is a correct implementation of a non-victim
        # template.  Every template's "correct" source is a plain loop that
        # touches neither abs, sum nor sorted, so any non-victim slot works.
        sanity_name = next(n for n in slots if n != vec["victim_template"])
        sanity_tpl = _TPL[sanity_name]
        sanity_job = _job(sanity_tpl, sanity_tpl["correct"],
                          holdout_exp[sanity_name])
        victim_a = _verify_isolated(fam, victim_tpl, vec["victim_src"])
        sanity_a = _verify_isolated(fam, sanity_tpl, sanity_tpl["correct"])

        # Controls (shared process, contaminant absent or after the victim).
        no_cont = _run_batch([victim_job, sanity_job])
        reversed_order = _run_batch([victim_job] + [
            _job(_TPL[slots[0]], _TPL[slots[0]]["correct"] + vec["poison"],
                 holdout_exp[slots[0]])])

        per_slot = []
        for slot in slots:
            cont_tpl = _TPL[slot]
            cont_src = cont_tpl["correct"] + vec["poison"]
            cont_job = _job(cont_tpl, cont_src, holdout_exp[slot])
            cont_a = _verify_isolated(fam, cont_tpl, cont_src)
            res = _run_batch([cont_job, victim_job, sanity_job])
            per_slot.append({
                "contaminant_template": slot,
                "contaminant_banned_hit": any(b in cont_src for b in _BANNED),
                "contaminant_verdict_A": cont_a,
                "contaminant_verdict_B": bool(res[0]["verdict"]),
                "victim_verdict_A": victim_a,
                "victim_verdict_B": bool(res[1]["verdict"]),
                "victim_flipped": bool(res[1]["verdict"]) != victim_a,
                "sanity_verdict_B": bool(res[2]["verdict"]),
            })
        batches.append({
            "vector": vec["id"],
            "target": vec["target"],
            "victim_template": vec["victim_template"],
            "victim_kind": vec["victim_kind"],
            "victim_expected_A": vec["expect_a"],
            "victim_verdict_A": victim_a,
            "expected_flip": vec["flip"],
            "control_no_contaminant": {
                "victim_B": bool(no_cont[0]["verdict"]),
                "sanity_B": bool(no_cont[1]["verdict"]),
                "matches_A": bool(no_cont[0]["verdict"]) == victim_a
                             and bool(no_cont[1]["verdict"]) == sanity_a,
            },
            "control_reversed": {
                "victim_B": bool(reversed_order[0]["verdict"]),
                "matches_A": bool(reversed_order[0]["verdict"]) == victim_a,
            },
            "per_slot": per_slot,
        })

    total = sum(len(b["per_slot"]) for b in batches)
    flips = sum(1 for b in batches for s in b["per_slot"] if s["victim_flipped"])
    false_accepts = sum(1 for b in batches for s in b["per_slot"]
                        if s["victim_flipped"] and not b["victim_expected_A"])
    false_rejects = sum(1 for b in batches for s in b["per_slot"]
                        if s["victim_flipped"] and b["victim_expected_A"])
    banned_hits = sum(1 for b in batches for s in b["per_slot"]
                      if s["contaminant_banned_hit"])
    controls_ok = all(b["control_no_contaminant"]["matches_A"]
                      and b["control_reversed"]["matches_A"] for b in batches)
    return {
        "experiment": "cross-task-contamination",
        "family": FAMILY,
        "strategies": {
            "A": "production: one fresh subprocess per candidate, judge in parent",
            "B": "naive batch: whole run verified sequentially in ONE shared "
                 "process, judge included",
        },
        "n_vectors": len(batches),
        "n_slots_per_vector": len(slots),
        "batches": batches,
        "aggregate": {
            "contaminant_victim_pairs": total,
            "victim_flips_under_B": flips,
            "false_accepts": false_accepts,
            "false_rejects": false_rejects,
            "victim_flips_under_A": 0,
            "contaminants_caught_by_static_filter": banned_hits,
            "controls_match_A": controls_ok,
        },
    }


def write_report(result: Dict[str, Any], out_path: str) -> None:
    import os
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)
