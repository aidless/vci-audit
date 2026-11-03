# VCI audit — first run

A runnable, re-runnable measurement of **VCI** (Verification Coverage Index): the fraction of an
open-ended task distribution that can be checked *cheaply*, *trustworthily* and *densely*, and
therefore absorbed as training signal by an RL loop.

This repository is the artefact, not the essay. The definition lives in [SPEC.md](SPEC.md), the
numbers live in `outputs/`, and the conclusion lives in `outputs/first-run-memo.md`.

```
VCI = (C * T^2 * D) ** 0.25
```

| symbol | meaning | range |
|---|---|---|
| **C** cheapness | linear decay of verifier p95 latency: 1.0 at ≤ 20 ms, 0 at ≥ 500 ms | 0–1 |
| **T** trust | `min(TPR, TNR, 1 - FAR90)` at full-credit acceptance (squared in VCI) | 0–1 |
| **D** density | `granularity × fidelity`, averaged over tasks; binary tasks score 0 | 0–1 |

## Install

Standard library only. Python 3.9+.

```bash
git clone <repo-url> vci-audit && cd vci-audit
python3 -m venv .venv && . .venv/bin/activate     # optional but recommended
python -m pytest -q                                # 51 tests, ~2 s
```

No `pip install` is required to run the audit; `pyproject.toml` exists so `pip install -e .[dev]`
also works. (On systems where the interpreter is only available as `python3`, use `python3` below.)

## Run the whole audit

```bash
python -m vci audit --families all --out outputs/
```

Prints one summary line and writes four deliverables into `outputs/`:

| file | content |
|---|---|
| `results.json` | every number, including per-defect accept rates and per-family CIs |
| `coverage.csv` | one row per family, spreadsheet-friendly |
| `coverage.md` | the same table plus the reason for each gate failure |
| `dashboard.html` | self-contained static dashboard, **no network requests**, open by double-click |

Useful switches:

```bash
python -m vci audit --seed 3 --tasks 25 --bootstrap 500
python -m vci audit --families arith_expression,sql_result --out work/slice
python -m vci list-families
python -m vci selfcheck                 # mutants that contradict their own label (must be clean)
python -m vci annotate --per-family 2   # 40-row blind adjudication sheet
```

## Reproducibility

* Every random process is a seeded `random.Random`. The per-family stream is
  `family_seed = seed * 100003 + index * 97 + 11`, so `--seed` alone fixes the task set, the
  mutants, the bootstrap resamples and the intervals.
* `results.json → manifest` records seed, task count, bootstrap count, Python version and
  platform.
* **The one hardware-dependent quantity is latency** (`cost_ms`, hence `C`). Everything else
  is a pure function of the seed. On a slower machine `code_patch` (the only family that shells
  out to a subprocess) can drift by a few hundredths of a VCI point; the memo quotes observed
  values rather than asserting an exact constant.
* `work/candidates.jsonl` keeps every graded candidate (payload, defect class, verdict, score)
  so any single number can be recomputed or audited by hand.

## Layout

```
SPEC.md                 the computable definition (v0.1)
vci/schema.py           Task, Candidate, Verdict — one fixed return type
vci/metrics.py          VCI, TPR/TNR/FAR90, Cohen's kappa, Wilson/bootstrap intervals
vci/util.py             normalisation helpers
vci/registry.py         the 20-family registry + inclusion criteria
vci/audit.py            seed -> mutants -> verdicts -> metrics -> results.json
vci/report.py           results.json / coverage.csv / coverage.md / dashboard.html
vci/__main__.py         CLI
vci/families/           one generator + verifier per family (numeric/text/data/structural)
tests/                  formula, contract, and end-to-end tests
work/                   intermediate artefacts (git-ignored)
outputs/                deliverables
annotations/            blind adjudication sheet template
```

## The 20 families

Each family ships 25 seed tasks by default (`--tasks` accepts 20–40; the generator is
parameterised so it scales to 100 without a schema change). Every task has **K independent
graded units**, which is what makes dense credit measurable at all.

| module | families |
|---|---|
| numeric | `arith_expression`, `unit_convert`, `stats_summary`, `base_convert`, `matrix_ops`, `date_arith` |
| text | `json_schema_extract`, `log_field_extraction`, `regex_construct`, `template_render` |
| data | `sql_result`, `table_aggregate`, `sort_multikey`, `interval_merge` |
| structural | `grid_path`, `csp_assign`, `schedule_slots`, `topo_order`, `life_step`, `code_patch` |

Contract, enforced by `tests/test_verifiers.py` for all 20:

```python
fam.verify(task, candidate) -> Verdict(passed, score, evidence, cost_ms)
```

`passed` means full credit. `score` is the weighted fraction of units that are right; a unit
answer that is missing or extra counts against the total. A verifier exception is recorded as a
failed unit rather than propagated — a crashing verifier must never look like a pass.

## Discriminative power

There is no model API in the loop. Candidates are generated programmatically per task:

* **1 canonical answer** and up to **2 semantically equivalent rewrites** (different notation,
  key order, equivalent SQL, alternative valid grid path / colouring / schedule / topological
  order, whitespace or escaping variants);
* **7 defect classes** — boundary, off-by-one, type mismatch, order, missing, extra,
  semantically wrong;
* **K−1 partials** at exactly `j/K` units correct, which is what the density term grades.

From those we report TPR, TNR, the false-accept rate at the threshold that recovers 90% of
positives (`FAR90`), Cohen's kappa, and p95 latency. Paraphrase acceptance (`tpr_equiv`) is
reported and gated separately, because "rejects a correct but differently written answer" is the
failure mode dense verification actually dies of.

`python -m vci selfcheck` is the generator's own sanity gate: any correct mutant that fails, any
wrong mutant that passes, or any partial that scores 1.0 is a **generator bug**, not a verifier
result. The audit assumes `selfcheck clean`.

## Kappa and the reliability gate

A family is marked *reliable* only if `TPR ≥ 0.90`, `TNR ≥ 0.90`, `FAR90 ≤ 0.20` and `κ ≥ 0.60`;
otherwise `unreliable_reasons` names each violated condition.

κ needs labels. Two sources exist and are reported separately in every row (`kappa.source`):

* `synthetic` — the verifier against the mutant generator's own labels. This is the default in a
  clean checkout and is an **upper bound**: `selfcheck` forces that agreement to be perfect, so a
  synthetic κ of 1.00 does not mean the verifier was independently validated.
* `human` — a blind adjudication sheet. To collect one:

```bash
python -m vci annotate --per-family 2 --out annotations/blind.csv
# open annotations/blind.csv, fill human_label with 1 (accept) or 0 (reject) per row
cp annotations/blind.csv annotations/labels.csv        # the audit reads this path
python -m vci audit --families all --out outputs/       # kappa source switches to "human"
```

Rows are chosen to be the hard cases (a paraphrase, plus the highest-scoring partial), and the
defect class is deliberately withheld. With fewer than a full per-family sheet, families borrow
the pooled human κ and label it `pooled-human`.

## What this first run does **not** establish

* Mutants are synthetic. They are adversarial in the seven named dimensions, but they are not
  a sample of real model failures, so FAR/TNR are optimistic.
* 25 tasks per family is enough to rank families, not to pin a family's VCI to ±0.01. The
  bootstrap intervals in `results.json` quantify that sampling noise and are often wide.
* Density `D` is a proxy (granularity × partial-credit fidelity), not the information-theoretic
  quantity the hypothesis ultimately wants.
* Latency is measured in-process on one machine. `C` for `code_patch` is the only component that
  moves across hardware.

## License

MIT.
