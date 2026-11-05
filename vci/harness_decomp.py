"""Harness differential decomposer.

Given **one benchmark** and **one model** evaluated under **two harnesses**, this
module splits the observed difference in task-level outcome into the four
mechanisms a harness can change:

=============  ==========================================================
factor         what the per-task record must say
=============  ==========================================================
``state``      ``state_retained``: is reasoning/scratchpad state kept across
               the task (or across repeated executions)?
``compaction`` ``compaction_events``: how many times context was compacted.
``tool``       ``tool_sig`` / ``tool_calls`` / ``tool_errors``: what the
               execution layer saw, e.g. the payload envelope that reached the
               runner.
``retry``      ``retries``: how many extra attempts the budget allowed.
=============  ==========================================================

What this *is*: a **budgeted attribution**.  The total delta is

    delta = mean(b) - mean(a) = sum_i (b_i - a_i) / N

so every task contributes ``(b_i - a_i) / N`` and the buckets below sum to the
total delta exactly.  A task is charged to a named source when **exactly one**
mechanism differs between the two harness records; to ``ambiguous`` when two or
more differ; to ``unexplained`` when none differ.

What this is **not**: a causal decomposition.  With two runs and no ablation
arms, observing that task ``t`` changed while factor ``X`` also changed does
not prove ``X`` caused the change.  Read the named buckets as *where to look
next*, and run a third arm that toggles only ``X`` to confirm.  The report
carries this assumption verbatim under ``assumption``.

Degraded input is refused rather than guessed: a document that carries only
aggregate scores (or per-task outcomes without mechanism flags) returns
``decomposable: False`` with an explicit ``reason`` and the observed delta.

Input
-----
Combined JSON document (one file, both harnesses)::

    {"benchmark": "...", "model": "...",
     "harness_a": "A", "harness_b": "B",
     "tasks": [{"task_id": "t1", "seed": 0,
                "a": {"passed": true,  "tool_sig": "json_list"},
                "b": {"passed": false, "tool_sig": "joined_source"}}]}

Two-run JSON/CSV files (one harness each, aligned on ``task_id``)::

    {"harness": "A", "records": [{"task_id": "t1", "passed": true, ...}]}

CSV columns are ``task_id, seed, a_passed, b_passed, a_<factor>, b_<factor>``.

``score`` (0..1) is used when present, otherwise ``passed`` (full credit).
"""
import csv
import json
import os
from typing import Any, Dict, List, Optional, Tuple

FACTORS = ("state", "compaction", "tool", "retry")

#: Accepted spellings for each mechanism.  A factor is compared only when both
#: harness records carry at least one of its fields.
FACTOR_FIELDS: Dict[str, Tuple[str, ...]] = {
    "state": ("state_retained", "state_kept", "reasoning_state", "state"),
    "compaction": ("compaction_events", "compactions", "context_compaction",
                   "compaction"),
    "tool": ("tool_sig", "tool_calls", "tool_errors", "tool_exec", "tool"),
    "retry": ("retries", "retries_used", "retry_count", "retry"),
}

REQUIRED = [
    "per-task outcomes for both harnesses (passed or score)",
    "at least one per-task mechanism flag on both sides "
    f"({', '.join(FACTORS)})",
]

_TRUTHY = {"1", "true", "yes", "y", "t"}
_FALSY = {"0", "false", "no", "n", "f"}


# ------------------------------------------------------------------- loading
def _parse_cell(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        low = s.lower()
        if low in _TRUTHY:
            return True
        if low in _FALSY:
            return False
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            return s
    return v


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_csv(path: str) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append({k: _parse_cell(v) for k, v in row.items() if k})
    return {"records": rows, "source": path}


def load_document(path: str) -> Any:
    """Load a JSON or CSV input document (CSV is treated as a record list)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return _load_csv(path)
    return _load_json(path)


# ------------------------------------------------------------------ normalise
def _value(side: Dict[str, Any]) -> Optional[float]:
    """Outcome of one side: ``score`` if present, else ``passed`` -> 0/1."""
    if side is None:
        return None
    if side.get("score") is not None:
        try:
            return float(side["score"])
        except (TypeError, ValueError):
            return None
    if side.get("passed") is not None:
        return 1.0 if bool(side["passed"]) else 0.0
    return None


def _flags(side: Dict[str, Any]) -> Dict[str, Tuple[Any, ...]]:
    out: Dict[str, Tuple[Any, ...]] = {}
    for factor, names in FACTOR_FIELDS.items():
        vals = tuple(side[n] for n in names if n in side and side[n] is not None)
        if vals:
            out[factor] = vals
    return out


def _diff_factors(fa: Dict[str, Tuple[Any, ...]],
                  fb: Dict[str, Tuple[Any, ...]]) -> List[str]:
    """Factors that are *measured on both sides* and differ."""
    out = []
    for factor in FACTORS:
        if factor in fa and factor in fb and fa[factor] != fb[factor]:
            out.append(factor)
    return out


def _key(task_id: Optional[str], seed: Any) -> Tuple[Any, Any]:
    return (task_id, seed)


def _label(task_id: Any, seed: Any) -> str:
    if seed in (None, 0, "0"):
        return str(task_id)
    return f"{task_id}@{seed}"


def _aggregate_of(doc: Any) -> Optional[Dict[str, float]]:
    """Pull an aggregate-score pair out of a document, if one is given."""
    if not isinstance(doc, dict):
        return None
    agg = doc.get("aggregate")
    if isinstance(agg, dict) and ("a" in agg or "b" in agg):
        try:
            return {"a": float(agg.get("a")), "b": float(agg.get("b"))}
        except (TypeError, ValueError):
            return None
    if "a_score" in doc and "b_score" in doc:
        try:
            return {"a": float(doc["a_score"]), "b": float(doc["b_score"])}
        except (TypeError, ValueError):
            return None
    return None


def _side_from_columns(row: Dict[str, Any], prefix: str) -> Optional[Dict[str, Any]]:
    """Rebuild one harness side from flat CSV columns (``a_passed`` -> ``passed``)."""
    side = {}
    for k, v in row.items():
        if isinstance(k, str) and k.startswith(prefix) and v is not None:
            side[k[len(prefix):]] = v
    return side or None


def _pairs_from_document(doc: Any) -> Tuple[List[Tuple[Any, Dict, Dict]], Dict[str, Any]]:
    """Normalise a combined document to ``[(key, side_a, side_b)]``."""
    meta: Dict[str, Any] = {}
    pairs: List[Tuple[Any, Dict, Dict]] = []
    if isinstance(doc, list):
        rows = doc
    elif isinstance(doc, dict):
        for k in ("benchmark", "model", "harness_a", "harness_b", "note"):
            if doc.get(k) is not None:
                meta[k] = doc[k]
        rows = doc.get("tasks") or doc.get("records") or []
    else:
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        seed = row.get("seed", 0)
        side_a = row.get("a") if isinstance(row.get("a"), dict) else \
            _side_from_columns(row, "a_")
        side_b = row.get("b") if isinstance(row.get("b"), dict) else \
            _side_from_columns(row, "b_")
        if side_a is None or side_b is None:
            continue
        pairs.append((_key(row.get("task_id"), seed), side_a, side_b))
    return pairs, meta


def _pairs_from_two_runs(doc_a: Any, doc_b: Any) -> Tuple[List, Dict[str, Any]]:
    """Align two single-harness documents by ``(task_id, seed)``."""
    meta: Dict[str, Any] = {}

    def rows_of(doc):
        if isinstance(doc, list):
            return doc
        if isinstance(doc, dict):
            return doc.get("records") or doc.get("tasks") or []
        return []

    for doc in (doc_a, doc_b):
        if isinstance(doc, dict):
            for k in ("benchmark", "model", "note"):
                if doc.get(k) is not None and k not in meta:
                    meta[k] = doc[k]

    side_a = {_key(r.get("task_id"), r.get("seed", 0)): r
              for r in rows_of(doc_a) if isinstance(r, dict)}
    side_b = {_key(r.get("task_id"), r.get("seed", 0)): r
              for r in rows_of(doc_b) if isinstance(r, dict)}
    names_a = doc_a.get("harness") if isinstance(doc_a, dict) else None
    names_b = doc_b.get("harness") if isinstance(doc_b, dict) else None
    if names_a:
        meta["harness_a"] = names_a
    if names_b:
        meta["harness_b"] = names_b
    keys = [k for k in side_a if k in side_b]
    pairs = [(k, side_a[k], side_b[k]) for k in keys]
    meta["n_tasks_a"] = len(side_a)
    meta["n_tasks_b"] = len(side_b)
    meta["n_unmatched"] = len(set(side_a) ^ set(side_b))
    return pairs, meta


# ------------------------------------------------------------------- analyse
def _bucket() -> Dict[str, Any]:
    return {"n_tasks": 0, "delta": 0.0}


def decompose(doc_a: Any, doc_b: Any = None, top_n: int = 10) -> Dict[str, Any]:
    """Decompose the score difference between harness A and harness B.

    ``decompose(combined_document)`` or ``decompose(run_a, run_b)``.
    """
    if doc_b is None:
        pairs, meta = _pairs_from_document(doc_a)
        agg = _aggregate_of(doc_a)
    else:
        pairs, meta = _pairs_from_two_runs(doc_a, doc_b)
        agg_a, agg_b = _aggregate_of(doc_a), _aggregate_of(doc_b)
        agg = ({"a": agg_a["a"], "b": agg_b["b"]}
               if (agg_a and agg_b) else None)

    aligned = [(k, a, b) for (k, a, b) in pairs
               if _value(a) is not None and _value(b) is not None]
    n_aligned = len(aligned)

    if not aligned:
        if agg is not None:
            return {
                "ok": True,
                "decomposable": False,
                "reason": "aggregate_only",
                "detail": ("only aggregate scores were supplied; a total delta cannot "
                           "be attributed to per-task mechanisms from aggregates alone"),
                "observed_delta": agg["b"] - agg["a"],
                "scores": {"a": agg["a"], "b": agg["b"], "delta": agg["b"] - agg["a"]},
                "required": REQUIRED,
                **meta,
            }
        return {
            "ok": True,
            "decomposable": False,
            "reason": "no_paired_outcomes" if pairs else "no_records",
            "detail": ("no task carries an outcome on both sides"
                       if pairs else "the document contains no task records"),
            "observed_delta": None,
            "required": REQUIRED,
            **meta,
        }

    flags_seen = sum(len(_flags(a)) + len(_flags(b)) for _, a, b in aligned)
    if flags_seen == 0:
        return {
            "ok": True,
            "decomposable": False,
            "reason": "no_factor_flags",
            "detail": ("per-task outcomes are present but no record carries any of the "
                       "four mechanism fields, so source attribution would be a guess"),
            "observed_delta": None,
            "required": REQUIRED,
            **meta,
        }

    n = n_aligned
    buckets: Dict[str, Dict[str, Any]] = {}
    for f in FACTORS:
        buckets[f] = _bucket()
    buckets["ambiguous"] = _bucket()
    buckets["unexplained"] = _bucket()

    rows: List[Dict[str, Any]] = []
    for key, a, b in aligned:
        va, vb = _value(a), _value(b)
        task_delta = (vb - va) / n
        differing = _diff_factors(_flags(a), _flags(b))
        if len(differing) == 1:
            bucket = differing[0]
        elif len(differing) > 1:
            bucket = "ambiguous"
        else:
            bucket = "unexplained"
        buckets[bucket]["n_tasks"] += 1
        buckets[bucket]["delta"] += task_delta
        rows.append({
            "task_id": key[0],
            "seed": key[1],
            "label": _label(*key),
            "a": va,
            "b": vb,
            "delta": vb - va,
            "contribution": task_delta,
            "differing_factors": differing,
            "source": bucket,
        })

    mean_a = sum(_value(a) for _, a, _ in aligned) / n
    mean_b = sum(_value(b) for _, _, b in aligned) / n
    total = mean_b - mean_a

    abs_total = sum(abs(v["delta"]) for v in buckets.values())
    for name, v in buckets.items():
        v["share_of_abs_delta"] = (
            abs(v["delta"]) / abs_total if abs_total > 0 else 0.0)

    rows.sort(key=lambda r: (-abs(r["delta"]), r["task_id"]))
    # Zero-delta tasks are not "divergence": show them only if nothing moved.
    movers = [r for r in rows if r["delta"] != 0]
    top = (movers or rows)[:max(0, top_n)]

    observed = [f for f in FACTORS
                if buckets[f]["n_tasks"] > 0
                or any(f in _flags(a) or f in _flags(b) for _, a, b in aligned)]
    unpaired = sorted({f for _, a, b in aligned
                       for f in FACTORS
                       if (f in _flags(a)) != (f in _flags(b))})

    return {
        "ok": True,
        "decomposable": True,
        "benchmark": meta.get("benchmark"),
        "model": meta.get("model"),
        "harnesses": {"a": meta.get("harness_a"), "b": meta.get("harness_b")},
        "n_tasks": n,
        "n_tasks_a": meta.get("n_tasks_a", n),
        "n_tasks_b": meta.get("n_tasks_b", n),
        "n_unmatched": meta.get("n_unmatched", 0),
        "scores": {"a": mean_a, "b": mean_b, "delta": total},
        "sources": {f: buckets[f] for f in FACTORS},
        "ambiguous": buckets["ambiguous"],
        "unexplained": buckets["unexplained"],
        "attribution_sums_to_total_delta": (
            abs(sum(v["delta"] for v in buckets.values()) - total) < 1e-9),
        "factors_observed": observed,
        "factors_unpaired": unpaired,
        "top_divergence": top,
        "assumption": (
            "Observational attribution, not a causal decomposition.  A task is "
            "charged to a source only when exactly one of the four measured "
            "mechanisms differs between the two harness records; tasks with "
            "several differing mechanisms are kept in 'ambiguous' and tasks with "
            "none in 'unexplained'.  Confirm any source with a third arm that "
            "toggles that mechanism alone."),
    }


def decompose_file(path: str, path_b: Optional[str] = None,
                   top_n: int = 10) -> Dict[str, Any]:
    doc = load_document(path)
    if path_b:
        return decompose(doc, load_document(path_b), top_n=top_n)
    return decompose(doc, top_n=top_n)


def write_report(result: Dict[str, Any], out_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)


def format_summary(result: Dict[str, Any]) -> str:
    """One-screen text rendering, used by the CLI and the example."""
    if not result.get("decomposable"):
        return (f"not decomposable ({result['reason']}): {result['detail']}\n"
                f"observed delta: {result.get('observed_delta')}")
    s = result["scores"]
    lines = [f"delta = {s['delta']:+.4f}  (A {s['a']:.4f} -> B {s['b']:.4f}, "
             f"n={result['n_tasks']} tasks)"]
    for name in FACTORS + ("ambiguous", "unexplained"):
        v = result["sources"][name] if name in result["sources"] else result[name]
        lines.append(f"  {name:12s} tasks={v['n_tasks']:4d}  "
                     f"delta={v['delta']:+.4f}  share={v['share_of_abs_delta']:.1%}")
    lines.append("top divergence:")
    for r in result["top_divergence"]:
        lines.append(f"  {r['label']:24s} a={r['a']:.0f} b={r['b']:.0f} "
                     f"{r['source']:<12s} {','.join(r['differing_factors']) or '-'}")
    return "\n".join(lines)
