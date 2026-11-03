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
from typing import Any, Dict, Optional

from . import adversarial
from . import metrics as M
from .registry import FAMILIES, INDEX
from .schema import Candidate, PARTIAL_DEFECT
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


def _verdict_record(fam, task, cand, source, expectation=None) -> Dict[str, Any]:
    verdict = fam.verify(task, cand)
    crashed = any(str(e.get("detail", "")).startswith("verifier exception")
                  for e in verdict.evidence)
    return {
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
        "source": source,
        "expectation": expectation,
    }


def _probe_record(fam, task, probe) -> Dict[str, Any]:
    """Run one non-aligned probe.  Its label comes from ``expectation``."""
    cand = Candidate(cand_id=probe.probe_id, task_id=task.task_id,
                     family=fam.name, payload=probe.payload,
                     defect=probe.failure_class, note=probe.note)
    rec = _verdict_record(fam, task, cand, "non_aligned", probe.expectation)
    rec["label"] = probe.label or "observe"
    rec["basis"] = probe.basis
    return rec


def collect(fam, n_tasks: int, seed: int, with_probes: bool = True):
    """Generate tasks, aligned mutants and non-aligned probes; return groups.

    ``records`` are the round-1 aligned mutants (same code generated and judged
    them).  ``probes`` are round-2 candidates built by ``vci.adversarial``, whose
    expected treatment is decided outside the verifier.
    """
    rng = random.Random(seed)
    groups = []
    for i, task in enumerate(fam.generate(n_tasks, rng)):
        recs = [_verdict_record(fam, task, cand, "aligned")
                for cand in fam.mutate(task, rng)]
        probes = []
        if with_probes and adversarial.has_builder(fam.name):
            for probe in adversarial.probes_for(fam.name, task, heavy=(i == 0)):
                probes.append(_probe_record(fam, task, probe))
        groups.append({"task": task, "records": recs, "probes": probes})
    return groups


def _task_density(task, recs) -> float:
    k = task.n_items
    partials = [{"j": parse_j(r["note"], k), "score": r["score"]}
                for r in recs if r["defect"] == PARTIAL_DEFECT]
    return M.task_density(k, partials)


def _components(groups) -> Dict[str, Any]:
    aligned = [r for g in groups for r in g["records"]]
    probes = [r for g in groups for r in g.get("probes", [])]
    scored_probes = [r for r in probes if r["label"] in ("correct", "incorrect")]
    op_aligned = M.operating_metrics(aligned)
    op_non = M.operating_metrics(scored_probes)
    op_all = M.operating_metrics(aligned + scored_probes)
    trust_aligned = M.trust_score(op_aligned)
    trust_non = M.trust_score(op_non) if op_non["n_pos"] and op_non["n_neg"] else trust_aligned
    # Trust is limited by the weaker evidence regime: a verifier that looks
    # perfect on self-generated mutants but leaks on independently built ones
    # is only as trustworthy as the stress test shows.
    trust = min(trust_aligned, trust_non)
    costs = [r["cost_ms"] for r in aligned]
    probe_costs = [r["cost_ms"] for r in scored_probes]
    p95 = pct(costs, 0.95)
    cheap = M.cheapness(p95)
    probe_p95 = pct(probe_costs, 0.95) if probe_costs else 0.0
    dense = sum(_task_density(g["task"], g["records"]) for g in groups) / len(groups)
    return {
        "op": op_all,
        "op_aligned": op_aligned,
        "op_non_aligned": op_non,
        "trust": trust,
        "trust_aligned": trust_aligned,
        "trust_non_aligned": trust_non,
        "cheapness": cheap,
        "density": dense,
        "p95_ms": p95,
        "p50_ms": pct(costs, 0.5),
        "mean_ms": (sum(costs) / len(costs)) if costs else 0.0,
        "probe_p95_ms": probe_p95,
        "vci": M.vci(cheap, trust, dense),
        "vci_aligned": M.vci(cheap, trust_aligned, dense),
        "vci_non_aligned": M.vci(cheap, trust_non, dense),
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


def _agreement(pairs, n_boot=0, seed=0):
    """Cohen's kappa for ``(gold_label, verifier_passed)`` pairs, with a CI."""
    if not pairs:
        return {"value": 0.0, "n": 0, "po": 0.0, "ci": [0.0, 1.0]}
    kappa, po = M.cohen_kappa([a for a, _ in pairs], [b for _, b in pairs])
    ci = (M.bootstrap_kappa([a for a, _ in pairs], [b for _, b in pairs],
                            n_boot=n_boot, seed=seed) if n_boot else (0.0, 1.0))
    return {"value": kappa, "n": len(pairs), "po": po, "ci": [ci[0], ci[1]]}


def _family_kappa(recs, probes, labels, retest=None, n_boot=0, seed=0) -> Dict[str, Any]:
    """Three agreement numbers, never merged into one headline.

    ``synthetic`` compares the verifier against the mutant generator's own
    labels.  It is an upper bound by construction (round-1 selfcheck forces a
    perfect match) and is therefore *not* a substitute for human agreement.
    ``human`` compares the verifier against blind adjudication rows
    (``annotations/labels.csv``) and is absent (``n == 0``) until a human labels.
    ``stability`` compares the same human against a second, re-ordered pass
    (``annotations/labels_retest.csv``): it measures the annotator, not the
    verifier.
    ``oracle_non_aligned`` compares the verifier against the independent probe
    labels -- an independent judge, still not a human.
    """
    synth = _agreement([(r["label"] == "correct", r["passed"]) for r in recs],
                       n_boot=n_boot, seed=seed)
    scored = [r for r in recs + probes if r["cand_id"] in labels
              and labels[r["cand_id"]]["value"] is not None]
    human = _agreement([(labels[r["cand_id"]]["value"], r["passed"]) for r in scored],
                       n_boot=n_boot, seed=seed + 1)
    human["n_undecidable"] = sum(1 for r in recs + probes
                                 if r["cand_id"] in labels
                                 and labels[r["cand_id"]]["value"] is None)
    oracle = _agreement([(r["label"] == "correct", r["passed"]) for r in probes
                         if r["label"] in ("correct", "incorrect")],
                        n_boot=n_boot, seed=seed + 2)
    shared = sorted(set(labels) & set(retest or {}))
    stab_pairs = [(labels[r]["value"], retest[r]["value"]) for r in shared
                  if labels[r]["value"] is not None
                  and (retest or {})[r]["value"] is not None]
    stability = (_agreement(stab_pairs, n_boot=n_boot, seed=seed + 3)
                 if stab_pairs else {"value": None, "n": 0, "po": 0.0,
                                     "ci": [0.0, 1.0]})
    stability["source"] = "human-test-retest"
    effective = human if human["n"] else synth
    return {
        "value": effective["value"],
        "n": effective["n"],
        "po": effective["po"],
        "ci": effective["ci"],
        "source": "human" if human["n"] else "synthetic",
        "human": human,
        "synthetic": dict(synth, source="synthetic-upper-bound"),
        "oracle_non_aligned": dict(oracle, source="independent-probe-oracle"),
        "stability": stability,
    }


def _failure_table(probes) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for cls in adversarial.FAILURE_CLASSES:
        rs = [r for r in probes if r["defect"] == cls]
        if not rs:
            continue
        op = M.operating_metrics(rs)
        if op["n_pos"] and op["n_neg"]:
            trust: Optional[float] = M.trust_score(op)
        elif op["n_neg"]:
            trust = op["tnr"]
        elif op["n_pos"]:
            trust = op["tpr"]
        else:
            trust = None
        out[cls] = {
            "n": len(rs),
            "n_pos": int(op["n_pos"]),
            "n_neg": int(op["n_neg"]),
            "n_observe": sum(1 for r in rs if r["label"] == "observe"),
            "tpr": op["tpr"],
            "tnr": op["tnr"],
            "far90": op["far90"],
            "accept_rate": (sum(1 for r in rs if r["passed"]
                                and r["label"] in ("correct", "incorrect")) /
                            max(1, op["n_pos"] + op["n_neg"])),
            "trust": trust,
        }
    return out


def evaluate_family(fam, n_tasks: int, seed: int, n_boot: int, labels,
                    retest=None) -> Dict[str, Any]:
    groups = collect(fam, n_tasks, seed)
    comp = _components(groups)
    recs = [r for g in groups for r in g["records"]]
    probes = [r for g in groups for r in g.get("probes", [])]
    op_aligned = comp["op_aligned"]
    op_non = comp["op_non_aligned"]
    kappa_info = _family_kappa(recs, probes, labels or {}, retest,
                               n_boot=n_boot, seed=seed)

    # Bootstrap over tasks: resample tasks with replacement, recompute every
    # component, and take the percentile interval of the resulting VCI.
    boot_rng = random.Random(seed ^ 0x5EED)
    boots = []
    for _ in range(n_boot):
        sample = [groups[boot_rng.randrange(len(groups))] for _ in range(len(groups))]
        boots.append(_components(sample)["vci"])
    boots.sort()
    ci = (boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1])

    verdict = M.reliability_verdict(dict(op_aligned, kappa=kappa_info["value"]))
    verdict_non = (M.reliability_verdict(dict(op_non, kappa=kappa_info["value"]))
                   if op_non["n_pos"] and op_non["n_neg"] else
                   {"reliable": None, "reasons": ["no non-aligned samples"]})

    human_backed = kappa_info["source"] == "human" and kappa_info["human"]["n"] > 0
    core = bool(comp["vci"] >= 0.7 and comp["trust"] >= 0.9 and comp["density"] > 0)

    return {
        "family": fam.name,
        "domain": fam.domain,
        "task_shape": fam.task_shape,
        "premise": fam.premise,
        "scoring": fam.scoring,
        "item_unit": fam.item_unit,
        "n_tasks": len(groups),
        "n_candidates": len(recs),
        "n_probes": len(probes),
        "n_probes_scored": sum(1 for r in probes if r["label"] in ("correct", "incorrect")),
        "n_probes_observe": sum(1 for r in probes if r["label"] == "observe"),
        "units_per_task": pct([g["task"].n_items for g in groups], 0.5),
        "metrics": op_aligned,
        "metrics_aligned": op_aligned,
        "metrics_non_aligned": op_non,
        "metrics_combined": comp["op"],
        "per_failure_class": _failure_table(probes),
        "cheapness": comp["cheapness"],
        "trust": comp["trust"],
        "trust_aligned": comp["trust_aligned"],
        "trust_non_aligned": comp["trust_non_aligned"],
        "density": comp["density"],
        "vci": comp["vci"],
        "vci_aligned": comp["vci_aligned"],
        "vci_non_aligned": comp["vci_non_aligned"],
        "vci_ci": [ci[0], ci[1]],
        "latency_ms": {"p50": comp["p50_ms"], "p95": comp["p95_ms"], "mean": comp["mean_ms"]},
        "probe_latency_ms": {"p95": comp["probe_p95_ms"]},
        "per_defect": _defect_table(recs),
        "verifier_errors": sum(1 for r in recs if r["crashed"]),
        "probe_errors": sum(1 for r in probes if r["crashed"]),
        "reliable": verdict["reliable"],
        "reliable_non_aligned": verdict_non["reliable"],
        "unreliable_reasons": verdict["reasons"],
        "unreliable_reasons_non_aligned": verdict_non["reasons"],
        "kappa": kappa_info,
        "core_eligible": core,
        "core_human_backed": bool(core and human_backed),
        "_groups": groups,
    }


def _strip_private(fam_row):
    out = {k: v for k, v in fam_row.items() if not k.startswith("_")}
    return out


def _load_label_rows(path) -> Dict[str, Dict[str, Any]]:
    """Full adjudication sheet: keeps ``undecidable`` rows instead of dropping them."""
    import csv
    labels: Dict[str, Dict[str, Any]] = {}
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                raw = (row.get("human_label") or "").strip().lower()
                rid = (row.get("row_id") or "").strip()
                if not rid:
                    continue
                if raw in ("1", "yes", "true", "correct", "pass", "y"):
                    value: Any = True
                elif raw in ("0", "no", "false", "wrong", "fail", "n"):
                    value = False
                elif raw in ("s", "undecidable", "?", "unknown", "skip"):
                    value = None
                else:
                    continue
                labels[rid] = {"value": value, "raw": raw}
    except FileNotFoundError:
        return {}
    return labels


def _load_labels(path):
    """Human adjudication sheet: ``row_id,human_label`` (1/0, correct/wrong).

    Returns ``row_id -> bool`` for the decided rows; ``undecidable`` rows are
    kept by :func:`_load_label_rows` and excluded from kappa (but counted).
    """
    return {rid: v["value"] for rid, v in _load_label_rows(path).items()
            if v["value"] is not None}


def run_audit(families=None, n_tasks=25, seed=0, n_boot=500, labels_path=None,
              labels_retest_path=None, keep_raw=False,
              work_dir=None) -> Dict[str, Any]:
    fams = families or FAMILIES
    labels = _load_label_rows(labels_path) if labels_path else {}
    retest = _load_label_rows(labels_retest_path) if labels_retest_path else {}
    rows = []
    for fam in fams:
        idx = INDEX[fam.name]
        row = evaluate_family(fam, n_tasks, family_seed(seed, idx), n_boot,
                              labels, retest)
        row["seed"] = family_seed(seed, idx)
        rows.append(row)

    # Pooled numbers over every family, kept separate by label source.
    total = [r for row in rows for g in row["_groups"] for r in g["records"]]
    total_probes = [r for row in rows for g in row["_groups"] for r in g["probes"]]
    pooled = _family_kappa(total, total_probes, labels, retest,
                           n_boot=n_boot, seed=seed)
    if pooled["source"] == "synthetic" and pooled["human"]["n"] == 0:
        pooled["source"] = "synthetic (no human labels yet)"

    # Sparse per-family sheets inherit the pooled human kappa so a single blind
    # pass over 60 rows can still be used, flagged as borrowed.
    for row in rows:
        if not row["kappa"]["human"]["n"] and pooled["human"]["n"]:
            row["kappa"]["value"] = pooled["human"]["value"]
            row["kappa"]["n"] = pooled["human"]["n"]
            row["kappa"]["po"] = pooled["human"]["po"]
            row["kappa"]["ci"] = pooled["human"]["ci"]
            row["kappa"]["source"] = "pooled-human"
        verdict = M.reliability_verdict(dict(row["metrics"], kappa=row["kappa"]["value"]))
        row["reliable"] = verdict["reliable"]
        row["unreliable_reasons"] = verdict["reasons"]
        row["core_eligible"] = bool(row["vci"] >= 0.7 and row["trust"] >= 0.9
                                    and row["density"] > 0)
        row["core_human_backed"] = bool(
            row["core_eligible"] and row["kappa"]["source"] in ("human", "pooled-human")
            and row["kappa"]["human"]["n"])

    vcis = [r["vci"] for r in rows]
    vcis_aligned = [r["vci_aligned"] for r in rows]
    med = pct(vcis, 0.5)
    med_ci = M.bootstrap_ci(vcis, "median", n_boot=n_boot, seed=seed)
    med_aligned = pct(vcis_aligned, 0.5)
    med_aligned_ci = M.bootstrap_ci(vcis_aligned, "median", n_boot=n_boot, seed=seed)
    class_pool = total_probes
    pooled_classes = _failure_table(class_pool)
    summary = {
        "vci_median": med,
        "vci_median_ci": list(med_ci),
        "vci_median_aligned": med_aligned,
        "vci_median_aligned_ci": list(med_aligned_ci),
        "vci_mean": sum(vcis) / len(vcis),
        "vci_min": min(vcis),
        "vci_max": max(vcis),
        "families_ge_0.7": sum(1 for v in vcis if v >= 0.7),
        "families_ge_0.5": sum(1 for v in vcis if v >= 0.5),
        "families_ge_0.7_aligned": sum(1 for v in vcis_aligned if v >= 0.7),
        "families_reliable": sum(1 for r in rows if r["reliable"]),
        "families_reliable_human_kappa": sum(
            1 for r in rows if r["reliable"] and r["kappa"]["human"]["n"]),
        "core_provisional": [r["family"] for r in rows if r["core_eligible"]],
        "core_human_backed": [r["family"] for r in rows if r["core_human_backed"]],
        "trust_median_aligned": pct([r["trust_aligned"] for r in rows], 0.5),
        "trust_median_non_aligned": pct([r["trust_non_aligned"] for r in rows], 0.5),
        "n_families": len(rows),
        "n_tasks_per_family": n_tasks,
        "n_candidates": sum(r["n_candidates"] for r in rows),
        "n_probes": sum(r["n_probes"] for r in rows),
        "n_probes_scored": sum(r["n_probes_scored"] for r in rows),
        "pooled_failure_classes": pooled_classes,
        "kappa_pooled": pooled,
        "kappa_sources": {
            "effective": pooled["source"],
            "human_rows": pooled["human"]["n"],
            "human_undecidable": pooled["human"]["n_undecidable"],
            "retest_rows": pooled["stability"]["n"],
            "synthetic_upper_bound": pooled["synthetic"]["value"],
            "human": pooled["human"]["value"] if pooled["human"]["n"] else None,
            "stability": pooled["stability"]["value"],
        },
    }

    manifest = {
        "vci_version": "0.2.0",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "seed": seed,
        "n_tasks": n_tasks,
        "n_boot": n_boot,
        "families": [f.name for f in fams],
        "labels_path": labels_path if labels else None,
        "labels_retest_path": labels_retest_path if retest else None,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Only latency (cost_ms) is hardware dependent; every other number "
                "is a pure function of the seed, the family set and the label sheets.",
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
        with open(os.path.join(work_dir, "probes.jsonl"), "w", encoding="utf-8") as fh:
            for row in rows:
                for g in row["_groups"]:
                    for r in g["probes"]:
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


def annotation_sample(n_tasks=25, seed=0, families=None, per_family=3):
    """Blind adjudication rows: aligned paraphrase, near-complete partial, probe.

    The sheet carries only ``row_id``, ``family``, the task prompt, the unit
    names and the candidate payload.  It deliberately omits ``defect``,
    ``failure_class``, ``expectation`` and the reference values: the annotator
    must not be able to read the true label off the screen.
    """
    fams = families or FAMILIES
    per_family = max(1, min(4, int(per_family)))
    rows = []
    for fam in fams:
        idx = INDEX[fam.name]
        groups = collect(fam, n_tasks, family_seed(seed, idx))
        # Use the third task so the sample is not the same rows as the demo.
        g = groups[2 % len(groups)]
        recs = g["records"]
        probes = g.get("probes", [])
        picks = []
        for r in recs:
            if r["defect"] == "semantic_equivalent":
                picks.append(r)
                break
        partials = [r for r in recs if r["defect"] == PARTIAL_DEFECT]
        if per_family >= 2 and partials:
            picks.append(max(partials, key=lambda r: r["score"]))
        if per_family >= 3:
            # Prefer a semantic-equivalence or ambiguity probe: these are the
            # cases where a strict verifier and a human are most likely to split.
            preferred = sorted(probes, key=lambda r: (
                r["defect"] not in ("semantic_equivalent", "spec_ambiguity"),
                r["defect"] not in ("hardcoded_expected", "overfit_to_tests"),
                r["cand_id"]))
            if preferred:
                picks.append(preferred[0])
        if per_family >= 4:
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
