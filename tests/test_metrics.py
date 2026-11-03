"""Formula tests: every number here is a hand-computed reference value."""
import random

import pytest

from vci import metrics as M


def test_vci_is_a_fourth_root_geometric_mean():
    assert M.vci(1.0, 1.0, 1.0) == pytest.approx(1.0)
    assert M.vci(0.16, 1.0, 1.0) == pytest.approx(0.16 ** 0.25)
    # Trust enters squared: halving trust costs a factor 2**0.5 in VCI.
    assert M.vci(1.0, 0.5, 1.0) == pytest.approx(0.5 ** 0.5)
    # Any zero component zeroes the index.
    for args in ((0.0, 1.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 0.0)):
        assert M.vci(*args) == 0.0


def test_vci_is_monotone_in_every_component():
    base = M.vci(0.7, 0.7, 0.7)
    for i in range(3):
        better = [0.7, 0.7, 0.7]
        better[i] = 0.9
        assert M.vci(*better) > base


def test_cheapness_piecewise_linear():
    assert M.cheapness(0.5) == 1.0
    assert M.cheapness(20.0) == 1.0
    assert M.cheapness(260.0) == pytest.approx(0.5)
    assert M.cheapness(400.0) == pytest.approx(1.0 - 380.0 / 480.0)
    assert M.cheapness(500.0) == 0.0
    assert M.cheapness(9000.0) == 0.0


def test_binary_task_carries_no_density():
    assert M.task_density(1, [{"j": 0, "score": 0.0}]) == 0.0
    assert M.task_density(1, []) == 0.0


def test_density_rewards_granularity_and_fidelity():
    # k=4: granularity = (4-1)/3 = 1.0; exact j/k scores give fidelity 1.0.
    exact = M.task_density(4, [{"j": 1, "score": 0.25}, {"j": 3, "score": 0.75}])
    assert exact == pytest.approx(1.0)
    # k=2: granularity = 1/3, fidelity 1.0.
    assert M.task_density(2, [{"j": 1, "score": 0.5}]) == pytest.approx(1.0 / 3.0)
    # A verifier that reports 1.0 for a 1/4-right answer has zero fidelity.
    assert M.task_density(4, [{"j": 1, "score": 1.0}]) == pytest.approx(0.25)
    # No partial probes collected: unmeasurable, so no credit.
    assert M.task_density(4, []) == 0.0


def test_kappa_matches_hand_computation():
    # po = 3/4; p_true = 1/2; p_pred = 1/4; pe = 0.5*0.25 + 0.5*0.75 = 0.5
    # kappa = (0.75 - 0.5) / 0.5 = 0.5
    kappa, po = M.cohen_kappa([True, True, False, False], [True, False, False, False])
    assert po == pytest.approx(0.75)
    assert kappa == pytest.approx(0.5)


def test_kappa_extremes():
    assert M.cohen_kappa([True, False, True], [True, False, True]) == (1.0, 1.0)
    # All labels identical on both sides: expected agreement is 1, kappa undefined
    # by convention reported as 0 with observed agreement 1.
    kappa, po = M.cohen_kappa([True, True], [True, True])
    assert kappa == 0.0 and po == 1.0
    assert M.cohen_kappa([], []) == (0.0, 0.0)


def test_operating_metrics_separates_paraphrases():
    recs = [
        {"label": "correct", "defect": "correct", "passed": True, "score": 1.0},
        {"label": "correct", "defect": "semantic_equivalent", "passed": True, "score": 1.0},
        {"label": "incorrect", "defect": "boundary", "passed": False, "score": 0.5},
        {"label": "incorrect", "defect": "partial", "passed": False, "score": 0.75},
    ]
    m = M.operating_metrics(recs)
    assert m["tpr"] == pytest.approx(1.0)
    assert m["tnr"] == pytest.approx(1.0)
    assert m["tpr_equiv"] == pytest.approx(1.0)
    assert m["tpr_canonical"] == pytest.approx(1.0)
    # tau90 = 1.0 (only two positives, both full credit); no negative reaches it.
    assert m["tau90"] == pytest.approx(1.0)
    assert m["far90"] == 0.0


def test_operating_metrics_far90_uses_relaxed_threshold():
    recs = [
        {"label": "correct", "defect": "correct", "passed": True, "score": 1.0},
        {"label": "correct", "defect": "semantic_equivalent", "passed": False, "score": 0.9},
        {"label": "incorrect", "defect": "boundary", "passed": False, "score": 0.9},
        {"label": "incorrect", "defect": "order", "passed": False, "score": 0.2},
    ]
    m = M.operating_metrics(recs)
    assert m["tpr"] == pytest.approx(0.5)
    # Relaxing to 0.9 recovers both positives but also admits one negative.
    assert m["tau90"] == pytest.approx(0.9)
    assert m["far90"] == pytest.approx(0.5)


def test_reliability_gate_names_its_reasons():
    bad = {"tpr": 0.8, "tnr": 0.85, "far90": 0.3, "kappa": 0.4}
    verdict = M.reliability_verdict(bad)
    assert verdict["reliable"] is False
    assert len(verdict["reasons"]) == 4
    good = {"tpr": 0.95, "tnr": 0.95, "far90": 0.05, "kappa": 0.8}
    assert M.reliability_verdict(good)["reliable"] is True
    assert M.reliability_verdict(good)["reasons"] == []


def test_bootstrap_is_reproducible_for_a_fixed_seed():
    values = [0.4, 0.6, 0.7, 0.8, 0.9, 1.0]
    a = M.bootstrap_ci(values, "median", n_boot=200, seed=11)
    b = M.bootstrap_ci(values, "median", n_boot=200, seed=11)
    assert a == b
    assert a[0] <= sorted(values)[len(values) // 2] <= a[1]
    # Wide, smooth input: the interval must be genuinely narrow.
    wide = [0.5] * 30
    assert M.bootstrap_ci(wide, "median", n_boot=100, seed=3) == pytest.approx((0.5, 0.5))


def test_wilson_interval_brackets_the_estimate():
    lo, hi = M.wilson_interval(8, 10)
    assert 0.0 <= lo < 0.8 < hi <= 1.0
    assert M.wilson_interval(0, 0) == (0.0, 1.0)
