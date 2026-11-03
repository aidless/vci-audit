"""Blind annotation CLI.

The annotator sees a task prompt and one candidate answer, nothing else.  The
sheet's ``defect`` / ``failure_class`` columns (if any) are never displayed, and
the reference values are never displayed; only unit *names* are kept in the
sheet file for later bookkeeping, not on screen.

Commands: ``y`` pass, ``n`` fail, ``s`` undecidable, ``k`` skip, ``q`` save & quit.
Answers are appended to ``labels.csv`` immediately, so an interrupted session
resumes where it stopped (already-labelled rows are filtered out).

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


def run(sheet_path: str, out_path: str, round_no: int = 1,
        annotator: str = "anon", shuffle_seed: Optional[int] = None,
        limit: int = 0, redo: bool = False,
        ask: Callable[[str], str] = input,
        say: Callable[[str], Any] = print) -> Dict[str, Any]:
    rows = load_sheet(sheet_path)
    if limit:
        rows = rows[:limit]
    done = load_answers(out_path)
    pending = [r for r in rows if redo or r["row_id"] not in done]
    if shuffle_seed is not None:
        random.Random(int(shuffle_seed)).shuffle(pending)
    total = len(rows)
    progress = total - len(pending)
    skipped = 0
    answered = 0

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
                        "covered": progress, "total": total, "quit": True}
            say("please answer y / n / s (k=skip, q=quit)")

    say(f"done: {answered} answered, {skipped} skipped, {progress}/{total} covered "
        f"(existing answers in {out_path}: {len(load_answers(out_path))})")
    return {"answered": answered, "skipped": skipped,
            "covered": progress, "total": total, "quit": False}
