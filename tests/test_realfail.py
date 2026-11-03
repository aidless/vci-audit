"""Offline tests for vci/realfail.py.

The ollama transport is never touched here: only prompt building, payload
parsing, sheet emission and the analysis math.
"""
import random

from vci import realfail
from vci.audit import family_seed
from vci.registry import INDEX, by_name


# ------------------------------------------------------------------- parsing
def test_parse_plain_answers_object():
    payload, status = realfail.parse_payload('{"answers": ["4.7", "7"]}', "list")
    assert status == "ok"
    assert payload == {"answers": ["4.7", "7"]}


def test_parse_bare_list():
    payload, status = realfail.parse_payload('["4.7", "7"]', "list")
    assert status == "ok"
    assert payload == {"answers": ["4.7", "7"]}


def test_parse_fenced_with_prose():
    text = 'Sure! Here you go:\n```json\n{"answers": [1, 2]}\n```\nHope that helps.'
    payload, status = realfail.parse_payload(text, "list")
    assert status == "ok"
    assert payload == {"answers": [1, 2]}


def test_parse_prose_then_object_and_trailing_junk():
    text = 'The answer is {"answers": ["x"]} -- done.'
    payload, status = realfail.parse_payload(text, "list")
    assert status == "ok"
    assert payload == {"answers": ["x"]}


def test_parse_no_json():
    assert realfail.parse_payload("I have no idea.", "list") == (None, "no_json")


def test_parse_wrong_shape_for_mapping():
    payload, status = realfail.parse_payload('{"answers": [1]}', "mapping")
    assert status == "ok"  # any non-empty object is a legal mapping payload
    assert payload == {"answers": [1]}
    assert realfail.parse_payload('[1, 2]', "mapping") == (None, "wrong_shape")


def test_parse_bad_answers_key():
    payload, status = realfail.parse_payload('{"answers": 42}', "list")
    assert status == "bad_answers"


def test_parse_escaped_quotes_inside_strings():
    text = '{"answers": ["say \\"hi\\"", "b"]}'
    payload, status = realfail.parse_payload(text, "list")
    assert status == "ok"
    assert payload == {"answers": ['say "hi"', "b"]}


# -------------------------------------------------------------------- prompt
def test_build_prompt_list_appends_contract():
    fam = by_name("arith_expression")
    task = fam.make_one(random.Random(1), 1)
    p = realfail.build_prompt(task, fam)
    assert p.startswith(task.prompt)
    assert '{"answers"' in p and str(task.n_items) in p


def test_build_prompt_mapping():
    fam = by_name("log_field_extraction")
    task = fam.make_one(random.Random(1), 1)
    p = realfail.build_prompt(task, fam)
    assert "ONLY the JSON object" in p


# -------------------------------------------------------------- sheet + analyze
def _fake_run():
    """A two-task synthetic run, verified for real by the family verifiers."""
    fam = by_name("arith_expression")
    rng = random.Random(family_seed(20261104, INDEX[fam.name]))
    tasks = fam.generate(25, rng)[:2]
    records = []
    for i, task in enumerate(tasks):
        good = fam.canonical(task)
        payload = {"answers": good if i == 0 else ["987654321"] * task.n_items}
        cand_payload = payload
        from vci.schema import Candidate
        verdict = fam.verify(task, Candidate("c", task.task_id, fam.name,
                                             cand_payload, "real_model_output"))
        records.append({
            "family": fam.name, "task_id": task.task_id,
            "n_units": task.n_items, "prompt_chars": 10,
            "raw_response": "x", "wall_s": 0.1, "eval_count": 5,
            "eval_duration_s": 0.1, "parse_status": "ok", "payload": payload,
            "verdict": {"passed": verdict.passed, "score": verdict.score,
                        "evidence": verdict.evidence},
        })
    return {"manifest": {"kind": "vci-realfail", "version": realfail.REALFAIL_VERSION,
                         "model": "m", "model_digest": None, "host": "h",
                         "seed": 20261104, "n_tasks": 25,
                         "families": [fam.name], "temperature": 0.0,
                         "max_tokens": 64, "date": "2026-11-04"},
            "records": records}


def test_emit_sheet_rows_and_labels_roundtrip(tmp_path):
    run = _fake_run()
    fams = {"arith_expression": by_name("arith_expression")}
    rows = realfail.emit_sheet(run, fams)
    n_units = sum(r["n_units"] for r in run["records"])
    assert len(rows) == n_units
    ids = {r["row_id"] for r in rows}
    assert len(ids) == n_units
    # human truth: task 1 correct everywhere, task 2 wrong everywhere
    labels = {r["row_id"]: (r["task_id"] == rows[0]["task_id"]) for r in rows}
    rep = realfail.analyze(run, labels, fams)
    cell = rep["per_family"]["arith_expression"]
    assert cell["n"] == n_units and cell["pos"] == run["records"][0]["n_units"]
    assert cell["neg"] == run["records"][1]["n_units"]
    assert cell["tpr"] == 1.0 and cell["tnr"] == 1.0
    assert cell["false_accepts"] == [] and cell["false_rejects"] == []
    assert rep["run_stats"]["n_tasks_run"] == 2
    assert rep["run_stats"]["verifier_passed_tasks"] == 1


def test_analyze_flags_false_accept_and_false_reject():
    run = _fake_run()
    fams = {"arith_expression": by_name("arith_expression")}
    rows = realfail.emit_sheet(run, fams)
    t1 = rows[0]["task_id"]
    labels = {}
    for r in rows:
        if r["task_id"] == t1:
            labels[r["row_id"]] = r["unit"] != "q1"  # lie: q1 is "wrong"
        else:
            labels[r["row_id"]] = r["unit"] == "q1"  # lie: one wrong is "right"
    rep = realfail.analyze(run, labels, fams)
    cell = rep["per_family"]["arith_expression"]
    assert len(cell["false_rejects"]) == 1
    assert len(cell["false_accepts"]) == 1
    assert cell["tn"] == 1 and cell["tp"] == 1


def test_load_human_labels(tmp_path):
    p = tmp_path / "labels.csv"
    p.write_text("row_id,human_label\na,1\nb,0\nc,u\n", encoding="utf-8")
    labels = realfail.load_human_labels(str(p))
    assert labels == {"a": True, "b": False, "c": None}


def test_analyze_reports_unlabeled_and_undecidable():
    run = _fake_run()
    fams = {"arith_expression": by_name("arith_expression")}
    rows = realfail.emit_sheet(run, fams)
    labels = {rows[0]["row_id"]: True, rows[1]["row_id"]: None}
    rep = realfail.analyze(run, labels, fams)
    assert rep["n_labeled"] == 1
    assert rep["n_undecidable"] == 1
    assert len(rep["unlabeled"]) == len(rows) - 2


def test_sheet_contexts_are_nonempty_for_all_six_families():
    fams = {n: by_name(n) for n in realfail.DEFAULT_FAMILIES}
    for name, fam in fams.items():
        rng = random.Random(family_seed(20261104, INDEX[name]))
        task = fam.generate(1, rng)[0]
        from vci.schema import Candidate
        payload = fam.canonical(task)
        verdict = fam.verify(task, Candidate("c", task.task_id, name,
                                             payload, "real_model_output"))
        run = {"manifest": {"seed": 20261104, "n_tasks": 1, "families": [name]},
               "records": [{"family": name, "task_id": task.task_id,
                            "parse_status": "ok", "payload": payload,
                            "verdict": {"passed": verdict.passed,
                                        "score": verdict.score,
                                        "evidence": verdict.evidence}}]}
        rows = realfail.emit_sheet(run, fams)
        assert rows and all(r["context"] for r in rows), name
