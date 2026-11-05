# Delivery plan — VCI audit as an installable, importable measurement toolkit

Status: implemented. This file records the structure so the chat reply can stay short.

## 1. Packaging

* `pyproject.toml` — unchanged metadata, added:

  ```toml
  [project.scripts]
  vci = "vci.__main__:main"
  ```

  Packages were already `["vci", "vci.families"]`, dependencies `[]` (stdlib only).
* `vci/__init__.py` — now the public surface:

  ```python
  from vci import Task, Candidate, Verdict          # data model
  from vci import FACTORS, decompose, decompose_file
  from vci import compute, compute_file, unbiased_pass_at_k, unbiased_pass_pow_k
  ```

  No local paths are embedded in the package. Examples resolve paths from
  `pathlib.Path(__file__).resolve().parents[1]`, so they run from any cwd.
* Verified in a throw-away venv:

  ```bash
  python3 -m venv /tmp/vci-venv
  /tmp/vci-venv/bin/pip install -e .
  /tmp/vci-venv/bin/python -c "import vci; print(vci.__version__, vci.__all__)"
  /tmp/vci-venv/bin/vci --help
  ```

  Result: editable wheel built, `0.1.0`, exports listed, subcommands
  `audit / verify / list-families / selfcheck / harness-diff / harness-decomp / passk`.

* Existing CLI untouched: `python3 -m vci <cmd>` still works for all old commands.

## 2. Component A — `vci/harness_decomp.py`

New module; the old round-4 `vci/harness_diff.py` (code_patch A/B) is left as-is and
keeps its tests. `harness-diff` and `harness-decomp` are different subcommands.

### Input

* Combined JSON: `{"benchmark", "model", "harness_a", "harness_b", "tasks": [...]}` where
  each task is `{"task_id", "seed", "a": {side}, "b": {side}}`.
* Combined CSV: flat columns `task_id, seed, a_passed, b_passed, a_<factor>, b_<factor>`.
* Two files: `decompose(run_a, run_b)`, aligned on `(task_id, seed)`; unmatched ids are
  counted (`n_unmatched`) and excluded from the decomposition.
* A side: `{"passed": bool}` or `{"score": 0..1}`, plus the mechanism flags.

### Factors and fields

| factor | first-match aliases |
|---|---|
| `state` | `state_retained`, `state_kept`, `reasoning_state`, `state` |
| `compaction` | `compaction_events`, `compactions`, `context_compaction`, `compaction` |
| `tool` | `tool_sig`, `tool_calls`, `tool_errors`, `tool_exec`, `tool` |
| `retry` | `retries`, `retries_used`, `retry_count`, `retry` |

A factor is "differing" only when it is present on **both** sides and the values differ.

### Accounting

```
delta = mean(b) - mean(a) = sum_i (b_i - a_i) / N
```

Each task contributes `(b_i - a_i)/N`; buckets sum to `delta` exactly
(`attribution_sums_to_total_delta` checks this):

* exactly one differing factor → that named bucket
* ≥2 differing factors → `ambiguous`
* 0 differing factors → `unexplained`

`top_divergence` = tasks sorted by `|delta_i|`, zero-delta tasks filtered out unless
nothing moved. Report also carries `assumption` (attribution ≠ causality).

### Degraded cases (explicit refusal)

| input | result |
|---|---|
| only aggregate scores | `decomposable: false`, `reason: "aggregate_only"`, `observed_delta` |
| outcomes but no mechanism flags | `reason: "no_factor_flags"` |
| pairs with no outcomes | `reason: "no_paired_outcomes"` |
| empty document | `reason: "no_records"` |

### Real result (qwen2.5:7b, 100 tasks, envelope change)

```
delta = +0.0300  (A 0.1000 -> B 0.1300, n=100)
tool        n=5   delta=+0.0300  share=100.0%
unexplained n=95  delta=+0.0000
top: code_patch-001, code_patch-002, code_patch-004 (0 -> 1)
aggregate-only 7B vs 14B (0.10/0.22) -> not decomposable (aggregate_only)
```

Source data: `outputs/realfail-real.json` + `outputs/realfail-real-check.json`
(`code_patch_regrade`). Same model, same replies; only the payload envelope differs.

## 3. Component B — `vci/passk.py`

### Input

* `{"tasks": [{"task_id", "seed", "runs": ["pass"|"fail"|...|true|false]}]}`
* flat `[{"task_id", "seed", "run", "status"|"passed"}]`
* statuses: `pass / fail / timeout / refusal / error` (+ aliases).

### Definitions (also emitted in every result under `definitions`)

* `pass@k = mean_tasks [1 - C(n-c, k)/C(n, k)]`
* `pass^k = mean_tasks [C(c, k)/C(n, k)]` — all k pass (reliability)
* `pass@1` = mean per-task pass rate (k=1 case of both)
* per-task estimates only; attempts are never pooled across tasks
* `k > n` → `estimable: false`, `value: null`
* `as_failure` (default) counts timeout/refusal/error as failures;
  `exclude_nonattest` drops them — both curves reported
* bootstrap resamples **tasks**, `n_boot` / `seed` / `alpha` recorded
* duplicate `(task_id, seed, run)` → `ValueError`

### Real result (one greedy sample per task)

```
qwen2.5:7b          pass@1 = 0.100 [0.050-0.160]   k=2,3 n/a
qwen2.5-coder:14b   pass@1 = 0.220 [0.140-0.310]   k=2,3 n/a
```

Matches the archived acceptance rates 10/100 and 22/100. `k≥2` is not estimable from
single-sample traces and the calculator says so instead of inventing repeats.

## 4. Tests

* Before: 137 passing.
* Added `tests/test_harness_decomp.py` — 9 tests (single-factor attribution, exact
  bucket-sum identity, ambiguous multi-factor, unexplained, aggregate-only refusal,
  no-factor-flags refusal, empty document, unmatched alignment, top-divergence order,
  CSV input).
* Added `tests/test_passk.py` — 11 tests (all-pass, all-fail, known unbiased values,
  pass@1 identity, k>n not estimable, timeout/refusal accounting modes, duplicate triples,
  multi-seed attempts, bootstrap determinism + interval bracketing, JSON round-trip,
  empty input).
* Total: **157 passing** (`python3 -m pytest -q`).

## 5. Examples

`examples/decompose_realfail.py`, `examples/passk_realfail.py`, `examples/README.md`.
Inputs and outputs are written to `outputs/example-*.json`; both scripts also show the
equivalent CLI invocation.

## 6. Explicit non-claims

* Not a cross-vendor / cross-model ranking tool.
* The decomposition is observational attribution over measured flags, not causal.
* No statement about model quality in absolute terms; numbers are observations under a
  fixed (benchmark × model × harness × decoding × seed) tuple.
