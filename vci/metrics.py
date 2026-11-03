"""Metric definitions.  Every formula here is mirrored in SPEC.md.

Design notes
------------
* ``passed`` is *full-credit* acceptance (score == 1.0).  That is the operating
  point an RL loop actually uses when it treats the verifier output as a reward
  gate.
* ``FAR90`` is the false-accept rate when the threshold is lowered just enough
  to recover 90% of valid answers.  It answers: "how many wrong answers sneak
  in if I make the verifier tolerant enough to accept paraphrases?"
* ``VCI`` is a weighted geometric mean ``(C * T^2 * D) ** 0.25``.  Trust is
  squared because a false positive is worse than a missing signal: it teaches
  the policy the wrong thing.
"""
import math
from typing import Any, Dict, Iterable, List, Sequence, Tuple

FULL_TOL = 1e-9


def cohen_kappa(y_true: Sequence[bool], y_pred: Sequence[bool]) -> Tuple[float, float]:
    """Cohen's kappa and observed agreement for two binary label vectors."""
    n = len(y_true)
    if n == 0:
        return 0.0, 0.0
    agree = sum(1 for a, b in zip(y_true, y_pred) if bool(a) == bool(b))
    po = agree / n
    p_t = sum(1 for a in y_true if a) / n
    p_p = sum(1 for b in y_pred if b) / n
    pe = p_t * p_p + (1 - p_t) * (1 - p_p)
    if abs(1 - pe) < 1e-15:
        return 0.0, po
    return (po - pe) / (1 - pe), po


def wilson_interval(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_ci(values: Iterable[float], stat="median", n_boot: int = 1000,
                 seed: int = 0, alpha: float = 0.05) -> Tuple[float, float]:
    """Percentile bootstrap over the supplied units (tasks or candidates)."""
    import random

    xs = list(values)
    if not xs:
        return 0.0, 0.0
    rng = random.Random(seed)
    fn = (lambda v: sorted(v)[len(v) // 2]) if stat == "median" else (lambda v: sum(v) / len(v))
    boots = []
    for _ in range(n_boot):
        sample = [xs[rng.randrange(len(xs))] for _ in range(len(xs))]
        boots.append(fn(sample))
    boots.sort()
    return boots[int(alpha / 2 * n_boot)], boots[int((1 - alpha / 2) * n_boot) - 1]


def operating_metrics(records: List[Dict]) -> Dict[str, float]:
    """TPR / TNR / FAR90 from per-candidate records.

    Each record needs ``score`` (float), ``passed`` (bool) and ``label``
    (``"correct"`` / ``"incorrect"``) plus optional ``defect``.  Records whose
    label is ``"observe"`` are skipped: they are resource observations with no
    stated verification policy, so they must not move TPR/TNR.
    """
    records = [r for r in records if r["label"] in ("correct", "incorrect")]
    pos = [r for r in records if r["label"] == "correct"]
    neg = [r for r in records if r["label"] == "incorrect"]
    out: Dict[str, float] = {}
    out["n_pos"] = float(len(pos))
    out["n_neg"] = float(len(neg))
    out["tpr"] = (sum(1.0 for r in pos if r["passed"]) / len(pos)) if pos else 0.0
    out["tnr"] = (sum(1.0 for r in neg if not r["passed"]) / len(neg)) if neg else 0.0
    out["fa_full"] = (sum(1.0 for r in neg if r["score"] >= 1 - FULL_TOL) / len(neg)) if neg else 0.0
    can = [r for r in pos if r["defect"] == "correct"]
    eqv = [r for r in pos if r["defect"] == "semantic_equivalent"]
    out["tpr_canonical"] = (sum(1.0 for r in can if r["passed"]) / len(can)) if can else 0.0
    out["tpr_equiv"] = (sum(1.0 for r in eqv if r["passed"]) / len(eqv)) if eqv else 0.0
    out["n_equiv"] = float(len(eqv))
    # Threshold that recovers >= 90% of positives.
    if pos:
        scores = sorted((r["score"] for r in pos), reverse=True)
        need = max(1, math.ceil(0.9 * len(scores)))
        tau = scores[need - 1]
    else:
        tau = 1.0
    out["tau90"] = tau
    out["far90"] = (sum(1.0 for r in neg if r["score"] >= tau - FULL_TOL) / len(neg)) if neg else 0.0
    return out


def trust_score(op: Dict[str, float]) -> float:
    """T = min(TPR, TNR, 1 - FAR90), clamped to [0, 1]."""
    return max(0.0, min(1.0, min(op["tpr"], op["tnr"], 1.0 - op["far90"])))


def bootstrap_kappa(y_true: Sequence[bool], y_pred: Sequence[bool],
                    n_boot: int = 500, seed: int = 0,
                    alpha: float = 0.05) -> Tuple[float, float]:
    """Percentile bootstrap interval for Cohen's kappa (rows resampled)."""
    import random

    n = len(y_true)
    if n < 3:
        return 0.0, 1.0
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        k, _po = cohen_kappa([y_true[i] for i in idx], [y_pred[i] for i in idx])
        vals.append(k)
    vals.sort()
    return vals[int(alpha / 2 * n_boot)], vals[int((1 - alpha / 2) * n_boot) - 1]


def krippendorff_alpha(units: Sequence[Sequence[Any]],
                       level: str = "ordinal") -> Dict[str, Any]:
    """Krippendorff's alpha for ``units`` of coders' ratings (missing = None).

    ``units`` is one sequence per judged item, holding one value per coder.
    ``None`` means "missing": an ``undecidable`` human label is missing data, not
    a third category, so it is excluded from both observed and expected
    disagreement rather than treated as "no".  ``level="ordinal"`` uses
    Krippendorff's ordinal distance

        delta^2(c, k) = ( sum_{g=c..k} n_g - (n_c + n_k)/2 )^2

    i.e. distance is measured in *cumulative frequencies*, not raw ranks: with
    an unbalanced marginal, "0 -> 1" can be further than "1 -> 2".  With the
    two-valued labels used here, ordinal and nominal differ only by a constant
    factor, so alpha is unchanged; the ordinal branch matters as soon as the
    label set has three levels (no / partial / yes).

    Returns a dict instead of a bare float so the report can state how many
    units were dropped as undecidable.  ``value`` is ``None`` when every unit is
    missing.
    """
    decided_values = [v for u in units for v in u if v is not None]
    n_missing = sum(1 for u in units for v in u if v is None)
    out = {"value": None, "n_units": len(units), "n_values": len(decided_values),
           "n_undecidable": n_missing, "do": 0.0, "de": 0.0, "level": level}
    if not decided_values:
        return out

    ordered = sorted(set(decided_values))
    rank = {v: i for i, v in enumerate(ordered)}
    counts = {v: decided_values.count(v) for v in ordered}
    by_rank = [counts[v] for v in ordered]

    def delta(a, b) -> float:
        if level == "nominal":
            return 0.0 if a == b else 1.0
        i, j = sorted((rank[a], rank[b]))
        span = sum(by_rank[i:j + 1])
        return float((span - (by_rank[i] + by_rank[j]) / 2.0) ** 2)

    # Observed disagreement: within each unit, average over the m_u*(m_u-1)
    # ordered pairs of distinct coders, then average over the n pairable values
    # (Krippendorff 2011: n = sum_u m_u, not the number of units).
    observed = 0.0
    n_pairable = 0
    n_pairs_units = 0
    for u in units:
        vals = [v for v in u if v is not None]
        m = len(vals)
        n_pairable += m
        if m < 2:
            continue
        n_pairs_units += 1
        pair_sum = sum(delta(a, b) for a in vals for b in vals)
        observed += pair_sum / (m - 1)
    if not n_pairs_units:
        # Nothing was rated twice: agreement is undefined, not perfect.
        return out
    do = observed / n_pairable

    # Expected disagreement: pair all pooled values (without replacement).
    n = len(decided_values)
    pair_sum = sum(counts[a] * counts[b] * delta(a, b) for a in ordered for b in ordered)
    de = pair_sum / (n * (n - 1)) if n > 1 else 0.0
    out["do"] = do
    out["de"] = de
    # de == 0 means every decided value has the same rank: no chance
    # disagreement exists, so agreement is perfect by definition.
    out["value"] = 1.0 if de <= 0 else max(-1.0, min(1.0, 1.0 - do / de))
    return out


def bootstrap_alpha(units: Sequence[Sequence[Any]], n_boot: int = 500,
                    seed: int = 0, alpha: float = 0.05) -> Tuple[float, float]:
    """Percentile bootstrap interval for :func:`krippendorff_alpha`.

    Units (not values) are resampled, matching the unit-level definition.
    """
    import random

    n = len(units)
    if n < 3:
        return 0.0, 1.0
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        sample = [units[rng.randrange(n)] for _ in range(n)]
        got = krippendorff_alpha(sample)
        vals.append(1.0 if got["value"] is None else got["value"])
    vals.sort()
    return vals[int(alpha / 2 * n_boot)], vals[int((1 - alpha / 2) * n_boot) - 1]


def cheapness(p95_ms: float, cheap_ms: float = 20.0, costly_ms: float = 500.0) -> float:
    """1.0 when verification is <=20 ms, decaying linearly to 0 at 500 ms."""
    if p95_ms <= cheap_ms:
        return 1.0
    if p95_ms >= costly_ms:
        return 0.0
    return 1.0 - (p95_ms - cheap_ms) / (costly_ms - cheap_ms)


def task_density(n_items: int, partials: List[Dict]) -> float:
    """Dense-credit score for one task.

    ``granularity`` rewards having independent units at all; ``fidelity``
    rewards the verifier for reporting ``j/k`` when exactly ``j`` of ``k``
    units are right.  A one-unit (binary) task cannot carry dense credit and
    scores 0 by definition.
    """
    if n_items <= 1:
        return 0.0
    granularity = min(1.0, (n_items - 1) / 3.0)
    if not partials:
        return 0.0
    devs = [abs(p["score"] - p["j"] / n_items) for p in partials]
    fidelity = max(0.0, 1.0 - sum(devs) / len(devs))
    return granularity * fidelity


def vci(cheap: float, trust: float, dense: float) -> float:
    """Weighted geometric mean; any zero component zeroes the index."""
    cheap = max(0.0, min(1.0, cheap))
    trust = max(0.0, min(1.0, trust))
    dense = max(0.0, min(1.0, dense))
    if cheap <= 0 or trust <= 0 or dense <= 0:
        return 0.0
    return (cheap * (trust ** 2) * dense) ** 0.25


def reliability_verdict(m: Dict[str, float]) -> Dict[str, object]:
    """Turn trust numbers into an explicit 'trust this verifier or not' call."""
    reasons = []
    if m["tpr"] < 0.90:
        reasons.append(f"TPR {m['tpr']:.2f} < 0.90 (valid variants rejected)")
    if m["tnr"] < 0.90:
        reasons.append(f"TNR {m['tnr']:.2f} < 0.90 (wrong answers accepted)")
    if m["far90"] > 0.20:
        reasons.append(f"FAR90 {m['far90']:.2f} > 0.20 (tolerance admits wrong answers)")
    if m.get("kappa", 0.0) < 0.60:
        reasons.append(f"kappa {m.get('kappa', 0.0):.2f} < 0.60")
    return {"reliable": not reasons, "reasons": reasons}
