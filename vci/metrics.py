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
from typing import Dict, Iterable, List, Sequence, Tuple

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
    (``"correct"`` / ``"incorrect"``) plus optional ``defect``.
    """
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
