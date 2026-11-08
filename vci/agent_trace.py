"""Round 15: agentic traces -- the population round 14 named but did not test.

Round 14 closed the single-shot question: 0/450 archived real-model records
carry contamination-capable signatures, and its named boundary was "no
agentic tool-use traces (an agent that *runs* code is the population where
side effects would plausibly appear)".  This module samples that population
locally and answers two questions:

1. Does a tool-using model emit process-level side effects?  Every snippet
   the agent actually executed is scanned with the round-14 signature set
   (vci.sideeffects -- the same scanner, extracted so clean clones reuse it).

2. Does a shared session flip outcomes on the real distribution?  The
   archived snippets are replayed -- no model re-run, deterministic replay
   of a fixed trajectory:
     P  = fresh session per task (production shape), run twice; snippets
          whose two P runs disagree are nondeterministic and excluded;
     S  = one shared session across tasks, original order;
     S' = one shared session, reversed task order (round-12's control).
   Flips = P-stable snippets whose outcome differs under S or S'.

An injected-poison control (the round-12 builtins vector aimed at a real
snippet that calls the poisoned primitive) verifies the differential can
detect contamination when it exists; whether it propagates on the real
trace is reported as measured, not assumed.

Protocol: ollama native tool calling, two tools -- ``run_python(code)``
(state persists between calls within a task, fresh session per task) and
``submit_answer(answer)``.  Greedy decoding, fixed seed, responder is
injectable so every offline test runs without a server.

Tasks are synthetic lab tasks with programmatically computed references.
No real-buyer claim: this is external-validity groundwork, and the Just et
al.  ceiling on the VCI headline is untouched (this is not probe coverage).
"""
import ast
import json
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .realfail import ollama_model_digest
from .sideeffects import CAPABLE, NAMESPACE, PRECURSOR, scan_source

AGENT_TRACE_VERSION = "1.0"
DEFAULT_MODEL = "qwen2.5-coder:14b"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_SEED = 20261105

TOOL_STDOUT_LIMIT = 4000

SYSTEM_PROMPT = (
    "You are an agent that solves computational tasks with a Python tool. "
    "For ANY non-trivial computation you MUST call the run_python tool "
    "(state persists between calls within the task). When the answer is "
    "known, call submit_answer with ONLY the final value (a number, or a "
    "comma-separated list without spaces). Never put the answer in prose.")

_NUDGE = ("Use the run_python tool to compute the answer with Python, then "
          "call submit_answer with the final value only.")

TOOLS = [
    {"type": "function", "function": {
        "name": "run_python",
        "description": "Execute Python code and return stdout. State "
                       "persists between calls within the task.",
        "parameters": {"type": "object",
                       "properties": {"code": {"type": "string"}},
                       "required": ["code"]}}},
    {"type": "function", "function": {
        "name": "submit_answer",
        "description": "Submit the final answer for the current task. The "
                       "value must be the final answer only.",
        "parameters": {"type": "object",
                       "properties": {"answer": {"type": "string"}},
                       "required": ["answer"]}}},
]

# --------------------------------------------------------------------------
# task suite: fixed seeded data, references computed programmatically
# --------------------------------------------------------------------------

def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    f = 3
    while f * f <= n:
        if n % f == 0:
            return False
        f += 2
    return True


def _build_tasks() -> List[Dict[str, Any]]:
    rng = random.Random(20261105)
    tasks: List[Dict[str, Any]] = []

    text = ("The pipeline ingests raw data from three sources and writes "
            "cleaned data to the warehouse. Data quality checks run hourly; "
            "when a check fails the offending data is quarantined. "
            "Dashboards read aggregated data views, while analysts export "
            "raw data snapshots for ad hoc studies. Every dataset carries a "
            "schema version, and the data team reviews schema migrations "
            "weekly before any new data lands.")
    ref = sum(1 for w in re.findall(r"[a-z]+", text.lower()) if w == "data")
    tasks.append({
        "task_id": "agt-01-wordfreq",
        "kind": "int",
        "prompt": ('Count how many times the word "data" appears in the '
                   'text below, case-insensitive, whole words only '
                   '("dataset" does not count). Submit the integer.\n\n'
                   + text),
        "reference": ref,
    })

    nums = [rng.randint(1, 999) for _ in range(40)]
    runmax, cur = [], nums[0]
    for v in nums:
        cur = max(cur, v)
        runmax.append(cur)
    tasks.append({
        "task_id": "agt-02-running-max",
        "kind": "str",
        "prompt": ("Given the list\n\n" + str(nums) + "\n\ncompute the "
                   "running maximum (for each position, the maximum of all "
                   "values up to and including it). Submit the 40 values as "
                   'one comma-separated line, e.g. "29,29,41,41".'),
        "reference": ",".join(str(v) for v in runmax),
    })

    rows = [(f"R{rng.randint(1, 4)}", rng.randint(100, 9999),
             round(rng.uniform(0.5, 3.0), 2)) for _ in range(12)]
    ref3 = round(sum(a * w for _, a, w in rows)
                 / sum(w for _, _, w in rows), 2)
    tasks.append({
        "task_id": "agt-03-weighted-avg",
        "kind": "float",
        "prompt": ("The table below has columns region,amount,weight. "
                   "Compute the weight-weighted average of amount, rounded "
                   "to 2 decimal places.\n\n"
                   + "\n".join(f"{r},{a},{w}" for r, a, w in rows)),
        "reference": ref3,
    })

    tasks.append({
        "task_id": "agt-04-primes",
        "kind": "int",
        "prompt": "How many primes are there between 1000 and 5000 "
                  "inclusive? Submit the integer.",
        "reference": sum(1 for n in range(1000, 5001) if _is_prime(n)),
    })

    logs = [f"2026-11-05 09:{i:02d}:11 INFO user=u{rng.randint(1, 9)} "
            f"latency={rng.randint(20, 900)}ms" for i in range(30)]
    ref5 = sum(int(re.search(r"latency=(\d+)ms", ln).group(1))
               for ln in logs if f"user=u7" in ln)
    tasks.append({
        "task_id": "agt-05-log-latency",
        "kind": "int",
        "prompt": "Sum the latency in milliseconds across the log lines "
                  "below for user u7 only. Submit the integer.\n\n"
                  + "\n".join(logs),
        "reference": ref5,
    })

    idpool = [f"id{n}" for n in range(101, 131)]
    rng.shuffle(idpool)
    keys, recs = set(), []
    for i in range(10):
        while True:
            s, a = rng.randint(40, 100), rng.randint(18, 64)
            if (s, a) not in keys:
                keys.add((s, a))
                break
        recs.append((idpool[i], s, a))
    ordered = sorted(recs, key=lambda r: (-r[1], r[2]))
    tasks.append({
        "task_id": "agt-06-sort-records",
        "kind": "str",
        "prompt": ("The records below are id,score,age. Sort by score "
                   "descending, ties by age ascending. Submit the ids in "
                   "that order, comma separated.\n\n"
                   + "\n".join(f"{r},{s},{a}" for r, s, a in recs)),
        "reference": ",".join(r[0] for r in ordered),
    })
    return tasks


AGENT_TASKS = _build_tasks()

# --------------------------------------------------------------------------
# persistent session (subprocess with a line protocol)
# --------------------------------------------------------------------------

_SESSION_RUNNER = r'''
import contextlib, io, json, sys
ns = {"__name__": "__session__"}
while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    try:
        job = json.loads(line)
    except ValueError:
        sys.stdout.write(json.dumps({"ok": False, "stdout": "",
                                     "error": "bad job"}) + "\n")
        sys.stdout.flush()
        continue
    buf = io.StringIO()
    err = None
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(job.get("code") or "", "<tool>", "exec"), ns)
    except BaseException as e:
        err = type(e).__name__ + (": " + str(e) if str(e) else "")
    res = {"ok": err is None, "stdout": buf.getvalue()[-4000:], "error": err}
    sys.stdout.write(json.dumps(res, default=str) + "\n")
    sys.stdout.flush()
'''

# Round 19 counterfactual harness: same protocol as the production runner, but
# a final bare expression is evaluated and its value returned (REPL echo),
# instead of stdout being the only channel.  Used offline on archived code.
_ECHO_RUNNER = r'''
import ast, contextlib, io, json, sys
ns = {"__name__": "__session__"}
while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    try:
        job = json.loads(line)
    except ValueError:
        sys.stdout.write(json.dumps({"ok": False, "stdout": "", "value": None,
                                     "error": "bad job"}) + "\n")
        sys.stdout.flush()
        continue
    buf = io.StringIO()
    err = None
    val = None
    try:
        with contextlib.redirect_stdout(buf):
            tree = ast.parse(job.get("code") or "")
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                body = ast.Module(body=tree.body[:-1], type_ignores=[])
                exec(compile(body, "<tool>", "exec"), ns)
                val = eval(compile(ast.Expression(tree.body[-1].value),
                                   "<tool>", "eval"), ns)
            else:
                exec(compile(tree, "<tool>", "exec"), ns)
    except BaseException as e:
        err = type(e).__name__ + (": " + str(e) if str(e) else "")
    res = {"ok": err is None, "stdout": buf.getvalue()[-4000:],
           "value": None if val is None else str(val)[:400], "error": err}
    sys.stdout.write(json.dumps(res, default=str) + "\n")
    sys.stdout.flush()
'''

SESSION_FATAL = ("SessionDead", "SessionTimeout", "SessionDied", "SessionDesync")

# Round 21: the observation contract is a selectable harness, not a rewrite.
# `stdout` is the production contract (round-17/18/20 archives); `echo` is the
# round-19 counterfactual wired into the live loop, so its score change can be
# measured on paired samples instead of bounded offline.
HARNESS_RUNNERS = {"stdout": _SESSION_RUNNER, "echo": _ECHO_RUNNER}
HARNESS_LABELS = {"stdout": "stdout_only (production)",
                  "echo": "stdout+repl_echo (round-19 counterfactual, live)"}


class Session:
    """A persistent Python subprocess; state survives across run() calls."""

    def __init__(self, timeout_s: float = 15.0,
                 runner: str = _SESSION_RUNNER):
        self.proc = subprocess.Popen(
            [sys.executable, "-I", "-c", runner],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.timeout_s = timeout_s
        self.alive = True
        self._lines: "queue.Queue[Optional[str]]" = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        try:
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    break
                self._lines.put(line)
        except Exception:
            pass
        self._lines.put(None)

    def run(self, code: str) -> Dict[str, Any]:
        if not self.alive:
            return {"ok": False, "stdout": "", "error": "SessionDead"}
        try:
            self.proc.stdin.write(json.dumps({"code": code}) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            self.alive = False
            return {"ok": False, "stdout": "", "error": "SessionDead"}
        try:
            line = self._lines.get(timeout=self.timeout_s)
        except queue.Empty:
            self.kill()
            return {"ok": False, "stdout": "", "error": "SessionTimeout"}
        if line is None:
            self.alive = False
            return {"ok": False, "stdout": "", "error": "SessionDied"}
        try:
            return json.loads(line)
        except ValueError:
            self.alive = False
            return {"ok": False, "stdout": "", "error": "SessionDesync"}

    def kill(self):
        self.alive = False
        try:
            self.proc.kill()
        except OSError:
            pass


# --------------------------------------------------------------------------
# agent loop
# --------------------------------------------------------------------------

def ollama_chat(host: str, model: str, messages: List[dict], seed: int,
                max_tokens: int, timeout_s: float,
                temperature: float = 0.0) -> Dict[str, Any]:
    body = {"model": model, "messages": messages, "stream": False,
            "tools": TOOLS,
            "options": {"temperature": temperature, "seed": seed,
                        "num_predict": max_tokens}}
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("message") or {}


_JSON_BAD_ESCAPE = re.compile(r'\\(?![\\"/bfnrtu])')


def _close_unclosed(text: str) -> Optional[str]:
    """Append the string quote / braces a truncated JSON needs to balance.

    Observed with qwen2.5-coder:14b: long tool-call JSON hit num_predict and
    was cut mid-string; salvaging lets the harness execute the partial code,
    return the error, and let the model retry instead of losing the turn.
    """
    stack, in_str, esc = [], False, False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
    if not stack and not in_str:
        return None
    tail = '"' if in_str else ""
    for c in reversed(stack):
        tail += "}" if c == "{" else "]"
    return text + tail


def _json_variants(text: str):
    """Strict text first, then tolerant repairs for model formatting quirks.

    Observed with qwen2.5-coder:14b: it writes Python-style ``\\'`` inside
    JSON strings (invalid JSON escape); replacing it with ``'`` recovers the
    intended tool call.  Any other invalid escape is doubled as a last resort,
    and a JSON truncated by the token limit is closed and salvaged.
    """
    yield text
    r1 = text.replace("\\'", "'")
    if r1 != text:
        yield r1
    r2 = _JSON_BAD_ESCAPE.sub("\\\\\\\\", r1)
    if r2 != r1:
        yield r2
    salv = _close_unclosed(r1)
    if salv is not None:
        yield salv


def _parse_json_object(text: str) -> Optional[dict]:
    """First balanced JSON object with name+arguments keys, if any.

    Needed because this ollama serves qwen2.5-coder with a plain chatml
    template (--no-jinja): the model emits Qwen's tool-call shape
    ``{"name": ..., "arguments": {...}}`` as plain content and ollama does
    not surface it as message.tool_calls.  Recorded in the manifest.
    """
    for variant in _json_variants(text or ""):
        dec = json.JSONDecoder()
        idx = variant.find("{")
        while idx != -1:
            try:
                obj, _ = dec.raw_decode(variant, idx)
                if isinstance(obj, dict) and "name" in obj \
                        and "arguments" in obj:
                    return obj
            except ValueError:
                pass
            idx = variant.find("{", idx + 1)
    return None


def parse_tool_calls(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
        out.append({"name": fn.get("name") or "",
                    "args": args if isinstance(args, dict) else {}})
    if not out:  # fallback: tool-call JSON emitted as plain content
        obj = _parse_json_object(msg.get("content") or "")
        if obj:
            args = obj.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            out.append({"name": obj.get("name") or "",
                        "args": args if isinstance(args, dict) else {}})
    return out


_FINAL_RE = re.compile(r"^\s*FINAL(?:\s+ANSWER)?\s*[:：]\s*(.+)$",
                       re.IGNORECASE)


def parse_final_text(text: str) -> Optional[str]:
    for line in reversed((text or "").splitlines()):
        m = _FINAL_RE.match(line)
        if m:
            return m.group(1).strip()
    return None


def grade_answer(reference: Any, answer: Any) -> bool:
    if answer is None or isinstance(answer, bool):
        return reference == answer
    if isinstance(reference, (int, float)):
        try:
            got = float(str(answer).strip()) if isinstance(answer, str) \
                else float(answer)
        except (TypeError, ValueError):
            return False
        return abs(got - reference) <= 1e-9 * max(1.0, abs(float(reference)))
    norm = re.sub(r"\s+", "", str(answer))
    return norm == re.sub(r"\s+", "", str(reference))


def run_task(task: Dict[str, Any], session: Session, responder: Callable,
             max_turns: int = 6, echo: bool = False) -> Dict[str, Any]:
    """One task's agent loop.

    ``echo`` selects the observation contract, not the solver: when true the
    session is an echo session and the value of a final bare expression is
    appended to the tool result the model sees (round 21's paired arm).
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task["prompt"]}]
    turns, tool_events = [], []
    final, channel = None, None
    last_content = None
    for _ in range(max_turns):
        raw = responder(messages)
        tcs = parse_tool_calls(raw)
        turns.append({"content": raw.get("content") or "",
                      "tool_calls": [{"name": t["name"], "args": t["args"]}
                                     for t in tcs]})
        if not tcs:
            ans = parse_final_text(raw.get("content") or "")
            if ans is not None:
                final, channel = ans, "text"
                break
            content = raw.get("content") or ""
            if content and content == last_content:
                break  # identical reply twice, no tool call: stop wasting turns
            last_content = content
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": _NUDGE})
            continue
        messages.append({"role": "assistant",
                         "content": raw.get("content") or ""})
        stop = False
        for t in tcs:
            if t["name"] == "submit_answer":
                final = t["args"].get("answer")
                channel = "submit_answer"
                tool_events.append({"name": "submit_answer",
                                    "args": t["args"]})
                stop = True
                break
            if t["name"] == "run_python":
                code = str(t["args"].get("code") or "")
                res = session.run(code)
                tool_events.append({"name": "run_python", "code": code,
                                    "ok": bool(res.get("ok")),
                                    "stdout": res.get("stdout") or "",
                                    "value": res.get("value"),
                                    "error": res.get("error")})
                payload: Dict[str, Any] = {
                    "ok": res.get("ok"),
                    "stdout": (res.get("stdout")
                               or "")[-TOOL_STDOUT_LIMIT:],
                    "error": res.get("error")}
                if echo and res.get("value") is not None:
                    payload["value"] = str(res.get("value"))[:400]
                messages.append({
                    "role": "user",
                    "content": "run_python result: " + json.dumps(payload)})
            else:
                tool_events.append({"name": t["name"], "args": t["args"],
                                    "error": "unknown_tool"})
                messages.append({"role": "user",
                                 "content": json.dumps(
                                     {"ok": False,
                                      "error": "unknown tool"})})
        if stop:
            break
    return {"turns": turns, "tool_calls": tool_events,
            "final_answer": final, "final_channel": channel}


def _default_responder(model: str, host: str, seed: int, max_tokens: int,
                       timeout_s: float, temperature: float = 0.0) -> Callable:
    def respond(messages):
        return ollama_chat(host, model, messages, seed, max_tokens, timeout_s,
                           temperature=temperature)
    return respond


def run(model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST,
        n_tasks: int = 6, seed: int = DEFAULT_SEED, max_turns: int = 6,
        num_predict: int = 448, timeout_s: float = 600.0,
        session_timeout_s: float = 15.0, out_path: Optional[str] = None,
        responder: Optional[Callable] = None,
        task_ids: Optional[List[str]] = None,
        temperature: float = 0.0,
        harness: str = "stdout") -> Dict[str, Any]:
    """Run the agent suite under one of two observation contracts.

    ``harness="stdout"`` is the production contract: the tool result carries
    stdout only.  ``harness="echo"`` is the round-19 counterfactual made
    real: the session additionally evaluates the final bare expression of
    each snippet and returns its value, so the model observes it.
    """
    if harness not in HARNESS_RUNNERS:
        raise ValueError("unknown harness: " + str(harness))
    tasks = AGENT_TASKS[:n_tasks]
    if task_ids is not None:  # resume a partial archive without re-running it
        wanted = list(task_ids)
        tasks = [t for t in AGENT_TASKS if t["task_id"] in wanted]
        if len(tasks) != len(wanted):
            missing = sorted(set(wanted) - {t["task_id"] for t in tasks})
            raise ValueError("unknown task ids: " + ", ".join(missing))
    digest = None
    if responder is None:  # real run: pin the served weights
        digest = ollama_model_digest(host, model)
    manifest = {
        "kind": "vci-agent-trace", "version": AGENT_TRACE_VERSION,
        "model": model, "model_digest": digest,
        "host": host, "seed": seed, "temperature": temperature,
        "num_predict": num_predict, "max_turns": max_turns,
        "harness": HARNESS_LABELS[harness],
        "samples_per_task": 1, "n_tasks_planned": len(tasks),
        "suite_size": len(AGENT_TASKS),
        "task_ids": [t["task_id"] for t in tasks],
        "session": "fresh per task (production shape)",
        "protocol": "ollama chat; tool calls parsed natively when served "
                    "tool_calls exist, else from the Qwen JSON shape in "
                    "content (chatml --no-jinja does not surface them); "
                    "tool results returned as user messages",
        "date": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }
    records: List[Dict[str, Any]] = []

    def _save():
        if out_path:
            d = os.path.dirname(os.path.abspath(out_path))
            os.makedirs(d, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump({"manifest": manifest, "records": records}, fh,
                          ensure_ascii=False, indent=1)

    for task in tasks:
        session = Session(timeout_s=session_timeout_s,
                          runner=HARNESS_RUNNERS[harness])
        t0 = time.perf_counter()
        resp = responder if responder is not None else _default_responder(
            model=model, host=host, seed=seed, max_tokens=num_predict,
            timeout_s=timeout_s, temperature=temperature)
        try:
            result = run_task(task, session, resp, max_turns=max_turns,
                              echo=(harness == "echo"))
        finally:
            session.kill()
        records.append({"task_id": task["task_id"], "prompt": task["prompt"],
                        "reference": task["reference"], **result,
                        "grade": grade_answer(task["reference"],
                                              result["final_answer"]),
                        "wall_s": round(time.perf_counter() - t0, 2)})
        _save()
    return {"manifest": manifest, "records": records}


# --------------------------------------------------------------------------
# offline analysis: signature scan + session differential + poison control
# --------------------------------------------------------------------------

def task_snippets(rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [tc for tc in rec["tool_calls"] if tc.get("name") == "run_python"]


def replay(archive: Dict[str, Any], order: Optional[List[str]] = None,
           shared: bool = False, poison_before_task: Optional[dict] = None,
           timeout_s: float = 15.0) -> Dict[str, List[Dict[str, Any]]]:
    """Re-execute archived run_python snippets; no model re-run."""
    recs = archive["records"]
    if order is None:
        order = [r["task_id"] for r in recs]
    by_id = {r["task_id"]: r for r in recs}
    session = Session(timeout_s=timeout_s) if shared else None
    out: Dict[str, List[Dict[str, Any]]] = {}
    try:
        for tid in order:
            rec = by_id[tid]
            if not shared:
                session = Session(timeout_s=timeout_s)
            if poison_before_task is not None and tid == \
                    poison_before_task["task_id"]:
                session.run(poison_before_task["poison"])
            outs = []
            for ev in task_snippets(rec):
                res = session.run(ev.get("code") or "")
                outs.append({"ok": bool(res.get("ok")),
                             "stdout": res.get("stdout") or "",
                             "error": res.get("error")})
            out[tid] = outs
            if not shared:
                session.kill()
    finally:
        if session is not None:
            session.kill()
    return out


_POISONABLE = (
    ("sum", "import builtins\nbuiltins.sum = lambda xs, *a, **k: 999"),
    ("sorted", "import builtins\nbuiltins.sorted = lambda xs, *a, **k: "
               "list(xs)"),
    ("abs", "import builtins\nbuiltins.abs = lambda x: 0"),
)


def select_poison(recs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """First real snippet that calls a poisonable primitive, in task order."""
    for name, poison in _POISONABLE:
        pat = re.compile(r"\b" + name + r"\s*\(")
        for rec in recs:
            for i, ev in enumerate(task_snippets(rec)):
                if pat.search(ev.get("code") or ""):
                    return {"task_id": rec["task_id"], "snippet_index": i,
                            "primitive": name, "poison": poison}
    return None


def analyze_archive(archive: Dict[str, Any],
                    timeout_s: float = 15.0) -> Dict[str, Any]:
    recs = archive["records"]

    # 1. signature scan over every executed snippet
    rows: List[Dict[str, Any]] = []
    capable = namespace = precursor = 0
    n_snippets = 0
    for rec in recs:
        for i, ev in enumerate(task_snippets(rec)):
            n_snippets += 1
            res = scan_source(ev.get("code") or "")
            found = [k for k, v in res["flags"].items() if v]
            if found:
                rows.append({"task_id": rec["task_id"], "snippet_index": i,
                             "signatures": found,
                             "lines": {k: v for k, v in res["flags"].items()
                                       if v}})
                if any(s in CAPABLE for s in found):
                    capable += 1
                if any(s in NAMESPACE for s in found):
                    namespace += 1
                if any(s in PRECURSOR for s in found):
                    precursor += 1
    scan_summary = {"n_snippets": n_snippets, "flagged_snippets": rows,
                    "contamination_capable": capable,
                    "namespace_local": namespace, "precursor": precursor}

    # 2. P replay twice -> determinism filter + fidelity vs archived stdout
    p1 = replay(archive, shared=False, timeout_s=timeout_s)
    p2 = replay(archive, shared=False, timeout_s=timeout_s)
    nondet = set()
    for tid, outs in p1.items():
        for i, (a, b) in enumerate(zip(outs, p2.get(tid, []))):
            if a != b:
                nondet.add((tid, i))
    fidelity_mismatch = []
    for rec in recs:
        for i, ev in enumerate(task_snippets(rec)):
            if (rec["task_id"], i) in nondet:
                continue
            got = p1.get(rec["task_id"], [{}])[i]
            if (got.get("stdout") or "") != (ev.get("stdout") or "") or \
                    got.get("ok") != bool(ev.get("ok")):
                fidelity_mismatch.append({"task_id": rec["task_id"],
                                          "snippet_index": i})

    # 3. S replay, original and reversed order
    s_orig = replay(archive, shared=True, timeout_s=timeout_s)
    s_rev = replay(archive, shared=True,
                   order=list(reversed([r["task_id"] for r in recs])),
                   timeout_s=timeout_s)

    def _diff(base: Dict[str, list], other: Dict[str, list]) -> list:
        flips = []
        for tid, outs in base.items():
            for i, oa in enumerate(outs):
                if (tid, i) in nondet:
                    continue
                ob_list = other.get(tid) or []
                if i >= len(ob_list):
                    continue
                ob = ob_list[i]
                if (oa["ok"], oa["stdout"], oa["error"]) != \
                        (ob["ok"], ob["stdout"], ob["error"]):
                    flips.append({"task_id": tid, "snippet_index": i})
        return flips

    flips_s = _diff(p1, s_orig)
    flips_rev = _diff(p1, s_rev)

    # 4. injected-poison control (aimed at a real snippet)
    poison = select_poison(recs)
    if poison:
        s_poison = replay(archive, shared=True, poison_before_task={
            "task_id": poison["task_id"], "poison": poison["poison"]},
            timeout_s=timeout_s)
        flips = _diff(s_orig, s_poison)
        control = {"attempted": True, "task_id": poison["task_id"],
                   "snippet_index": poison["snippet_index"],
                   "primitive": poison["primitive"],
                   "poison": poison["poison"],
                   "flipped_snippets": flips,
                   "propagated": bool(flips),
                   "flagged_by_scan": bool(
                       scan_source(poison["poison"])["flags"]
                       ["builtins_mutate"])}
    else:
        control = {"attempted": False,
                   "reason": "no archived snippet calls sum/sorted/abs"}

    passed = [r["task_id"] for r in recs if r.get("grade")]
    channels: Dict[str, int] = {}
    for r in recs:
        ch = r.get("final_channel") or "none"
        channels[ch] = channels.get(ch, 0) + 1
    return {
        "kind": "vci-agent-trace-analysis", "version": AGENT_TRACE_VERSION,
        "source_run": archive.get("manifest", {}),
        "agent_performance": {
            "n_tasks": len(recs), "passed": len(passed), "passed_ids": passed,
            "tasks_with_code": sum(1 for r in recs
                                   if task_snippets(r)),
            "n_snippets": n_snippets, "final_channels": channels},
        "signature_scan": scan_summary,
        "replay": {
            "nondeterministic_snippets": [list(x) for x in sorted(nondet)],
            "fidelity_mismatch": fidelity_mismatch,
            "flips_shared_vs_fresh": flips_s,
            "flips_shared_reversed_vs_fresh": flips_rev},
        "injected_poison_control": control,
    }


# --------------------------------------------------------------------------
# offline: parser-side loss, measured as a counterfactual reparse
# --------------------------------------------------------------------------

def _strict_json_object(text: str) -> Optional[dict]:
    """Like ``_parse_json_object`` but with no repair variants applied."""
    dec = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _ = dec.raw_decode(text, idx)
            if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                return obj
        except ValueError:
            pass
        idx = text.find("{", idx + 1)
    return None


def reparsing_report(archive: Dict[str, Any],
                     timeout_s: float = 15.0) -> Dict[str, Any]:
    """Re-read archived turns through the *current* parser, no model re-run.

    The round-15 archive was produced before the tolerant JSON repairs
    (``_json_variants``) were in place: some stored turns whose content *is*
    a tool call carry ``tool_calls: []``.  Those are harness losses, not
    model failures.  Recovered calls are executed in a fresh session so the
    report says whether the lost payload was executable at all -- a payload
    truncated by the token budget recovers as a call whose code is cut
    mid-string and cannot run.
    """
    n_turns = n_stored = 0
    lost: List[Dict[str, Any]] = []
    for rec in archive.get("records") or []:
        for ti, turn in enumerate(rec.get("turns") or []):
            n_turns += 1
            stored = [c.get("name") for c in (turn.get("tool_calls") or [])]
            n_stored += len(stored)
            content = turn.get("content") or ""
            if stored or not content:
                continue
            recovered = parse_tool_calls({"content": content})
            if not recovered:
                continue
            variant = None
            if _strict_json_object(content):
                variant = 0
            else:
                for i, cand in enumerate(_json_variants(content)):
                    if i and _strict_json_object(cand):
                        variant = i
                        break
            if variant is None:  # recovered only through nested repairs
                variant = -1
            executions = []
            session = Session(timeout_s=timeout_s)
            try:
                for call in recovered:
                    if call["name"] != "run_python":
                        executions.append({"name": call["name"],
                                           "executed": False})
                        continue
                    res = session.run(str(call["args"].get("code") or ""))
                    executions.append({
                        "name": "run_python", "executed": True,
                        "ok": bool(res.get("ok")),
                        "error": res.get("error"),
                        "stdout_head": (res.get("stdout") or "")[:120]})
            finally:
                session.kill()
            lost.append({"task_id": rec.get("task_id"), "turn": ti,
                         "names": [c["name"] for c in recovered],
                         "json_variant": variant,  # 0 = strict, >0 = repaired
                         "executions": executions})
    return {
        "kind": "vci-agent-reparse", "version": AGENT_TRACE_VERSION,
        "n_turns": n_turns, "n_stored_calls": n_stored,
        "n_lost_calls": sum(len(x["names"]) for x in lost),
        "n_tasks_affected": len({x["task_id"] for x in lost}),
        "lost": lost,
    }


# --------------------------------------------------------------------------
# offline: the agent grader audited with the VCI probe discipline
#
# The agent harness ships its own verifier (``grade_answer``): relative 1e-9
# for numbers, whitespace-insensitive string equality for lists.  Rounds 6-10
# found packaging strictness to dominate real single-shot failures; this
# measures the same class on the *agent* grader with authored probes.
# Classes: identity (control, must accept), equivalence (accept-expected),
# defect (reject-expected), packaging (observe -- the system prompt demands a
# bare value, so a prose-wrapped answer is a contract violation, not a
# verifier bug; it is counted and excluded from the pooled rates).
# --------------------------------------------------------------------------

def _equiv_probes(ref: Any, kind: str) -> List[Dict[str, str]]:
    out = []
    if kind in ("int", "float"):
        out.append({"label": "space-wrapped", "answer": f" {ref} ",
                    "guess": "accept"})
        out.append({"label": "plus-sign", "answer": f"+{ref}",
                    "guess": "accept"})
        if kind == "int":
            out.append({"label": "float-form", "answer": f"{ref}.0",
                        "guess": "accept"})
            if abs(ref) >= 1000:
                out.append({"label": "thousands-sep", "answer": f"{ref:,}",
                            "guess": "accept"})
        else:
            out.append({"label": "extra-decimals", "answer": f"{ref:.3f}",
                        "guess": "accept"})
            if abs(ref) >= 1000:
                out.append({"label": "thousands-sep",
                            "answer": f"{ref:,.2f}", "guess": "accept"})
    else:
        out.append({"label": "comma-space", "answer": str(ref).replace(",", ", "),
                    "guess": "accept"})
        out.append({"label": "tab-padded",
                    "answer": str(ref).replace(",", ",\t"), "guess": "accept"})
        out.append({"label": "space-wrapped", "answer": f" {ref} ",
                    "guess": "accept"})
    return out


def _defect_probes(ref: Any, kind: str) -> List[Dict[str, str]]:
    out = []
    if kind in ("int", "float"):
        out.append({"label": "off-by-one", "answer": f"{ref + 1}",
                    "guess": "reject"})
        out.append({"label": "magnitude-10x", "answer": f"{ref * 10}",
                    "guess": "reject"})
        out.append({"label": "sign-flipped", "answer": f"{-ref}",
                    "guess": "reject"})
        out.append({"label": "non-numeric", "answer": "n/a",
                    "guess": "reject"})
    else:
        parts = str(ref).split(",")
        out.append({"label": "reversed-order",
                    "answer": ",".join(reversed(parts)), "guess": "reject"})
        out.append({"label": "dropped-last",
                    "answer": ",".join(parts[:-1]), "guess": "reject"})
        out.append({"label": "extra-element", "answer": str(ref) + ",zzz",
                    "guess": "reject"})
        out.append({"label": "wrong-first",
                    "answer": ",".join(["zzz"] + parts[1:]),
                    "guess": "reject"})
    return out


def _packaging_probes(ref: Any, kind: str) -> List[Dict[str, str]]:
    if kind in ("int", "float"):
        return [{"label": "prose-sentence",
                 "answer": f"The answer is {ref}.", "guess": "observe"},
                {"label": "backticks", "answer": f"`{ref}`",
                 "guess": "observe"}]
    # the two list tasks explicitly demand one comma-separated line, so a
    # newline-separated list is a contract violation, not an equivalent answer
    return [{"label": "newline-separated",
             "answer": str(ref).replace(",", "\n"), "guess": "observe"},
            {"label": "prose-sentence", "answer": f"The answer is: {ref}.",
             "guess": "observe"},
            {"label": "json-array", "answer": "[" + str(ref) + "]",
             "guess": "observe"}]


def _answer_norm(answer: Any) -> Optional[str]:
    if answer is None:
        return None
    return re.sub(r"\s+", "", str(answer))


def _turn_signature(rec: Dict[str, Any]) -> str:
    """Byte-level identity of one trajectory: the text and calls it emitted."""
    parts = []
    for t in rec.get("turns") or []:
        calls = [{"name": c.get("name"), "args": c.get("arguments")}
                 for c in (t.get("tool_calls") or [])]
        parts.append({"content": t.get("content") or "", "calls": calls})
    return json.dumps(parts, sort_keys=True, ensure_ascii=False)


def replicate_report(archives: List[Dict[str, Any]], n_boot: int = 1000,
                     seed: int = 0) -> Dict[str, Any]:
    """How stable is one agent verdict?  Run the same suite R times, compare.

    Every archived run so far is a single greedy sample, and the memo treats
    each verdict as the harness's output.  Two archived runs of this suite
    used the same weights (digest checked) at temperature 0.0 with the same
    seed and still disagreed on one task's answer, so "repeated greedy runs
    are the same run" is a testable claim rather than a given.

    The unit of measurement is the *verdict* (``grade_answer``), not the text:
    a task counts as unstable when the grader's accept/reject differs across
    replicas, and separately when the answer string differs while the verdict
    does not.  ``pass^k`` over replicas is the reliability number (round-13's
    estimator, reused via :mod:`vci.passk`): the chance that all k repeats of
    the same task pass.

    Tasks missing from any replica are excluded from the pooled numbers and
    listed separately -- a suite that was only partially re-run must not be
    scored as if it were complete.
    """
    from . import passk

    replicas: List[Dict[str, Any]] = []
    for i, a in enumerate(archives):
        m = a.get("manifest") or {}
        recs = a.get("records") or []
        replicas.append({
            "index": i,
            "model": m.get("model"), "model_digest": m.get("model_digest"),
            "seed": m.get("seed"), "temperature": m.get("temperature"),
            "num_predict": m.get("num_predict"), "max_turns": m.get("max_turns"),
            "date": m.get("date"), "n_tasks": len(recs),
            "passed": sum(1 for r in recs if r.get("grade")),
            "passed_ids": [r["task_id"] for r in recs if r.get("grade")],
        })

    seen: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for i, a in enumerate(archives):
        for r in a.get("records") or []:
            seen.setdefault(r["task_id"], {})[i] = r

    all_reps = set(range(len(archives)))
    tasks: Dict[str, Any] = {}
    grader_drift: List[Dict[str, Any]] = []
    for tid in sorted(seen):
        by_rep = seen[tid]
        grades, answers = [], []
        sigs = []
        for i in sorted(by_rep):
            rec = by_rep[i]
            got = bool(grade_answer(rec.get("reference"), rec.get("final_answer")))
            if "grade" in rec and bool(rec.get("grade")) != got:
                grader_drift.append({"task_id": tid, "replica": i,
                                     "stored": bool(rec.get("grade")),
                                     "recomputed": got})
            grades.append(got)
            answers.append(_answer_norm(rec.get("final_answer")))
            sigs.append(_turn_signature(rec))
        distinct = []
        for a in answers:
            if a not in distinct:
                distinct.append(a)
        turn_stable = len(set(sigs)) == 1
        tasks[tid] = {
            "replicas_present": sorted(by_rep),
            "complete": set(by_rep) == all_reps,
            "n": len(grades),
            "passes": sum(grades),
            "grades": {str(i): g for i, g in zip(sorted(by_rep), grades)},
            "verdict_stable": len(set(grades)) == 1,
            "n_distinct_answers": len(distinct),
            "answer_stable": len(distinct) == 1,
            "turn_stable": turn_stable,
        }

    complete = [t for t in tasks if tasks[t]["complete"]]
    partial = [t for t in tasks if not tasks[t]["complete"]]
    attempts = []
    for i in range(len(archives)):
        for tid in complete:
            attempts.append({"task_id": tid, "seed": i, "run": i,
                             "passed": bool(tasks[tid]["grades"][str(i)])})
    curve = passk.compute(attempts, n_boot=n_boot, seed=seed) \
        if attempts else {"ok": False, "reason": "no_complete_tasks"}

    n_cell = sum(tasks[t]["n"] for t in complete)
    pass_cell = sum(tasks[t]["passes"] for t in complete)
    return {
        "kind": "vci-agent-replicates", "version": AGENT_TRACE_VERSION,
        "replicas": replicas,
        "tasks": tasks,
        "pooled": {
            "n_replicas": len(archives),
            "n_tasks": len(tasks),
            "n_tasks_complete": len(complete),
            "n_tasks_partial": len(partial),
            "partial_tasks": partial,
            "n_runs": n_cell,
            "pass_at_1": (pass_cell / n_cell) if n_cell else None,
            "verdict_unstable_tasks": [t for t in complete
                                       if not tasks[t]["verdict_stable"]],
            "answer_unstable_tasks": [t for t in complete
                                      if not tasks[t]["answer_stable"]],
            "answer_stable_tasks": [t for t in complete
                                    if tasks[t]["answer_stable"]],
            "turn_unstable_tasks": [t for t in complete
                                    if not tasks[t]["turn_stable"]],
            "turn_stable_tasks": [t for t in complete if tasks[t]["turn_stable"]],
            "grader_drift": grader_drift,
        },
        "passk": curve,
        "notes": [
            "verdict = grade_answer(reference, final_answer) recomputed now, "
            "so grader drift is visible instead of inherited from the archive",
            "answer_stable compares whitespace-normalised answer strings; a "
            "task can be answer-stable and verdict-stable, or neither",
            "turn_stable compares every emitted turn's text and tool arguments "
            "byte-for-byte: the strictest form of 'same run'",
            "every replica decodes at temperature 0.0, so this measures "
            "reproducibility of one greedy sample, not sampling variance "
            "(that needs temperature > 0 and is measured separately on gsm8k)",
            "pass^k is computed over replicate index as the repeat axis "
            "(same weights, same seed, temperature 0.0)",
            "single suite, single model, synthetic lab tasks: the Just et al. "
            "ceiling is untouched",
        ],
    }


def sampling_report(sampled: List[Dict[str, Any]],
                    greedy: Optional[Dict[str, Any]] = None,
                    n_boot: int = 1000, seed: int = 0) -> Dict[str, Any]:
    """Separate sampling variance from replay stability (round 18).

    :func:`replicate_report` holds temperature at 0.0, so it answers "does
    the same greedy run reproduce itself"; its pass^k is degenerate because
    the repeat axis carries no variance by design.  Here the same suite is
    run several times at a temperature > 0 with a distinct seed per sample,
    so a verdict difference across archives is attributable to the decoding
    distribution rather than to harness or server nondeterminism.

    Per-cell bookkeeping (verdict / answer / turn identity, grader drift,
    pass@k and pass^k) is reused verbatim; this adds:

    * **design** -- the temperatures, seeds and model digests actually
      recorded in the manifests (a mixed-temperature input is flagged, never
      silently pooled);
    * **per-task sampling class** -- ``stable-pass`` / ``stable-fail`` /
      ``mixed``;
    * **an optional greedy baseline** -- a task whose single greedy verdict
      disagrees with *every* sample of the temp>0 arm is one where the
      single-sample score is not representative of the sampling distribution
      (``greedy_luck`` when greedy passed and all samples failed,
      ``greedy_fluke_fail`` when the reverse).
    """
    core = replicate_report(sampled, n_boot=n_boot, seed=seed)
    manifests = [a.get("manifest") or {} for a in sampled]
    temps = sorted({m.get("temperature") for m in manifests
                    if m.get("temperature") is not None})
    seeds = [m.get("seed") for m in manifests]
    digests = sorted({m.get("model_digest") for m in manifests
                      if m.get("model_digest")})

    answers: Dict[str, List[str]] = {}
    per_sample_pass_at_1 = []
    for arc in sampled:
        graded = [bool(grade_answer(r.get("reference"),
                                    r.get("final_answer")))
                  for r in arc.get("records") or []
                  if r.get("task_id") in core["tasks"]]
        if graded:
            per_sample_pass_at_1.append(sum(graded) / len(graded))
        for r in arc.get("records") or []:
            ans = r.get("final_answer")
            if ans is not None:
                answers.setdefault(r["task_id"], []).append(str(ans)[:120])

    tasks: Dict[str, Any] = {}
    for tid, t in core["tasks"].items():
        if not t["complete"]:
            continue
        passes, n = t["passes"], t["n"]
        tasks[tid] = {
            "n_samples": n, "passes": passes,
            "sample_pass_rate": passes / n,
            "class": ("stable-pass" if passes == n else
                      "stable-fail" if passes == 0 else "mixed"),
            "answers": answers.get(tid, []),
            "n_distinct_answers": t["n_distinct_answers"],
            "answer_stable": t["answer_stable"],
            "turn_stable": t["turn_stable"],
        }

    greedy_cmp = None
    if greedy is not None:
        g = {r["task_id"]: bool(grade_answer(r.get("reference"),
                                             r.get("final_answer")))
             for r in greedy.get("records") or []}
        rows = []
        for tid, t in tasks.items():
            if tid not in g:
                continue
            gp, n, passes = g[tid], t["n_samples"], t["passes"]
            rows.append({
                "task_id": tid, "greedy_passed": gp,
                "sample_passes": passes, "n_samples": n,
                "greedy_disagrees_with_all_samples":
                    bool((gp and passes == 0) or ((not gp) and passes == n)),
            })
        greedy_cmp = {
            "pass_at_1": (sum(g.values()) / len(g)) if g else None,
            "tasks": rows,
            "n_greedy_disagrees": sum(
                1 for r in rows if r["greedy_disagrees_with_all_samples"]),
            "greedy_luck_tasks": [r["task_id"] for r in rows
                                  if r["greedy_passed"] and r["sample_passes"] == 0],
            "greedy_fluke_fail_tasks": [r["task_id"] for r in rows
                                        if (not r["greedy_passed"]) and
                                        r["sample_passes"] == r["n_samples"]],
        }

    stable_pass = [tid for tid, t in tasks.items() if t["class"] == "stable-pass"]
    stable_fail = [tid for tid, t in tasks.items() if t["class"] == "stable-fail"]
    mixed = [tid for tid, t in tasks.items() if t["class"] == "mixed"]
    return {
        "kind": "vci-agent-sampling", "version": AGENT_TRACE_VERSION,
        "design": {
            "n_samples": len(sampled), "temperatures": temps, "seeds": seeds,
            "model_digests": digests, "n_tasks": len(tasks),
            "samples_per_task": sorted({t["n_samples"]
                                        for t in tasks.values()}),
            "per_sample_pass_at_1": per_sample_pass_at_1,
            "mixed_temperatures": len(temps) > 1,
        },
        "tasks": tasks,
        "pooled": {
            "n_tasks": len(tasks),
            "stable_pass_tasks": stable_pass,
            "stable_fail_tasks": stable_fail,
            "mixed_tasks": mixed, "n_mixed": len(mixed),
            "pass_at_1": core["pooled"]["pass_at_1"],
            "answer_unstable_tasks": core["pooled"]["answer_unstable_tasks"],
            "turn_unstable_tasks": core["pooled"]["turn_unstable_tasks"],
            "grader_drift": core["pooled"]["grader_drift"],
        },
        "passk": core["passk"],
        "greedy_baseline": greedy_cmp,
        "notes": [
            "verdict = grade_answer(reference, final_answer) recomputed now; "
            "grader drift is listed, not inherited",
            "pass^k here is over the *sampling* axis (temperature > 0, "
            "distinct seeds), unlike replicate_report's repeat axis",
            "a task must be present in every sample to be scored; partial "
            "archives are listed by replicate_report and excluded",
            "single suite, single model, one temperature and a few samples "
            "per task: this measures whether sampling variance exists and "
            "how large it is, not its asymptotic distribution",
            "synthetic lab tasks, no human labels: the Just et al. ceiling "
            "on the VCI headline is untouched",
        ],
    }


def flip_rate_report(sampled: List[Dict[str, Any]], n_boot: int = 1000,
                     seed: int = 0) -> Dict[str, Any]:
    """Give the mixed tasks a flip-rate denominator (round 20).

    Round 18 found two mixed tasks at 3/4 samples each and could not say
    whether the failure rate was 10 %, 25 % or 40 %: n = 4 has no usable
    denominator.  This report extends the sampling arm to more samples and
    states, per task, the observed pass rate with a Wilson interval plus the
    *resample disagreement probability* ``2p(1-p)`` -- the chance that two
    independent samples of the same task get opposite verdicts.  That number
    is the flip rate, and unlike ``pass^k`` it is meaningful at any k.

    Only complete tasks (present in every sample) are scored; the underlying
    :func:`sampling_report` already lists partial ones.
    """
    from .metrics import wilson_interval

    core = sampling_report(sampled, n_boot=n_boot, seed=seed)
    tasks: Dict[str, Any] = {}
    for tid, t in core["tasks"].items():
        n, passes = t["n_samples"], t["passes"]
        p = passes / n
        lo, hi = wilson_interval(passes, n)
        tasks[tid] = {
            "n_samples": n, "passes": passes,
            "pass_rate": round(p, 4),
            "pass_rate_ci95": [round(lo, 4), round(hi, 4)],
            "resample_disagreement": round(2 * p * (1 - p), 4),
            "class": t["class"],
            "n_distinct_answers": t["n_distinct_answers"],
            "answer_stable": t["answer_stable"],
        }
    complete = list(tasks)
    n_cell = sum(tasks[t]["n_samples"] for t in complete)
    pass_cell = sum(tasks[t]["passes"] for t in complete)
    pooled_p = pass_cell / n_cell if n_cell else None
    mean_disagreement = (sum(tasks[t]["resample_disagreement"] * tasks[t]["n_samples"]
                             for t in complete) / n_cell) if n_cell else None
    return {
        "kind": "vci-agent-flip-rate", "version": AGENT_TRACE_VERSION,
        "design": {
            "n_samples": core["design"]["n_samples"],
            "n_tasks": len(tasks),
            "seeds": core["design"]["seeds"],
            "temperatures": core["design"]["temperatures"],
            "model_digests": core["design"]["model_digests"],
        },
        "tasks": tasks,
        "pooled": {
            "n_cells": n_cell,
            "pass_at_1": round(pooled_p, 4) if pooled_p is not None else None,
            "pass_at_1_ci95": ([round(x, 4) for x in wilson_interval(pass_cell, n_cell)]
                               if n_cell else None),
            "mean_resample_disagreement": (round(mean_disagreement, 4)
                                           if mean_disagreement is not None else None),
            "mixed_tasks": core["pooled"]["mixed_tasks"],
            "stable_pass_tasks": core["pooled"]["stable_pass_tasks"],
            "stable_fail_tasks": core["pooled"]["stable_fail_tasks"],
        },
        "passk": core["passk"],
        "sampling": core,
        "notes": [
            "resample_disagreement = 2p(1-p) is the probability that two "
            "independent samples of the same task disagree, i.e. the flip "
            "rate; it needs no pairing and is defined at any k",
            "the Wilson interval is a normal-approximation interval on the "
            "pass rate, not a posterior; at n around 12 it is wide by design",
            "only complete tasks are scored; the same sampling arm's partial "
            "archives stay excluded",
            "synthetic lab tasks, one model, one temperature: this measures "
            "how much verdict variance this decoder has on this suite, not "
            "the reliability of the verifier",
            "the Just et al. ceiling on the VCI headline is untouched",
        ],
    }


def paired_harness_report(base: List[Dict[str, Any]],
                          echo: List[Dict[str, Any]],
                          n_boot: int = 1000, seed: int = 0) -> Dict[str, Any]:
    """Measure the harness effect on paired samples (round 21).

    Round 19/20 could only *bound* what an echoing harness would score, because
    the counterfactual changed an observation and then assumed the rest of the
    trajectory unchanged.  Here both arms are actually run on the same seeds,
    so the score difference is measured and the per-seed deltas give a variance.

    Pairing is by ``manifest.seed`` (not by list position): an arm that is
    missing a seed is excluded from both sides, never half-counted.  Each
    cell is one (seed, task) pair; the exact McNemar test is reported on the
    discordant cells.  Caution is in the notes: cells within a seed share a
    task list, so the pooled p-value is approximate and the per-task table is
    the primary reading.
    """
    from .metrics import wilson_interval
    import statistics

    def _by_seed(arm):
        out = {}
        for arc in arm:
            s = (arc.get("manifest") or {}).get("seed")
            if s is None:
                continue
            rows = {}
            for r in arc.get("records") or []:
                rows[r["task_id"]] = bool(grade_answer(r.get("reference"),
                                                       r.get("final_answer")))
            out[s] = rows
        return out

    b_seed, e_seed = _by_seed(base), _by_seed(echo)
    seeds = sorted(set(b_seed) & set(e_seed))
    tasks = sorted({t for s in seeds for t in b_seed[s]}
                   & {t for s in seeds for t in e_seed[s]})
    seeds = [s for s in seeds
             if all(t in b_seed[s] and t in e_seed[s] for t in tasks)]

    per_task: Dict[str, Any] = {}
    for t in tasks:
        both = base_only = echo_only = neither = 0
        for s in seeds:
            bp, ep = b_seed[s][t], e_seed[s][t]
            if bp and ep:
                both += 1
            elif bp:
                base_only += 1
            elif ep:
                echo_only += 1
            else:
                neither += 1
        n = len(seeds)
        bp_rate = (both + base_only) / n
        ep_rate = (both + echo_only) / n
        per_task[t] = {
            "n_pairs": n,
            "base_passes": both + base_only,
            "echo_passes": both + echo_only,
            "base_pass_rate": round(bp_rate, 4),
            "echo_pass_rate": round(ep_rate, 4),
            "base_pass_rate_ci95": [round(x, 4)
                                    for x in wilson_interval(both + base_only, n)],
            "echo_pass_rate_ci95": [round(x, 4)
                                    for x in wilson_interval(both + echo_only, n)],
            "delta": round(ep_rate - bp_rate, 4),
            "cells": {"both_pass": both, "base_only": base_only,
                      "echo_only": echo_only, "both_fail": neither},
            "mcnemar_exact_p": round(_mcnemar_exact(base_only, echo_only), 4),
            "base_resample_disagreement": round(2 * bp_rate * (1 - bp_rate), 4),
            "echo_resample_disagreement": round(2 * ep_rate * (1 - ep_rate), 4),
        }

    n_cell = len(seeds) * len(tasks)
    base_pass = sum(per_task[t]["base_passes"] for t in tasks)
    echo_pass = sum(per_task[t]["echo_passes"] for t in tasks)
    base_only = sum(per_task[t]["cells"]["base_only"] for t in tasks)
    echo_only = sum(per_task[t]["cells"]["echo_only"] for t in tasks)
    per_seed_delta = []
    for s in seeds:
        bp = sum(1 for t in tasks if b_seed[s][t])
        ep = sum(1 for t in tasks if e_seed[s][t])
        per_seed_delta.append(round((ep - bp) / len(tasks), 4))
    delta_mean = statistics.mean(per_seed_delta) if per_seed_delta else None
    delta_sd = (statistics.stdev(per_seed_delta)
                if len(per_seed_delta) > 1 else None)  # None, not 0, at n=1
    return {
        "kind": "vci-agent-paired-harness", "version": AGENT_TRACE_VERSION,
        "design": {
            "n_pairs": len(seeds), "n_tasks": len(tasks),
            "n_cells": n_cell, "seeds": seeds,
            "base_harness": HARNESS_LABELS["stdout"],
            "echo_harness": HARNESS_LABELS["echo"],
            "pairing": "manifest.seed; a seed missing from either arm is "
                       "dropped from both",
        },
        "tasks": per_task,
        "pooled": {
            "n_cells": n_cell,
            "base_passes": base_pass, "echo_passes": echo_pass,
            "base_pass_at_1": round(base_pass / n_cell, 4) if n_cell else None,
            "echo_pass_at_1": round(echo_pass / n_cell, 4) if n_cell else None,
            "delta": (round((echo_pass - base_pass) / n_cell, 4)
                      if n_cell else None),
            "base_pass_at_1_ci95": ([round(x, 4)
                                     for x in wilson_interval(base_pass, n_cell)]
                                    if n_cell else None),
            "echo_pass_at_1_ci95": ([round(x, 4)
                                     for x in wilson_interval(echo_pass, n_cell)]
                                    if n_cell else None),
            "cells": {"both_pass": n_cell - base_only - echo_only
                      - sum(per_task[t]["cells"]["both_fail"] for t in tasks),
                      "base_only": base_only, "echo_only": echo_only,
                      "both_fail": sum(per_task[t]["cells"]["both_fail"]
                                       for t in tasks)},
            "mcnemar_exact_p": round(_mcnemar_exact(base_only, echo_only), 4),
            "per_seed_delta": per_seed_delta,
            "per_seed_delta_mean": (round(delta_mean, 4)
                                    if delta_mean is not None else None),
            "per_seed_delta_sd": round(delta_sd, 4) if delta_sd is not None else None,
        },
        "notes": [
            "the two arms differ only in the observation contract (stdout vs "
            "stdout + final bare expression); model, seed, temperature, "
            "num_predict and max_turns are identical per pair",
            "the exact McNemar test is on discordant cells; cells inside one "
            "seed share a task list, so the pooled reading is approximate and "
            "the per-task rows are primary",
            "per_seed_delta is the score difference in tasks per sample; its "
            "sd is the arm-difference variance, not the solver's variance",
            "synthetic lab tasks, one 14B local model, one temperature, no "
            "human labels: this is a harness effect on this decoder, not a "
            "claim about verifier validity; Just et al. ceiling untouched",
        ],
    }


def _mcnemar_exact(base_only: int, echo_only: int) -> float:
    """Two-sided exact binomial McNemar p-value on the discordant pairs."""
    from math import comb
    n = base_only + echo_only
    if n == 0:
        return 1.0
    m = min(base_only, echo_only)
    tail = sum(comb(n, x) for x in range(0, m + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _last_statement_kind(code: str) -> str:
    """Shape of the final top-level statement (stdout is the only channel)."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return "unparseable"
    if not tree.body:
        return "empty"
    last = tree.body[-1]
    if isinstance(last, ast.Expr):
        val = last.value
        if isinstance(val, ast.Call) and isinstance(val.func, ast.Name) \
                and val.func.id == "print":
            return "print"
        return "bare_expression"
    return "statement"


def _fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Exact Fisher test for [[a, b], [c, d]]; stdlib only (math.comb)."""
    from math import comb
    n, r1, c1 = a + b + c + d, a + b, a + c
    if n == 0:
        return 1.0

    def prob(x: int) -> float:
        return (comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1))

    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    observed = prob(a)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1)
                        if prob(x) <= observed + 1e-12))


def _unique_records(archives: List[Dict[str, Any]]):
    """Collapse byte-identical trajectories; replicas are not independent."""
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    for arc in archives:
        temp = (arc.get("manifest") or {}).get("temperature")
        for rec in arc.get("records") or []:
            key = (rec.get("task_id"), _turn_signature(rec))
            groups.setdefault(key, []).append({"temperature": temp, "rec": rec})
    return [{"task_id": tid, "signature": sig, "copies": cells,
             "rec": cells[0]["rec"]} for (tid, sig), cells in sorted(groups.items())]


def _failure_mode(rec: Dict[str, Any], passed: bool) -> str:
    if passed:
        return "pass"
    snippets = task_snippets(rec)
    if not snippets:
        return "no_run_python"
    last = snippets[-1]
    answered = rec.get("final_answer") is not None
    if not answered:
        if not last.get("ok") and _last_statement_kind(last.get("code")) == "unparseable":
            return "no_submit_truncated_tool_error"
        return "no_submit_turn_budget"
    if not last.get("ok"):
        return "tool_error_unresolved"
    if not (last.get("stdout") or ""):
        return "empty_tool_output"
    ref = str(rec.get("reference") or "")
    if "," in ref:
        want = len(ref.split(","))
        got = len(str(rec.get("final_answer")).split(","))
        if want != got:
            return "length_mismatch"
    return "evidence_present_wrong_answer"


def failure_report(archives: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify every archived agent task-run by its observable failure mode.

    Round 18 named one mechanism -- stdout-only tool results plus a bare final
    expression -- as the source of the two verdict flips.  That is a claim
    about *why runs fail*, and it is testable offline: classify all archived
    runs, then cross-tabulate the empty-tool-output predictor against failure.
    Duplicate replicas are collapsed before any rate is computed, because
    seven byte-identical copies are one observation, not seven.
    """
    unique = _unique_records(archives)
    cells = []
    for u in unique:
        rec = u["rec"]
        passed = bool(grade_answer(rec.get("reference"),
                                   rec.get("final_answer")))
        snippets = task_snippets(rec)
        last = snippets[-1] if snippets else None
        ref = str(rec.get("reference") or "")
        cells.append({
            "task_id": u["task_id"],
            "copies": len(u["copies"]),
            "temperatures": sorted({c["temperature"] for c in u["copies"]}),
            "passed": passed,
            "failure_mode": _failure_mode(rec, passed),
            "final_channel": rec.get("final_channel"),
            "n_turns": len(rec.get("turns") or []),
            "n_run_python": len(snippets),
            "n_submit": sum(1 for t in rec.get("tool_calls") or []
                            if t.get("name") == "submit_answer"),
            "last_statement_kind": (_last_statement_kind(last.get("code"))
                                    if last else "none"),
            "last_tool_ok": None if last is None else bool(last.get("ok")),
            "last_stdout_len": (len(last.get("stdout") or "")
                                if last else 0),
            "n_submitted_elems": (len(str(rec.get("final_answer")).split(","))
                                  if "," in ref and rec.get("final_answer")
                                  is not None else None),
            "n_reference_elems": len(ref.split(",")) if "," in ref else None,
        })

    def _modes(rows):
        out: Dict[str, int] = {}
        for r in rows:
            out[r["failure_mode"]] = out.get(r["failure_mode"], 0) + 1
        return dict(sorted(out.items()))

    def _predictor(flag):
        fails = [c for c in cells if not c["passed"]]
        fail_flag = sum(1 for c in fails if flag(c))
        fail_rest = len(fails) - fail_flag
        pass_flag = sum(1 for c in cells if c["passed"] and flag(c))
        pass_rest = sum(1 for c in cells if c["passed"]) - pass_flag
        n_flag = fail_flag + pass_flag
        return {
            "n_flag": n_flag,
            "table_[[fail_flag, pass_flag], [fail_rest, pass_rest]]":
                [[fail_flag, pass_flag], [fail_rest, pass_rest]],
            "fail_rate_given_flag": (round(fail_flag / n_flag, 4)
                                     if n_flag else None),
            "fail_rate_without_flag": (round(fail_rest / (fail_rest + pass_rest), 4)
                                       if (fail_rest + pass_rest) else None),
            "fisher_two_sided_p": round(_fisher_two_sided(
                fail_flag, pass_flag, fail_rest, pass_rest), 4),
        }

    per_task: Dict[str, Dict[str, int]] = {}
    for c in cells:
        b = per_task.setdefault(c["task_id"], {"cells": 0, "passed": 0})
        b["cells"] += 1
        b["passed"] += int(c["passed"])
    n_cells = sum(len(a.get("records") or []) for a in archives)
    n_unique = len(cells)
    n_unique_pass = sum(1 for c in cells if c["passed"])
    manifests = [a.get("manifest") or {} for a in archives]
    return {
        "kind": "vci-agent-failure-modes", "version": AGENT_TRACE_VERSION,
        "design": {
            "n_archives": len(archives), "n_cells": n_cells,
            "n_unique_cells": n_unique,
            "duplicate_factor": (round(n_cells / n_unique, 3)
                                 if n_unique else None),
            "temperatures": sorted({m.get("temperature") for m in manifests
                                    if m.get("temperature") is not None}),
            "seeds": [m.get("seed") for m in manifests],
            "model_digests": sorted({m.get("model_digest") for m in manifests
                                     if m.get("model_digest")}),
            "pass_at_1_all_cells": (round(sum(
                1 for c in cells for _ in range(c["copies"]) if c["passed"])
                / n_cells, 4) if n_cells else None),
            "pass_at_1_unique": round(n_unique_pass / n_unique, 4)
            if n_unique else None,
        },
        "per_task": per_task,
        "modes": {"unique_cells": _modes(cells),
                  "all_cells": _modes([
                      {"failure_mode": c["failure_mode"]}
                      for c in cells for _ in range(c["copies"])])},
        "predictor": {
            "empty_last_tool_output": _predictor(
                lambda c: c["last_statement_kind"] == "bare_expression"
                and c["last_stdout_len"] == 0),
            "bare_final_expression": _predictor(
                lambda c: c["last_statement_kind"] == "bare_expression"),
        },
        "cells": cells,
        "notes": [
            "a cell is one (task, trajectory) pair; byte-identical replicas are "
            "collapsed before rates, so R17's 42 runs contribute 6 observations",
            "failure_mode is descriptive, not causal: length_mismatch means the "
            "submitted list length differs from the reference, not that the "
            "answer was computed wrongly",
            "the predictor table is two-by-two over unique cells; a single "
            "empty-output cell moves the fail rate by more than ten points",
            "synthetic lab tasks, one model, no human labels: the Just et al. "
            "ceiling is untouched",
        ],
    }


def echo_replay(archives: List[Dict[str, Any]], timeout_s: float = 15.0) -> Dict[str, Any]:
    """Counterfactual: replay failing trajectories under a REPL-echo harness.

    Same subprocess protocol, but the final bare expression of each snippet is
    evaluated and its value returned alongside stdout.  For a failing run,
    this answers a narrow question: *was the correct value available at the
    model's last tool call under a harness that echoes it?*  It does **not**
    predict what the model would have submitted, because a different
    observation would change the rest of the trajectory; the pooled delta is
    therefore an upper bound, stated as such.
    """
    unique = _unique_records(archives)
    pass_unique = sum(1 for u in unique
                      if grade_answer(u["rec"].get("reference"),
                                      u["rec"].get("final_answer")))
    rows = []
    for u in unique:
        rec = u["rec"]
        if grade_answer(rec.get("reference"), rec.get("final_answer")):
            continue
        session = Session(timeout_s=timeout_s, runner=_ECHO_RUNNER)
        last = None
        try:
            for snip in task_snippets(rec):
                last = session.run(snip.get("code") or "")
        finally:
            session.kill()
        echo = last.get("value") if last else None
        echo_ok = bool(echo is not None
                       and grade_answer(rec.get("reference"), echo))
        rows.append({
            "task_id": u["task_id"],
            "copies": len(u["copies"]),
            "temperatures": sorted({c["temperature"] for c in u["copies"]}),
            "failure_mode": _failure_mode(rec, False),
            "n_snippets": len(task_snippets(rec)),
            "last_tool_ok": None if last is None else bool(last.get("ok")),
            "last_error": None if last is None else last.get("error"),
            "last_stdout_len": (len(last.get("stdout") or "")
                                if last else 0),
            "last_statement_kind": (_last_statement_kind(
                task_snippets(rec)[-1].get("code"))
                if task_snippets(rec) else "none"),
            "echo_value": echo,
            "echo_grades_correct": echo_ok,
        })
    recoverable = [r for r in rows if r["echo_grades_correct"]]
    unreplayable = [r for r in rows if r["last_tool_ok"] is False]
    n_unique = len(unique)
    return {
        "kind": "vci-agent-echo-replay", "version": AGENT_TRACE_VERSION,
        "design": {
            "n_unique_cells": n_unique, "n_unique_failing": len(rows),
            "harness": "production protocol + eval of the final bare "
                       "expression per snippet; stdout still captured",
            "scope": "offline replay of archived code only; no model calls",
        },
        "pooled": {
            "n_unique_failing": len(rows),
            "n_echo_recoverable": len(recoverable),
            "recoverable_tasks": [r["task_id"] for r in recoverable],
            "n_unreplayable": len(unreplayable),
            "unreplayable_tasks": [r["task_id"] for r in unreplayable],
            "pass_at_1_unique_before": round(pass_unique / n_unique, 4)
            if n_unique else None,
            "pass_at_1_unique_after_echo_upper_bound":
                round((pass_unique + len(recoverable)) / n_unique, 4)
                if n_unique else None,
            "delta_upper_bound": round(len(recoverable) / n_unique, 4)
            if n_unique else None,
        },
        "rows": rows,
        "notes": [
            "the echo run changes what the model would observe, so "
            "delta_upper_bound assumes the rest of the trajectory is unchanged",
            "unreplayable = the archived snippet does not parse on replay "
            "(truncated by num_predict), so its value cannot be recovered",
            "a row with last_statement_kind=statement/print has no echoed "
            "value even though stdout was non-empty: echo only adds one channel",
            "side effects are bounded by round 14's scanner (0/450 signatures) "
            "and every replay runs in a fresh 15 s subprocess",
        ],
    }


def grade_probes(tasks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Author probes for ``grade_answer`` and report its accept/reject rates."""
    tasks = AGENT_TASKS if tasks is None else tasks
    rows: List[Dict[str, Any]] = []
    for t in tasks:
        ref, kind = t["reference"], t.get("kind")
        rows.append({"task_id": t["task_id"], "kind": kind,
                     "label": "identity", "cls": "identity",
                     "answer": ref, "ref": ref, "guess": "accept"})
        for p in _equiv_probes(ref, kind):
            rows.append({"task_id": t["task_id"], "kind": kind,
                         "label": p["label"], "cls": "equivalence",
                         "answer": p["answer"], "ref": ref,
                         "guess": p["guess"]})
        for p in _defect_probes(ref, kind):
            rows.append({"task_id": t["task_id"], "kind": kind,
                         "label": p["label"], "cls": "defect",
                         "answer": p["answer"], "ref": ref,
                         "guess": p["guess"]})
        for p in _packaging_probes(ref, kind):
            rows.append({"task_id": t["task_id"], "kind": kind,
                         "label": p["label"], "cls": "packaging",
                         "answer": p["answer"], "ref": ref,
                         "guess": p["guess"]})
    for r in rows:
        r["accepted"] = bool(grade_answer(r["ref"], r["answer"]))
    by_cls: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        b = by_cls.setdefault(r["cls"], {"n": 0, "accepted": 0})
        b["n"] += 1
        b["accepted"] += int(r["accepted"])
    def _rate(cls, want_accept):
        b = by_cls.get(cls, {"n": 0, "accepted": 0})
        good = b["accepted"] if want_accept else b["n"] - b["accepted"]
        return None if not b["n"] else round(good / b["n"], 4)
    return {
        "kind": "vci-agent-grader-probes", "version": AGENT_TRACE_VERSION,
        "grader": "grade_answer: relative 1e-9 for numbers, whitespace-"
                  "insensitive equality for lists",
        "n_tasks": len(tasks), "n_probes": len(rows),
        "pooled": {
            "identity_control_pass": _rate("identity", True),
            "equivalence_accept_rate": _rate("equivalence", True),
            "defect_reject_rate": _rate("defect", False),
            "packaging_accepted": by_cls.get("packaging", {}).get("accepted", 0),
            "packaging_n": by_cls.get("packaging", {}).get("n", 0),
            "counts": by_cls,
        },
        "false_rejects": [r for r in rows
                          if r["cls"] == "equivalence" and not r["accepted"]],
        "false_accepts": [r for r in rows
                          if r["cls"] == "defect" and r["accepted"]],
        "rows": rows,
    }
