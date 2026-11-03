"""Round 6: sample *real* model outputs and measure verifier behaviour on them.

Every other number in this repository comes from authored probes (synthetic
mutants).  This module replaces the authored defect distribution with the
observed failure distribution of an actual (small, local) model:

  1. generate fresh seed tasks (a seed disjoint from the audit's),
  2. ask a local model served by ollama to solve them,
  3. parse the reply into the family's payload format,
  4. run the family's own ``verify()`` on the parsed payload,
  5. emit a per-unit grading sheet for human adjudication.

The human labels are then merged by :func:`analyze` to compute verifier
TPR/TNR and Cohen's kappa *against human truth on real outputs* — the one
measurement that is not capped by the Just et al. (FSE 2014) ceiling, because
the errors are the model's own, not ours.

Nothing here calls the network beyond the local ollama host, and the analysis
path is fully offline so tests never touch a server.
"""
import json
import random
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .audit import family_seed
from .metrics import cohen_kappa, wilson_interval
from .registry import INDEX, by_name
from .schema import Candidate

REALFAIL_VERSION = "1.0"

DEFAULT_FAMILIES = [
    "arith_expression",
    "unit_convert",
    "template_render",
    "log_field_extraction",
    "regex_construct",
    "sql_result",
]

DEFAULT_MODEL = "evalsft-qwen25-05b:latest"
DEFAULT_HOST = "http://localhost:11434"

_FMT_LIST = ("\n\nAnswer with ONLY a JSON object of the form "
             "{\"answers\": [a1, a2, ...]} with exactly %d entries in order. "
             "No prose, no code fences.")
_FMT_MAP = ("\n\nReturn ONLY the JSON object described above. "
            "No prose, no code fences.")


# --------------------------------------------------------------------- prompt
def build_prompt(task, family) -> str:
    if family.payload_kind == "list":
        return task.prompt + (_FMT_LIST % task.n_items)
    return task.prompt + _FMT_MAP


# --------------------------------------------------------------------- parsing
def _strip_fences(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.DOTALL)
    return m.group(1) if m else t


def _balanced(text: str, start: int) -> Optional[str]:
    """Return the balanced bracket slice starting at ``start`` or ``None``."""
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _json_candidates(text: str) -> List[str]:
    t = _strip_fences(text)
    out = [t]
    for i, ch in enumerate(t):
        if ch in "{[":
            s = _balanced(t, i)
            if s is not None:
                out.append(s)
    return out


def parse_payload(text: str, payload_kind: str) -> Tuple[Any, str]:
    """Best-effort extraction of a payload from raw model text.

    Returns ``(payload, status)`` where status is one of ``ok``,
    ``no_json``, ``wrong_shape`` or ``bad_answers``.  ``payload`` is ``None``
    unless status is ``ok``.
    """
    parsed: List[Any] = []
    for cand in _json_candidates(text):
        try:
            parsed.append(json.loads(cand))
        except (ValueError, TypeError):
            continue
    if not parsed:
        return None, "no_json"
    if payload_kind == "mapping":
        for obj in parsed:
            if isinstance(obj, dict) and obj:
                return obj, "ok"
        return None, "wrong_shape"
    # list payload: accept {"answers": [...]} or a bare list
    for obj in parsed:
        if isinstance(obj, dict) and isinstance(obj.get("answers"), list):
            return {"answers": obj["answers"]}, "ok"
    for obj in parsed:
        if isinstance(obj, list) and obj:
            return {"answers": obj}, "ok"
    if any(isinstance(o, dict) for o in parsed):
        return None, "bad_answers"
    return None, "wrong_shape"


# ---------------------------------------------------------------------- ollama
def ollama_generate(host: str, model: str, prompt: str, seed: int,
                    max_tokens: int, timeout_s: float) -> Dict[str, Any]:
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "seed": seed, "num_predict": max_tokens},
    }
    req = urllib.request.Request(
        host.rstrip("/") + "/api/generate", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {
        "text": data.get("response", ""),
        "wall_s": time.perf_counter() - t0,
        "eval_count": data.get("eval_count"),
        "eval_duration_s": (data.get("eval_duration") or 0) / 1e9,
    }


def ollama_model_digest(host: str, model: str) -> Optional[str]:
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags",
                                    timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models", []):
            if m.get("name") == model:
                return m.get("digest")
    except (OSError, ValueError, urllib.error.URLError):
        pass
    return None


# ------------------------------------------------------------------------- run
def run(families, n_tasks: int, seed: int, model: str, host: str,
        max_tokens: int = 1024, timeout_s: float = 120.0) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    for fam in families:
        rng = random.Random(family_seed(seed, INDEX[fam.name]))
        tasks = fam.generate(n_tasks, rng)
        for task in tasks:
            prompt = build_prompt(task, fam)
            rec: Dict[str, Any] = {
                "family": fam.name, "task_id": task.task_id,
                "n_units": task.n_items, "prompt_chars": len(prompt),
            }
            try:
                gen = ollama_generate(host, model, prompt, seed=seed,
                                      max_tokens=max_tokens, timeout_s=timeout_s)
                rec.update({
                    "raw_response": gen["text"],
                    "wall_s": round(gen["wall_s"], 3),
                    "eval_count": gen["eval_count"],
                    "eval_duration_s": round(gen["eval_duration_s"], 3),
                })
            except Exception as ex:  # network/timeout is a run failure, not a defect
                rec["error"] = f"{type(ex).__name__}: {ex}"
                records.append(rec)
                continue
            payload, status = parse_payload(gen["text"], fam.payload_kind)
            rec["parse_status"] = status
            rec["payload"] = payload
            cand = Candidate(cand_id=f"{task.task_id}-real", task_id=task.task_id,
                             family=fam.name, payload=payload,
                             defect="real_model_output", note="ollama sample")
            verdict = fam.verify(task, cand)
            rec["verdict"] = {
                "passed": verdict.passed,
                "score": round(verdict.score, 6),
                "evidence": verdict.evidence,
            }
            records.append(rec)
    return {
        "manifest": {
            "kind": "vci-realfail",
            "version": REALFAIL_VERSION,
            "model": model,
            "model_digest": ollama_model_digest(host, model),
            "host": host,
            "seed": seed,
            "n_tasks": n_tasks,
            "families": [f.name for f in families],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "date": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        },
        "records": records,
    }


# ------------------------------------------------------------------- sheet
def _numbered_lines(prompt: str) -> Dict[int, str]:
    out = {}
    for line in prompt.splitlines():
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if m:
            out[int(m.group(1))] = m.group(2).strip()
    return out


def _unit_context(family: str, task, item, prompt_q: Dict[int, str]) -> str:
    unit = item["unit"]
    if family == "arith_expression":
        return item.get("expr", "")
    if family == "unit_convert":
        return f"{item.get('value')} {item.get('src')} -> {item.get('dst')}"
    if family == "template_render":
        idx = int(unit[1:]) - 1
        tpl_lines = [ln.strip() for ln in task.prompt.splitlines()[1:]
                     if ln.strip() and not ln.strip().startswith("data =")]
        spec_line = tpl_lines[idx] if 0 <= idx < len(tpl_lines) else ""
        return json.dumps({"template": spec_line, "data": task.meta.get("data")},
                          ensure_ascii=False, default=str)
    if family == "log_field_extraction":
        rec_no = int(unit.split(".")[0][1:])
        field = unit.split(".")[1]
        lines = task.meta.get("lines", [])
        line = lines[rec_no - 1] if 0 < rec_no <= len(lines) else ""
        return json.dumps({"line": line, "field": field}, ensure_ascii=False)
    if family == "regex_construct":
        idx = int(unit[1:]) - 1
        specs = task.meta.get("specs", [])
        spec = specs[idx] if 0 <= idx < len(specs) else {}
        return json.dumps({"desc": prompt_q.get(idx + 1, ""),
                           "match": spec.get("pos"), "must_not": spec.get("neg")},
                          ensure_ascii=False, default=str)
    if family == "sql_result":
        idx = int(unit[1:]) - 1
        qs = task.meta.get("questions", [])
        q = qs[idx] if 0 <= idx < len(qs) else {}
        return json.dumps({"question": prompt_q.get(idx + 1, ""),
                           "ref": q.get("ref"), "ordered": item.get("ordered")},
                          ensure_ascii=False, default=str)
    return ""


def emit_sheet(payload: Dict[str, Any], families_by_name) -> List[Dict[str, Any]]:
    """Flatten a run into one row per gradable unit for human adjudication."""
    rows: List[Dict[str, Any]] = []
    seed = payload["manifest"]["seed"]
    n_tasks = payload["manifest"]["n_tasks"]
    task_cache: Dict[str, Any] = {}
    for rec in payload["records"]:
        if "verdict" not in rec:
            continue
        fam_name = rec["family"]
        if fam_name not in task_cache:
            fam = families_by_name[fam_name]
            rng = random.Random(family_seed(seed, INDEX[fam_name]))
            task_cache[fam_name] = {t.task_id: t for t in fam.generate(n_tasks, rng)}
        task = task_cache[fam_name][rec["task_id"]]
        fam = families_by_name[fam_name]
        answers, _, _ = fam.extract_answers(task, rec["payload"])
        prompt_q = _numbered_lines(task.prompt)
        ev_by_unit = {e["unit"]: e for e in rec["verdict"]["evidence"]}
        for item in task.items:
            unit = item["unit"]
            ev = ev_by_unit.get(unit, {})
            rows.append({
                "row_id": f"{rec['task_id']}:{unit}",
                "family": fam_name,
                "task_id": rec["task_id"],
                "unit": unit,
                "context": _unit_context(fam_name, task, item, prompt_q),
                "reference": item.get("expected"),
                "model_answer": answers.get(unit),
                "verifier_ok": ev.get("ok"),
                "verifier_detail": ev.get("detail", ""),
            })
    return rows


# ------------------------------------------------------------------- analysis
def load_human_labels(path: str) -> Dict[str, Optional[bool]]:
    """Read ``row_id,human_label`` with label in {1, 0, u}."""
    import csv
    out: Dict[str, Optional[bool]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            lab = (row.get("human_label") or "").strip().lower()
            if lab == "1":
                out[row["row_id"]] = True
            elif lab == "0":
                out[row["row_id"]] = False
            elif lab in ("u", "undecidable", ""):
                out[row["row_id"]] = None
            else:
                raise ValueError(f"bad human_label {lab!r} for {row['row_id']}")
    return out


def analyze(payload: Dict[str, Any], labels: Dict[str, Optional[bool]],
            families_by_name) -> Dict[str, Any]:
    rows = emit_sheet(payload, families_by_name)
    merged = [r for r in rows if r["row_id"] in labels and
              labels[r["row_id"]] is not None]
    n_undecidable = sum(1 for r in rows
                        if labels.get(r["row_id"]) is None and r["row_id"] in labels)
    unlabeled = [r["row_id"] for r in rows if r["row_id"] not in labels]

    def cell(sub: List[Dict[str, Any]]) -> Dict[str, Any]:
        human = [bool(labels[r["row_id"]]) for r in sub]
        verif = [bool(r["verifier_ok"]) for r in sub]
        tp = sum(1 for h, v in zip(human, verif) if h and v)
        fn = sum(1 for h, v in zip(human, verif) if h and not v)
        tn = sum(1 for h, v in zip(human, verif) if not h and not v)
        fp = sum(1 for h, v in zip(human, verif) if not h and v)
        tpr = tp / (tp + fn) if tp + fn else None
        tnr = tn / (tn + fp) if tn + fp else None
        kap, po = cohen_kappa(human, verif) if sub else (None, None)
        return {
            "n": len(sub), "pos": tp + fn, "neg": tn + fp,
            "tp": tp, "fn": fn, "tn": tn, "fp": fp,
            "tpr": tpr, "tnr": tnr, "kappa": kap, "po": po,
            "tpr_ci": wilson_interval(tp, tp + fn) if tp + fn else None,
            "tnr_ci": wilson_interval(tn, tn + fp) if tn + fp else None,
            "false_accepts": [r["row_id"] for r in sub
                              if not labels[r["row_id"]] and r["verifier_ok"]],
            "false_rejects": [r["row_id"] for r in sub
                              if labels[r["row_id"]] and not r["verifier_ok"]],
        }

    per_family: Dict[str, Any] = {}
    for fam_name in payload["manifest"]["families"]:
        sub = [r for r in merged if r["family"] == fam_name]
        per_family[fam_name] = cell(sub)
    pooled = cell(merged)

    recs = payload["records"]
    scored = [r for r in recs if "verdict" in r]
    run_stats = {
        "n_tasks_run": len(recs),
        "n_errors": sum(1 for r in recs if "error" in r),
        "parse_fail": sum(1 for r in scored if r["parse_status"] != "ok"),
        "verifier_passed_tasks": sum(1 for r in scored if r["verdict"]["passed"]),
        "mean_wall_s": (round(sum(r["wall_s"] for r in scored) / len(scored), 3)
                        if scored else None),
        "mean_score": (round(sum(r["verdict"]["score"] for r in scored)
                             / len(scored), 4) if scored else None),
    }
    return {
        "run_stats": run_stats,
        "n_sheet_rows": len(rows),
        "n_labeled": len(merged),
        "n_undecidable": n_undecidable,
        "unlabeled": unlabeled,
        "per_family": per_family,
        "pooled": pooled,
    }
