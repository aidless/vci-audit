# VCI audit — round 3 memo

**Run**: `python3 -m vci audit --families all --out outputs` · seed `0` · 25 tasks/family · 20 families ·
6,849 aligned candidates · **1,232 non-aligned probes (1,231 scored, 1 `observe`)** · probe generator
`v3.0` · 500 bootstrap resamples · Linux / Python 3.
Numbers: `outputs/results.json`; per-family table: `outputs/coverage.md`; every probe with its verdict
and basis: `outputs/attribution.csv`; dashboard: `outputs/dashboard.html`.
Round-1 and round-2 memos are preserved in git history.

---

## Round-5 addendum — positive directional probes, authored where they are measurable (2026-11-04)

Round 5 closed the §8-3 blank **for the families where it can be closed honestly**:
150 `directional_shift` probes (operator `DIR`, generator `v4.0`), one accept/reject pair
per task for `sql_result`, `regex_construct`, `code_patch`.  Each probe carries a
`task_override` — a perturbed copy of the task — and `audit` verifies the candidate
against the override.  Accept probes submit the independently recomputed correct answer
to the perturbed input; reject probes submit the answer that was correct *before* the
change.

**Result:** the `directional` row is now measured — n=575, pos=75/neg=500, **TPR 1.00,
TNR 1.00, FAR90 0.00**, zero false rejects, zero stale accepts.  The sharp side is the
stale-answer one: the sql constant-queries that memorise the visible primary result
(the two HARD leaks of §4) are now caught 25/25 once the dataset shifts; the regex
alternation of the original positives fails on fresh unseen strings 25/25; the
`code_patch` implementation of the original spec fails the shifted spec's hidden cases
25/25.

**Structural finding (why 3 families, not 20):** seventeen verifiers in this suite grade
the payload against expected values stored in the task itself.  There, a perturbed
(input, truth) pair is accepted *by construction* — authoring 425 positive directional
probes would manufacture a meaningless TPR 1.00.  Only verifiers that re-derive truth by
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
  VCI is unchanged (0.934).  Probe κ 0.664 → 0.701 [0.662, 0.736], α 0.666 → 0.701
  (n=1,381 scored probes).

The validity ceiling of §7 is unchanged: all new probes are still synthetic, and the
directional row additionally measures only execution-derived verifiers by construction.

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
python3 -m pytest -q                       # 112 tests
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
