# VCI audit — round 3

A runnable, re-runnable measurement of **VCI** (Verification Coverage Index): the fraction of an
open-ended task distribution that can be checked *cheaply*, *trustworthily* and *densely*, and
therefore absorbed as training signal by an RL loop.

This repository is the artefact, not the essay. The definition lives in [SPEC.md](SPEC.md), the
annotation rulebook in [annotations/PROTOCOL.md](annotations/PROTOCOL.md), the numbers live in
`outputs/`, and the conclusion lives in `outputs/first-run-memo.md`.

```
VCI = (C * T^2 * D) ** 0.25
```

| symbol | meaning | range |
|---|---|---|
| **C** cheapness | linear decay of verifier p95 latency: 1.0 at ≤ 20 ms, 0 at ≥ 500 ms | 0–1 |
| **T** trust | `min(TPR, TNR, 1 - FAR90)` at full-credit acceptance, computed on **aligned mutants and on non-aligned probes separately**, then `min` of the two | 0–1 |
| **D** density | `granularity × fidelity`, averaged over tasks; binary tasks score 0 | 0–1 |

Round 1 measured trust only on mutants that shared the verifier's own code, so TPR/TNR were
saturated at 1.0. Round 2 adds a second, independently constructed candidate source (§3.4 of SPEC)
and reports `T_aligned` and `T_non_aligned` side by side. Round 3 adds no formula: it labels every
probe with a CheckList category (`minimum_functionality` / `invariance` / `directional`) and a
mutation operator (§3.5), publishes a three-way attribution of every disagreement in
`attribution.csv`, and reports Krippendorff's α beside κ. A family keeps its VCI and is listed as
unreliable rather than being patched into passing.

**Read `outputs/first-run-memo.md` §7 before quoting any number**: probes are synthetic mutants,
so TPR/TNR are an upper bound on real behaviour (Just et al., FSE 2014), and κ/α are currently
synthetic because no human sheet exists.

## Install

Standard library only. Python 3.9+.

```bash
git clone <repo-url> vci-audit && cd vci-audit
python3 -m venv .venv && . .venv/bin/activate     # optional but recommended
python3 -m pytest -q                                # 137 tests, ~2 s
```

No `pip install` is required to run the audit; `pyproject.toml` exists so `pip install -e .[dev]`
also works. (On systems where the interpreter is only available as `python3`, use `python3` below.)

## Run the whole audit

```bash
python3 -m vci audit --families all --out outputs/
```

Prints one summary line and writes five deliverables into `outputs/`:

| file | content |
|---|---|
| `results.json` | every number, including per-defect accept rates, per-category TPR/TNR and per-family CIs |
| `coverage.csv` | one row per family, spreadsheet-friendly (VCI, κ, α, per-category rates) |
| `coverage.md` | the same table plus the CheckList-category and attribution tables |
| `attribution.csv` | **one row per non-aligned probe**: category, operator, generator version, expected verdict, true label, attribution bucket, basis |
| `dashboard.html` | self-contained static dashboard, **no network requests**, open by double-click |

Useful switches:

```bash
python3 -m vci audit --seed 3 --tasks 25 --bootstrap 500
python3 -m vci audit --families arith_expression,sql_result --out work/slice
python3 -m vci list-families
python3 -m vci selfcheck                 # mutants that contradict their own label (must be clean)
python3 -m vci annotate --per-family 3   # 60-row blind adjudication sheet
python3 -m vci label --qualification --group-by-family --shuffle-seed 7
python3 -m vci score-annotations         # recompute kappa from labels.csv without a full rerun
python3 -m vci realfail-tolerant         # counterfactual: re-grade the archived realfail run
                                         # with schema-tolerant extraction (round 8, offline)
```

One command reproduces every deliverable in `outputs/`:

```bash
python3 -m vci audit --families all --out outputs
```

It picks up `annotations/labels.csv` and `annotations/labels_retest.csv` automatically when they
exist and switches κ to `human`; with no sheet it prints a warning that κ is a synthetic upper
bound.

## Real model traces (separate from the synthetic probe pool)

Round 10 samples an actual local model through ollama.  The archived run stores the **verbatim
prompt**, the raw reply, the decoding parameters (temperature 0.0, fixed seed, one greedy sample)
and the model digest; it is reproducible and auditable, not synthetic:

```bash
python3 -m vci realfail --families all --tasks 5 --seed 20261104 \
    --model qwen2.5:7b --max-tokens 512 --out outputs/realfail-real.json
python3 -m vci realfail-sheet --run outputs/realfail-real.json \
    --out outputs/realfail-real-sheet.jsonl
```

`realfail-real-sheet.jsonl` is one row per task unit with the model's answer, the gold reference
and the verifier's per-unit verdict.  These traces are **not** merged into the VCI headline:
without human labels, mixing them into TPR/TNR would grade the verifier against itself.  They
are the external-validity check and the input to a future blind human sheet.

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
SPEC.md                 the computable definition (v0.2)
annotations/PROTOCOL.md the blind-labelling rulebook (pass/fail/undecidable)
vci/schema.py           Task, Candidate, Verdict — one fixed return type
vci/metrics.py          VCI, TPR/TNR/FAR90, Cohen's kappa, Wilson/bootstrap intervals
vci/util.py             normalisation helpers
vci/registry.py         the 20-family registry + inclusion criteria
vci/adversarial.py      round-2 non-aligned probes (independent of every verifier)
vci/labeler.py          blind terminal labelling CLI (resume, retest pass)
vci/audit.py            seed -> mutants + probes -> verdicts -> metrics -> results.json
vci/report.py           results.json / coverage.csv / coverage.md / dashboard.html
vci/__main__.py         CLI
vci/families/           one generator + verifier per family (numeric/text/data/structural)
tests/                  formula, contract, labeler, probe-independence and end-to-end tests
work/                   intermediate artefacts (git-ignored)
outputs/                deliverables
annotations/            blind sheet, protocol and your labels (labels are git-ignored)
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

## Non-aligned probes

Round 1's problem was that the generator and the verifier were written together, so every mutant
was labelled by the same code that judged it. `vci/adversarial.py` adds a second candidate source
whose labels are decided before the verifier runs. It never calls `verify`, `canonical`,
`equivalents`, `wrongs`, `mutate` or `partial`; `tests/test_adversarial.py` enforces that by AST
inspection, and the module recomputes expected values with its own reference implementations.

Each probe is tagged with a failure class and an expectation (`accept` / `reject` / `observe`):

| failure class | example | families |
|---|---|---|
| `hardcoded_expected` | lookup table of the hidden-test answers | `code_patch`, `sql_result` |
| `overfit_to_tests` | correct on the visible cases, empty on longer input; regex matching only the positive samples | `code_patch`, `regex_construct` |
| `spec_ambiguity` | 6 significant digits where the prompt states no precision | `unit_convert`, `template_render` |
| `silent_partial` | runs, locally right, off by a factor of 1000 | most numeric/data families |
| `semantic_equivalent` | same instant in three RFC-3339 spellings, fractions vs decimals, alternate valid solution | all |
| `resource` | `while True`, module-level call counter, ~16 MB allocation | `code_patch` |

`observe` probes are measured but excluded from TPR/TNR: no memory budget is part of the verifier
contract, so scoring them either way would invent a trust number. A probe the verifier wrongly
accepts is reported as a leak; it is never reclassified to make the verifier look better.

## Kappa and the reliability gate

A family is marked *reliable* only if `TPR ≥ 0.90`, `TNR ≥ 0.90`, `FAR90 ≤ 0.20` and `κ ≥ 0.60`,
evaluated once on aligned mutants (`reliable`) and once on non-aligned probes
(`reliable_non_aligned`); otherwise `unreliable_reasons` names each violated condition.

κ needs labels. Three numbers are reported separately in every row and are never merged:

* `synthetic` — the verifier against the mutant generator's own labels. Default in a clean
  checkout. It is an **upper bound**: `selfcheck` forces that agreement to be perfect, so 1.00
  does not mean the verifier was independently validated, and it is never quoted as human.
* `human` — a blind sheet filled with `python -m vci label`, following
  [annotations/PROTOCOL.md](annotations/PROTOCOL.md). Each κ comes with a row-level bootstrap CI
  and its `n`; `undecidable` rows are counted (`n_undecidable`) and excluded.
* `human-stability` — the same annotator's second, re-ordered pass (`labels_retest.csv`). It
  measures the annotator, not the verifier; a low value is a warning about the labels, never a
  bonus for the verifier.

```bash
python -m vci annotate --per-family 3 --out annotations/blind.csv
python -m vci label --out annotations/labels.csv                 # y / n / s / k / q, resumable
python -m vci label --out annotations/labels_retest.csv \
    --round 2 --shuffle-seed 99                                  # stability pass
python -m vci audit --families all --out outputs                # picks labels up automatically
python -m vci score-annotations                                 # kappa only, no full rerun
```

Rows are the hard cases (a paraphrase, the highest-scoring partial, and a
`semantic_equivalent`/`spec_ambiguity` probe), and the defect class is withheld. The CLI shows only
`row_id`, `family`, `task_prompt` and `candidate`; a test asserts the true label cannot appear on
screen. With a sparse per-family sheet, families borrow the pooled human κ and are labelled
`pooled-human` with the borrowed count.

## What this round does **not** establish

* Non-aligned probes come from a different module than the verifier, but from the same author.
  They are not a sample of real model failures, and they cannot detect a blind spot shared by the
  author and the verifier. Only the human sheet, and eventually an independent annotator, can.
* 25 tasks per family is enough to rank families, not to pin a family's VCI to ±0.01. The
  bootstrap intervals in `results.json` quantify that sampling noise and are often wide.
* The annotation sheet is 60 rows pooled. Per-family κ intervals are wide; the human-backed core
  list is usually empty until a family gets its own dense sheet.
* Density `D` is a proxy (granularity × partial-credit fidelity), not the information-theoretic
  quantity the hypothesis ultimately wants.
* Latency is measured in-process on one machine. `C` for `code_patch` is the only component that
  moves across hardware.

## License

MIT.
