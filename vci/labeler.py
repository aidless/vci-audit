"""Blind annotation CLI.

The annotator sees a task prompt and one candidate answer, nothing else.  The
sheet's ``defect`` / ``failure_class`` columns (if any) are never displayed, and
the reference values are never displayed; only unit *names* are kept in the
sheet file for later bookkeeping, not on screen.

Commands: ``y`` pass, ``n`` fail, ``s`` undecidable, ``k`` skip, ``q`` save & quit.
Answers are appended to ``labels.csv`` immediately, so an interrupted session
resumes where it stopped (already-labelled rows are filtered out).

Round 3 adds three things:

* ``--group-by-family``: present one family at a time, shuffled *within* the
  family, so the annotator does not silently switch criteria every row.
* ``--shuffle``: randomise the whole pending list (already available as
  ``shuffle_seed``; the CLI exposes it).
* qualifications: before the first answer, three calibration items with a
  protocol-defined answer.  A wrong answer prints the expected ruling and why,
  then continues -- the point is to surface a misread protocol, not to gate.

Run a second, re-ordered pass into ``labels_retest.csv`` to measure annotator
stability:

    python -m vci label --sheet annotations/blind.csv \
        --out annotations/labels_retest.csv --round 2 --shuffle-seed 99
"""
from __future__ import annotations

import csv
import os
import random
import time
from typing import Any, Callable, Dict, List, Optional

HEADER = ["row_id", "human_label", "round", "annotator", "timestamp"]
_ANSWERS = {"y": True, "n": False, "s": None}
_SHEET_FIELDS = ("row_id", "family", "task_prompt", "candidate")

#: Three protocol-boundary checks.  They are *not* part of labels.csv and never
#: touch the real sheet; they only calibrate the annotator on pass / fail /
#: undecidable before the first real row.
CALIBRATION: List[Dict[str, str]] = [
    {
        "id": "cal-1",
        "prompt": "Task: return the sum of the list [1, 2, 3].",
        "candidate": "6",
        "correct": "y",
        "why": "The answer is exactly the stated value; there is nothing to "
               "interpret. This is a pass.",
    },
    {
        "id": "cal-2",
        "prompt": "Task: return the mean rounded to 2 decimals: [1, 2, 4].",
        "candidate": "2.333",
        "correct": "n",
        "why": "The value is arithmetically right but violates the stated rounding "
               "precision. A stated output contract is part of the task, so this "
               "is a fail.",
    },
    {
        "id": "cal-3",
        "prompt": "Task: sort the records by score.",
        "candidate": "sorted descending by score",
        "correct": "s",
        "why": "The prompt never states a direction, so ascending and descending "
               "are both defensible. When the task text cannot decide the "
               "question, the ruling is undecidable -- do not guess.",
    },
]


def load_sheet(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(fh)]
    for row in rows:
        if not row.get("row_id"):
            raise ValueError(f"blind sheet {path} has a row without row_id")
    return rows


def load_answers(path: str) -> Dict[str, Dict[str, str]]:
    """``row_id -> last answer row``; later rows win, so re-labelling works."""
    out: Dict[str, Dict[str, str]] = {}
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("row_id"):
                    out[row["row_id"]] = row
    except FileNotFoundError:
        return {}
    return out


def _bar(done: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    filled = min(width, int(round(width * done / total)))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def format_entry(index: int, total: int, row: Dict[str, str],
                 skipped: int = 0, width: int = 24) -> str:
    """Render one blind row.  Only whitelisted sheet fields are shown."""
    head = (f"[{index}/{total}] {_bar(index - 1, total, width)} "
            f"family={row.get('family', '?')}  skipped={skipped}")
    return "\n".join([
        head,
        "-" * 72,
        row.get("task_prompt", "").rstrip(),
        "",
        "Candidate:",
        row.get("candidate", "").rstrip(),
        "",
        "  y = pass   n = fail   s = undecidable   k = skip   q = save & quit",
    ])


def run_qualification(ask: Callable[[str], str] = input,
                      say: Callable[[str], Any] = print) -> Dict[str, Any]:
    """Ask the three calibration items.  Wrong answers warn but never block."""
    say("qualification: 3 calibration items before the real sheet "
        "(wrong answers warn, they do not stop the session)")
    correct = 0
    wrong: List[str] = []
    for item in CALIBRATION:
        say("\n" + "-" * 72)
        say(item["prompt"])
        say("Candidate:\n" + item["candidate"])
        say("  y = pass   n = fail   s = undecidable")
        while True:
            key = (ask("> ") or "").strip().lower()
            if key in _ANSWERS:
                break
            say("please answer y / n / s")
        if key == item["correct"]:
            correct += 1
            say(f"correct ({key})")
        else:
            wrong.append(item["id"])
            say(f"WRONG: expected '{item['correct']}', not '{key}'. "
                f"{item['why']}")
    say(f"\nqualification: {correct}/{len(CALIBRATION)} correct"
        + (f"; revisit the protocol for {', '.join(wrong)}" if wrong else ""))
    return {"correct": correct, "total": len(CALIBRATION), "wrong": wrong}


def append_answer(path: str, row_id: str, value: Optional[bool],
                  round_no: int, annotator: str,
                  timestamp: Optional[str] = None) -> None:
    new = not os.path.exists(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    label = "undecidable" if value is None else ("1" if value else "0")
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        if new:
            writer.writeheader()
        writer.writerow({
            "row_id": row_id,
            "human_label": label,
            "round": str(round_no),
            "annotator": annotator,
            "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%S"),
        })


def order_rows(rows: List[Dict[str, str]], shuffle_seed: Optional[int] = None,
               group_by_family: bool = False) -> List[Dict[str, str]]:
    """Order the pending rows.

    ``group_by_family`` keeps one family together and shuffles *within* it, so
    criteria change rarely; the family order is shuffled too.  Otherwise the
    whole list is shuffled when a seed is given.  With no seed and no grouping
    the sheet order is preserved (resume becomes a stable, resumable sequence).
    """
    if group_by_family:
        rng = random.Random(0 if shuffle_seed is None else int(shuffle_seed))
        groups: Dict[str, List[Dict[str, str]]] = {}
        for r in rows:
            groups.setdefault(r.get("family", ""), []).append(r)
        names = sorted(groups)
        rng.shuffle(names)
        out: List[Dict[str, str]] = []
        for name in names:
            bucket = list(groups[name])
            rng.shuffle(bucket)
            out.extend(bucket)
        return out
    if shuffle_seed is not None:
        out = list(rows)
        random.Random(int(shuffle_seed)).shuffle(out)
        return out
    return list(rows)


def run(sheet_path: str, out_path: str, round_no: int = 1,
        annotator: str = "anon", shuffle_seed: Optional[int] = None,
        limit: int = 0, redo: bool = False,
        ask: Callable[[str], str] = input,
        say: Callable[[str], Any] = print,
        group_by_family: bool = False,
        qualification: bool = False) -> Dict[str, Any]:
    rows = load_sheet(sheet_path)
    if limit:
        rows = rows[:limit]
    done = load_answers(out_path)
    pending = [r for r in rows if redo or r["row_id"] not in done]
    pending = order_rows(pending, shuffle_seed=shuffle_seed,
                         group_by_family=group_by_family)
    total = len(rows)
    progress = total - len(pending)
    skipped = 0
    answered = 0
    qual: Optional[Dict[str, Any]] = None
    if qualification and pending:
        qual = run_qualification(ask=ask, say=say)

    for row in pending:
        say(format_entry(progress + 1, total, row, skipped))
        while True:
            key = (ask("> ") or "").strip().lower()
            if key in _ANSWERS:
                append_answer(out_path, row["row_id"], _ANSWERS[key], round_no, annotator)
                progress += 1
                answered += 1
                break
            if key in ("k", ""):
                progress += 1
                skipped += 1
                break
            if key == "q":
                say(f"stopped: {answered} answered, {skipped} skipped this session, "
                    f"{progress}/{total} covered. Answers are saved in {out_path}.")
                return {"answered": answered, "skipped": skipped,
                        "covered": progress, "total": total, "quit": True,
                        "qualification": qual}
            say("please answer y / n / s (k=skip, q=quit)")

    say(f"done: {answered} answered, {skipped} skipped, {progress}/{total} covered "
        f"(existing answers in {out_path}: {len(load_answers(out_path))})")
    return {"answered": answered, "skipped": skipped,
            "covered": progress, "total": total, "quit": False,
            "qualification": qual}
