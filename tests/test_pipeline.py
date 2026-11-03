"""End-to-end smoke test of the audit pipeline on a small family slice."""
import json
import os

import pytest

from vci import audit, registry, report

SLICE = ["arith_expression", "sql_result"]


def _run(tmp_path, **kw):
    return audit.run_audit(
        families=registry.resolve(",".join(SLICE)),
        n_tasks=kw.pop("n_tasks", 4),
        seed=kw.pop("seed", 1),
        n_boot=kw.pop("n_boot", 40),
        labels_path=None,
        keep_raw=True,
        work_dir=str(tmp_path / "work"),
    )


def test_audit_is_deterministic_for_a_fixed_seed(tmp_path):
    a = _run(tmp_path / "a", seed=1)
    b = _run(tmp_path / "b", seed=1)
    for ra, rb in zip(a["families"], b["families"]):
        assert ra["metrics"]["tpr"] == rb["metrics"]["tpr"]
        assert ra["metrics"]["tnr"] == rb["metrics"]["tnr"]
        assert ra["density"] == pytest.approx(rb["density"])
        assert ra["vci"] == pytest.approx(rb["vci"])
    assert a["summary"]["n_candidates"] == b["summary"]["n_candidates"]


def test_audit_reports_every_required_metric(tmp_path):
    payload = _run(tmp_path)
    assert payload["summary"]["n_families"] == len(SLICE)
    assert payload["summary"]["n_candidates"] > 0
    for row in payload["families"]:
        for key in ("vci", "vci_ci", "cheapness", "trust", "density",
                    "per_defect", "latency_ms", "reliable", "unreliable_reasons"):
            assert key in row
        assert 0.0 <= row["vci"] <= 1.0
        assert row["vci_ci"][0] <= row["vci_ci"][1]
        # No verifier may crash on any mutant in the slice.
        assert row["verifier_errors"] == 0
        # The audit must publish the paraphrase acceptance rate separately.
        assert "tpr_equiv" in row["metrics"]


def test_raw_jsonl_is_written_for_auditability(tmp_path):
    _run(tmp_path)
    cand_path = tmp_path / "work" / "candidates.jsonl"
    assert cand_path.is_file()
    lines = cand_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 0
    first = json.loads(lines[0])
    assert {"cand_id", "defect", "label", "passed", "score", "cost_ms"} <= set(first)


def test_report_writes_four_self_contained_deliverables(tmp_path):
    payload = _run(tmp_path)
    out = tmp_path / "out"
    report.write_all(payload, str(out))
    names = sorted(os.listdir(out))
    assert names == ["coverage.csv", "coverage.md", "dashboard.html", "results.json"]
    html = (out / "dashboard.html").read_text(encoding="utf-8")
    assert "<script id=\"data\"" in html
    # Offline: no remote assets of any kind.
    assert "http://" not in html and "https://" not in html
    reloaded = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert reloaded["summary"]["n_families"] == payload["summary"]["n_families"]


def test_human_labels_flow_into_kappa(tmp_path):
    """A filled adjudication sheet must change kappa and the gate outcome."""
    fam = registry.by_name(SLICE[0])
    task = fam.generate(1, __import__("random").Random(0))[0]
    cands = fam.mutate(task, __import__("random").Random(1))
    # Deliberately invert two labels: kappa must drop below 1.0.
    sheet = tmp_path / "labels.csv"
    rows = [{"row_id": c.cand_id, "human_label": "0" if c.is_correct else "1"}
            for c in cands[:2]]
    rows += [{"row_id": c.cand_id, "human_label": "1" if c.is_correct else "0"}
             for c in cands[2:]]
    with open(sheet, "w", encoding="utf-8") as fh:
        fh.write("row_id,human_label\n")
        for r in rows:
            fh.write(f"{r['row_id']},{r['human_label']}\n")
    labels = audit._load_labels(str(sheet))
    assert len(labels) == len(cands)
    kappa = audit._agreement([(labels[c.cand_id], c.is_correct) for c in cands])
    assert 0.0 <= kappa["value"] < 1.0
    assert kappa["n"] == len(cands)


def test_selfcheck_is_clean_on_the_slice():
    assert audit.selfcheck(families=registry.resolve(",".join(SLICE)),
                           n_tasks=3, seed=5) == []
