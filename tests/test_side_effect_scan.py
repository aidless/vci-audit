"""Round 14: side-effect scan on archived real traces.

Pins two things: (1) construct validity -- the scanner must flag the exact
poison vectors round 12 measured synthetically, and must not flag correct
plain implementations; (2) the archived empirical result -- 450 real records
carry zero contamination-capable signatures.
"""
import json
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "work")

from side_effect_scan import (RUNS, scan_run, scan_source,  # noqa: E402
                              CAPABLE)
from vci import registry  # noqa: E402
from vci.cross_task import VECTORS, _TPL  # noqa: E402

FAMS = {f.name: f for f in registry.FAMILIES}


def test_round12_poison_vectors_are_flagged_capable():
    for vec in VECTORS:
        src = _TPL["dedupe"]["correct"] + vec["poison"]
        res = scan_source(src)
        assert res["parse_ok"]
        assert res["flags"]["builtins_mutate"], vec["id"]
        assert res["flags"]["import_builtins"], vec["id"]


def test_correct_implementations_carry_no_flags():
    for name, tpl in _TPL.items():
        res = scan_source(tpl["correct"])
        assert res["parse_ok"]
        assert not any(res["flags"].values()), name


def test_signature_classes_are_distinct():
    src = ("sum = lambda xs: 999\n"
           "def solve(xs):\n    return sum(xs)\n")
    res = scan_source(src)
    assert res["flags"]["builtin_shadow"]
    assert not res["flags"]["builtins_mutate"]  # namespace-local is not capable


def test_process_level_writes_are_all_caught():
    src = ("import sys, os\n"
           "globals()['x'] = 1\n"
           "sys.modules['json'] = None\n"
           "os.environ['A'] = '1'\n"
           "del sys.modules['os']\n")
    flags = scan_source(src)["flags"]
    assert flags["globals_write"]
    assert len(flags["sys_modules_write"]) == 2
    assert flags["env_write"]


def test_truncated_source_is_a_parse_failure_not_a_crash():
    res = scan_source("def solve(nums):\n    for x in nums:\n        if x:")
    assert not res["parse_ok"]
    assert not any(res["flags"].values())


def test_archived_real_traces_carry_zero_side_effect_signatures():
    total_records, total_capable, total_flagged = 0, 0, 0
    raw_total = 0
    for path in RUNS:
        rep = scan_run(path, FAMS)
        total_records += rep["n_records"]
        total_flagged += len(rep["flagged_code_patch"])
        total_capable += rep["contamination_capable_records"]
        raw_total += sum(rep["raw_response_regex_hits"].values())
        assert rep["contamination_capable_records"] == 0, path
    assert total_records == 450
    assert total_flagged == 0
    assert total_capable == 0
    assert raw_total == 0


def test_artifact_totals_match_rescan():
    with open("outputs/realfail-side-effects.json", encoding="utf-8") as fh:
        art = json.load(fh)
    assert art["totals"]["records"] == 450
    assert art["totals"]["contamination_capable"] == 0
    assert set(CAPABLE) <= set(art["totals"]["raw_hits"])
