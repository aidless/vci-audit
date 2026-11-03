"""Blind-label CLI: resume, key mapping, no label leakage, progress counts."""
import csv

import pytest

from vci import labeler


def _sheet(tmp_path, rows):
    path = tmp_path / "blind.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["row_id", "family", "task_prompt",
                                           "reference_answer", "candidate",
                                           "human_label", "defect",
                                           "failure_class", "expectation"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(path)


def _answers(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["row_id"]: r["human_label"] for r in csv.DictReader(fh)}


ROWS = [
    {"row_id": "a-01", "family": "regex_construct", "task_prompt": "Write a regex",
     "reference_answer": '["pattern"]', "candidate": '"^[a-z]+$"',
     "human_label": "", "defect": "semantic_equivalent",
     "failure_class": "", "expectation": "accept"},
    {"row_id": "a-02", "family": "regex_construct", "task_prompt": "Write a regex",
     "reference_answer": '["pattern"]', "candidate": '"["',
     "human_label": "", "defect": "malformed",
     "failure_class": "silent_partial", "expectation": "reject"},
    {"row_id": "a-03", "family": "regex_construct", "task_prompt": "Write a regex",
     "reference_answer": '["pattern"]', "candidate": '"a|b"',
     "human_label": "", "defect": "overfit_to_tests",
     "failure_class": "overfit_to_tests", "expectation": "reject"},
]


def test_render_never_shows_the_true_label_or_defect_class():
    row = dict(ROWS[1], _hidden="reject")
    for key in ("defect", "failure_class", "expectation", "human_label"):
        assert row[key] in ("malformed", "silent_partial", "reject", "")
    text = labeler.format_entry(1, 3, row)
    assert "malformed" not in text
    assert "failure_class" not in text and "expectation" not in text
    assert text.count("Candidate:") == 1
    assert "[1/3]" in text


def test_labels_are_appended_and_mapped_y_n_s(tmp_path):
    sheet = _sheet(tmp_path, ROWS)
    out = str(tmp_path / "labels.csv")
    inputs = iter(["y", "n", "s"])
    stats = labeler.run(sheet, out, ask=lambda _: next(inputs), say=lambda *_: None)
    assert stats["answered"] == 3 and stats["quit"] is False
    assert _answers(out) == {"a-01": "1", "a-02": "0", "a-03": "undecidable"}


def test_skip_is_not_written_and_can_be_resumed(tmp_path):
    sheet = _sheet(tmp_path, ROWS)
    out = str(tmp_path / "labels.csv")
    first = iter(["y", "k", "q"])
    s1 = labeler.run(sheet, out, ask=lambda _: next(first), say=lambda *_: None)
    assert s1 == {"answered": 1, "skipped": 1, "covered": 2, "total": 3,
                  "quit": True, "qualification": None}
    assert _answers(out) == {"a-01": "1"}  # k and q write nothing

    second = iter(["n", "s"])
    s2 = labeler.run(sheet, out, ask=lambda _: next(second), say=lambda *_: None)
    assert s2["answered"] == 2
    assert _answers(out) == {"a-01": "1", "a-02": "0", "a-03": "undecidable"}


def test_resume_skips_already_labelled_rows(tmp_path):
    sheet = _sheet(tmp_path, ROWS)
    out = str(tmp_path / "labels.csv")
    labeler.append_answer(out, "a-01", True, 1, "tester")
    shown = []
    inputs = iter(["n", "n"])
    labeler.run(sheet, out, ask=lambda _: next(inputs),
                say=lambda s: shown.append(s))
    assert len([s for s in shown if s.startswith("[")]) == 2  # only pending rows
    assert "[2/3]" in shown[0] and "[3/3]" in shown[1]
    assert _answers(out)["a-01"] == "1"


def test_invalid_key_is_reprompted(tmp_path):
    sheet = _sheet(tmp_path, ROWS[:1])
    out = str(tmp_path / "labels.csv")
    inputs = iter(["maybe", "y"])
    prompts = []
    labeler.run(sheet, out, ask=lambda p: (prompts.append(p), next(inputs))[1],
                say=lambda *_: None)
    assert len(prompts) == 2
    assert _answers(out) == {"a-01": "1"}


def test_second_pass_is_shuffled_and_recorded_as_round_two(tmp_path):
    sheet = _sheet(tmp_path, ROWS)
    out = str(tmp_path / "labels_retest.csv")
    inputs = iter(["y", "y", "y"])
    labeler.run(sheet, out, round_no=2, annotator="tester",
                shuffle_seed=99, ask=lambda _: next(inputs), say=lambda *_: None)
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["row_id"] for r in rows] != [r["row_id"] for r in ROWS]
    assert {r["round"] for r in rows} == {"2"}
    assert {r["annotator"] for r in rows} == {"tester"}


def test_limit_caps_the_session(tmp_path):
    sheet = _sheet(tmp_path, ROWS)
    out = str(tmp_path / "labels.csv")
    inputs = iter(["y", "y"])
    stats = labeler.run(sheet, out, limit=2, ask=lambda _: next(inputs),
                        say=lambda *_: None)
    assert stats["total"] == 2 and stats["answered"] == 2


def test_group_by_family_keeps_families_contiguous(tmp_path):
    rows = [dict(r, row_id=f"{r['row_id']}-{f}", family=f)
            for r in ROWS for f in ("zz_family", "regex_construct")]
    sheet = _sheet(tmp_path, rows)
    out = str(tmp_path / "labels.csv")
    order = labeler.order_rows(rows, group_by_family=True, shuffle_seed=5)
    seen = [r["family"] for r in order]
    assert len(seen) == len(rows)
    # Contiguous: no family reappears after another one has started.
    blocks = [f for i, f in enumerate(seen) if i == 0 or seen[i - 1] != f]
    assert len(blocks) == len(set(blocks))
    # ... while the order is still randomised (row order changed, and each
    # family's own order changed relative to the sheet).
    assert [r["row_id"] for r in order] != [r["row_id"] for r in rows]
    inputs = iter(["y"] * len(rows))
    labeler.run(sheet, out, group_by_family=True, ask=lambda _: next(inputs),
                say=lambda *_: None)
    assert len(_answers(out)) == len(rows)


def test_qualification_warns_but_never_blocks(tmp_path):
    sheet = _sheet(tmp_path, ROWS[:1])
    out = str(tmp_path / "labels.csv")
    shown = []
    asked: list = []

    def ask(_prompt):
        # Deliberately give the wrong key for every calibration item, then
        # answer the real sheet correctly.
        i = len(asked)
        asked.append(_prompt)
        if i < len(labeler.CALIBRATION):
            expected = labeler.CALIBRATION[i]["correct"]
            return "n" if expected != "n" else "y"
        return "y"

    stats = labeler.run(sheet, out, qualification=True, ask=ask,
                        say=lambda s: shown.append(s))
    assert shown[0].startswith("qualification: 3 calibration items")
    verdicts = [s for s in shown if s.startswith(("correct (", "WRONG:"))]
    assert len(verdicts) == len(labeler.CALIBRATION) == 3
    assert all("WRONG" in s for s in verdicts)
    assert stats["qualification"]["wrong"] == [c["id"] for c in labeler.CALIBRATION]
    # Three wrong answers warn but never block: the sheet still ran.
    assert _answers(out) == {"a-01": "1"}


def test_load_answers_keeps_the_last_write(tmp_path):
    sheet = _sheet(tmp_path, ROWS[:1])
    out = str(tmp_path / "labels.csv")
    labeler.append_answer(out, "a-01", True, 1, "x", timestamp="2026-01-01T00:00:00")
    labeler.append_answer(out, "a-01", False, 2, "x", timestamp="2026-01-02T00:00:00")
    assert list(labeler.load_answers(out)) == ["a-01"]
    assert _answers(out) == {"a-01": "0"}
