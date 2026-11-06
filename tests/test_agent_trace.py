"""Round-15 offline tests: agentic trace machinery.  No ollama server needed
-- the agent loop runs against canned responders; analysis runs on synthetic
archives.  The live-run protocol (native tool calling, greedy decoding) is
exercised by `python -m vci agent-trace`, not here."""
import ast

import pytest

from vci import agent_trace as at
from vci.sideeffects import scan_source


# ---------------------------------------------------------------- Session

def test_session_persists_state_within_task():
    s = at.Session(timeout_s=10)
    try:
        assert s.run("x = 5")["ok"]
        r = s.run("print(x + 1)")
        assert r["ok"] and r["stdout"].strip() == "6"
    finally:
        s.kill()


def test_sessions_are_isolated_from_each_other():
    a, b = at.Session(), at.Session()
    try:
        a.run("y = 42")
        rb = b.run("print(y)")  # NameError: y undefined in the fresh session
        assert not rb["ok"] and "NameError" in rb["error"]
    finally:
        a.kill()
        b.kill()


def test_session_survives_model_errors_and_exit():
    s = at.Session()
    try:
        r1 = s.run("1/0")
        assert not r1["ok"] and "ZeroDivisionError" in r1["error"]
        r2 = s.run("raise SystemExit")
        assert not r2["ok"]
        r3 = s.run("print('still here')")
        assert r3["ok"] and "still here" in r3["stdout"]
    finally:
        s.kill()


def test_session_timeout_marks_dead():
    s = at.Session(timeout_s=1.0)
    try:
        r = s.run("while True: pass")
        assert r["error"] == "SessionTimeout" and not s.alive
        r2 = s.run("print(1)")
        assert r2["error"] == "SessionDead"
    finally:
        s.kill()


# ------------------------------------------------- tasks and references

def test_references_recomputed_independently():
    tasks = {t["task_id"]: t for t in at.AGENT_TASKS}

    # primes: independent trial division
    def is_p(n):
        return n > 1 and all(n % d for d in range(2, int(n ** .5) + 1))
    assert tasks["agt-04-primes"]["reference"] == \
        sum(1 for n in range(1000, 5001) if is_p(n))

    # running maximum: recover the data from the prompt, recompute
    prompt = tasks["agt-02-running-max"]["prompt"]
    nums = ast.literal_eval(prompt.split("\n\n")[1])
    ref = [int(v) for v in tasks["agt-02-running-max"]["reference"].split(",")]
    cur = nums[0]
    exp = []
    for v in nums:
        cur = max(cur, v)
        exp.append(cur)
    assert ref == exp and ref[-1] == max(nums)

    # weighted average: Fraction recomputation within rounding tolerance
    from fractions import Fraction
    lp = tasks["agt-03-weighted-avg"]["prompt"]
    rows = [ln.split(",") for ln in lp.split("\n\n")[1].splitlines()]
    wavg = (sum(Fraction(a) * Fraction(w) for _, a, w in rows)
            / sum(Fraction(w) for _, _, w in rows))
    assert abs(float(wavg) - tasks["agt-03-weighted-avg"]["reference"]) <= 0.005

    # log latency: recount with a different parse (rsplit, no regex)
    total = 0
    for ln in tasks["agt-05-log-latency"]["prompt"].split("\n\n")[1].splitlines():
        if "user=u7" in ln:
            total += int(ln.rsplit("=", 1)[1].rstrip("ms"))
    assert total == tasks["agt-05-log-latency"]["reference"]
    assert total > 0  # u7 must actually appear, else the task is vacuous

    # word frequency: split-based tokenization, no regex
    text = tasks["agt-01-wordfreq"]["prompt"].split("\n\n", 1)[1]
    toks = "".join(c.lower() if c.isalpha() else " " for c in text).split()
    assert toks.count("data") == tasks["agt-01-wordfreq"]["reference"]

    # sort records: independent sort
    lp = tasks["agt-06-sort-records"]["prompt"]
    rows = [ln.split(",") for ln in lp.split("\n\n")[1].splitlines()]
    ordered = sorted(rows, key=lambda r: (-int(r[1]), int(r[2])))
    assert ",".join(r[0] for r in ordered) == \
        tasks["agt-06-sort-records"]["reference"]


# ------------------------------------------------- loop with canned responder

def _script(*steps):
    it = iter(steps)

    def respond(messages):
        return next(it)
    return respond


def test_run_task_executes_code_and_grades():
    task = {"task_id": "t", "prompt": "add", "reference": 5}
    res = None
    s = at.Session()
    try:
        res = at.run_task(task, s, _script(
            {"content": "",
             "tool_calls": [{"function": {"name": "run_python",
                                          "arguments": {"code": "print(2 + 3)"}}}]},
            {"content": "",
             "tool_calls": [{"function": {"name": "submit_answer",
                                          "arguments": {"answer": "5"}}}]},
        ), max_turns=4)
    finally:
        s.kill()
    assert res["final_channel"] == "submit_answer"
    assert res["final_answer"] == "5"
    assert at.grade_answer(5, res["final_answer"])
    codes = [e["code"] for e in res["tool_calls"] if e["name"] == "run_python"]
    assert codes == ["print(2 + 3)"]
    assert res["tool_calls"][0]["stdout"].strip() == "5"


def test_run_task_nudges_then_accepts_final_text():
    task = {"task_id": "t2", "prompt": "p", "reference": "7"}
    s = at.Session()
    try:
        res = at.run_task(task, s, _script(
            {"content": "Let me think... 7", "tool_calls": []},
            {"content": "FINAL: 7", "tool_calls": []},
        ), max_turns=4)
    finally:
        s.kill()
    assert res["final_channel"] == "text" and res["final_answer"] == "7"


def test_parse_tool_calls_arguments_as_json_string():
    msg = {"tool_calls": [{"function": {
        "name": "run_python", "arguments": "{\"code\": \"print(1)\"}"}}]}
    tcs = at.parse_tool_calls(msg)
    assert tcs[0]["args"] == {"code": "print(1)"}


def test_parse_tool_calls_from_qwen_content_json():
    # this ollama serves chatml --no-jinja: the model emits the Qwen
    # tool-call shape as plain content and ollama does not surface it
    msg = {"content": '{\n  "name": "run_python",\n  "arguments": {\n'
                      '    "code": "print(1)"\n  }\n}'}
    tcs = at.parse_tool_calls(msg)
    assert tcs == [{"name": "run_python", "args": {"code": "print(1)"}}]


def test_parse_tool_calls_ignores_plain_text():
    assert at.parse_tool_calls({"content": "The answer is 7."}) == []


def test_parse_tool_calls_repairs_python_quote_escapes():
    # qwen2.5-coder emits Python-style \' inside JSON strings (invalid JSON);
    # the harness must recover the intended tool call (observed round-15)
    bad = '{"name": "run_python", "arguments": {"code": "print(\'hi\')"}}'
    bad = bad.replace("print('hi')", "print(\\'hi\\')")
    tcs = at.parse_tool_calls({"content": bad})
    assert tcs[0]["name"] == "run_python"
    assert tcs[0]["args"] == {"code": "print('hi')"}


def test_run_task_stops_on_identical_repeats():
    task = {"task_id": "t3", "prompt": "p", "reference": "x"}
    s = at.Session()
    try:
        res = at.run_task(task, s, _script(
            {"content": "same", "tool_calls": []},
            {"content": "same", "tool_calls": []},
        ), max_turns=5)
    finally:
        s.kill()
    assert res["final_channel"] is None
    assert len(res["turns"]) == 2  # stopped instead of nudging to max_turns


def test_run_task_parses_json_content_tool_call():
    task = {"task_id": "t4", "prompt": "add", "reference": 9}
    s = at.Session()
    try:
        res = at.run_task(task, s, _script(
            {"content": '{"name": "run_python", '
                        '"arguments": {"code": "print(4 + 5)"}}',
             "tool_calls": []},
            {"content": '{"name": "submit_answer", '
                        '"arguments": {"answer": "9"}}',
             "tool_calls": []},
        ), max_turns=4)
    finally:
        s.kill()
    assert res["final_channel"] == "submit_answer"
    assert res["final_answer"] == "9"
    assert at.grade_answer(9, res["final_answer"])
    assert res["tool_calls"][0]["stdout"].strip() == "9"


def test_grade_answer_variants():
    assert at.grade_answer(12, "12")
    assert at.grade_answer(548.62, 548.62)
    assert not at.grade_answer(12, "13")
    assert at.grade_answer("a,b,c", "a, b, c")  # whitespace-normalized
    assert not at.grade_answer("a,b,c", "a,b,d")
    assert not at.grade_answer(12, None)
    assert not at.grade_answer(12, "abc")


# -------------------------------------------- scanner x round-12 vectors

def test_scanner_flags_round12_vectors():
    from vci.cross_task import VECTORS
    for vec in VECTORS:
        res = scan_source(vec["poison"])
        found = [k for k, v in res["flags"].items() if v]
        assert "builtins_mutate" in found
        assert "import_builtins" in found


def test_poison_actually_flips_sum_in_session():
    s = at.Session()
    try:
        assert s.run("print(sum([1, 2, 3]))")["stdout"].strip() == "6"
        s.run(at._POISONABLE[0][1])
        assert s.run("print(sum([1, 2, 3]))")["stdout"].strip() == "999"
    finally:
        s.kill()


# ------------------------------------------------- replay + differential

def _synthetic_archive():
    rec_a = {"task_id": "sa", "prompt": "", "reference": 1, "turns": [],
             "final_answer": "1", "final_channel": "submit_answer",
             "tool_calls": [{"name": "run_python", "code": "print('A1')",
                             "ok": True, "stdout": "A1\n", "error": None}],
             "grade": True}
    rec_b = {"task_id": "sb", "prompt": "", "reference": 6, "turns": [],
             "final_answer": "6", "final_channel": "submit_answer",
             "tool_calls": [{"name": "run_python",
                             "code": "vals = [1, 2, 3]\nprint(sum(vals))",
                             "ok": True, "stdout": "6\n", "error": None}],
             "grade": True}
    return {"manifest": {"kind": "vci-agent-trace"},
            "records": [rec_a, rec_b]}


def test_replay_fidelity_matches_archived_stdout():
    arc = _synthetic_archive()
    p1 = at.replay(arc, shared=False)
    for tid, outs in p1.items():
        rec = next(r for r in arc["records"] if r["task_id"] == tid)
        for ev, out in zip(at.task_snippets(rec), outs):
            assert out["stdout"] == ev["stdout"] and out["ok"] == ev["ok"]


def test_differential_no_flips_without_contamination():
    rep = at.analyze_archive(_synthetic_archive())
    assert rep["replay"]["flips_shared_vs_fresh"] == []
    assert rep["replay"]["flips_shared_reversed_vs_fresh"] == []
    assert rep["replay"]["nondeterministic_snippets"] == []
    assert rep["replay"]["fidelity_mismatch"] == []
    assert rep["signature_scan"]["contamination_capable"] == 0
    assert rep["signature_scan"]["n_snippets"] == 2
    assert rep["agent_performance"]["passed"] == 2
    assert rep["agent_performance"]["tasks_with_code"] == 2


def test_injected_poison_flips_and_is_flagged():
    rep = at.analyze_archive(_synthetic_archive())
    ctrl = rep["injected_poison_control"]
    assert ctrl["attempted"]
    assert ctrl["primitive"] == "sum"
    assert ctrl["flagged_by_scan"]
    assert ctrl["propagated"]
    assert ctrl["flipped_snippets"] == [{"task_id": "sb", "snippet_index": 0}]
    # the real snippets themselves stay clean -- only the injected poison is
    # capable, and it was caught
    assert rep["signature_scan"]["contamination_capable"] == 0


def test_nondeterministic_snippet_excluded_from_differential():
    rec = {"task_id": "nt", "prompt": "", "reference": 0, "turns": [],
           "final_answer": None, "final_channel": None,
           "tool_calls": [{"name": "run_python",
                           "code": "import time\nprint(time.time())",
                           "ok": True, "stdout": "1720000000.0\n",
                           "error": None}],
           "grade": False}
    rep = at.analyze_archive({"manifest": {}, "records": [rec]})
    assert len(rep["replay"]["nondeterministic_snippets"]) == 1
    assert rep["replay"]["fidelity_mismatch"] == []
    assert rep["replay"]["flips_shared_vs_fresh"] == []


def test_analyze_empty_tool_trace_is_honest():
    rec = {"task_id": "nc", "prompt": "", "reference": 1, "turns": [],
           "final_answer": None, "final_channel": "none",
           "tool_calls": [], "grade": False}
    rep = at.analyze_archive({"manifest": {}, "records": [rec]})
    assert rep["signature_scan"]["n_snippets"] == 0
    assert not rep["injected_poison_control"]["attempted"]
    assert rep["agent_performance"]["passed"] == 0
