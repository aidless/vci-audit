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
median VCI 0.9342 (CI 0.904–1.000), families ≥ 0.70 stays 17/20, both core lists unchanged.
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

Results: **10/100 tasks accepted by the verifier, 89 real failures** (1 parse failure, 88
semantic/format failures).  Against the strict gold reference at unit level, **131/146
gold-correct real answers were accepted** and **0/288 wrong real answers were accepted**
(earlier wording said 131/131 and 0/303; the code_patch regrade in §6 moved 15 units from
"wrong" to "gold-correct", so the denominators are 146/288).  The labels in that sentence
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

Full rerun, same seed: median **VCI 0.969** [0.904, 1.000] (aligned 0.986), 17/20 families
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
follow-up.
