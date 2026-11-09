# VCI audit — round 3 memo

**Run**: `python3 -m vci audit --families all --out outputs` · seed `0` · 25 tasks/family · 20 families ·
6,849 aligned candidates · **1,232 non-aligned probes (1,231 scored, 1 `observe`)** · probe generator
`v3.0` · 500 bootstrap resamples · Linux / Python 3.
Numbers: `outputs/results.json`; per-family table: `outputs/coverage.md`; every probe with its verdict
and basis: `outputs/attribution.csv`; dashboard: `outputs/dashboard.html`.
Round-1 and round-2 memos are preserved in git history.

> **Round labels matter — this memo is cumulative.** Each section's numbers hold only under
> its own round's口径. **Current values (round 10)**: median VCI **0.969** (aligned **0.986**
> on the round-10 machine; the 2026-11-05 rerun reads 0.978 because aligned VCI consumes
> latency-driven `cheapness`, §8), `families ≥ 0.70` **17/20**, directional **771** (pos 173 / neg 598).
> Round 3's 0.934 / 16/20 / 425 and round 5's 575 / 0.934 are **historical** values of the
> same quantities, not contradictions. Per-number audit:
> [`outputs/number-reconciliation.md`](number-reconciliation.md).

---

## Round-5 addendum — positive directional probes, authored where they are measurable (2026-11-04)

Round 5 closed the §8-3 blank **for the families where it can be closed honestly**:
150 `directional_shift` probes (operator `DIR`, generator `v4.0`), one accept/reject pair
per task for `sql_result`, `regex_construct`, `code_patch`.  Each probe carries a
`task_override` — a perturbed copy of the task — and `audit` verifies the candidate
against the override.  Accept probes submit the independently recomputed correct answer
to the perturbed input; reject probes submit the answer that was correct *before* the
change.

**Result (round 5 口径; round 10 later reads n=771, pos=173/neg=598):** the `directional` row is now measured — n=575, pos=75/neg=500, **TPR 1.00,
TNR 1.00, FAR90 0.00**, zero false rejects, zero stale accepts.  The sharp side is the
stale-answer one: the sql constant-queries that memorise the visible primary result
(the two HARD leaks of §4) are now caught 25/25 once the dataset shifts; the regex
alternation of the original positives fails on fresh unseen strings 25/25; the
`code_patch` implementation of the original spec fails the shifted spec's hidden cases
25/25.

**Structural finding (why 3 families, not 20):** seventeen verifiers in this suite grade
the payload against expected values stored in the task itself.  There, a perturbed
(input, truth) pair is accepted *by construction* — authoring positive directional
probes in their round-3 quantity (425 negatives, zero positives) would manufacture a meaningless TPR 1.00.  Only verifiers that re-derive truth by
executing the candidate against task-carried data (sql runs the query on shifted rows,
regex re-tests fresh strings, code_patch re-runs hidden cases) can express directional
risk at all.  Stated plainly: for fixture-replay verifiers the directional risk class
does not exist in this architecture, and its absence is a property of the architecture,
not evidence of robustness.  Their per-family directional cells stay `–`.

**Two construction notes, honestly recorded.**

- 2 of 25 sql tasks (items ⊆ {rich_depts, regions_over_3} with every region already over
  the threshold) are invariant under any pure relabelling shift; they only became
  shiftable after adding a variant that removes most rows of one region.  A task whose
  answer does not change under a shift cannot support a stale-answer probe — authoring
  one would be a false accusation, so the builder returns no probe rather than forcing
  one.
- Pooling caveat: the 50 correct directional outcomes per family dilute each family's
  *pooled* trust (regex 0.500 → 0.667, sql 0.920 → 0.960, code_patch 0.585 → 0.652), and
  `regex_construct` thereby crosses the provisional bar (0.690 → 0.797; the ≥0.70 count
  moves 16/20 → 17/20).  **The leaks themselves are unchanged** — regex
  minimum-functionality trust is still 0.500 and the per-category cells show it.  Median
  VCI is unchanged within round 5 (0.934; the round-10 rerun later reads 0.969).  Probe κ 0.664 → 0.701 [0.662, 0.736], α 0.666 → 0.701
  (n=1,381 scored probes).

The validity ceiling of §7 is unchanged: all new probes are still synthetic, and the
directional row additionally measures only execution-derived verifiers by construction.

---

## 1. Headline (round 3 — historical; current = round 10 box above)

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

Table values are **round-3** (0.934 / 16/20). Round 5 onwards the count is **17/20**
(`regex_construct` crosses 0.70 after the directional addendum); the round-10 rerun reads
median **0.969** (aligned **0.986** at round 10; 0.978 on the 2026-11-05 rerun, see §8). Same quantities, different rounds — not two values of one number.

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

## 3. Per category (CheckList, round 3): TPR / TNR / FAR90

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
and α all improve *bookkeeping*; none of them samples real model output. **Round 6 (addendum
below) partially lifts consequence 2 for six families**: it replays the exercise on outputs from a
real model instead of authored mutants, and confirms the second predicted failure mode
("plausible-but-wrong … none of which this probe set creates" — in fact real failures were
*mostly not plausible*, and the dominant real risk turned out to be false rejects, not leaks).

## 8. What the next round must do to raise validity

In priority order — each removes one of the ceilings above, and none is a cosmetic addition:

1. **Sample real failures.** Run each family's verifier against output from an actual model that
   produces wrong answers (a cheap local model is enough), then grade 20 *observed* wrong answers
   per family by hand. Recompute TPR/TNR against those. This is the only step that lifts the
   Just et al. ceiling; until it is done, "verification coverage" is coverage of authored probes
   only. The purpose-built sample is a diagnostic, not an estimate.  **Done in round 6 for six
   families (779 units hand-graded) — see the round-6 addendum. Still open for the other fourteen
   and for a stronger model.**
2. **Human labels.** Fill `annotations/labels.csv` (3-level scale, `undecidable` allowed) with the
   round-3 labeler (`--qualification --group-by-family --shuffle-seed 7`) and rerun the retest at
   `--round 2 --shuffle-seed 99` for stability. Until a human sheet exists, κ and α stay synthetic
   and `core_human_backed` stays empty.
3. **Author positive directional probes** (25 per family: correct answer to the perturbed input).
   Without them `directional` TPR remains unmeasured and one third of the category table is half
   studied.  **Done in round 5 for the three execution-derived verifiers — see the round-5
   addendum, which also shows why the other seventeen cannot express the category.**
4. **Close the `STATE/x02` leak.** Run the code_patch verifier in a subprocess per case, or run all
   cases twice and require identical output. Then the stateful probe set stops being a measure of
   the harness's process model.
5. **Widen `OVF` and `STATE` beyond their single-family origin.** `OVF` currently rests on
   `regex_construct` and `code_patch`; a generalising probe (answer fits a random 20 % holdout)
   would cover all 20.

## 9. Reproduce

```
python3 -m pytest -q                       # 137 tests
python3 -m vci audit --families all --out outputs
python3 -m vci label --sheet annotations/blind.csv --out annotations/labels.csv \
    --qualification --group-by-family --shuffle-seed 7
python3 -m vci audit --families all --out outputs     # with human labels present
```

Bootstrap intervals are seeded per block (`seed + 1 … seed + 6`), so a rerun reproduces the
same CI; only latency (`p95 ms`) depends on the machine.

---

# Round-6 addendum — real model failures replace synthetic mutants (6 families)

Rounds 1–5 measured verifiers against *authored* probes, so every TPR/TNR carried the
Just et al. ceiling (§7). Round 6 implements §8-1: a real local model
(`evalsft-qwen25-05b`, digest `075e6329e216…`, temperature 0, seed 20261104, single sample)
solves fresh tasks (a seed disjoint from the audit's), the family verifiers grade the parsed
outputs, and **all 779 units are hand-adjudicated by a human** against the task content.
Artifacts: `work/realfail.json` (raw run), `work/realfail_sheet.jsonl` (grading sheet),
`work/realfail_human.csv` (labels), `work/realfail_analysis.json` (metrics).
Reproduce: `python3 -m vci realfail` then `realfail-sheet` then `realfail-analyze`
(requires a local ollama server for the first step only).

## R6.1 What the model did

150 tasks, 0 transport errors, mean 2.0 s/task. Verifier accepted 25/150 tasks
(mean score 0.314). Per family (unit level, human truth):

| family | units | model correct (human) | verifier TPR | verifier TNR | κ | false acc | false rej |
|---|---|---|---|---|---|---|---|
| arith_expression | 87 | 6 (7 %) | 1.000 | 1.000 | 1.000 | 0 | 0 |
| unit_convert | 80 | 0 (0 %) | n/a | 1.000 | — | 0 | 0 |
| template_render | 125 | 29 (23 %) | 0.931 | 1.000 | 0.954 | 0 | 2 |
| log_field_extraction | 315 | 315 (100 %) | 1.000 | n/a | — | 0 | 0 |
| regex_construct | 105 | 7 (7 %) | **0.000** | 1.000 | — | 0 | 7 |
| sql_result | 67 | 12 (18 %) | 0.083 | 1.000 | 0.130 | 0 | 11 |
| **pooled** | 779 | 369 | **0.946** [0.918, 0.965] | **1.000** [0.991, 1.000] | 0.948 | **0** | **20** |

## R6.2 Findings

1. **Zero false accepts on 410 real wrong units** (TNR 1.000, Wilson lower 0.991). The leaks
   that synthetic probes proved exploitable — the sql_result memorized-constant query, the
   regex overfit alternation (x01, still open per round 5) — were *not exercised* by natural
   failures: the model did emit literal alternations of the visible positives in 6/25 regex
   tasks, but always corrupted (`a | b` with spaces around the pipe, or wrapped in dicts), so
   all were rejected. The leak is real and remains open; this particular failure distribution
   simply never produced a well-formed exploit. A stronger model plausibly would.
2. **The dominant real risk is false rejects (20/369 correct units, pooled TPR 0.946), and
   18/20 are packaging strictness, not grading logic**: correct regex patterns rejected because
   the model wrapped them as `{"pattern": …}` per unit (regex real TPR 0.000!); semantically
   correct SQL rejected for the same dict wrapping (sql real TPR 0.083); 2 money values
   rejected for being JSON numbers (`853.35`) instead of strings (`"853.35"`). This is exactly
   the EQUIV/format-strictness class that drove the synthetic 0.000 VCIs — corroborated on
   real outputs, from the accept side.
3. **Real defect modes barely overlap the synthetic operator set.** Among the 430 rejected
   units: 192 wrong values, 132 dict-wrapped answers, 79 missing answers (parse failure or
   truncated output), 27 enumeration-prefixed strings (`"1. 1/5"`). The synthetic wrongs are
   "close but wrong" scalars (off-by-one, sign flip, floor); natural failures are catastrophic
   (unit-name echoes, 10×–1000× magnitude errors, repeated identical values across all units,
   schema hallucination in SQL). `unit_convert`: 0/80 correct — a complete inability, which no
   synthetic probe predicted.
4. **The real model surfaced a task-side defect the probes never flagged.** In
   `arith_expression`, the generator evaluates strictly left-to-right but renders expressions
   with standard operator notation ("evaluate … with precedence" in the premise). 8/87 units
   across 7/25 tasks therefore have references that contradict the printed expression under
   standard precedence (e.g. `(11 - 2 * 6) / 5` expects `54/5`, i.e. `((11-2)*6)/5`). All 8
   model answers were wrong under *both* readings, so labels are unaffected — but a human or
   stronger model answering standard mathematics would be unfairly rejected on 28 % of tasks.
   This is a `task_under_specified`-class defect discovered *by* hand-grading real outputs.

## R6.3 What this does and does not change

- For these six families and this model, "the verifier accepts real garbage" is **not** the
  observed failure mode (0/410); "the verifier rejects correct-but-mispackaged answers" is
  (20/369). The round-3 repair list (close the leaks) remains valid as *adversarial*
  hardening, but deployment grading of weak models would first need output-schema tolerant
  extraction (unwrap `{"pattern": …}`, `{"sql": …}`, accept numeric money).
- Still synthetic-ceilinged: the other 14 families; any claim about stronger models (whose
  failure modes — including well-formed overfit exploits — may differ qualitatively);
  human-label κ from §4.2 (`annotations/labels.csv` still empty); and this study itself uses
  a single adjudicator, one model, temperature 0, one sample per task.
- The Just et al. ceiling is lifted exactly here and only here: real failures confirm the
  direction of the synthetic audit (strictness classes bit in reality) while reversing the
  perceived severity ranking (leaks matter less than false rejects, for this model).

---

# Round-7 addendum — the arith_expression render/eval mismatch is fixed (2026-11-04)

R6.2-4 found that the `arith_expression` generator evaluated strictly left-to-right while
rendering standard operator notation, contradicting the reference value on 7/25 tasks.
Round 7 changes `_expr` to accumulate with standard precedence (`*` before `+`/`-`), so the
reference now equals what a reader computes from the printed expression.  A new invariant
test (`test_arith_expression_reference_matches_the_printed_expression`, 30 seeds × 25
tasks = 750 tasks) checks `expected == eval(expr)` using Python's own evaluator as an
independent implementation; selfcheck stays clean.

The full audit was rerun after the fix.  **No metric moved**: arith VCI 0.9722 → 0.9722,
median VCI 0.9342 (CI 0.904–1.000; round-10 rerun later reads 0.969), families ≥ 0.70 stays 17/20, both core lists unchanged.
That is expected, not a disappointment: the fix changes task *content*, and every aligned
mutant and probe derives its expected verdict from the reference values, so the synthetic
audit is internally invariant to the change.  Where the defect actually bit was grading
*real* outputs — a standard-maths answer would have been unfairly rejected on 28 % of
tasks — which is exactly why it was found by hand-grading real outputs and not by the
probe suite.  The 8 affected units in the round-6 human sheet stay as labelled (the model
was wrong under both readings).  The validity ceiling of §7 is unchanged.

---

# Round-8 addendum — schema-tolerant extraction, measured as a counterfactual (2026-11-04)

R6.3 said deployment grading of weak models would first need output-schema tolerant
extraction.  Round 8 measures that counterfactual on the archived round-6 run **without
re-sampling the model**: `python3 -m vci realfail-tolerant` replays every archived payload
through regenerated tasks, re-grades each unit under two tolerant rule variants, and
recomputes agreement against the frozen human labels.  A family enters only if strict
replay reproduces its archived verdict bit-for-bit.  All six families passed; note that
arith_expression's round-7 precedence fix changed 8 reference values but 0 verdicts (the
model was already wrong on all 8), so the replay is verdict-identical.

Rule variants: **v1** = unwrap single-key dicts (`{"sql": …}`) + coerce JSON numbers to
strings; **v2** = v1 + keyed unwrap for multi-key dicts carrying a payload key
(`{"pattern": …, "description": …}`).

| variant | pooled TPR | pooled TNR | κ | units flipped | of which correct | new false accepts |
|---|---|---|---|---|---|---|
| strict (baseline) | 0.946 | 1.000 | 0.948 | — | — | — |
| v1 | 0.981 | 0.998 | 0.979 | 14 | 13 | 1 |
| v2 | **1.000** | 0.993 | 0.992 | 23 | 20 | 3 |

Per family (v2): template_render TPR .931 → 1.000; sql_result .083 → 1.000 (TNR .982);
regex_construct .000 → 1.000 (TNR .980).  v2 repairs **all 20** round-6 false rejects.

The three new false accepts are verifier weaknesses the strict path never reached — they
only become visible once tolerant extraction lets the answers in:

1. `regex_construct-009:r3` — `.*\d{1,3}` for a "starts with a lower-case letter, then
   3-16 chars of [a-z0-9_]" spec passes the sampled pos/neg probes under fullmatch
   semantics (the probe set contains no short lowercase-then-digit counterexample).
2. `regex_construct-022:r1` — an alternation hardcoding the three visible positive IPs;
   passes the sampled probes, fails the spec.  Both are the known loose-probe class
   (round-5's open regex leak), now observed on real outputs.
3. `sql_result-006:q2` — `ORDER BY AVG(amount) DESC` where the task demanded order by
   region; for this particular data the two orderings coincide, so result comparison
   passes (data-coincidence false accept).

So R6.2-2's "≥18 units, zero TNR cost" estimate is refined by measurement: the repair
count is 14 (v1) to 23 (v2) and the cost is small but **not** zero (1–3 new false accepts
out of 410 negatives, TNR ≥ 0.993).  Tolerance trades a little TNR for a lot of TPR.  If
tolerant extraction is adopted, v2's keyed unwrap should ship together with tightened
regex pos/neg probes — that is exactly where its new false accepts landed.

Artifact: `work/realfail_tolerant.json`.  Offline tests +8 (variant rules, per-rule
repairs, wrong-answer-stays-rejected, multi-key keyed unwrap, generator-drift exclusion).
Nothing in this section re-ran the model; the raw run and the human labels are untouched.

---

# Round 9 (2026-11-04): MFT-only tightening -- behavioural verifier hardening

Scope: **minimum-functionality probes only**.  Invariance and directional verifiers were
not touched; their TPR is unchanged (invariance 0.8636, directional 1.000).  The pass was
requested as the round-4 follow-up after the round-3 `code_patch` 0.131→0.756 lesson (that
gain came from probes authored to match the verifier, not from discrimination).  It ran on
top of rounds 4–8.

## What changed

1. `code_patch` (`vci/families/structural.py`): the verifier now executes the suite **twice
   in one process** and appends a **held-out input set** (`_CODE_HOLDOUT`, 2 inputs per
   template) that is not in the prompt, not in the fixture table the solver sees, and not
   imported by `vci.adversarial`.  Expected answers for the held-out inputs come from the
   task's own reference implementation.  This closes `HARD` (lookup table of the visible
   test answers), `OVF` (rules keyed to the visible shapes/sizes) and `STATE/x02` (correct
   for the first calls, degrading afterwards).
2. `regex_construct` (`vci/families/text.py`): every spec now carries held-out positive and
   negative strings that the prompt never shows and the probe builder never reads.  The
   verifier classifies the candidate pattern on them too.  This closes the alternation
   overfit that round 8 observed on real outputs (`regex_construct-022:r1`).
3. Probes (`vci/adversarial.py`, generator 4.0 → 5.0): code_patch `OVF` grows from 4 to 54
   probes (two per task, plus the historic chunk probe); `STATE` stays at 4 per task = 100.
   The new OVF payloads are asserted at test time to reproduce the reference answer on
   **every visible case** and to fail at least one held-out case, so they are genuine
   overfits rather than plain mutations.

## MFT per-family TNR, before → after (Wilson 95% CI on the after value)

| family | MFT negatives | TNR before | TNR after | 95% CI (after) |
|---|---|---|---|---|
| code_patch | 79 | **0.000** (n=29) | **1.000** | [0.954, 1.000] |
| regex_construct | 50 | **0.500** | **1.000** | [0.929, 1.000] |
| sql_result | 25 | 0.920 | 0.920 | [0.750, 0.978] |
| other 17 families | 0 (AMB positives only) | n/a | n/a | — |
| **pooled MFT** | **154** | **0.4615** (n=104) | **0.9870** | — |

"before" is the round-8 committed audit; "after" is this run.  The family-level before
values are reproduced on the **current** probe set by the paired check below, so the
headline delta is not an artifact of adding probes.

## Is this real discrimination or another probe artifact?

Self-check, in the order round 3 taught:

1. **Paired design.** Same probes, two verifiers (`work/mft_after_check.py`).  Legacy
   (round-3 harness / visible-only regex grading) vs hardened: code_patch 0.000 → 1.000 on
   the same 79 negatives, regex 0.500 → 1.000 on the same 50.  Only the verifier differs.
2. **Pre-existing probes carried the delta.** `code_patch x01` (HARD) and `x06` (chunk OVF)
   and the regex `x01` alternation were authored before this round.  They flip
   accepted → rejected without any probe edit, so the gain is not "write a probe the fix
   happens to catch".
3. **Construct validity is tested, not asserted.** `test_code_patch_overfit_rules_are_rejected_only_by_heldout_inputs`
   runs every OVF payload on all five templates and requires it to be correct on every
   visible case and wrong on at least one held-out case.  A payload that were also wrong on
   a visible case would be a plain mutation and could not support the attribution.
4. **Held-out independence.** The regex held-out strings are disjoint from the labelled
   strings the prompt shows (`test_regex_overfit_patterns_are_rejected_by_heldout_strings`);
   the code_patch held-out inputs live in a separate structure that `vci.adversarial` does
   not import (`test_only_the_code_patch_fixture_table_is_imported`).
5. **No new false rejects.** Accept-expected probes: code_patch 25/25 equivalents still
   accepted, regex 25/25 equivalents still accepted, and every other family's accept-expected
   pass count is identical before/after (false rejects unchanged in all 20 families).
   Invariance TPR 0.8636 and directional TPR 1.000 are unchanged.

Residual risk: the held-out sets and the OVF payload thresholds were written by the same
author in the same round.  The mitigating evidence is items 1–3 (pre-existing probes and a
construct-validity test).  What would falsify the claim: a correct-but-unusual patch that
passes the visible suite and fails held-out inputs.  None was found in the 10 reference
implementations tested, but this is synthetic evidence, not human-labelled.

## STATE/x02 and what remains undecidable

- `STATE/x02` is closed for `code_patch`: invariance-category TNR 0.7549 → 1.0000 (101
  rejected negatives, 0 accepted; `resource` class 0/101 accepted).  The two-pass harness
  makes late-call degradation observable.
- **Bounded call budget.** Two passes only catch state that manifests within the tested call
  count.  A candidate that is correct for the first 1,000 calls and degrades afterwards
  survives any fixed repeat count; deciding that needs a call-budget clause in the task
  contract, not a better verifier.  Reported as undecidable, not fixed.
- **Cross-task memory contamination.** Each task is verified in its own subprocess, so
  leakage *between tasks* is invisible by construction.  The within-task arity memo (`x05`)
  is caught; cross-task reuse would need the harness to share one process across tasks and a
  task-order-dependent expected answer.  Undecidable at the verifier level.
- **17 fixture-replay families (unit_convert, log_field_extraction, template_render, …).**
  Their payload is a static value, not an executable procedure.  There is no "rule" to
  overfit and no call history to contaminate: `OVF` and `STATE` are **not constructible**,
  not merely uncaught.  This is why "≥50 OVF/STATE per family" is achieved only for
  code_patch (OVF 54, STATE 100) and regex (OVF 50).  Writing probes there would measure
  nothing.
- **sql_result, 2/25 residual HARD accepts.** `rich_depts` reads only the `depts` table,
  which is identical on the visible and probe datasets, and for two task instances
  `regions_over_3`'s probe rows do not cross the `HAVING` boundary, so
  `expected_probe == expected_primary` and a constant answer passes both.  This is a
  **degenerate held-out dataset**, not verifier blindness.  It is decidable in principle
  with a provably discriminating second dataset (a second `depts` table plus a generated
  probe set guaranteed to change every answer); that is a task-data change, not done here.
- **50 MFT false rejects remain (unit_convert 25, template_render 25).**  These are
  `spec_ambiguity` positives (AMB), i.e. the task spec does not determine an answer; the
  verifier is right to reject.  Unchanged and out of scope.

## Verdict

MFT is **fixable, not structural** for the three defects that matter: hardcoding,
visible-case overfitting and state contamination are all decided by behaviour (unseen
inputs, changed shapes, repeated calls).  The gain (0.4615 → 0.9870) is real discrimination
on a paired design, not a probe artifact.  The residual MFT leak is 2/25 in `sql_result`
(degenerate held-out data) and the 50 AMB false rejects (under-specified tasks); the
undecidable parts are cross-task contamination and unbounded call budgets, which need task
interface guarantees rather than tighter verifiers.

# Round 10 (2026-11-04): real traces, SQL second dataset, directional coverage

## 1. Real model traces (highest priority)

A real local model was sampled, not simulated: **qwen2.5:7b** through ollama 0.33.3
(digest `845dbda0ea48…` in the manifest), temperature **0.0**, seed **20261104**, one
greedy sample per task, `num_predict=512`, timeout 180 s.  The run covers **all 20
families × 5 tasks = 100 tasks**; 100 scored, 0 transport errors.  Every record stores the
**verbatim prompt**, raw reply, decoding parameters and wall time in
`outputs/realfail-real.json` (215 KB); `outputs/realfail-real-sheet.jsonl` (529 unit rows)
splits each task into units with the model answer, the gold reference and the per-unit
verdict.  One record (`regex_construct`) failed to produce parseable JSON.

Results: **10/100 tasks accepted by the verifier, 90 real failures** (1 parse failure, 89
semantic/format failures; 10 + 90 = 100).  Against the strict gold reference at unit level,
**131/146 gold-correct real answers were accepted** and **0/288 wrong real answers were
accepted** — this is the round-10 **regraded oracle** (denominators are gold-checked units
with an extracted answer, 146 + 288 = 434, not the 529 sheet rows).  Two口径 labels apply:
(1) 529 sheet rows vs 434 units with an extracted answer (95 units have no parseable answer);
(2) 146/288 uses the code_patch regrade (+15 units) and treats `base_convert`'s representation
as verifier-adjudicated.  A strict-gold recheck on the same artifact instead yields
**128/306 with 3 accepted negatives**, all `base_convert` (expected stores the decimal input,
the model answers in the target base; the verifier decodes it correctly).  Full derivation:
[`outputs/number-reconciliation.md`](number-reconciliation.md).  The labels in that sentence
are gold-checked, **not human**; the raw replies are archived for review.  `sql_result` was
re-sampled after the second-dataset change and the manifest records the two segments.
These traces are deliberately **not merged into the VCI headline**: without a human sheet,
mixing them into TPR/TNR would grade the verifier against itself.  They are the
external-validity evidence and the seed for the next blind label sheet.

## 2. SQL: a provably discriminating second dataset

`PROBE_DEPTS` is a second `depts` table with different rows (MKT/Turing joins, ENG 950,
SLS 650), the visible orders cover only two of three regions while the held-out rows add
the third (four rows per region, four paid), and `top2_depts` gets one decisive row outside
the visible top two.  `make_one` asserts `expected_probe != expected_primary` for every
item, and the verifier executes the probe on the held-out `depts` table.  Result:

| family | MFT TNR before | after | n | VCI |
|---|---|---|---|---|
| `sql_result` | 0.920 | **1.000** | 25 | 0.798 → 0.844 |

Only the two previously degenerate HARD probes (`sql_result-020/021`, `x01`) flipped;
the other 23 HARD and all equivalence probes did not.

## 3. Directional positives

The round-3 premise "directional has no positives" was stale: round 5 already had 75
accept probes (TPR 1.000, `code_patch`/`regex_construct`/`sql_result`).  This round adds
**98 more** in four constraint-shaped families whose verifiers re-derive truth from the
task data, by changing the data and independently recomputing the answer: `grid_path`
(obstacles moved, 23 positives), `csp_assign` (node appended, 25), `schedule_slots`
(availability changed, 25), `topo_order` (node inserted, 25).

| directional | before | after |
|---|---|---|
| positives | 75 | **173** |
| TPR | 1.000 | **1.000** [0.978, 1.000] |
| TNR (stale answers) | 1.000 | **1.000** [0.994, 1.000] |

Each accept payload is rejected when checked against the *unshifted* task (vacuous-override
test), so the TPR is not produced by an override that accepts everything.

## 4. Rerun and artifact self-check

Full rerun, same seed: median **VCI 0.969** [0.904, 1.000] (aligned 0.986 at round 10;
the 2026-11-05 rerun reads 0.978 — see §8), 17/20 families
≥ 0.70, 20/20 reliable.  Pooled categories:

| category | n | n_pos | n_neg | TPR | TNR |
|---|---|---|---|---|---|
| minimum functionality | 204 | 50 | 154 | 0.000 [0, 0.071] | **1.000** [0.976, 1.000] |
| directional | 771 | 173 | 598 | **1.000** [0.978, 1.000] | **1.000** [0.994, 1.000] |
| invariance | 652 | 550 | 102 | 0.864 [0.832, 0.890] | 1.000 [0.964, 1.000] |

MFT TNR is now 1.000 (154/154), up from 0.987.  MFT TPR remains 0 because its only
positives are the 50 `spec_ambiguity` tasks that the verifier correctly rejects; invariance
TPR is unchanged at 0.864 (75 pre-existing false rejects, out of scope here).

Labels: κ and α are still **synthetic self-agreement**, upper bound 1.000, n = 6,854
aligned units / 13,708 decisions, **human rows = 0**; the non-aligned oracle gives
α = κ = 0.844 (n = 1,627).  The synthetic κ is not evidence of label quality.

Self-check (paired, same seed): the only probe verdicts that flipped were the two SQL HARD
probes fixed by the second dataset; no untouched probe flipped on its own; 14/15 untouched
families have identical verdict-derived metrics.  `code_patch`'s VCI moved 0.7799 → 0.7776
**only through latency** (`cheapness` 0.9794 → 0.9678, probe p95 30.9 → 34.3 ms); its
metrics and every verdict are identical.  No verifier code was changed for the SQL,
directional or real-sample work — the SQL gain comes from the data, and the directional
probes are new inputs, not a new accept rule.

## Verdict

The headline VCI did **not** rise (0.969 → 0.969).  What improved is coverage and
specificity at the bottom: MFT TNR closed to 1.000, SQL's last 2 leaks are gone, and
directional positives more than doubled with TPR 1.000.  The validity ceiling is still
**capped by label provenance** — every TPR/TNR denominator is synthetic or gold-derived,
human κ/α is 0 rows — and by the 50 AMB / 75 invariance false rejects.  Real traces now
exist in the repo, but a blind human sheet on them is what would raise the ceiling; no
model access was the blocker this round.

## 5. Exploit-signature check on the real outputs (round 10, continued)

`work/realfail_real_check.py` replays the archived run and mechanically flags the known
memorization signatures the synthetic probes encode: regex patterns that are pure
alternations of the visible positives or literally embed ≥2 of them, sql constant
(no-FROM) queries or queries embedding ≥2 visible reference literals, and `code_patch`
sources embedding ≥2 visible fixture outputs.  Result: **0 flagged units across all 500**
(`outputs/realfail-real-check.json`).  The round-6 speculation that a stronger model would
emit well-formed overfit exploits is therefore **not confirmed on this run** — the leak
remains demonstrated only by synthetic probes.  One greedy 7b sample per task cannot rule
the behaviour out; a temperature sweep would settle it.

## 6. code_patch envelope false-rejects and the adapt hook (round 10, continued)

The 7b run returned `code_patch` sources as a JSON list of lines (`{"answers": [...]}`),
while the verifier takes a single source string: all 23 archived units were false-rejects
("candidate is not Python source").  Replaying the archived payloads through a join — no
re-sampling — makes 3/5 tasks fully correct (visible 5/5, holdout rows ok, adapted_score
1.0); the two `count_vowels` tasks stay rejected, so the repair creates no false accepts
(`outputs/realfail-real-check.json → code_patch_regrade`: tasks 0 → 3 of 5, units 0/23 →
15/23 visible).  This is round-8's extraction fragility recurring on a second model, now
with a permanent fix: `Family.realfail_adapt` (default identity; `CodePatch` joins
list-of-lines) is applied inside `realfail run` (v2.1), so future runs grade the joined
source.  Archived records are unchanged and the regrade stays explicitly counterfactual.
The audit path is untouched: synthetic mutants already carry string payloads, so no probe
verdict or VCI number moved.  137 tests pass, including three new adapt tests.

## Next candidates (updated after §5/§6)

1. **Re-run the real model with the v2.1 harness** (needs ollama) so `code_patch` records
   are archived in adapted form; then re-issue the blind sheet including the 15 recovered
   units.
2. **Human labels** for the archived sheets.  Deterministic; needs a human.
3. **Harness-level cross-task contamination experiment** (process verifier at the run
   level, not per task).
4. **Generalise `OVF`** beyond regex/code_patch via a random-20%-holdout probe.

---

# Round 11 (2026-11-04): stronger-model retest — the exploit hypothesis fails a second time

Round-10 §5 mechanically checked the 7b run for the memorization signatures the
synthetic leaks encode and found 0/500 units, leaving "a stronger model plausibly
would" open.  Round 11 retests that with **qwen2.5-coder:14b** (coding-specialised,
digest `9ec8897f747e…`) on the *same* 100 tasks as the 7b run — 20 families × 5,
seed 20261104, temperature 0.0, `num_predict` 512, one sample, i.e. only the model
changes.  The 100 records are `outputs/realfail-coder14b-100.json` (0 transport
errors).  A second 100-record replicate of the same tasks at `num_predict` 1024
(the earlier interrupted attempt, `outputs/realfail-coder14b-full.json` +
`outputs/realfail-coder14b-rest17.json`) reproduces the same picture and is
reported as a within-model robustness check.  All tables live on disk:
`outputs/realfail-compare.json` (buckets, per-family, matched pairs, leak list),
`outputs/realfail-coder14b-100-audit.md` / `.json` (accepted samples with prompt,
answer, reference and verifier evidence).  Analysis code: `work/round11_failmix.py`
(taxonomy), `work/round11_audit.py` (evidence dump), `work/round11_finalize.py`
(one-shot report), `work/realfail_real_check.py` (exploit signatures).

## R11.1 Findings

1. **Acceptance doubles, deep-failure share rises modestly, nothing new appears.**
   22/100 tasks accepted (0.22) vs 7b's 10/100 (0.10).  Buckets (14b / 7b):
   FORMAT 0/6, HARD 0/0, SPEC 15/10, STATE 0/0, PARTIAL 28/29, DRIFT 0/0,
   CALC 35/45, correct 22/10.  Strict deep share (HARD+SPEC+STATE+DRIFT)
   15/78 = **0.192** vs 10/90 = **0.111**; counting PARTIAL as deep gives 0.551 vs
   0.433.  So the stronger model does not fail *deeper* — it fails in the same
   shallow arithmetic/partial cell — but it fails a bit more often in the SPEC
   cell, and all 15 SPEC records sit in exactly three template-bound families
   (`grid_path` 5, `schedule_slots` 5, `template_render` 5; 7b: `grid_path` 5,
   `template_render` 5).  The taxonomy's HARD bucket is **0/100 coder14b records**
   (7b: 0/100): no literal copies, no well-formed overfit exploits.
2. **Accepted output is concentrated where the task is perception, not reasoning.**
   10 of the 22 accepts are the two extraction families (`json_schema_extract` 5/5,
   `log_field_extraction` 5/5), plus 4 `sql_result` accepts whose queries were
   executed on both the primary and the second dataset.  The remaining 8 are
   `arith_expression` 2, `date_arith` 2, `regex_construct` 2, `csp_assign` 1,
   `code_patch` 1.  Accept rate is therefore not a reasoning score: half of it is
   reading values out of the prompt.
3. **0 false accepts, 0 false rejects, 0 memorization exploits.**  On the
   reference-graded families every accepted answer equals the generator's
   reference.  The 12 ALT-family accepts were audited by hand: `sql_result`
   queries reproduce both result sets, `code_patch` passes all 5 hidden tests,
   `csp_assign` gives a different but constraint-satisfying colouring, and the
   two `regex_construct` accepts use general patterns (`^\d{1,3}(\.\d{1,3}){3}$`,
   `^([0-9a-f]{2} ){1,2}[0-9a-f]{2}$`; the latter covers the spec's labelled
   2–3-pair domain, and no 1-pair or 4-pair `must not` case exists, so this is
   spec under-specification rather than a leak).  Suspected leaks: **0 of 22**
   (cumulative real-output false accepts: 0 across 300 records, 299 scored).
4. **The tail does not decay for the stronger model.**  Accuracy by unit position
   for coder14b rises 0.39 → 0.65 from position 1 to 8; 7b falls 0.29 → 0.13.
   `code_patch` improves from 5/5 FORMAT (7b) to 0 FORMAT, 1 correct, 4 CALC at
   the *same* 512-token budget, so the round-10 FORMAT drop is model-attributable
   after all (the 1024-token replicate only confirms it).

## R11.2 Boundaries

- Still greedy single-sample local models ≤ 14B, one seed set; the 1024-token
  replicate is the same model, not an independent family of behaviour.  A
  temperature sweep or a frontier API model is untested — recon
  (`outputs/realfail-recon.json`, `work/round11_keys.json`) records no API keys
  (names only) and no usable GPU, so that path is blocked, not merely undone.
  32B cannot be loaded (weights + KV exceed 14 GiB RAM and the 11 GiB free disk).
- The taxonomy's false-reject cell is blind for the seven ALT families (gold is
  the verifier's own execution); their 12 accepts rest on manual audit.
- **Comparator defect found and fixed while auditing.**  `_as_num` coerced
  zero-padded digit strings, so different `life_step` grid rows (`001011` vs
  `0001011`) compared equal and one record was mislabelled STATE.  Labels now
  reject `-?0\d+` strings; that record reverts to CALC and STATE is 0/100.
- The Just et al. ceiling is untouched where no real trace exists; every
  synthetic TPR/TNR in §1–§6 stands unchanged.

## R11.3 What changes

The evidence on "the verifier accepts real garbage" is now: three real-model runs
(7b 100, coder14b 100 at 512, coder14b 100 at 1024), **0 false accepts, 0
memorization exploits**, and 0 false rejects.  Switching to a model twice the size
with a coding-specialised vocabulary changed *which* tasks pass (extraction and
SQL) and *where* the residuals land (three template families), but not the
verdict on the verifier.  For natural outputs of local models the risk order from
round 6 stands: **extraction/packaging strictness > memorization leaks**.  The
synthetic leak classes remain precautionary hardening targets, not observed
deployment failures.

---

# Round-12 addendum — cross-task contamination: the round-9 "undecidable" is quantified (2026-11-05)

Round 9 declared cross-task memory contamination *undecidable at the verifier
level* because the production harness verifies every candidate in its own
subprocess.  Round 12 turns that qualitative statement into a measured one with
a second harness-level differential (the round-4 experiment measured execution
strategy *within* a task; this one measures isolation strategy *across* tasks).
New module `vci/cross_task.py`, CLI `cross-task-diff`, artifact
`work/cross_task_diff.json`; no production code, probe, or VCI number moved.

**Design.**  Strategy A is production: one fresh subprocess per candidate, the
numeric judge in the parent.  Strategy B is a naive batch harness: a whole run
of candidates `exec`ed sequentially in ONE shared process, judge included — the
shape a real harness takes when it trades isolation for spawn cost.  The probe
is a contaminant–victim pair: the contaminant is fully correct code for its own
template plus one poison line (`import builtins`; rewrite `abs`/`sum`/`sorted`),
and the victim is a later candidate whose verdict depends on the poisoned
primitive.  Three vectors: `judge_abs` (the in-process near-equality judge
degenerates → a wrong `safe_div` off-by-0.1 answer is accepted — a
contamination-driven *false accept*), `candidate_sum` and `candidate_sorted`
(correct victims compute garbage → *false rejects*).  Two controls pin the
attribution: a no-contaminant batch and a reversed batch must both reproduce A.

**Results [M]** (3 vectors × 5 contaminant slots = 15 pairs):

| quantity | A (isolated) | B (shared process) |
|---|---|---|
| victim verdict flips | **0 / 15** | **15 / 15** (5 false accepts, 10 false rejects) |
| contaminant accepted | 15 / 15 | 15 / 15 (it *is* correct code) |
| contaminant caught by the static `_BANNED` filter | 0 / 15 (`import builtins` is not banned) | – |
| controls (no contaminant / reversed order) | – | both match A exactly |

The flips are order-dependent state leakage, not a bias of the batch runner:
with the victim scheduled before the contaminant, B agrees with A on every pair.

**What this changes.**  "Undecidable" is refined: cross-task contamination is
*decided by the harness's process model, not by verifier logic*.  Per-candidate
isolation decides it to zero (invisible = defended); a shared process decides
it to 15/15 against the run — including corruption of the judge itself, which
no per-task verifier can see.  For real harnesses that batch candidates into
one process to save spawn cost, part of any score difference may be a
contamination component, and the static filter does not see the vector
(0/15): isolation, not screening, is the defence.  The validity ceiling is
unchanged: contaminant and victim are synthetic constructions (the Just et al.
ceiling is untouched), the experiment covers only `code_patch` (the single
family whose payload is an executable procedure; for the 17 fixture-replay
families cross-task state is *not constructible*, not merely unmeasured), and
whether real model output carries process-level side effects is untested —
scanning the archived real traces for side-effect signatures is the named
follow-up.  **Closed in round 14 (below): zero.**

---

# Round-14 addendum — real traces carry zero process-level side effects (2026-11-05)

Round 12's named follow-up: does *real* model output carry the side effects
that made strategy B collapse synthetically?  Round 14 scans all archived
real traces without re-running any model (`work/side_effect_scan.py`,
artifact `outputs/realfail-side-effects.json`).  AST scan of every
`code_patch` payload plus a regex scan of every verbatim `raw_response`
(covering the families whose payload is not executable), for:
`builtins.X =` / `setattr(builtins,…)`, `sys.modules[…]` writes,
`os.environ` writes (all process-level, contamination-capable),
`globals()[…] =` and top-level builtin shadowing (namespace-local), and
`import builtins` (precursor).

**Result [M]: 0 / 450 records across all five archived runs** (round-6 0.5b
150, round-10 7b 100, round-11 coder14b 100@512, and the 100@1024 replicate
in two segments).  Zero contamination-capable, zero namespace-local, zero
precursor hits — including a zero from the raw-response regex channel, so
the claim does not rest on parser reach.  Construct validity is pinned by
test: the scanner flags all three round-12 poison vectors and none of the
five correct template implementations.  The only unscannable payloads are
4 coder14b `code_patch` answers truncated mid-function by the 512-token
budget (verbatim text still regex-scanned, 0 hits).

Interpretation, kept narrow: for greedy single-sample local models ≤ 14B on
this task suite, cross-task contamination via process-level side effects is
a *harness-design* risk, not an *observed output* risk — real candidates do
not even attempt the vector.  The round-12 advice stands on different
footing: isolation defends against a synthetic adversary, not against
anything these models actually emit.  Bounds: greedy decoding only, no
frontier model, no agentic tool-use traces (an agent that *runs* code is
the population where side effects would plausibly appear); the scan covers
Python process state, not filesystem or network effects.  The Just et al.
ceiling is untouched — this round added real-distribution evidence *about a
synthetic vector's absence*, not about defect coverage.

---

# Round-15 addendum — temperature sweep: the exploit hypothesis fails a third time (2026-11-07)

Round-10 §5 and round-11 R11.2 left one named hypothesis open: every real
trace so far was a *greedy* single sample, so "a temperature sweep would
settle" whether well-formed overfit exploits — the synthetic leak classes of
§4 (HARD/OVF memorization) — appear once the decoding distribution has
variance.  Round 15 runs that sweep.  Script `work/temp_sweep.py` (local,
like the other round scripts); artifacts `outputs/realfail-tempsweep.json`
(+ `-check.json`) and `outputs/realfail-tempsweep-hot.json` (+ `-check.json`).

**Design.**  The three exploit-prone families only (`regex_construct`,
`sql_result`, `code_patch` — the ones the signature scanner encodes), 5
tasks each, model **qwen2.5-coder:14b** — the *same checkpoint* as round 11
(digest `9ec8897f747e…`), so only the decoding distribution differs from the
greedy archive.  Samples: 2 per task at temperature 0.7 and 1.0 (main arm,
60 records), plus a supplementary arm at temperature 1.3, 2 per task
(30 records), because at ≤ 1.0 several tasks produced near-identical
answers across samples (all 4 sql samples of task 001 were the same query —
low-entropy sampling would have made a null verdict weak).  Distinct seeds
per sample; prompts byte-identical to the round-11 protocol; every sample
goes through the same parse → `realfail_adapt` → verify path as `realfail
run`; 90/90 parsed, 0 transport errors, total wall 937 s (mean 10.4 s).

**Result [M]: 0 / 90 units flagged by the round-10 exploit-signature scan,
0 accepted flagged units** (regex pure-alternation / ≥ 2-literal
memorization, sql constant or ≥ 2-literal queries, code_patch ≥ 2-literal
lookup tables).  Accepts under sampling: 26/60 at ≤ 1.0 (sql 16/20 — each
verified by execution on *both* the primary and the held-out dataset;
code_patch 5/20 — hidden-test 5/5; regex 5/20) and 12/30 at 1.3.  All 38
accepted samples were audited by hand: canonical general solutions of the
same classes round 11 audited (real `GROUP BY … HAVING` queries, character-
class patterns like `^(\d{1,3}\.){3}\d{1,3}$`, a genuine `safe_div`
implementation), none a disguised overfit.  Sampling diversity was real
where it matters: at 1.3, regex emitted 10/10 distinct payloads.

**What this settles.**  The memorization-exploit question is now closed
along both axes it could be tested on locally: model strength (7b → 14b
coder-specialised, round 11) *and* decoding diversity (greedy → temp 1.3).
Cumulative real-output evidence stands at **0 well-formed overfit exploits
across 390 archived real records** (7b greedy 100, 14b greedy 200, 14b
sampled 90).  The synthetic leak classes remain what rounds 9–10 made them:
precautionary hardening targets demonstrated only by authored probes; the
already-hardened verifiers (held-out regex strings, second sql dataset,
two-pass code harness) never met an exploit-shaped payload, because the
sweep produced none.  The validity ceiling of §7 is unchanged: this round
adds real-distribution evidence about a synthetic vector's *absence*, not
defect coverage.

Bounds: local models ≤ 14B, temperature ≤ 1.3, one task suite, no frontier
model, 4 samples per task per temperature.  The signature scan is
mechanical and shape-based; subtle overfits are caught by the held-out
verification plus the manual audit of accepts, not by the scan alone.
Suite size is now **201 tests** (§9's count below is historical).


---

# Round-17 addendum — is one agent run the run's verdict? Replays of the agent suite (2026-11-07)

Every agent verdict in this repo (§R15/§R16) is a **single greedy sample**.
The 11-05 and 11-06 archives of the same 6-task suite were produced at
temperature 0.0 with the same seed and the *same served weights*
(`9ec8897f747e…`) — and they disagreed on `agt-02-running-max` (pass → fail).
That makes "a repeated run reproduces the run" a testable claim instead of a
premise.  This round replays the suite and measures it.

**Design.**  6 tasks × 7 replicas = 42 task-runs, 126 emitted turns, same
model digest, seed `20261105`, `num_predict 448`, `max_turns 6`, fresh
session per task, prompts byte-identical across archives.  Replica 0 is the
11-06 archive; replicas 1–4 are fresh runs under the continuously loaded
model; replicas 5–6 run after `keep_alive: 0` evicted the model, i.e. under
fresh loads (each re-loaded with the same 4,791,247,830 / 9,953,733,507-byte
VRAM split, ctx 4096).  Code `work/agent_replicate_run.py` +
`work/agent_reload_run.py`, analysis in `vci/agent_trace.replicate_report`
(CLI `vci agent-replicate`, offline), artifacts
`outputs/agent-replicates.json` + `outputs/agent-replicate-summary.json`.

**Result [M]: 6/6 tasks turn-identical across all 7 replicas** — text and
tool arguments byte-for-byte, 0 verdict flips, 0 answer differences, 0 grader
drift between stored and recomputed grades.  `pass@1 = 4/6 = 0.667` in every
replica, and `pass^k = 0.667` for k = 2…7: the repeat axis carries no
variance, so reliability equals single-sample accuracy here.  Forced
unload/reload did not change a byte either.

**The one flip that exists.**  Comparing the 11-05 archive with the 11-06
archive over 5 tasks the older run covers (`agt-06` is absent there, so it
is excluded as partial): `verdict-unstable = [agt-02-running-max]`,
`pass@1 = 0.625` vs `pass^k = 0.600`.  The divergence is inside turn 0 at
character 276, *before* the 448-token cap: 11-05 chose a `for`-loop,
11-06 a list comprehension; the loop's turn then ran into `num_predict` and
its stored text ends mid-string, so the harness executed a salvaged
truncated call.  So the difference starts in the solver's greedy choice, not
in the harness — and the harness diff between those two commits touched
output parsing and `task_ids` only, never the request body.  Same weights,
same seed, same temperature, same prompt bytes: this is one unresolved
server-side nondeterminism event, n = 1, not reproducible in 6 controlled
replays.

**Quantified risk.**  Same-protocol instability: 0 / 42 cells → 95% upper
bound 7.1% per cell (rule of three).  Cover from the single cross-archive
pair: 1 / 6 tasks, which with n = 1 bounds nothing — it is an existence
proof, not a rate.

**What this changes.**  The archived single-run agent evidence can be cited
as "reproducible within one serving generation, and reproducible across
reloads on this host", instead of being an untested assumption.  It also
puts a number on the harness-version effect already measured in §R16: the
pre-fix parser lost 2 of 12 turns (16.7%) in `agt-05`, which changes the
conversation the model sees and is a protocol change, not a model change —
so pre-fix and post-fix archives must never be pooled.

Bounds: temperature 0.0 only, so this is *reproducibility of one greedy
sample*, **not** sampling variance (that is measured on GSM8K with
temperature > 0, round 13); one 6-task suite, one 14B local model, four
model load generations on one host (the 11-06 archive, one continuous
08:06–08:47 load, and two forced evict/reload cycles); the manifest does not
record the ollama version or the VRAM split of the historical runs, which is
exactly what would be needed to name the cause of the single flip.  The
Just et al. ceiling is untouched — synthetic lab tasks, no human labels.
Suite size is now **214 tests locally / 204 in a clean clone** (the earlier
counts here are historical).

## R18. Sampling-variance arm: is a greedy verdict representative of the decoder?

**Question.**  R17 showed that greedy replays are stable (0/42 verdict flips).
That still leaves the sampling axis unmeasured: `pass^k` over replays collapses
onto `pass@1` *because temperature is pinned at 0.0*, so the archive could not
distinguish "the verdict is reliable" from "the decoding path is unique".  This
round runs the same suite at temperature 1.0 with four distinct seeds and
changes nothing else.

**Design.**  6 tasks × 4 samples = 24 task-runs, 24 fresh sessions, temperature
1.0, seeds `20261105 + 7919k` (k = 0…3), model digest `9ec8897f747e…`,
`num_predict 448`, `max_turns 6`, `timeout 600 s`, prompts byte-identical to
R17 (scratch slices execute with the same `sys.path` injection, so `sympy`
remains importable).  Sample wall times: 826 / 729 / 754 / 693 s (3,002 s total,
plus one model load).  Code `work/agent_sampling_run.py`; analysis
`vci/agent_trace.sampling_report` (CLI `vci agent-sampling`, offline, pure
recompute over archives); artifacts `outputs/agent-samples.json`,
`outputs/agent-samples/temp1.0-sample-0[0-3].json`,
`outputs/agent-sampling-summary.json`.

**Result [M] (24 cells, 4 samples × 6 tasks).**
Per-sample pass rates are 4/6, 4/6, 3/6, 3/6; pooled `pass@1 = 14/24 = 0.583`
(bootstrap over tasks, 95% CI [0.250, 0.917]).  The greedy baseline is
`4/6 = 0.667` — the maximum observed per-sample rate, +0.083 (one task) above
the sample mean, and no task where the greedy verdict disagrees with *all* four
samples (`n_greedy_disagrees = 0`).

Per-task stability classes: 2 stable-pass (`agt-01-wordfreq`,
`agt-03-weighted-avg`), 2 stable-fail (`agt-02-running-max`,
`agt-05-log-latency`), 2 mixed (`agt-04-primes` 3/4, `agt-06-sort-records` 3/4).
`pass^k` (all k samples pass) = 0.583 / 0.500 / 0.417 / 0.333 for k = 1…4
(k = 4 95% CI [0.000, 0.667]); `pass@k` (any sample passes) = 0.583 / 0.667 /
0.667 / 0.667.  Answer stability is 4/6 tasks (identical answer in all four
samples); two tasks produced two distinct answers.  Turn text differs in **6/6**
tasks (4 distinct trajectories each), and turn counts differ (`agt-03` 2 vs 3,
`agt-04` 2 vs 3, `agt-06` 2 vs 3), so temperature is demonstrably active.

**Failure anatomy [M].**  The two stable failures are deterministic and
structural, not decoding noise:
`agt-02-running-max` submits 39 comma-separated values against the 40-value
reference (first mismatch at index 30, identical in all four samples, 4/4
`submit_answer` calls), i.e. a manual re-typing/serialization defect after a
correct-looking tool run; `agt-05-log-latency` makes **0** `submit_answer`
calls and always exhausts the 6-turn budget while re-emitting a truncated copy
of the log list (4/4, `final_answer = null`).

Both mixed tasks flip through *the same* harness-contract mechanism.  The
`run_python` scratch session captures stdout only (`contextlib.redirect_stdout`
around `exec`, no REPL echo), so a bare final expression returns an empty
result.  In the failing `agt-04-primes` sample the last statements are bare
`len(primes)` and then bare `count`, the tool returns nothing, and the model
submits 1354 instead of 501; the three passing samples all end with
`print(...)`.  In the failing `agt-06-sort-records` sample the sort itself is
correct (`key=lambda x: (-x[1], x[2])`) but the last statement is bare
`result`, so the tool again returns nothing and the submitted order is a
fabricated permutation (`id116,id126,id127,id130,id120,…`) rather than the
reference.  So the verdict variance lives in whether the solver asks for
evidence (`print`) or assumes REPL echo, not in arithmetic.


**What this changes.**  R17's `pass^k = pass@1` is repeat-axis stability at
temperature 0.0 and must not be cited as verdict reliability.  On the sampling
axis the verdict is not deterministic: 2/6 tasks change verdict across four
draws, and a single greedy run sits at the top of the observed range.  It does
**not** show arithmetic unreliability — both stable failures are task
comprehension/turn-budget, identical in every sample, and would not be fixed by
a sampler; both flips are empty-tool-output events under a bare-expression
contract, i.e. a harness/usage interaction.  Net: the archived single-run score
is reproducible but optimistic by one task at this sample size, and pass^k at
temp 0 measures the harness, not the model's sampling distribution.

Bounds: one 6-task synthetic suite, one 14B local model, one non-zero
temperature (1.0), four samples per task, n = 6 tasks (per-task rates are k/4),
no human labels; the bootstrap over six tasks is coarse, so the CIs describe
this suite, not a general sampling-variance law.  The Just et al. ceiling is
untouched: these are authored tasks with machine references.  Suite size is
now **219 tests locally / 209 in a clean clone** (earlier counts are
historical).

**Next candidates.**  (1) Run k = 12 on the two mixed tasks only, to put a
denominator on the flip rate (1/4 currently cannot separate 10% from 40%);
(2) offline failure-mode classifier over all 66 archived task-runs (R17 42 +
R18 24), testing whether the final tool-call shape (`print(...)` vs bare
expression) predicts the flips, alongside turn-budget and serialization;
(3) record ollama version and VRAM split in the manifest and repeat under a
constrained-VRAM split (R17 leftover).

## R19. Failure-mode audit: the empty-output mechanism explains the flips, not the failure mass

**Question.**  R18 attributed the two verdict flips to the stdout-only tool
contract (`run_python` captures stdout, not the value of a bare final
expression) and wrote that "the verdict variance lives in whether the solver
asks for evidence (`print`) or assumes REPL echo".  That is a claim about why
runs fail, so it is testable offline over every archived agent task-run:
classify each run's observable failure mode, cross-tabulate the empty-output
predictor against the verdict, and replay failing trajectories under an
echo-capable harness.

**Design.**  Eleven archives -- R17's 7 greedy replicas (6 tasks) and R18's 4
temperature-1.0 samples (6 tasks), one model digest -- give 66 task-runs.
Byte-identical trajectories are collapsed *before* any rate is computed
(R17's seven copies are one observation): 66 cells -> **28 unique
trajectories**.  Classification is read-only over `tool_calls` / `turns`
(final statement parsed with `ast`; stdout length; submitted-vs-reference list
length).  Echo replay re-executes archived snippets in a fresh 15 s
subprocess under a second runner that returns the value of each snippet's
final bare expression *alongside* stdout.  Code
`vci/agent_trace.failure_report` + `echo_replay`, CLI
`vci agent-failure-modes`, artifact `outputs/agent-failure-modes.json`.

**Result [M].**

| failure mode | unique trajectories (n=28) | archived cells (n=66) |
|---|---|---|
| pass | 17 | 42 |
| `length_mismatch` (submitted list length != reference) | 5 | 11 |
| `no_submit_truncated_tool_error` (no answer, snippet truncated) | 4 | 11 |
| `empty_tool_output` (submit after an empty tool result) | 2 | 2 |

`pass@1` is **42/66 = 0.636** over archived cells and **17/28 = 0.607** over
unique trajectories; the gap is replica inflation, not a second estimate.
Empty last tool output: **2/2 failed** (fail rate 1.00) versus **9/26 = 0.346**
without it, Fisher two-sided **p = 0.1455**.  The direction matches R18, but
at n = 2 this is a mechanism/existence check, *not* a validated predictor.
The two empty-output cells are exactly the two mixed-task failing samples of
R18 (`agt-04-primes`, `agt-06-sort-records`); no other unique trajectory has
an empty final stdout.

**Echo counterfactual [M].**  Eleven unique failing trajectories replayed:
**2 recover a correct echoed value** (`agt-04` -> `501`; `agt-06` -> the
correct id order), 5 `agt-02` rows echo nothing (last statement is a `print`;
stdout already carried 40 values while the submitted string held 39), and 4
`agt-05` rows are **unreplayable** (the archived snippet is truncated by
`num_predict` and raises `SyntaxError`).  So `pass@1` on unique trajectories
would move **0.607 -> 0.679 (+0.071)** if the model submitted the echoed
value.  That is an upper bound: echo changes the observation and therefore the
rest of the trajectory, which was not re-run.

**What this changes.**  R18's sentence survives only in its narrow form: both
observed flips are bare-expression cells, and both carried the correct value
at the last tool call.  It does **not** generalise to the failure mass --
9 of 11 unique failures carry non-empty evidence, and the two dominant modes
are structural: 5 serialization/`length_mismatch` defects (39 of 40 values
re-typed by hand) and 4 turn-budget/truncation failures with no
`submit_answer`.  The harness contract is a 2/2 explanation of the flips and
a 2/11 explanation of failures; citing it as the main failure cause would be
wrong.  This is also the smallest honest form of the harness-differential
question: same task set, two execution contracts, and a quantified (upper
bound) score difference of +0.071 on this suite.

Bounds: one 6-task synthetic suite, one 14B local model, one host, two
decoding settings; classifier features are shape-level, so a hidden reasoning
error that happens to end in `print(...)` is labelled
`evidence_present_wrong_answer` without further attribution.  The echo arm is
an upper bound, not a predicted score.  The Just et al. ceiling is untouched:
authored tasks with machine references, no human labels.  Suite size is now
**224 tests locally / 214 passed + 2 skipped in a clean clone** (earlier
counts are historical).

**Next candidates.**  (1) Run k = 12 on the two mixed tasks only -- the
flip-rate denominator R18 named, still unrun; (2) fill
`annotations/labels.csv`, the only step that lifts the κ/α ceiling; (3) widen
the suite beyond 6 tasks so the pooled `pass@1` CI is informative.

## R20. Flip-rate denominator: k = 12 on the two mixed tasks

**Question.**  R18 reported each mixed task at 3/4 samples and wrote that n = 4
cannot tell a 10 % failure rate from 40 %.  `pass^k` was also uninformative
there because k was capped at 4.  This round extends the *same* sampling axis
(temperature 1.0, seed `20261105 + 7919k`, byte-identical prompts /
`num_predict 448` / `max_turns 6`) to k = 12 on exactly the two mixed tasks.

**Design.**  Samples 0–3 are the R18 archives (reused verbatim, not re-run);
samples 4–11 were generated here, 2 tasks per sample, wall 69–157 s per sample
(8 samples, 766 s).  Model digest `9ec8897f747e…` (same weights as R17/R18).
Every per-sample file is a 2-task archive and the merged artifact trims the
R18 archives to the same two tasks, so all reports see 2 tasks × 12 samples =
**24 cells** (23 unique trajectories; one byte-identical pair).  Code
`work/agent_mixed_k12.py`; analysis `vci/agent_trace.flip_rate_report` (new
CLI `vci agent-flip-rate`, offline) plus the R19 `failure_report` /
`echo_replay`; artifacts `outputs/agent-mixed-k12.json`,
`outputs/agent-samples/mixed12/sample-00..11.json`,
`outputs/agent-flip-rate.json`, `outputs/agent-mixed-k12-failure-modes.json`.

**Result [M].**

| quantity | value |
|---|---|
| pooled `pass@1` (24 cells) | **0.750**, Wilson 95 % CI [0.551, 0.880] |
| `agt-04-primes` | **8/12 = 0.667**, CI [0.391, 0.862], flip rate **0.444** |
| `agt-06-sort-records` | **10/12 = 0.833**, CI [0.552, 0.953], flip rate **0.278** |
| mean resample disagreement (2p(1−p)) | **0.361** |
| `pass^k` (all k samples pass), k = 1…10 | 0.750 / 0.553 / 0.400 / 0.283 / 0.194 / 0.129 / 0.081 / 0.046 / 0.023 / **0.0076** |
| `pass@k` (any sample passes), k = 2…5 | 0.947 / 0.991 / 0.999 / **1.000** |

(`pass^k` stops at k = 10 because that is the estimator's default cap; it
would continue falling with a larger k given 8/12 and 10/12 pass rates.)

Per-sample pass rates over the two tasks: 1.0, 1.0, 0.5, 0.5, 1.0, 0.5, 1.0,
0.5, 0.5, 1.0, 1.0, 0.5 (18/24).  The R18 four-sample reading (0.75 pass rate,
2p(1−p) = 0.375) is within 0.014 of the 12-sample mean disagreement (0.361):
the light estimate was numerically close, but only now does it carry an
interval.  The interval is still wide — 0.391–0.862 for `agt-04` does not
exclude the 40 % failure reading — so what k = 12 buys is a denominator and a
flip statistic, not a tight rate.

**Failure anatomy [M].**  Six unique failing trajectories among 23 unique cells:
**5** end on a tool call with empty stdout (4 of them a bare final expression),
**1** is a turn-budget/truncation failure (6 turns, no `submit_answer`, archived
snippet raises `SyntaxError` on replay).  The empty-output predictor on this
pair is now statistically visible: 4 flagged cells, **4/4 failed** vs
**2/19 = 0.105** without the flag, Fisher two-sided **p = 0.0017** (R19 had
n = 2 and p = 0.146; this is the same mechanism with four times the
denominator, not a new claim).  Echo replay recovers **4 of 6** unique failures
(`agt-04` → 501 twice; `agt-06` → the correct id order twice), so
`pass@1` on unique trajectories moves **0.739 → 0.913 (+0.174)** under an
echoing harness — again an upper bound, because the observation would change
the rest of the trajectory.  Counting differs by denominator and is labelled:
the flip table above counts **all** cells (agt-06 10/12), the mode table and
the echo replay count **unique** cells (agt-06 9/11, `agt-04` 8/12), because
one passing `agt-06` trajectory appears twice byte-for-byte.

**What this changes.**  R19's sentence "the harness contract is a 2/11
explanation of failures" holds *for the whole suite*; on this two-task pair it
is **5/6**.  The difference is compositional, not contradictory: these two
tasks are compute-then-report tasks, so the failure surface is dominated by
"did the solver print", while the six-task suite's failure mass is dominated
by serialization and turn budget.  The practical reading: verdict variance on
these tasks is real (flip rate 0.36 pooled, i.e. roughly one draw in three
disagrees with another), a single run is therefore not a reliability
measurement, and the ~99× drop from `pass@1` 0.750 to `pass^10` 0.0076 is the
honest cost of scoring a stochastic solver once.

Bounds: two synthetic tasks, one 14B local model, one host, one temperature,
no human labels; flip rate is a property of this task pair and this decoder,
not of the verifier.  The agent grader is machine-checked (`grade_answer`
against authored references), so the Just et al. ceiling is untouched.  Test
suite is now **227 tests locally / 217 passed + 2 skipped in a clean clone**
(224 → 227: three round-20 tests; earlier counts are historical).

**Next candidates.**  (1) Fill `annotations/labels.csv` — still the only step
that lifts the κ/α ceiling, and still the top item; (2) widen the agent suite
beyond 6 tasks (the pooled `pass@1` CI and the flip rate both need task
diversity, not more samples of the same two tasks); (3) make the echo contract
a *selectable* production runner and run a paired arm (score difference
measured rather than bounded); (4) carry the same k = 12 design to the
stable-fail tasks to see whether they stay structural at 12 draws.

## R21. Paired harness differential: the echo contract measured, not bounded

**Question.**  R19 bounded the echo harness at +0.071 on the 11 unique suite
failures; R20 bounded it at +0.174 on the two mixed tasks by *replaying*
archived failures and assuming the rest of the trajectory unchanged.  Both
numbers are counterfactuals.  R20's next-candidate (3) was to turn the echo
contract into a selectable runner and run a genuinely paired arm, so the
difference is measured with a variance on the same seeds.

**Design.**  `vci/agent_trace.py` now routes the session through
`HARNESS_RUNNERS = {stdout, echo}`; `run_task(..., echo=True)` appends the
value of a final bare expression to the tool result the model observes and
changes nothing else.  The echo arm was run on the same axis as R20:
`qwen2.5-coder:14b`, digest `9ec8897f747e…`, temperature 1.0, seed
`20261105 + 7919k` for k = 0…11, `num_predict 448`, `max_turns 6`, tasks
`agt-04-primes` and `agt-06-sort-records`, fresh session per task.  Paired by
`manifest.seed` (a seed missing from an arm is dropped from both, never
half-counted).  24 cells in the echo arm, wall **1,071.6 s** (65.6–151.7 s per
sample), 0 transport or parse errors.  Code `work/agent_echo_run.py`; analysis
`paired_harness_report` (new CLI `vci agent-echo-paired`, offline); artifacts
`outputs/agent-echo-k12.json`, `outputs/agent-samples/echo12/sample-00..11.json`,
`outputs/agent-echo-paired.json`.

**Result [M].**

| quantity | value |
|---|---|
| base (`stdout`) `pass@1` | **18/24 = 0.750**, Wilson 95 % CI [0.551, 0.880] |
| echo (`stdout` + bare-expression value) `pass@1` | **22/24 = 0.917**, CI [0.742, 0.977] |
| measured delta | **+0.167** |
| cell table (both / base-only / echo-only / both-fail) | **18 / 0 / 4 / 2** |
| exact McNemar, pooled | **p = 0.125** (4 : 0) |
| per-seed delta | mean **0.167**, sd **0.246** (4 of 12 seeds +0.5, 8 of 12 0.0) |
| `agt-04-primes` | 8/12 → **10/12**, delta +0.167, p = 0.5 |
| `agt-06-sort-records` | 10/12 → **12/12**, delta +0.167, p = 0.5 |
| mean resample disagreement, 2p(1−p) | **0.361 → 0.139** (agt-04 0.444 → 0.278; agt-06 0.278 → **0.000**) |

**It is really one variable.**  The two arms' manifests agree on model, model
digest, host, temperature, `num_predict`, `max_turns`, `suite_size` and session
policy.  The one manifest field that differs is `task_ids`: the R20 base
archive still lists the full six-task suite in its manifest although its
records were trimmed to the same two tasks (a bookkeeping residue of the R20
merge, not a run difference — the analysis reads records only).  At the record
level, **20 of 24 final answers are byte-identical** between arms; the four
that changed are exactly the four `echo_only` cells, i.e. every changed answer
turned a failure into a pass, and **no passing cell was disturbed**.  The two
residual echo failures split cleanly: seed `20316538` ends with
`final_answer = None` (turn budget, no `submit_answer` — the echo contract
cannot help), and seed `20348214` answers `'348'` in **both** arms (the same
genuinely wrong computation, unchanged — again not an observation problem).

**What this changes.**  R20's +0.174 upper bound predicted +0.167 measured:
the bound was tight for this pair, and the measured effect comes with zero
regressions in 24 cells.  The flip statistic is the more interesting half:
`agt-06` goes from a 0.278 resample disagreement to **0.000** under echo, so
the entire verdict variance of that task was the observation contract, not the
solver.  But significance is *not* reached: 4 discordant cells in one
direction give exact McNemar p = 0.125, so "echo is better" is a directionally
consistent measurement at this n, not a demonstrated effect at the 5 % level,
and a true delta of 0 is not excluded.  Citing the point estimate (+0.167)
without the p = 0.125 would overstate it; citing p alone would hide that the
sign is 4:0 and no cell regressed.

Bounds: two synthetic tasks, one 14B local model, one host, one temperature,
no human labels.  The echo arm changes what the *system* observes, so this is
a harness effect on this decoder, not evidence that verifier validity (VCI)
improves, and the Just et al. ceiling is untouched.  Test suite is now
**232 tests locally / 222 passed + 2 skipped in a clean clone** (227 → 232:
five round-21 tests; earlier counts are historical).

**Next candidates.**  (1) Fill `annotations/labels.csv` — still the only step
that lifts the κ/α ceiling; (2) run the paired echo arm on the two
**stable-fail** suite tasks (`agt-02-running-max`, `agt-05-log-latency`, 0/4 at
temperature 1.0), where R19 predicts the contract cannot help and the replay
already showed agt-02 echoes nothing while agt-05 is unreplayable — a predicted
null, live, is the cheapest falsification test this design has; (3) widen the
agent suite beyond 6 tasks; (4) raise paired n only if the 4:0 sign survives
the stable-fail arm, since n = 24 cannot reach significance at a 0.17 effect.

## R22. Stable-fail paired echo arm: the predicted null, live

**Question.** R21's next-candidate (2) asked for the cheapest falsification
test of the harness-differential story: run the paired `stdout` / `echo` arms
on the two stable-fail suite tasks, where R19 predicted the echo contract
cannot help. This section records that cloud rerun; it does not retroactively
change R21's mixed-task measurement.

**Design.** Both arms were run on AMD/Radeon cloud with `qwen2.5-coder:14b`,
digest `9ec8897f747e…`, temperature 1.0, seeds `20261105 + 7919*k` for
`k=0..11`, `num_predict=448`, `max_turns=6`, and fresh session per task.
Tasks: `agt-02-running-max` and `agt-05-log-latency`. The only manifest field
differing between arms is `harness` (`stdout_only (production)` vs
`stdout+repl_echo (round-19 counterfactual, live)`). Both arms contain 12
complete two-record archives; pairing is by `manifest.seed`. Committed
artifacts: `outputs/round22/agent-stable-stdout-k12.json`,
`outputs/round22/agent-stable-echo-k12.json`,
`outputs/round22/agent-stable-echo-paired.json`, and `outputs/round22/round22.log`.
Offline verification command: `python3 examples/verify_round22.py`.

**Result [M].**

| quantity | value |
|---|---|
| stdout `pass@1` | **9/24 = 0.375**, Wilson 95% CI [0.2116, 0.5729] |
| echo `pass@1` | **9/24 = 0.375**, Wilson 95% CI [0.2116, 0.5729] |
| measured delta | **0.0** |
| cell table (both / base-only / echo-only / both-fail) | **9 / 0 / 0 / 15** |
| exact McNemar, pooled | **p = 1.0** |
| per-seed delta | mean **0.0**, sd **0.0** |
| `agt-02-running-max` | 9/12 → 9/12, delta 0.0, p = 1.0 |
| `agt-05-log-latency` | 0/12 → 0/12, delta 0.0, p = 1.0 |

The echo contract changed no verdict on this task pair: there are zero
discordant cells, so an exact McNemar test has no evidence of an arm effect.
This is the pre-registered null R19 predicted. It also shows that R21's
`+0.167` on the mixed `agt-04` / `agt-06` task pair is task-composition
specific: the observation contract affects that "compute-then-report" failure
surface, but does not rescue a serialization/turn-budget surface.

**Bounds.** Two synthetic tasks, one 14B model, one temperature, 12 paired
seeds, no human labels. The confidence intervals remain wide; `p=1.0` means
this experiment found no discordant cells, not that the two harnesses are
universally equivalent, and it is not a verifier-validity (VCI) improvement.
The Just et al. ceiling is untouched. The older local stopped-run artifacts
(`outputs/agent-samples/stable-stdout12/`,
`outputs/agent-stable-stdout-k12.json`) are partial and are not merged into
this result.

**Next candidates.** (1) Fill `annotations/labels.csv`, still the only step
that lifts the κ/α ceiling; (2) widen the agent suite beyond six tasks;
(3) do not raise paired `n` for this null unless a wider task set produces a
discordant signal worth resolving.


