# VCI audit — round 3 memo

**Run**: `python3 -m vci audit --families all --out outputs` · seed `0` · 25 tasks/family · 20 families ·
6,849 aligned candidates · **1,232 non-aligned probes (1,231 scored, 1 `observe`)** · probe generator
`v3.0` · 500 bootstrap resamples · Linux / Python 3.
Numbers: `outputs/results.json`; per-family table: `outputs/coverage.md`; every probe with its verdict
and basis: `outputs/attribution.csv`; dashboard: `outputs/dashboard.html`.
Round-1 and round-2 memos are preserved in git history.

---

## 1. Headline

| quantity | round 1 | round 2 | **round 3** |
|---|---|---|---|
| Median VCI (all evidence) | 0.983 | 0.934 | **0.934** (95% bootstrap CI 0.904 – 1.000) |
| Median VCI (aligned mutants only) | 0.983 | 0.978 | 0.984 |
| Families ≥ 0.70 | 20 / 20 | 15 / 20 | **16 / 20** |
| Families failing the aligned gate | 0 | 0 | 0 |
| Families failing the non-aligned gate | *not measured* | 5 | **5** |
| Core list (provisional) | 20 | 15 | **15** |
| Core list (human-backed) | 0 | 0 | **0** |
| κ source | synthetic | synthetic | **synthetic (no human sheet)** |
| α source | — | synthetic (value was wrong, §5) | **synthetic** |

The median did not move. Only `code_patch` moved (0.131 → **0.756**, CI 0.746-0.764; a second
run on a quieter machine gave 0.760 because `C` is measured from p95 latency), and that movement
is a *measurement* change, not a verifier improvement: round 2 probed it with two resource probes
per task and both were invisible to a one-shot harness. Round 3 added three and two of them are
caught.

## 2. Why `code_patch` moved, and what it means

Round-2's `code_patch` VCI 0.131 came from `T_non_aligned = 0.018`: 25/25 hardcoded answers
accepted, 25/25 stateful answers accepted. The stateful ones were a single probe, "answer is
correct on the first call and `None` afterwards". A verifier that runs all cases in one import
process sees only the first call, so the probe was *structurally* invisible, not a sign that the
verifier was weak. Round 3 adds three state probes per task, a repeated-call non-determinism probe,
and two non-termination probes for the family (156 probes in total):

| probe | defect | round 3 verdict |
|---|---|---|
| `x02` correct for calls 1-5, `None` after | one-shot correctness | **still accepted** (known leak) |
| `x03` fails from the second invocation | repeated use | rejected |
| `x04` alternates correct / `None` | non-determinism (NONDET) | rejected |
| `x05` memoised by arity | cross-call contamination | rejected |
| `x08` unbounded loop | non-termination | rejected (subprocess timeout) |
| `x07` 16 MB for a 5-element input | resource use | observed, excluded from TPR/TNR |

Consequence: 0.131 was partly an artifact of the probe sample, not of the verifier. That is a
warning about round-2's headline as well — a VCI built on a thin probe set reports the probe
set as much as the verifier. `tests/test_adversarial.py` now registers the surviving leak by
probe id, so fixing it shows up as a test change rather than a silent improvement.

`unit_convert`, `template_render` and `log_field_extraction` remain at 0.000, and the attribution
table (§4) says their zeros are **not** verifier blindness: 125 of their 126 scored probes are
rejected correct answers (75 equivalent timestamps + 50 defensible second readings). Those are
prompt problems (§4). `regex_construct` (0.690) and `sql_result` (0.781) are the two genuine
verifier-side gaps below 0.80.

## 3. Per category (CheckList): TPR / TNR / FAR90

| category | n | pos | neg | TPR | TNR | FAR90 |
|---|---|---|---|---|---|---|
| minimum functionality | 154 | 50 | 104 | **0.00** | 0.46 | 1.00 |
| invariance | 652 | 550 | 102 | 0.86 | 0.75 | 0.25 |
| directional | 425 | 0 | 425 | **–** | 1.00 | 0.00 |

Three honest readings:

1. **`minimum_functionality` is the weak category.** It accepts 56 of 104 wrong answers (TNR 0.46)
   and at 90 % true-positive operating point it accepts every negative (FAR90 1.00). The TPR 0.00
   is *entirely* the 50 `spec_ambiguity` probes: no positive minimum-functionality probe other than
   those was authored. Under §4 those 50 rejections are charged to the prompt, not the verifier —
   so handle this category's TPR and TNR separately; they measure different objects.
2. **`invariance` is measured best and still leaks.** TPR 0.86 (79 of 550 equivalent answers
   rejected), TNR 0.75 (26 of 102 invariance negatives accepted). The negative side is where the
   cost is.
3. **`directional` has no positive probe at all.** Its TNR 1.00 means every silent-partial defect
   was rejected; its TPR is `-`, not 0.00. Reporting it as 0.00 would claim "the verifier rejects
   every correct directional answer" — a claim no data supports. This is a structural gap, listed
   in §7 as a must-fix.

The most leaky family by category is `code_patch` (minimum-functionality TNR **0.00**: all 25
hardcoded and all 4 overfit answers accepted), then `regex_construct` (0.50, 25/50 accepted).

## 4. Attribution: where each disagreement lands

Rule (fixed before the verifier is called, never post-hoc):
`verifier_too_strict` = accept-expected `semantic_equivalent` probe rejected;
`task_under_specified` = accept-expected `spec_ambiguity` probe rejected;
`true_defect` = reject-expected probe (`caught` / `missed`); `agreement` = true negative;
`observe` = measured, excluded from TPR/TNR/FAR90.

| bucket | n | caught | missed | false-reject | accepted |
|---|---|---|---|---|---|
| verifier too strict | 75 | – | – | **75** | – |
| task under-specified | 50 | – | – | **50** | – |
| true defect | 631 | 550 | **81** | – | – |
| agreement | 475 | – | – | – | 475 |
| observe | 1 | – | – | – | – |

Split by operator (miss rate = accepted true defects / true-defect probes):

| operator | caught | missed | miss rate | where |
|---|---|---|---|---|
| `HARD` | 23 | 27 | 54.0 % | `code_patch` 25, `sql_result` 2 |
| `OVF` | 25 | 29 | 53.7 % | `regex_construct` 25, `code_patch` 4 |
| `STATE` | 51 | 25 | 32.9 % | `code_patch` 25 (first-call-only) |
| `CR` | 175 | 0 | 0 % | – |
| `SDL` | 75 | 0 | 0 % | – |
| `TR` | 75 | 0 | 0 % | – |
| `AOR`, `ROR` | 100 | 0 | 0 % | – |
| `NONDET` | 25 | 0 | 0 % | – |
| `INF` | 1 | 0 | 0 % | – |

The attribution is stark: **all 81 missed defects are `HARD`, `OVF` or `STATE`** — the three defect
classes that ask "does the answer generalise beyond the fixtures it was checked against". Every
loud operator (wrong formula, boundary, constant, deleted step, transposition, non-determinism,
non-termination) is caught 100 %. The verifier is not bad at checking values; it is bad at
checking *generalisation*, which is exactly what a fixture-replaying harness cannot check.

## 5. κ and α: sources and n

| coefficient | effective source | n | value | CI |
|---|---|---|---|---|
| κ (two-class accept/reject) | synthetic — **no human sheet exists** | 6,849 rows (6,849 units) | 1.000 | 1.000 – 1.000 |
| κ on non-aligned probes | independent probe oracle (not human) | 1,231 | 0.664 | – |
| α (ordinal, 3 levels) | synthetic | 13,698 ratings / 6,849 units, 0 undecidable | 1.000 | 1.000 – 1.000 |
| α on non-aligned probes | independent probe oracle | 2,462 ratings / 1,231 units | 0.664 | – |
| human κ / human α | none | 0 | `None` | – |

Both are **synthetic**. `annotations/blind.csv` exists but `annotations/labels.csv` does not, so the
human path has never been exercised; the report prints `n/a` for human κ rather than the
synthetic 1.000, and `core_human_backed` is empty. Any sentence of the form "agreement is 1.0"
would be a statement about the generator agreeing with itself, not about two annotators.

**Alpha correction.** Round 2 reported probe-oracle α = 0.328. That number was wrong: `D_o` was
divided by the number of *units* instead of the number of *pairable values*, doubling `D_o` for
two-coder units, and the ordinal distance was a plain rank gap. With Krippendorff's ordinal
distance on cumulative frequencies and the correct denominator, the same 1,231 probes give
**α = 0.664**, matching κ = 0.664 on the same pool — as it must, because with two label values the
ordinal distance is a constant multiple of the nominal one. The round-2 value must not be quoted.

When κ and α disagree the report says which one is being read: κ keeps a fixed marginal-based
expectation and collapses the 3-level scale, α keeps the scale distance and reports `undecidable`
as missing (`None`) rather than folding it into "accept". With no human labels, neither supports a
per-family claim: 25–154 probes per category is a diagnosis, not a certification.

## 6. Operators: what each one stands for

| operator | real defect it stands for | representative weakness |
|---|---|---|
| `AOR` | wrong formula | loud; acceptance says nothing, rejection says little |
| `ROR` | boundary error | one inequality per family; happy-path checks are blind |
| `CR` | stale constant / off-by-one | easy to kill with exact fixtures; over-weights small numeric errors |
| `SDL` | missing step / dropped functionality | needs the verifier to assert that step at all |
| `TR` | transposed operands or emission order | looks equivalent when the checker sorts or compares sets |
| `OVF` | rule that only holds on labelled examples | one per family: cannot represent the space of overfitting |
| `HARD` | lookup table instead of an algorithm | obviously wrong in principle, invisible to fixture replay |
| `STATE` | answer depends on history, not input | needs a second invocation; one-shot verifiers cannot see it |
| `NONDET` | same input, different answer | needs repeated calls; most harnesses call once |
| `INF` | non-termination / unbounded resources | watchdog-detectable, but the cost is wall-clock: observed, not scored |
| `EQUIV` | not a defect: same meaning, different spelling | authored, not decided; only measures false rejects where the author is right |
| `AMB` | not a defect: defensible second reading of an underspecified prompt | a rejection here blames the task text, not the verifier |

Coverage is uneven by design: 12 operators over 20 families means several classes rest on a
single family (`OVF` is 50 probes from two families, `STATE` 76 from one). A category table built
on one family per operator inherits that family's quirks.

Generator/verifier independence: probes are built from `Probe` payloads in `vci/adversarial.py`
and scored by the family's own `verify()` in `vci/families/`. They share the *task spec* (which is
what makes "correct" meaningful) but not the *oracle*: probe inputs, expected verdicts and
acceptance bases never call the verifier, and `expectation`/`attribution` are fixed before
`verify()` runs. Probe payloads are byte-identical across rounds, tracked by
`adversarial.GENERATOR_VERSION`, and `results.json.manifest` records it.

## 7. Validity ceiling — read before quoting any number here

**Synthetic mutants are not real defects.** Just et al. (FSE 2014) test whether mutants substitute
for real faults: they correlate, but mutants are *easier to kill* and their distribution does not
match the distribution of real faults. Every TPR/TNR in this memo is therefore an **optimistic
upper bound** on behaviour in deployment, never an estimate of it. Two concrete consequences:

1. `T = min(T_aligned, T_non_aligned)` takes the minimum of two synthetic sources. Both are capped
   at 1.000 by construction in the aligned case (round-1 selfcheck forces generator/verifier
   agreement), so a family that scores 1.000 here has not been "validated" — its harness agrees
   with its fixtures.
2. The 81 missed defects are our authored idea of what a defect looks like. Real failures will
   include partial correctness, plausible-but-wrong summaries, and wrong answers that pass weak
   assertions — none of which this probe set creates.

This ceiling is not softened by the round-3 additions. The category table, the attribution table
and α all improve *bookkeeping*; none of them samples real model output.

## 8. What the next round must do to raise validity

In priority order — each removes one of the ceilings above, and none is a cosmetic addition:

1. **Sample real failures.** Run each family's verifier against output from an actual model that
   produces wrong answers (a cheap local model is enough), then grade 20 *observed* wrong answers
   per family by hand. Recompute TPR/TNR against those. This is the only step that lifts the
   Just et al. ceiling; until it is done, "verification coverage" is coverage of authored probes
   only. The purpose-built sample is a diagnostic, not an estimate.
2. **Human labels.** Fill `annotations/labels.csv` (3-level scale, `undecidable` allowed) with the
   round-3 labeler (`--qualification --group-by-family --shuffle-seed 7`) and rerun the retest at
   `--round 2 --shuffle-seed 99` for stability. Until a human sheet exists, κ and α stay synthetic
   and `core_human_backed` stays empty.
3. **Author positive directional probes** (25 per family: correct answer to the perturbed input).
   Without them `directional` TPR remains unmeasured and one third of the category table is half
   studied.
4. **Close the `STATE/x02` leak.** Run the code_patch verifier in a subprocess per case, or run all
   cases twice and require identical output. Then the stateful probe set stops being a measure of
   the harness's process model.
5. **Widen `OVF` and `STATE` beyond their single-family origin.** `OVF` currently rests on
   `regex_construct` and `code_patch`; a generalising probe (answer fits a random 20 % holdout)
   would cover all 20.

## 9. Reproduce

```
python3 -m pytest -q                       # 79 tests
python3 -m vci audit --families all --out outputs
python3 -m vci label --sheet annotations/blind.csv --out annotations/labels.csv \
    --qualification --group-by-family --shuffle-seed 7
python3 -m vci audit --families all --out outputs     # with human labels present
```

Bootstrap intervals are seeded per block (`seed + 1 … seed + 6`), so a rerun reproduces the
same CI; only latency (`p95 ms`) depends on the machine.
