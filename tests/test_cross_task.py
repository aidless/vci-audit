"""Cross-task contamination differential: the contract of strategies A and B.

These tests pin the measured claim of round 12: cross-task contamination is
*invisible by construction* under per-candidate subprocess isolation (A) and
*measurable* under a shared-process batch harness (B), and the production
static filter does not see the contaminant.  They assert the behavioural
contract on small runs; the full archived numbers live in
work/cross_task_diff.json and the LOGBOOK.
"""
from vci import cross_task
from vci.cross_task import (_BANNED, _CODE_HOLDOUT, _TPL, VECTORS,
                            _run_batch, _job, _holdout_expected,
                            _verify_isolated)
from vci.registry import by_name

FAM = by_name("code_patch")
SLOTS = ["running_max", "dedupe"]  # small, one non-victim slot included


def _contaminant(vector, template):
    return _TPL[template]["correct"] + vector["poison"]


def test_contaminants_pass_the_static_filter():
    # The whole point: `_BANNED` does not see the poison line, so under a
    # shared-process harness only isolation would have stopped it.
    for vec in VECTORS:
        for name in _TPL:
            src = _contaminant(vec, name)
            assert not any(b in src for b in _BANNED), (vec["id"], name)


def test_strategy_a_verdicts_match_expectations():
    for vec in VECTORS:
        victim_tpl = _TPL[vec["victim_template"]]
        got = _verify_isolated(FAM, victim_tpl, vec["victim_src"])
        assert got == vec["expect_a"], vec["id"]
        # The contaminant itself is correct code and is accepted in isolation.
        assert _verify_isolated(FAM, _TPL["running_max"],
                                _contaminant(vec, "running_max"))


def test_batch_runner_flips_victims_only_after_a_contaminant():
    for vec in VECTORS:
        hold = _holdout_expected(_TPL[vec["victim_template"]])
        victim = _job(_TPL[vec["victim_template"]], vec["victim_src"], hold)
        # No contaminant: the batch verdict matches isolation.
        assert _run_batch([victim])[0]["verdict"] == vec["expect_a"]
        # Contaminant first: the victim verdict flips.
        cont = _job(_TPL["count_vowels"], _contaminant(vec, "count_vowels"),
                    _holdout_expected(_TPL["count_vowels"]))
        res = _run_batch([cont, victim])
        assert res[0]["verdict"] is True           # contaminant passes itself
        assert res[1]["verdict"] != vec["expect_a"], vec["id"]
        # Reversed order: the victim runs before the poison, verdict matches A.
        res_rev = _run_batch([victim, cont])
        assert res_rev[0]["verdict"] == vec["expect_a"], vec["id"]


def test_batch_runner_survives_broken_candidates():
    hold = _holdout_expected(_TPL["running_max"])
    broken = _job(_TPL["running_max"], "def solve(nums\n", hold)
    good = _job(_TPL["running_max"], _TPL["running_max"]["correct"], hold)
    res = _run_batch([broken, good])
    assert res[0]["verdict"] is False
    assert res[1]["verdict"] is True  # a syntax error does not poison the batch


def test_experiment_small_run_is_consistent():
    r = cross_task.run_experiment(slot_names=SLOTS)
    ag = r["aggregate"]
    n = len(VECTORS) * len(SLOTS)
    assert ag["contaminant_victim_pairs"] == n
    # Under isolation nothing flips; under the shared process every victim
    # flips; the static filter catches no contaminant.
    assert ag["victim_flips_under_A"] == 0
    assert ag["victim_flips_under_B"] == n
    assert ag["false_accepts"] == len(SLOTS)              # judge_abs vector
    assert ag["false_rejects"] == n - len(SLOTS)          # the other two
    assert ag["contaminants_caught_by_static_filter"] == 0
    assert ag["controls_match_A"] is True
    # Per-slot detail: contaminant accepted under both strategies.
    for b in r["batches"]:
        for s in b["per_slot"]:
            assert s["contaminant_verdict_A"] and s["contaminant_verdict_B"]
            assert s["victim_flipped"]
