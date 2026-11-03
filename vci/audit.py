"""Audit orchestration: seed tasks -> mutants -> verdicts -> VCI.

The whole run is a pure function of ``(seed, n_tasks, family set)``.  Nothing
uses wall-clock time except latency measurement, which is reported separately
and is the only hardware-dependent quantity (see README).
"""
import json
import platform
import random
import sys
import time
from typing import Any, Dict

from . import metrics as M
from .registry import FAMILIES, INDEX
from .schema import PARTIAL_DEFECT
from .util import pct

#: Fixed positions used by ``annotate`` so the blind sheet is reproducible.
ANNOTATE_PICKS = ("semantic_equivalent", "partial_k_minus_1")


def family_seed(seed: int, index: int) -> int:
    """A distinct, deterministic stream per family."""
    return int(seed) * 100003 + index * 97 + 11


def parse_j(note: str, k: int) -> int:
    if not note:
        return 0
    head = note.split("/", 1)[0].strip()
    try:
        return int(head)
    except ValueError:
        return 0


def collect(fam, n_tasks: int, seed: int):
    """Generate tasks and their mutants; return per-task record groups."""
    rng = random.Random(seed)
    groups = []
    for task in fam.generate(n_tasks, rng):
        recs = []
        for cand in fam.mutate(task, rng):
            verdict = fam.verify(task, cand)
            crashed = any(str(e.get("detail", "")).startswith("verifier exception")
                          for e in verdict.evidence)
            recs.append({
                "cand_id": cand.cand_id,
                "task_id": task.task_id,
                "defect": cand.defect,
                "note": cand.note,
                "label": "correct" if cand.is_correct else "incorrect",
                "passed": bool(verdict.passed),
                "score": float(verdict.score),
                "cost_ms": float(verdict.cost_ms),
                "crashed": crashed,
                "payload": cand.payload,
            })
        groups.append({"task": task, "records": recs})
    return groups


def _task_density(task, recs) -> float:
    k = task.n_items
    partials = [{"j": parse_j(r["note"], k), "score": r["score"]}
                for r in recs if r["defect"] == PARTIAL_DEFECT]
    return M.task_density(k, partials)


def _components(groups) -> Dict[str, float]:
    recs = [r for g in groups for r in g["records"]]
    op = M.operating_metrics(recs)
    trust = max(0.0, min(1.0, min(op["tpr"], op["tnr"], 1.0 - op["far90"])))
    costs = [r["cost_ms"] for r in recs]
    p95 = pct(costs, 0.95)
    cheap = M.cheapness(p95)
    dense = sum(_task_density(g["task"], g["records"]) for g in groups) / len(groups)
    return {
        "op": op, "trust": trust, "cheapness": cheap, "density": dense,
        "p95_ms": p95, "p50_ms": pct(costs, 0.5),
        "mean_ms": (sum(costs) / len(costs)) if costs else 0.0,
        "vci": M.vci(cheap, trust, dense),
    }


def _defect_table(recs) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for r in recs:
        row = out.setdefault(r["defect"], {"n": 0, "accepted": 0, "score_sum": 0.0})
        row["n"] += 1
        row["accepted"] += 1 if r["passed"] else 0
        row["score_sum"] += r["score"]
    for row in out.values():
        row["accept_rate"] = row["accepted"] / row["n"] if row["n"] else 0.0
        row["mean_score"] = row["score_sum"] / row["n"] if row["n"] else 0.0
        del row["accepted"]
        del row["score_sum"]
    return out


def _agreement(pairs):
    """Cohen's kappa for ``(human_or_gold_label, verifier_passed)`` pairs."""
    if not pairs:
        return {"value": 0.0, "n": 0, "po": 0.0}
    kappa, po = M.cohen_kappa([a for a, _ in pairs], [b for _, b in pairs])
    return {"value": kappa, "n": len(pairs), "po": po}


def _family_kappa(recs, labels) -> Dict[str, Any]:
    """Two independent agreement numbers.

    ``synthetic`` compares the verifier against the mutant generator's own
    labels; it is the only kappa available with no human in the loop, and it is
    an upper bound because ``selfcheck`` forces that agreement to be perfect.
    ``human`` compares the verifier against the blind adjudication sheet.
    """
    synth = _agreement([(r["label"] == "correct", r["passed"]) for r in recs])
    human = _agreement([(labels[r["cand_id"]], r["passed"]) for r in recs
                        if r["cand_id"] in labels])
    effective = human if human["n"] else synth
    return {
        "value": effective["value"],
        "n": effective["n"],
        "po": effective["po"],
        "source": "human" if human["n"] else "synthetic",
        "synthetic": synth,
        "human": human,
    }


def evaluate_family(fam, n_tasks: int, seed: int, n_boot: int, labels) -> Dict[str, Any]:
    groups = collect(fam, n_tasks, seed)
    comp = _components(groups)
    recs = [r for g in groups for r in g["records"]]
    op = comp["op"]
    kappa_info = _family_kappa(recs, labels)

    # Bootstrap over tasks: resample tasks with replacement, recompute every
    # component, and take the percentile interval of the resulting VCI.
    boot_rng = random.Random(seed ^ 0x5EED)
    boots = []
    for _ in range(n_boot):
        sample = [groups[boot_rng.randrange(len(groups))] for _ in range(len(groups))]
        boots.append(_components(sample)["vci"])
    boots.sort()
    ci = (boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1])

    verdict = M.reliability_verdict(dict(op, kappa=kappa_info["value"]))

    return {
        "family": fam.name,
        "domain": fam.domain,
        "task_shape": fam.task_shape,
        "premise": fam.premise,
        "scoring": fam.scoring,
        "item_unit": fam.item_unit,
        "n_tasks": len(groups),
        "n_candidates": len(recs),
        "units_per_task": pct([g["task"].n_items for g in groups], 0.5),
        "metrics": op,
        "cheapness": comp["cheapness"],
        "trust": comp["trust"],
        "density": comp["density"],
        "vci": comp["vci"],
        "vci_ci": [ci[0], ci[1]],
        "latency_ms": {"p50": comp["p50_ms"], "p95": comp["p95_ms"], "mean": comp["mean_ms"]},
        "per_defect": _defect_table(recs),
        "verifier_errors": sum(1 for r in recs if r["crashed"]),
        "reliable": verdict["reliable"],
        "unreliable_reasons": verdict["reasons"],
        "kappa": kappa_info,
        "_groups": groups,
    }


def _strip_private(fam_row):
    out = {k: v for k, v in fam_row.items() if not k.startswith("_")}
    return out


def _load_labels(path):
    """Human adjudication sheet: ``row_id,human_label`` (1/0, correct/wrong)."""
    import csv
    labels = {}
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                raw = (row.get("human_label") or "").strip().lower()
                if raw in ("1", "yes", "true", "correct", "pass"):
                    labels[row["row_id"]] = True
                elif raw in ("0", "no", "false", "wrong", "fail"):
                    labels[row["row_id"]] = False
    except FileNotFoundError:
        return {}
    return labels


def run_audit(families=None, n_tasks=25, seed=0, n_boot=500, labels_path=None,
              keep_raw=False, work_dir=None) -> Dict[str, Any]:
    fams = families or FAMILIES
    labels = _load_labels(labels_path) if labels_path else {}
    rows = []
    for fam in fams:
        idx = INDEX[fam.name]
        row = evaluate_family(fam, n_tasks, family_seed(seed, idx), n_boot, labels)
        row["seed"] = family_seed(seed, idx)
        rows.append(row)

    # Pooled numbers over every family, kept separate by label source.
    total = [r for row in rows for g in row["_groups"] for r in g["records"]]
    pooled = {
        "value": 0.0, "n": 0, "po": 0.0, "source": "none",
        "synthetic": _agreement([(r["label"] == "correct", r["passed"]) for r in total]),
        "human": _agreement([(labels[r["cand_id"]], r["passed"]) for r in total
                             if r["cand_id"] in labels]),
    }
    if pooled["human"]["n"]:
        pooled.update(pooled["human"], source="human")
    else:
        pooled.update(pooled["synthetic"], source="synthetic")

    # Sparse per-family sheets inherit the pooled human kappa so a single blind
    # pass over 40 rows can still be used, flagged as borrowed.
    for row in rows:
        if not row["kappa"]["human"]["n"] and pooled["human"]["n"]:
            row["kappa"]["value"] = pooled["human"]["value"]
            row["kappa"]["n"] = pooled["human"]["n"]
            row["kappa"]["po"] = pooled["human"]["po"]
            row["kappa"]["source"] = "pooled-human"
        verdict = M.reliability_verdict(dict(row["metrics"], kappa=row["kappa"]["value"]))
        row["reliable"] = verdict["reliable"]
        row["unreliable_reasons"] = verdict["reasons"]

    vcis = [r["vci"] for r in rows]
    med = pct(vcis, 0.5)
    med_ci = M.bootstrap_ci(vcis, "median", n_boot=n_boot, seed=seed)
    summary = {
        "vci_median": med,
        "vci_median_ci": list(med_ci),
        "vci_mean": sum(vcis) / len(vcis),
        "vci_min": min(vcis),
        "vci_max": max(vcis),
        "families_ge_0.7": sum(1 for v in vcis if v >= 0.7),
        "families_ge_0.5": sum(1 for v in vcis if v >= 0.5),
        "families_reliable": sum(1 for r in rows if r["reliable"]),
        "families_reliable_human_kappa": sum(
            1 for r in rows if r["reliable"] and r["kappa"]["human"]["n"]),
        "n_families": len(rows),
        "n_tasks_per_family": n_tasks,
        "n_candidates": sum(r["n_candidates"] for r in rows),
        "kappa_pooled": pooled,
    }

    manifest = {
        "vci_version": "0.1.0",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "seed": seed,
        "n_tasks": n_tasks,
        "n_boot": n_boot,
        "families": [f.name for f in fams],
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Only latency (cost_ms) is hardware dependent; every other number "
                "is a pure function of the seed and the family set.",
    }

    if keep_raw and work_dir:
        import os
        os.makedirs(work_dir, exist_ok=True)
        with open(os.path.join(work_dir, "candidates.jsonl"), "w", encoding="utf-8") as fh:
            for row in rows:
                for g in row["_groups"]:
                    for r in g["records"]:
                        fh.write(json.dumps(dict(r, family=row["family"]),
                                            ensure_ascii=False) + "\n")
        with open(os.path.join(work_dir, "tasks.jsonl"), "w", encoding="utf-8") as fh:
            for row in rows:
                for g in row["_groups"]:
                    t = g["task"]
                    fh.write(json.dumps({"family": row["family"], "task_id": t.task_id,
                                         "prompt": t.prompt,
                                         "units": t.units},
                                        ensure_ascii=False) + "\n")

    return {"manifest": manifest, "config": {
        "seed": seed, "n_tasks": n_tasks, "n_boot": n_boot,
        "cheap_ms": 20.0, "costly_ms": 500.0,
        "reliability_gate": {"tpr": 0.90, "tnr": 0.90, "far90": 0.20, "kappa": 0.60},
    }, "summary": summary, "families": [_strip_private(r) for r in rows]}


def annotation_sample(n_tasks=25, seed=0, families=None, per_family=2):
    """Blind adjudication rows: a paraphrase, a near-complete partial, a near-miss."""
    fams = families or FAMILIES
    per_family = max(1, min(3, int(per_family)))
    rows = []
    for fam in fams:
        idx = INDEX[fam.name]
        groups = collect(fam, n_tasks, family_seed(seed, idx))
        # Use the third task so the sample is not the same rows as the demo.
        g = groups[2 % len(groups)]
        recs = g["records"]
        picks = []
        for r in recs:
            if r["defect"] == "semantic_equivalent":
                picks.append(r)
                break
        partials = [r for r in recs if r["defect"] == PARTIAL_DEFECT]
        if per_family >= 2 and partials:
            picks.append(max(partials, key=lambda r: r["score"]))
        if per_family >= 3:
            for r in recs:
                if r["defect"] in ("boundary", "off_by_one"):
                    picks.append(r)
                    break
        for r in picks:
            rows.append({
                "row_id": r["cand_id"],
                "family": fam.name,
                "task_prompt": g["task"].prompt,
                "reference_answer": json.dumps(g["task"].units, ensure_ascii=False),
                "candidate": json.dumps(r["payload"], ensure_ascii=False, indent=1),
                "human_label": "",
            })
    return rows


def selfcheck(families=None, n_tasks=3, seed=7):
    """Report mutants that contradict their own label.

    A ``correct``/``semantic_equivalent`` candidate that fails means the verifier
    is too strict; a wrong candidate that passes means the mutant generator
    produced a legal answer by accident.  Both are bugs to fix, not results.
    """
    fams = families or FAMILIES
    problems = []
    for fam in fams:
        idx = INDEX[fam.name]
        groups = collect(fam, n_tasks, family_seed(seed, idx))
        for g in groups:
            for r in g["records"]:
                if r["label"] == "correct" and not r["passed"]:
                    problems.append((fam.name, r["task_id"], r["defect"],
                                     "valid answer rejected", r["score"]))
                elif r["label"] == "incorrect" and r["defect"] != PARTIAL_DEFECT and r["passed"]:
                    problems.append((fam.name, r["task_id"], r["defect"],
                                     "wrong answer accepted", r["score"]))
                elif r["defect"] == PARTIAL_DEFECT and r["score"] >= 1 - 1e-9:
                    problems.append((fam.name, r["task_id"], r["defect"],
                                     "partial scored as fully correct", r["score"]))
    return problems
