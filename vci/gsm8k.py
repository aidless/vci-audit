"""GSM8K helpers for a CPU-budgeted multi-sample run.

GSM8K (Cobbe et al., 2021) is public, MIT-licensed, has a programmatic exact-match
reference answer, and each problem is short.  This module only contains the pure,
testable pieces: answer extraction, prompt building and deterministic task selection.
The runner that talks to a local ollama server lives in
``examples/gsm8k_multisample.py``.
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_TEST_SIZE = 1319


def gold_answer(answer_field: str) -> Optional[str]:
    """Final number of the GSM8K ``answer`` field (``... #### 18``)."""
    if not isinstance(answer_field, str):
        return None
    tail = answer_field.split("####")[-1]
    m = _NUM.findall(tail.replace(",", ""))
    return m[-1] if m else None


def extract_prediction(text: str) -> Optional[str]:
    """Last number in the model output, or ``None`` if it printed none."""
    if not isinstance(text, str):
        return None
    m = _NUM.findall(text.replace(",", ""))
    return m[-1] if m else None


def is_correct(prediction: Optional[str], gold: Optional[str]) -> bool:
    """Exact numeric match after stripping trailing ``.0``."""
    if prediction is None or gold is None:
        return False

    def norm(x: str) -> str:
        try:
            f = float(x)
        except ValueError:
            return x
        return str(int(f)) if f == int(f) else repr(f)

    return norm(prediction) == norm(gold)


def build_prompt(question: str) -> str:
    """Answer-only prompt: keeps generation short enough for a CPU-only box."""
    return ("Answer only with the final number.\n"
            f"Problem: {question}\nAnswer:")


def tasks_with_passes(records: Iterable[Dict[str, Any]],
                      min_passes: int = 1) -> List[str]:
    """Task ids that passed at least ``min_passes`` times in a pilot file.

    Used to build a difficulty-calibrated subset: GSM8K is too hard for a 0.5B
    model in answer-only mode, so an unfiltered slice is all-fail and the
    pass@k / pass^k curves are degenerate.  This is deliberately a naive
    difficulty filter (selection happens on the test split, so the absolute
    score is not a GSM8K benchmark number -- only the estimator gap is read).
    """
    counts: Dict[str, int] = {}
    for rec in records:
        tid = rec.get("task_id")
        if not tid:
            continue
        counts.setdefault(tid, 0)
        if rec.get("status") == "pass":
            counts[tid] += 1
    return sorted(tid for tid, c in counts.items() if c >= min_passes)


def select_tasks(rows: Sequence[Dict[str, Any]], n: int,
                 test_size: int = _TEST_SIZE) -> List[Dict[str, Any]]:
    """Deterministic stride selection over the official test file.

    No difficulty-based filtering: a stride is reproducible and does not let the
    runner pick an easier or harder subset after seeing results.
    """
    if n <= 0 or not rows:
        return []
    stride = max(1, test_size // n)
    picked = []
    for k in range(n):
        i = k * stride
        if i >= len(rows):
            break
        row = rows[i]
        picked.append({
            "task_id": f"gsm8k-test-{i:04d}",
            "index": i,
            "question": row["question"],
            "gold": gold_answer(row["answer"]),
        })
    return picked
