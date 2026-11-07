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

SESSION_FATAL = ("SessionDead", "SessionTimeout", "SessionDied", "SessionDesync")


class Session:
    """A persistent Python subprocess; state survives across run() calls."""

    def __init__(self, timeout_s: float = 15.0):
        self.proc = subprocess.Popen(
            [sys.executable, "-I", "-c", _SESSION_RUNNER],
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
                max_tokens: int, timeout_s: float) -> Dict[str, Any]:
    body = {"model": model, "messages": messages, "stream": False,
            "tools": TOOLS,
            "options": {"temperature": 0.0, "seed": seed,
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
             max_turns: int = 6) -> Dict[str, Any]:
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
                                    "error": res.get("error")})
                messages.append({
                    "role": "user",
                    "content": "run_python result: " + json.dumps({
                        "ok": res.get("ok"),
                        "stdout": (res.get("stdout")
                                   or "")[-TOOL_STDOUT_LIMIT:],
                        "error": res.get("error")})})
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
                       timeout_s: float) -> Callable:
    def respond(messages):
        return ollama_chat(host, model, messages, seed, max_tokens, timeout_s)
    return respond


def run(model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST,
        n_tasks: int = 6, seed: int = DEFAULT_SEED, max_turns: int = 6,
        num_predict: int = 448, timeout_s: float = 600.0,
        session_timeout_s: float = 15.0, out_path: Optional[str] = None,
        responder: Optional[Callable] = None,
        task_ids: Optional[List[str]] = None) -> Dict[str, Any]:
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
        "host": host, "seed": seed, "temperature": 0.0,
        "num_predict": num_predict, "max_turns": max_turns,
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
        session = Session(timeout_s=session_timeout_s)
        t0 = time.perf_counter()
        resp = responder if responder is not None else _default_responder(
            model=model, host=host, seed=seed, max_tokens=num_predict,
            timeout_s=timeout_s)
        try:
            result = run_task(task, session, resp, max_turns=max_turns)
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
