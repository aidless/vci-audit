# VCI audit

A measurement toolkit for open-ended task verification, plus two standalone components you can
point at **your own** benchmark:

| component | import | question it answers |
|---|---|---|
| harness differential decomposer | `from vci import decompose` | "two harnesses differ by X points — which mechanism moved?" |
| pass@k / pass^k calculator | `from vci import compute` | "what are pass@1, pass@k and reliability over N runs?" |

The rest of the repository (20 task families, adversarial probes, the VCI index) is the artefact
behind [SPEC.md](SPEC.md); it is not required to use either component.

## Quick start — three commands

```bash
git clone <repo-url> vci-audit && cd vci-audit
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python3 examples/decompose_realfail.py && python3 examples/passk_realfail.py
```

What you get on the archived real traces (qwen2.5:7b and qwen2.5-coder:14b, 100 tasks each;
no API calls, nothing downloaded):

```
delta = +0.0300  (A 0.1000 -> B 0.1300, n=100 tasks)
  tool         tasks=   5  delta=+0.0300  share=100.0%
  ...          code_patch-001/002/004 flipped fail -> pass

qwen2.5:7b          pass@1 = 0.100 [0.050-0.160]   k=2,3 not estimable (1 sample/task)
qwen2.5-coder:14b   pass@1 = 0.220 [0.140-0.310]   k=2,3 not estimable (1 sample/task)
```

See [examples/README.md](examples/README.md) for what each script does and
`outputs/delivery-plan.md` for the design notes.

## What these components measure — and what they do not

**Measure:** the difference between two harness configurations on one benchmark/model pair
(decomposer), and the success/reliability curves of N runs on a fixed task set (pass@k).

**Do not measure, and are not intended to support:**

* **cross-vendor or cross-model ranking.** A decomposition across two different models is
  invalid — the harness factors are not the only thing that changed. The tool refuses
  aggregate-only input for exactly this reason, and a model swap is not one of its four
  factors. The pass@k numbers are observations of one model on one task set, never a ranking.
* causal attribution without an ablation arm. The decomposer is a **budgeted attribution**;
  see Component 1 below.
* partial credit. `passed` means full credit; a 3-of-5 answer is not a pass.
* any statement about whether a model is "good enough", whether a benchmark is absolute, or
  whether some milestone has been reached. Every number is an observation under a specific
  tuple (benchmark × model × harness × decoding × seed).

---

A runnable, re-runnable measurement of **VCI** (Verification Coverage Index): the fraction of an
open-ended task distribution that can be checked *cheaply*, *trustworthily* and *densely*, and
therefore absorbed as training signal by an RL loop.

This repository is the artefact, not the essay. The definition lives in [SPEC.md](SPEC.md), the
annotation rulebook in [annotations/PROTOCOL.md](annotations/PROTOCOL.md), the numbers live in
`outputs/`, and the reading of the first run lives in `outputs/first-run-memo.md`.

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

Standard library only. Python 3.9+. Nothing is fetched at run time.

```bash
git clone <repo-url> vci-audit && cd vci-audit
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"    # editable install + the `vci` console script
python3 -m pytest -q       # 157 tests, a few seconds
```

Verified from a clean clone: `pip install -e .` builds an editable wheel, `from vci import
Task, Candidate, Verdict, decompose, compute` works, and `vci --help` lists the
subcommands. No machine-specific path appears in the package. Running without installing
also works (`python3 -m vci ...`).

## Component 1 — harness differential decomposer

```python
from vci import decompose

doc = {"benchmark": "...", "model": "...",
       "tasks": [{"task_id": "t1",
                  "a": {"passed": False, "tool_sig": "json_list"},
                  "b": {"passed": True,  "tool_sig": "joined_source"}}]}
result = decompose(doc)          # also decompose(run_a, run_b) or decompose_file("x.json")
```

The four named sources and what each reads from the per-task record:

| source | field | means |
|---|---|---|
| `state` | `state_retained` | reasoning/scratchpad state kept across the task |
| `compaction` | `compaction_events` | context compactions performed |
| `tool` | `tool_sig` / `tool_calls` / `tool_errors` | what the execution layer saw or did |
| `retry` | `retries` | extra attempts the budget allowed |

Output: `scores.delta`, the four named buckets plus `ambiguous` and `unexplained`, and
`top_divergence`. **The buckets sum to `scores.delta` exactly** (`n_tasks`-normalised task
contributions). A task is charged to a named source only when exactly one measured
mechanism differs; two or more differing mechanisms land in `ambiguous`; no differing
mechanism lands in `unexplained`. That is *budgeted attribution, not causal identification*
— confirm a source with a third arm that toggles that mechanism alone. The report repeats
this under `assumption`.

Degraded input is refused, never guessed: aggregate scores only → `decomposable: false`,
`reason: "aggregate_only"` plus the observed delta; outcomes with no mechanism flags →
`reason: "no_factor_flags"`.

Inputs accepted: one combined JSON/CSV document (`tasks[]` with `a`/`b` sides, or flat
`a_passed`/`b_passed`/`a_tool_sig`/... columns), or two single-harness files aligned on
`(task_id, seed)`. `score` (0–1) is used when present, otherwise `passed`.

CLI: `vci harness-decomp --input x.json --out work/decomp.json [--b y.json] [--top-n 10]`

## Component 2 — pass@k / pass^k calculator

```python
from vci import compute

doc = {"tasks": [{"task_id": "t1", "seed": 0, "runs": ["pass", "fail", "timeout"]}]}
result = compute(doc, k_max=3)   # also compute_file("attempts.json")
```

Definitions — the same text is written into every output under `definitions`:

* `pass@k = mean_tasks [1 - C(n-c, k) / C(n, k)]` — at least one of k attempts passes.
* `pass^k = mean_tasks [C(c, k) / C(n, k)]` — every one of k attempts passes (reliability).
* At `k = 1` both are the mean per-task success rate; `pass@1` is that value.
* Attempts are **never pooled across tasks**: a task with 2 runs and one with 8 contribute
  their own per-task estimate.
* `k > n` is **not estimable** for that task and is reported as `estimable: false`,
  `value: null` — never interpolated.
* Statuses are `pass` / `fail` / `timeout` / `refusal` / `error`. `as_failure` (default)
  counts every attempt; `exclude_nonattest` drops timeout/refusal/error and recomputes.
  Both curves are reported.
* The bootstrap CI resamples **tasks** (the unit of generalisation), not runs; `n_boot`,
  `seed` and `alpha` are recorded.
* Duplicate `(task_id, seed, run)` triples **raise**: they mean two run files were merged
  twice. Different seeds for one task are legitimate independent attempts and are counted.

CLI: `vci passk --input attempts.json --k-max 3 [--bootstrap 1000] [--seed 0]`

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
vci/harness_decomp.py   standalone 4-source harness differential decomposer
vci/passk.py            standalone pass@1 / pass@k / pass^k calculator with bootstrap CI
vci/util.py             normalisation helpers
vci/registry.py         the 20-family registry + inclusion criteria
vci/adversarial.py      round-2 non-aligned probes (independent of every verifier)
vci/labeler.py          blind terminal labelling CLI (resume, retest pass)
vci/audit.py            seed -> mutants + probes -> verdicts -> metrics -> results.json
vci/report.py           results.json / coverage.csv / coverage.md / dashboard.html
vci/__main__.py         CLI (audit, harness-decomp, passk, ...)
vci/families/           one generator + verifier per family (numeric/text/data/structural)
examples/               two end-to-end examples on the archived real traces
tests/                  formula, contract, component, labeler, probe-independence and e2e tests
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
