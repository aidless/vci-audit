"""pass@k / pass^k calculator over N runs of a task suite.

The two numbers are different questions and are reported side by side:

``pass@k``
    *"if I sample k attempts, what is the chance at least one passes?"*
    Per task with ``n`` attempts and ``c`` of them passing, the unbiased
    estimator (Chen et al., 2021, *Evaluating Large Language Models Trained on
    Code*) is::

        pass@k = 1 - C(n - c, k) / C(n, k)

    averaged over tasks.  ``k > n`` is not estimable for that task.

``pass^k``
    *"if I sample k attempts, what is the chance all of them pass?"*
    Per task the unbiased estimator is::

        pass^k = C(c, k) / C(n, k)

    averaged over tasks.  This is the reliability number: a harness that is
    unstable across repeats shows a low ``pass^k`` even at high ``pass@1``.

At ``k = 1`` both reduce to the per-task pass rate, so ``pass@1`` is the mean
per-task success rate.  Attempts are never pooled across tasks: a task with
2 runs and a task with 8 runs contribute their own per-task estimate.

Accounting for timeouts and refusals
------------------------------------
Every attempt carries one of five statuses: ``pass``, ``fail``, ``timeout``,
``refusal``, ``error``.  Two accounting modes are computed **and reported
separately**, because the choice changes the number:

``as_failure`` (default)
    Every attempt is an attempt: ``timeout`` / ``refusal`` / ``error`` count as
    a failure.  This is the honest end-to-end success rate.
``exclude_nonattest``
    Drop attempts whose status is ``timeout``, ``refusal`` or ``error`` and
    recompute from the remaining ``pass`` / ``fail`` attempts.  This is a
    sensitivity check, not the headline: it answers "how much of the delta is
    infrastructure versus model behaviour?".  Tasks left with zero attempts are
    dropped from that mode.

Alignment and duplicates
------------------------
Attempts are grouped by ``task_id``; the ``(task_id, seed, run)`` triple must be
unique.  Duplicate triples mean the input was concatenated twice or two runs
were merged by mistake, so they raise :class:`ValueError` rather than being
silently deduplicated.  Different seeds for one task are legitimate
independent repetitions and are counted together; the result records how many
distinct seeds each task used so a caller can check that the intended seed set
was actually run.

Input
-----
::

    {"tasks": [{"task_id": "t1", "seed": 0,
                "runs": ["pass", "fail", "timeout"]}]}

or a flat list::

    [{"task_id": "t1", "seed": 0, "run": 0, "passed": true}, ...]

A bare boolean / ``"pass"`` / ``"fail"`` is accepted as an attempt outcome.
"""
import json
import math
import os
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

STATUSES = ("pass", "fail", "timeout", "refusal", "error")

STATUS_ALIASES = {
    "pass": "pass", "passed": "pass", "ok": "pass", "success": "pass",
    "correct": "pass", "true": "pass",
    "fail": "fail", "failed": "fail", "wrong": "fail", "incorrect": "fail",
    "false": "fail",
    "timeout": "timeout", "timed_out": "timeout", "timedout": "timeout",
    "refusal": "refusal", "refused": "refusal", "no_answer": "refusal",
    "error": "error", "crash": "error", "transport_error": "error",
}

NON_ATTEST = ("timeout", "refusal", "error")
MODES = ("as_failure", "exclude_nonattest")

DEFINITIONS = {
    "pass@k": "mean over tasks of 1 - C(n-c, k)/C(n, k); k>n not estimable",
    "pass^k": "mean over tasks of C(c, k)/C(n, k); k>n not estimable",
    "pass@1": "mean over tasks of c/n (full-credit pass only)",
    "n": "attempts for one task; c = attempts with status 'pass'",
    "as_failure": "timeout/refusal/error count as failures",
    "exclude_nonattest": "timeout/refusal/error attempts are dropped",
}


# ------------------------------------------------------------------ parsing
def _status_of(x: Any) -> str:
    if isinstance(x, bool):
        return "pass" if x else "fail"
    if isinstance(x, str):
        s = STATUS_ALIASES.get(x.strip().lower())
        if s is None:
            raise ValueError(f"unknown attempt status {x!r}; "
                             f"expected one of {', '.join(STATUSES)}")
        return s
    if isinstance(x, dict):
        for k in ("status", "outcome", "result"):
            if k in x:
                return _status_of(x[k])
        for k in ("passed", "ok", "success"):
            if k in x:
                return _status_of(bool(x[k]))
    raise ValueError(f"cannot read an attempt outcome from {x!r}")


def _expand(doc: Any) -> List[Dict[str, Any]]:
    """Normalise every accepted input shape to flat attempt records."""
    if isinstance(doc, list):
        rows = doc
    elif isinstance(doc, dict):
        if "tasks" in doc:
            rows = []
            for t in doc["tasks"]:
                for j, run in enumerate(t.get("runs", [])):
                    rec = {"task_id": t.get("task_id"), "seed": t.get("seed", 0),
                           "run": j}
                    if isinstance(run, dict) and "run" in run:
                        rec["run"] = run["run"]
                    rec["_outcome"] = run
                    rows.append(rec)
        else:
            rows = doc.get("attempts") or doc.get("records") or []
    else:
        raise ValueError("pass^k input must be a list or a mapping")

    out: List[Dict[str, Any]] = []
    auto: Dict[Tuple[Any, Any], int] = {}
    for r in rows:
        if not isinstance(r, dict):
            out.append({"task_id": None, "seed": 0, "run": 0,
                        "_outcome": r})
            continue
        task_id = r.get("task_id")
        seed = r.get("seed", 0)
        if "run" in r:
            run = r["run"]
        else:
            key = (task_id, seed)
            run = auto.get(key, 0)
            auto[key] = run + 1
        if "_outcome" in r:
            outcome = r["_outcome"]
        elif any(k in r for k in ("status", "outcome", "result", "passed", "ok",
                                  "success")):
            outcome = r
        else:
            raise ValueError(f"attempt {r!r} carries no outcome")
        out.append({"task_id": task_id, "seed": seed, "run": run,
                    "_outcome": outcome})
    return out


def load_attempts(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        if os.path.splitext(path)[1].lower() == ".jsonl":
            return [json.loads(line) for line in fh if line.strip()]
        return json.load(fh)


# -------------------------------------------------------------- combinatorics
def unbiased_pass_at_k(n: int, c: int, k: int) -> Optional[float]:
    """``1 - C(n-c, k) / C(n, k)`` or ``None`` when ``n < k``."""
    if k > n:
        return None
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def unbiased_pass_pow_k(n: int, c: int, k: int) -> Optional[float]:
    """``C(c, k) / C(n, k)`` or ``None`` when ``n < k``."""
    if k > n:
        return None
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)


# ------------------------------------------------------------------- compute
def _mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _percentile(xs: Sequence[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    idx = min(len(s) - 1, max(0, int(q * (len(s) - 1))))
    return s[idx]


def compute(doc: Any, k_max: Optional[int] = None, n_boot: int = 1000,
            seed: int = 0, alpha: float = 0.05) -> Dict[str, Any]:
    """Compute the ``pass@k`` / ``pass^k`` curves with bootstrap intervals."""
    attempts = _expand(doc)
    if not attempts:
        return {"ok": False, "reason": "no_attempts",
                "detail": "the document contains no attempts"}

    seen: Dict[Tuple[Any, Any, Any], int] = {}
    grouped: Dict[Any, List[Dict[str, Any]]] = {}
    counts = {s: 0 for s in STATUSES}
    for a in attempts:
        triple = (a["task_id"], a["seed"], a["run"])
        if triple in seen:
            raise ValueError(
                f"duplicate attempt {triple!r}: (task_id, seed, run) must be "
                "unique; two run files were probably merged twice")
        seen[triple] = 1
        status = _status_of(a["_outcome"])
        a["status"] = status
        counts[status] += 1
        grouped.setdefault(a["task_id"], []).append(a)

    empty = [t for t, runs in grouped.items() if not runs]
    if empty:
        raise ValueError(f"tasks with no attempts: {empty[:5]}")

    # Per task, per accounting mode: (n, c).
    stats: Dict[Any, Dict[str, Tuple[int, int]]] = {}
    seeds_per_task: Dict[Any, set] = {}
    for task_id, runs in grouped.items():
        n_all = len(runs)
        c_all = sum(1 for r in runs if r["status"] == "pass")
        kept = [r for r in runs if r["status"] not in NON_ATTEST]
        stats[task_id] = {
            "as_failure": (n_all, c_all),
            "exclude_nonattest": (len(kept),
                                  sum(1 for r in kept if r["status"] == "pass")),
        }
        seeds_per_task[task_id] = {r["seed"] for r in runs}

    max_runs = max(v["as_failure"][0] for v in stats.values())
    if k_max is None:
        k_max = max(1, min(max_runs, 10))
    k_max = int(k_max)

    task_ids = sorted(stats, key=lambda t: str(t))
    rng = random.Random(seed)

    curves: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for mode in MODES:
        at, pw = [], []
        for k in range(1, k_max + 1):
            vals_at, vals_pw = [], []
            for t in task_ids:
                n, c = stats[t][mode]
                a = unbiased_pass_at_k(n, c, k)
                p = unbiased_pass_pow_k(n, c, k)
                if a is None or p is None:
                    continue
                vals_at.append(a)
                vals_pw.append(p)
            at.append({"k": k, "value": _mean(vals_at),
                       "n_tasks": len(vals_at), "estimable": bool(vals_at)})
            pw.append({"k": k, "value": _mean(vals_pw),
                       "n_tasks": len(vals_pw), "estimable": bool(vals_pw)})

        # Bootstrap resamples tasks (the unit of generalisation), not runs.
        boots_at = {k: [] for k in range(1, k_max + 1)}
        boots_pw = {k: [] for k in range(1, k_max + 1)}
        for _ in range(max(1, int(n_boot))):
            sample = [rng.choice(task_ids) for _ in task_ids]
            for k in range(1, k_max + 1):
                va, vp = [], []
                for t in sample:
                    n, c = stats[t][mode]
                    a = unbiased_pass_at_k(n, c, k)
                    p = unbiased_pass_pow_k(n, c, k)
                    if a is None or p is None:
                        continue
                    va.append(a)
                    vp.append(p)
                if va:
                    boots_at[k].append(sum(va) / len(va))
                    boots_pw[k].append(sum(vp) / len(vp))
        for point in at:
            b = boots_at[point["k"]]
            point["ci"] = ([_percentile(b, alpha / 2), _percentile(b, 1 - alpha / 2)]
                           if b else None)
        for point in pw:
            b = boots_pw[point["k"]]
            point["ci"] = ([_percentile(b, alpha / 2), _percentile(b, 1 - alpha / 2)]
                           if b else None)
        curves[mode] = {"pass@k": at, "pass^k": pw}

    return {
        "ok": True,
        "n_tasks": len(task_ids),
        "n_attempts": len(attempts),
        "k_max": k_max,
        "max_runs_per_task": max_runs,
        "status_counts": counts,
        "run_counts": {"min": min(v["as_failure"][0] for v in stats.values()),
                       "max": max_runs,
                       "mean": sum(v["as_failure"][0] for v in stats.values())
                               / len(task_ids)},
        "seeds": {"per_task": {str(t): sorted(seeds_per_task[t]) for t in task_ids},
                  "consistent": len({tuple(sorted(seeds_per_task[t]))
                                    for t in task_ids}) <= 1},
        "curves": curves,
        "bootstrap": {"n_boot": int(n_boot), "seed": seed, "alpha": alpha},
        "definitions": DEFINITIONS,
        "notes": [
            "attempts are never pooled across tasks; each task contributes its "
            "own per-task estimate",
            "k > n is not estimable for that task and is excluded from that "
            "point (see n_tasks and estimable)",
            "'pass' means full-credit acceptance; partial credit is not a pass",
            "timeouts, refusals and transport errors are counted as failures in "
            "'as_failure' and dropped in 'exclude_nonattest'",
        ],
    }


def compute_file(path: str, k_max: Optional[int] = None, n_boot: int = 1000,
                 seed: int = 0, alpha: float = 0.05) -> Dict[str, Any]:
    return compute(load_attempts(path), k_max=k_max, n_boot=n_boot, seed=seed,
                   alpha=alpha)


def write_report(result: Dict[str, Any], out_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)


def format_summary(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"pass^k: {result['reason']}: {result.get('detail', '')}"
    lines = [f"tasks={result['n_tasks']}  attempts={result['n_attempts']}  "
             f"k_max={result['k_max']}  statuses={result['status_counts']}"]
    for mode in MODES:
        for metric in ("pass@k", "pass^k"):
            parts = []
            for p in result["curves"][mode][metric]:
                if not p["estimable"]:
                    parts.append(f"k={p['k']}:n/a")
                else:
                    ci = p["ci"] or [float("nan"), float("nan")]
                    parts.append(f"k={p['k']}:{p['value']:.3f}"
                                 f"[{ci[0]:.3f}-{ci[1]:.3f}]")
            lines.append(f"  {mode:18s} {metric:8s} " + "  ".join(parts))
    return "\n".join(lines)
