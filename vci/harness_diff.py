"""Harness differential experiment: one task set, two execution strategies.

Strategy A is the round-3 production ``code_patch`` harness (``verify_legacy``):
every case is called once inside a single subprocess.  Strategy B runs the whole
suite *twice* in the same subprocess and rejects when the second pass disagrees
with the first.

Hypothesis under test (round-3 memo, section 8 item 4): the surviving
``STATE/x02`` leak -- correct for the first five calls, ``None`` afterwards --
is an artifact of A's process model (too few calls to trip the counter), not a
property any harness must have.  If so, B catches x02 and the other
history-dependent probes *without* flipping any accept-expected or aligned
verdict.  The experiment reports the flip matrix, per-strategy trust on the
non-aligned probes, the per-seed spread of the delta, and B's behaviour on the
aligned mutant set (where A and B should agree on every candidate).

Round 4 adopted strategy B (plus held-out cases) as ``CodePatch.verify``; this
module keeps A as ``verify_legacy`` so the differential remains reproducible.
"""
import json
import random
import statistics
from typing import Any, Callable, Dict, List

from . import adversarial
from . import metrics as M
from .audit import family_seed
from .registry import INDEX, by_name
from .schema import Candidate
from .util import pct

FAMILY = "code_patch"


def _probe_candidate(task, probe) -> Candidate:
    return Candidate(cand_id=probe.probe_id, task_id=task.task_id,
                     family=FAMILY, payload=probe.payload,
                     defect=probe.failure_class, note=probe.note)


def _run_probe_rows(fam, tasks, verify: Callable) -> List[Dict[str, Any]]:
    rows = []
    for i, task in enumerate(tasks):
        for probe in adversarial.probes_for(FAMILY, task, heavy=(i == 0)):
            verdict = verify(fam, task, _probe_candidate(task, probe))
            rows.append({
                "probe_id": probe.probe_id,
                "task_id": task.task_id,
                "operator": probe.operator,
                "expectation": probe.expectation,
                "label": probe.label or "observe",
                "defect": probe.failure_class,
                "passed": bool(verdict.passed),
                "score": float(verdict.score),
                "cost_ms": float(verdict.cost_ms),
            })
    return rows


def _op_metrics(rows) -> Dict[str, Any]:
    scored = [r for r in rows if r["label"] in ("correct", "incorrect")]
    op = M.operating_metrics(scored)
    return {"n": len(scored), "n_pos": int(op["n_pos"]), "n_neg": int(op["n_neg"]),
            "tpr": op["tpr"], "tnr": op["tnr"],
            "trust": M.trust_score(op) if op["n_pos"] and op["n_neg"] else None,
            "p95_ms": pct([r["cost_ms"] for r in scored], 0.95) if scored else 0.0}


def _flip_summary(rows_a, rows_b) -> Dict[str, Any]:
    by_id_b = {r["probe_id"]: r for r in rows_b}
    flips = {"A_pass_B_pass": 0, "A_pass_B_fail": 0,
             "A_fail_B_pass": 0, "A_fail_B_fail": 0}
    by_operator: Dict[str, Dict[str, int]] = {}
    for ra in rows_a:
        rb = by_id_b[ra["probe_id"]]
        key = f"A_{'pass' if ra['passed'] else 'fail'}_B_{'pass' if rb['passed'] else 'fail'}"
        flips[key] += 1
        bucket = by_operator.setdefault(ra["operator"], {k: 0 for k in flips})
        bucket[key] += 1
    return {"matrix": flips, "by_operator": by_operator}


def _x02_outcomes(rows) -> Dict[str, int]:
    hits = [r for r in rows if r["probe_id"].endswith("-x02")]
    return {"n": len(hits), "accepted": sum(1 for r in hits if r["passed"])}


def _aligned_agreement(fam, tasks) -> Dict[str, Any]:
    """Do A and B give the same verdict on the aligned mutant set?

    Every aligned candidate is a deterministic pure function of its input, so
    any disagreement here is a defect of strategy B (e.g. a false reject of a
    correct answer), not of the probe set.
    """
    n = 0
    disagree = []
    for task in tasks:
        rng = random.Random(0)  # mutate() draws are irrelevant to the payloads
        for cand in fam.mutate(task, rng):
            va = verify_a(fam, task, cand)
            vb = verify_b(fam, task, cand)
            n += 1
            if bool(va.passed) != bool(vb.passed):
                disagree.append({"cand_id": cand.cand_id, "defect": cand.defect,
                                 "A": bool(va.passed), "B": bool(vb.passed)})
    return {"n": n, "n_disagree": len(disagree), "disagreements": disagree[:20]}


def verify_a(fam, task, cand):
    return fam.verify_legacy(task, cand)


def verify_b(fam, task, cand):
    return fam.verify_twice(task, cand)


def run_differential(n_tasks: int = 25, seed: int = 0, n_seeds: int = 5) -> Dict[str, Any]:
    fam = by_name(FAMILY)
    idx = INDEX[FAMILY]
    per_seed = []
    pooled_a: List[Dict[str, Any]] = []
    pooled_b: List[Dict[str, Any]] = []
    for s in range(seed, seed + n_seeds):
        rng = random.Random(family_seed(s, idx))
        tasks = fam.generate(n_tasks, rng)
        rows_a = _run_probe_rows(fam, tasks, verify_a)
        rows_b = _run_probe_rows(fam, tasks, verify_b)
        pooled_a += rows_a
        pooled_b += rows_b
        per_seed.append({
            "seed": s,
            "n_probes": len(rows_a),
            "A": _op_metrics(rows_a),
            "B": _op_metrics(rows_b),
            "flips": _flip_summary(rows_a, rows_b)["matrix"],
            "x02": {"A": _x02_outcomes(rows_a), "B": _x02_outcomes(rows_b)},
        })

    rng0 = random.Random(family_seed(seed, idx))
    aligned = _aligned_agreement(fam, fam.generate(n_tasks, rng0))

    deltas = [row["B"]["trust"] - row["A"]["trust"]
              for row in per_seed
              if row["A"]["trust"] is not None and row["B"]["trust"] is not None]
    return {
        "experiment": "harness-differential",
        "family": FAMILY,
        "strategies": {
            "A": "single pass per case, one subprocess (production)",
            "B": "suite executed twice in-process; repeat must reproduce pass 1",
        },
        "probe_generator_version": adversarial.GENERATOR_VERSION,
        "n_tasks": n_tasks,
        "seeds": list(range(seed, seed + n_seeds)),
        "per_seed": per_seed,
        "pooled": {
            "A": _op_metrics(pooled_a),
            "B": _op_metrics(pooled_b),
            "flips": _flip_summary(pooled_a, pooled_b),
            "x02": {"A": _x02_outcomes(pooled_a), "B": _x02_outcomes(pooled_b)},
        },
        "aligned_agreement_seed0": aligned,
        "trust_delta_B_minus_A": {
            "per_seed": deltas,
            "mean": statistics.mean(deltas) if deltas else None,
            "sd": (statistics.stdev(deltas) if len(deltas) > 1 else None),
        },
        "probe_rows": {"A": pooled_a, "B": pooled_b},
    }


def write_report(result: Dict[str, Any], out_path: str) -> None:
    import os
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)
