# VCI Specification (v0.1)

This document is the normative definition of the Verification Coverage Index as
implemented in this repository. Every quantity below is computed by
`vci/metrics.py`; if this document and the code disagree, the code is the
authority and the document is a bug.

---

## 1. Why a single number

The hypothesis under test: *in open-domain tasks, how much RL experience can be
absorbed is bounded by the share of behaviour that can be checked cheaply,
trustworthily and densely.* A check that is expensive, unreliable or binary
gives the learner little usable signal. VCI compresses those three properties
into one scalar per task family so families can be compared and rank-ordered.

VCI is explicitly **not** a measure of task difficulty, model quality or
usefulness. It measures *checkability* only.

## 2. Task and candidate model

A `Task` carries:

| field | meaning |
|---|---|
| `family` | registry name |
| `task_id` | `<family>-<NNN>` |
| `prompt` | the literal text shown to a solver |
| `items` | `K` independently gradeable units, each `{unit, expected, ...}` |
| `meta` | family-private data needed by the verifier |

A `Candidate` is one attempted answer with `payload` and a `defect` label from
the taxonomy in section 6.

Grading rules, identical for all 20 families:

1. The payload is normalised into `answers_by_unit` plus `extra_units`.
   A list payload maps positionally onto units; a mapping payload maps by unit
   key. Unknown keys or trailing elements become `extra_units`.
2. Each unit yields `(ok, detail)` from `grade_item`.
3. `score = sum(w_i * ok_i) / sum(w_i)` — weights are 1 in every family today.
4. `passed = all(ok_i) and not extra_units`.
   Partial credit is reported but does **not** count as a pass. RL-relevant
   acceptance is all-or-nothing.
5. A verifier exception is caught, recorded as `verifier exception`, and scored
   as a failed unit. A verifier must never crash the audit.

`Verdict` is always `{passed, score, evidence, cost_ms}`. `evidence` is a list
of `{unit, ok, detail}`. No family may return anything else.

## 3. The three components

### 3.1 Cheapness `C`

Latency is measured per verification call with `time.perf_counter()`.

```
p95 = 95th percentile of cost_ms over every candidate in the family
C   = 1                                if p95 <= 20 ms
    = (500 - p95) / (500 - 20)         if 20 < p95 < 500
    = 0                                if p95 >= 500
```

Rationale: a check costing 20 ms or less can run on every rollout without
becoming the bottleneck; 500 ms is the point where an outer-loop optimiser
would have to subsample checks. The interpolation is a convenience, not a
physical law, and is the same for every family so ranking is unaffected.

### 3.2 Trust `T`

Let `pos` be candidates labelled correct (canonical **and** semantic
equivalent) and `neg` candidates from the wrong classes (excluding `partial`).

```
TPR   = mean(passed  for pos)
TNR   = mean(not passed for neg)
fa_full = mean(score >= 1.0 for neg)
tau90 = the largest positive score t such that #{pos: score >= t} >= ceil(0.9 * |pos|)
FAR90 = mean(score >= tau90 for neg)
T     = min(TPR, TNR, 1 - FAR90)
```

* `TPR` is measured at the **full-credit** operating point, because that is what
  an RL loop consumes. A verifier that gives 0.8 to a correct answer is a
  failure for training even though its ranking may be fine.
* `FAR90` answers "if I loosen acceptance until I recover 90% of correct
  answers, how much junk do I let in". `1 - FAR90` is the tolerance-cost term.
* `T` is squared in the VCI formula because a false accept does not merely add
  noise, it reinforces the wrong behaviour; the penalty is deliberately convex.
* `min` (not a product) prevents a strong TNR from masking a broken TPR.

`tp_equiv` is reported separately: the pass rate restricted to
`semantic_equivalent` candidates. This is the failure mode verifiers most often
have, and it must not be hidden inside the aggregate TPR.

### 3.3 Density `D`

Density measures how much of a task's quality a check can see. A single
pass/fail bit carries one bit of information regardless of how much work the
task contains, so a family of monolithic tasks is sparse even if its checks are
perfect.

For a task with `K` units and the `K-1` partial candidates that keep exactly
`j` of `K` units correct:

```
granularity g = min(1, (K - 1) / 3)
fidelity    f = 1 - mean_j |score_j - j / K|
D_task        = g * f
D_family      = mean over seed tasks
```

Consequences:

* `K = 1` → `D = 0`. A binary signal is, by definition, not dense.
* `K = 2` → `g = 0.33`, `K = 4+` → `g = 1`.
* A verifier that ignores partial credit (`score` always 0 or 1) gets `f ≈ 0`
  and therefore `D ≈ 0`, even on a 10-unit task.

## 4. VCI

```
VCI = (C * T^2 * D) ** 0.25        if C, T, D > 0
    = 0                            otherwise
```

The fourth root is a geometric mean, so VCI is on the same 0–1 scale as its
components, is zero if any component is zero, and cannot be inflated by
excelling at one component while failing another. A family that is cheap and
dense but only 50% trustworthy caps at `0.5 ** 0.5 = 0.707`; a family that is
perfectly trustworthy but only gives binary credit caps at `D ** 0.25`.

## 5. Sampling and intervals

* **Seed tasks.** `n_tasks` (default 25) per family, generated from
  `Random(family_seed(seed, index))` with
  `family_seed(s, i) = s * 100003 + i * 97 + 11`. Twenty-five is a compromise
  between coverage and runtime; the generator is written so that increasing it
  to 100 needs no code change, only a longer run.
* **Candidates.** Every task emits 1 canonical answer, 1–2 semantic
  equivalents, 7 wrong classes, and `K-1` partials. All are graded.
* **Task-level bootstrap.** For a family, resample its tasks with replacement
  `n_boot` times (default 500), recompute every component from scratch on the
  resample, and report the 2.5/97.5 percentiles of the resulting VCI.
* **Family-level interval.** The median-VCI interval resamples the family
  values themselves, because families are the unit of analysis.
* **Proportions** (TPR, TNR, FAR90, κ) are reported with Wilson intervals at
  95% where a proportion is the headline; the family VCI interval is the
  bootstrap above.

`--seed` changes every generated task and every mutant. The run manifest
records the seed, task count, family list and Python version, and the
`SHA-256`-free design means the outputs are reproducible from the seed alone as
long as the source tree is unchanged.

## 6. Defect taxonomy

| label | applied to | construction rule |
|---|---|---|
| `correct` | correct | the reference answer |
| `semantic_equivalent` | correct | same meaning, different spelling (different valid colouring, alternate shortest path, equivalent SQL, `(?:…)` regex wrapper, ids as floats, …) |
| `boundary` | wrong | an inclusive/exclusive or quantifier edge is moved by one *class*, e.g. `>=`→`>`, `{6}`→`{1,8}`, no end-of-month clamp |
| `off_by_one` | wrong | a single index, limit, colour or date is displaced by exactly one |
| `type_mismatch` | wrong | correct value, wrong JSON type (string vs int, null, nested object) |
| `order` | wrong | correct multiset, wrong sequence |
| `missing` | wrong | one unit absent |
| `extra` | wrong | one unit too many, or an unknown key |
| `semantic_wrong` | wrong | a plausible but wrong computation (median for mean, transposed result, wrong join, edge violated) |
| `partial` | wrong | exactly `j` of `K` units correct, `1 <= j < K`; used only for density |

**Every wrong mutant is validated at generation time.** If a wrong-class
candidate happens to reproduce the reference result — for example because a
symmetric matrix transposes to itself, or because rounding a large number to
two decimals is still inside a relative tolerance — the generator substitutes a
guaranteed-different value. `python -m vci selfcheck` runs this check across
families and seeds and must print `selfcheck clean`; a contradictory mutant is a
generator bug, not a verifier result.

## 7. Annotation consistency κ

Cohen's κ between the author's blind labels and the verifier's `passed`:

```
po = (a + d) / n                      # observed agreement
pe = ((a + b)/n) * ((a + c)/n) + ((c + d)/n) * ((b + d)/n)
κ  = (po - pe) / (1 - pe)             # 0 if pe == 1
```

where `a` = both accept, `b` = verifier accepts / human rejects,
`c` = verifier rejects / human accepts, `d` = both reject.

The sample is produced by `python -m vci annotate`: two rows per family, the
semantic equivalent and the highest-scoring partial (i.e. exactly the two cases
where a mechanical verifier is most likely to disagree with a person). The
defect label is withheld; the canonical answer is shown as a reference. With
`n = 2` per family, per-family κ is not estimable, so the gate uses the pooled
κ over all 40 rows and each family is marked `kappa.source = pooled-human` with
its borrowed count.

If no sheet exists, the audit falls back to the labels produced by the mutant
generator itself and marks every row `kappa.source = synthetic`. That value is
**an upper bound and must never be reported as independent validation**: §6
requires the generator and the verifier to agree completely, so the synthetic
agreement is 1.00 by construction whenever `selfcheck` is clean. `results.json`
therefore carries both numbers (`kappa.synthetic`, `kappa.human`) and the source
flag, and the memo must quote the flag alongside the value.

Single annotator: the author. This measures whether the written spec and the
written verifier agree with a human reading of the same prompt. It is **not**
inter-annotator agreement, and cannot detect a bias shared by the author and
the verifier.

## 8. Reliability gate

A family is *reliable* iff all four hold:

```
TPR >= 0.90, TNR >= 0.90, FAR90 <= 0.20, κ >= 0.60
```

Otherwise the family is reported with an explicit reason list. A family that
fails is not deleted and not patched into passing; it keeps its VCI and is
labelled untrustworthy, because a high VCI built on an unreliable verifier is
the exact failure mode this audit exists to catch.

## 9. Family inclusion criteria

A task family may enter the registry only if:

1. It has a decidable ground truth checkable without a trained judge.
2. It admits at least 2 independently gradeable units per task, so density is
   measurable at all.
3. It admits at least one legal answer that differs textually from the
   reference, so paraphrase tolerance is testable.
4. Its verifier is expressible in pure Python + standard library: no network,
   no proprietary model, no human in the loop.
5. It exists in the wild as an open-domain task shape, not as a puzzle invented
   to make the numbers look good.

## 10. Known limitations

* **Synthetic mutants are easy.** Mutants are authored alongside the verifier,
  so they share its notion of "wrong". TPR/TNR measured this way are an
  optimistic upper bound. The audit therefore reports `tp_equiv` separately and
  treats `κ` as the only outside check on the labels.
* **Small seeds.** 25 tasks per family gives wide bootstrap intervals; the
  median across 20 families is more stable than any single family's number.
* **Latency is hardware dependent.** Only `cost_ms` depends on the machine;
  every other number is a pure function of `(seed, family set)`.
* **Semantic equivalence is only sampled.** Each family has 1–2 paraphrase
  forms; a verifier could accept those and still reject a third spelling.
* **`D` is a proxy.** Units per task is a design choice, not a property of the
  domain; a family with `K = 3` is penalised relative to `K = 5` even if both
  are equally checkable in principle.
