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


# ----------------------------------------------------------------- tolerant
def _fixture_run(fam_name, mutate, seed=20261104, n_tasks=1):
    """A one-task run whose archived verdict is computed by the current code."""
    from vci.schema import Candidate
    fam = by_name(fam_name)
    rng = random.Random(family_seed(seed, INDEX[fam_name]))
    task = fam.generate(seed and 1 or 1, rng)[0]
    payload = {"answers": mutate(fam.canonical(task))}
    verdict = fam.verify(task, Candidate("c", task.task_id, fam_name,
                                         payload, "real_model_output"))
    return ({"manifest": {"kind": "vci-realfail", "seed": seed, "n_tasks": 1,
                          "families": [fam_name], "model": "m",
                          "model_digest": None, "host": "h", "temperature": 0.0,
                          "max_tokens": 64, "date": "2026-11-04"},
             "records": [{"family": fam_name, "task_id": task.task_id,
                          "parse_status": "ok", "payload": payload,
                          "verdict": {"passed": verdict.passed,
                                      "score": verdict.score,
                                      "evidence": verdict.evidence}}]},
            task)


def test_tolerant_variants_rules():
    assert realfail.tolerant_variants("plain") == [("plain", None)]
    assert realfail.tolerant_variants({"pattern": "x"}) == [({"pattern": "x"}, None),
                                                            ("x", "unwrap")]
    assert realfail.tolerant_variants(853.35) == [(853.35, None), ("853.35", "num2str")]
    assert realfail.tolerant_variants(7) == [(7, None), ("7", "num2str")]
    # booleans are not numbers for this purpose
    assert realfail.tolerant_variants(True) == [(True, None)]
    # multi-key dicts are not unwrapped
    assert realfail.tolerant_variants({"a": 1, "b": 2}) == [({"a": 1, "b": 2}, None)]


def test_analyze_tolerant_repairs_numeric_money():
    def mutate(ans):
        out = list(ans)
        out[1] = float(ans[1])  # money line as a JSON number
        return out
    run, task = _fixture_run("template_render", mutate)
    if realfail._num_to_str(float(task.items[1]["expected"])) != task.items[1]["expected"]:
        # pathological rounding in this seed's money line; pick another seed
        run, task = _fixture_run("template_render", mutate, seed=7)
    fams = {"template_render": by_name("template_render")}
    labels = {f"{task.task_id}:{it['unit']}": True for it in task.items}
    rep = realfail.analyze_tolerant(run, labels, fams)
    assert rep["faithful_families"] == ["template_render"]
    cell = rep["per_family"]["template_render"]
    v1 = cell["variants"]["v1"]
    assert v1["repairs"] == [f"{task.task_id}:s2"]
    assert v1["repairs_by_rule"] == {"unwrap": 0, "num2str": 1}
    assert cell["strict"]["tpr"] < 1.0 and v1["tpr"] == 1.0
    assert len(v1["repaired_correct"]) == 1
    assert v1["new_false_accepts"] == []


def test_analyze_tolerant_repairs_wrapped_pattern():
    def mutate(ans):
        out = list(ans)
        out[0] = {"pattern": out[0]}
        return out
    run, task = _fixture_run("regex_construct", mutate)
    fams = {"regex_construct": by_name("regex_construct")}
    labels = {f"{task.task_id}:{it['unit']}": True for it in task.items}
    rep = realfail.analyze_tolerant(run, labels, fams)
    cell = rep["per_family"]["regex_construct"]
    v1 = cell["variants"]["v1"]
    assert v1["repairs"] == [f"{task.task_id}:r1"]
    assert v1["repairs_by_rule"]["unwrap"] == 1
    assert v1["tpr"] == 1.0


def test_analyze_tolerant_keeps_verdict_when_strict_already_ok():
    run, task = _fixture_run("template_render", lambda a: list(a))
    fams = {"template_render": by_name("template_render")}
    labels = {f"{task.task_id}:{it['unit']}": True for it in task.items}
    rep = realfail.analyze_tolerant(run, labels, fams)
    cell = rep["per_family"]["template_render"]
    assert cell["variants"]["v1"]["repairs"] == []
    assert cell["strict"]["tpr"] == cell["variants"]["v1"]["tpr"] == 1.0


def test_analyze_tolerant_wrong_answer_stays_rejected():
    def mutate(ans):
        out = list(ans)
        out[1] = float(ans[1]) + 1.0  # wrong value, not a schema issue
        return out
    run, task = _fixture_run("template_render", mutate)
    fams = {"template_render": by_name("template_render")}
    labels = {f"{task.task_id}:{it['unit']}": it["unit"] != "s2"
              for it in task.items}  # human says s2 is wrong
    rep = realfail.analyze_tolerant(run, labels, fams)
    cell = rep["per_family"]["template_render"]
    assert cell["variants"]["v1"]["repairs"] == []
    assert cell["variants"]["v1"]["tnr"] == 1.0 and cell["variants"]["v1"]["tpr"] == 1.0


def test_analyze_tolerant_excludes_drifted_family():
    run, task = _fixture_run("template_render", lambda a: list(a))
    # simulate generator drift: corrupt one archived evidence flag
    run["records"][0]["verdict"]["evidence"][0]["ok"] = False
    fams = {"template_render": by_name("template_render")}
    rep = realfail.analyze_tolerant(run, {}, fams)
    assert rep["faithful_families"] == []
    assert "template_render" in rep["excluded_families"]
    assert rep["excluded_families"]["template_render"]["mismatched_units"] == 1
    assert rep["n_units"] == 0


def test_tolerant_variants_keyed_unwrap_is_v2_only():
    d = {"pattern": "^x$", "description": "ends in x"}
    assert realfail.tolerant_variants(d, "v1") == [(d, None)]
    assert realfail.tolerant_variants(d, "v2") == [(d, None), ("^x$", "keyed_unwrap")]
    # unknown keys are not unwrapped even in v2
    d2 = {"regexp": "^x$", "note": "n"}
    assert realfail.tolerant_variants(d2, "v2") == [(d2, None)]


def test_analyze_tolerant_v2_repairs_multikey_pattern():
    def mutate(ans):
        out = list(ans)
        out[0] = {"pattern": out[0], "description": "wrapped with metadata"}
        return out
    run, task = _fixture_run("regex_construct", mutate)
    fams = {"regex_construct": by_name("regex_construct")}
    labels = {f"{task.task_id}:{it['unit']}": True for it in task.items}
    rep = realfail.analyze_tolerant(run, labels, fams)
    cell = rep["per_family"]["regex_construct"]
    assert cell["variants"]["v1"]["repairs"] == []
    v2 = cell["variants"]["v2"]
    assert v2["repairs"] == [f"{task.task_id}:r1"]
    assert v2["repairs_by_rule"]["keyed_unwrap"] == 1
    assert v2["tpr"] == 1.0
