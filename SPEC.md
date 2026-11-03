# VCI Specification (v0.3)

This document is the normative definition of the Verification Coverage Index as
implemented in this repository. Every quantity below is computed by
`vci/metrics.py` and `vci/audit.py`; if this document and the code disagree, the
code is the authority and the document is a bug.

v0.2 changes the trust term: `T` is now measured twice, on the round-1 aligned
mutants and on a round-2 sample constructed independently of the verifier
(§3.4), and the headline `T` is the weaker of the two. κ gains human and
human-stability sources (§7). The VCI formula itself is unchanged.

v0.3 adds no formula. It adds bookkeeping the earlier rounds lacked:

1. every probe carries a CheckList category, a mutation operator, a generator
   version and a *verdict basis*, so TPR/TNR are reported per category (§3.5)
   instead of only pooled;
2. a three-way attribution table separates "verifier too strict" from "task
   under-specified" from "true defect", published as one row per probe in
   `attribution.csv` (§3.5.2);
3. Krippendorff's α (ordinal, `undecidable` = missing) is reported beside κ, and
   §7.3 states when the two must diverge.

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

`T` is computed on two disjoint sample sources and then combined conservatively:

```
T_aligned     = T over round-1 mutants (generator and verifier share code)
T_non_aligned = T over round-2 probes  (labels decided outside the verifier, §3.4)
T             = min(T_aligned, T_non_aligned)
```

Round-1 mutants are authored next to the verifier, so `T_aligned` is an optimistic
upper bound by construction. `T_non_aligned` is the honest term. `min` is used
because a verifier that looks perfect on its own mutants and leaks on
independently built ones is only as trustworthy as the stress test shows; no
weighted average is taken, since averaging would let a perfect aligned score hide
a collapsing non-aligned one.

When one side has no usable sample (all probes are `observe`, or a family has no
probe builder), that side falls back to the other and the row records which
regime supplied the number.

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

### 3.4 Non-aligned probes

`vci/adversarial.py` builds a second candidate source whose expected treatment is
fixed **before** the verifier is called. The independence contract, enforced by
`tests/test_adversarial.py` via AST inspection, is:

1. It never calls `verify`, `grade_item`, `canonical`, `equivalents`, `wrongs`,
   `corrupt_item`, `extract_answers`, `mutate` or `partial`.
2. Expected values are recomputed from the prompt rule and the task's public
   fixture data by reference implementations written inside the module (own
   rational formatter, own BFS, own scheduler, own formatter), not by the
   family's own "correct" answer string.
3. The only cross-module import is the code-patch fixture *table* (inputs and
   function names); the expected values come from `adversarial._CODE_IMPL`.
4. `expectation` is a measurement target, not a fallback. A probe whose
   expectation is `reject` and which the verifier accepts is reported as a leak.

Each probe carries `failure_class ∈ {hardcoded_expected, overfit_to_tests,
spec_ambiguity, silent_partial, semantic_equivalent, resource}` and
`expectation ∈ {accept, reject, observe}`, plus the round-3 bookkeeping fields
`checklist_category`, `operator`, `generator_version` and `basis` (§3.5).

`observe` is used where the verifier contract has no policy — an allocation that
costs ~16 MB, but no memory budget is specified. Observe rows are recorded
(note, basis, latency) and **excluded from TPR, TNR and FAR90**, because counting
them as either pass or fail would manufacture a trust number the contract never
promised. They are reported in `per_failure_class` with `n_observe`.

A task therefore contributes `records` (aligned) and `probes` (non-aligned),
never mixed into one pool except for the pooled κ in §7.

### 3.5 CheckList categories, operators and attribution

#### 3.5.1 Categories

Each probe is assigned the CheckList test type it corresponds to (Ribeiro et al.,
ACL 2020), because a verifier can be good at one type and blind to another, and
a pooled TPR/TNR hides exactly that.

| category | the question it asks | failure classes mapped to it |
|---|---|---|
| `minimum_functionality` | does the answer do the stated job on an input it was not authored against? | `hardcoded_expected`, `overfit_to_tests`, `spec_ambiguity` |
| `invariance` | does an irrelevant change (spelling, call count, task order) leave the verdict unchanged? | `semantic_equivalent`, `resource` |
| `directional` | does the required perturbation flip the verdict in the stated direction? | `silent_partial` |

The mapping is an authored judgment, one `CATEGORY_BY_CLASS` table in
`vci/adversarial.py`; it is not derived. In particular `spec_ambiguity` sits in
`minimum_functionality` because it asks whether the stated minimum job is
accepted under a second defensible reading — even though the defect it reveals
is in the prompt (§3.5.2). `directional` currently has **no positive probe**, so
its TPR is reported as undefined (`-`) rather than as `0.00`; an unmeasured rate
is not a measured zero.

#### 3.5.2 Attribution table

Every non-aligned probe is classified once, from fields fixed before the
verifier is called:

| attribution | condition | what it means |
|---|---|---|
| `verifier_too_strict` | `expectation == accept` and the verifier rejected it, on a `semantic_equivalent` probe | a false reject caused by the verifier |
| `task_under_specified` | `expectation == accept` and the verifier rejected it, on a `spec_ambiguity` probe | a false reject caused by the prompt, not the verifier |
| `true_defect`, detail `caught` / `missed` | `expectation == reject` | the verifier rejected / accepted a genuine defect |
| `agreement` | `expectation == reject` and rejected | true negative |
| `observe` | `expectation == observe` | measured, excluded from TPR/TNR/FAR90 |

The rule is mechanical: the bucket is a function of `(failure_class,
expectation, passed)`, never of a post-hoc judgement. `attribution.csv` holds
**one row per probe** (`family`, `cand_id`, `category`, `operator`,
`generator_version`, `expectation`, `label`, `passed`, `attribution`, `basis`,
`verifier_evidence`), so any row can be re-derived by re-running the verifier on
the recorded probe. `results.json` keeps only capped `examples` per bucket, so
the JSON does not grow with the probe count.

#### 3.5.3 Operators

`vci/adversarial.py` holds the normative operator table (`OPERATORS`), each with
the real defect it stands for and its representative weakness. The operator set
is `AOR, ROR, CR, SDL, TR, OVF, HARD, STATE, NONDET, INF, EQUIV, AMB`; a test
fails if the table and the code drift apart.

**Synthetic mutants are not real defects.** Just et al. (FSE 2014) show mutants
correlate with real faults but are easier to kill and their distribution is not
the distribution of real faults. TPR/TNR in this repository are therefore an
optimistic upper bound on deployment behaviour and never an estimate of it. This
is a validity ceiling on the whole round, not a caveat on one probe class; §10
restates it and the memo must state it without softening.

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
* **Probes.** Every task also emits 2–6 non-aligned probes (§3.4). The expensive
  ones (a `while True` timeout, a ~16 MB allocation) run once per family, on its
  first task, so the extra cost is O(families) rather than O(tasks).
* **Task-level bootstrap.** For a family, resample its tasks with replacement
  `n_boot` times (default 500), recompute **every component including both trust
  regimes** from scratch on the resample, and report the 2.5/97.5 percentiles of
  the resulting VCI. Task resampling is the correct unit because aligned mutants
  and probes of the same task share one prompt.
* **Family-level interval.** The median-VCI interval resamples the family
  values themselves, because families are the unit of analysis.
* **Proportions** (TPR, TNR, FAR90, κ) are reported with Wilson intervals at
  95% where a proportion is the headline; the family VCI interval is the
  bootstrap above. κ additionally gets a row-level bootstrap interval, because
  the annotation sample is small and a point estimate alone would overstate
  precision.

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

Cohen's κ between a label source and the verifier's `passed`:

```
po = (a + d) / n                      # observed agreement
pe = ((a + b)/n) * ((a + c)/n) + ((c + d)/n) * ((b + d)/n)
κ  = (po - pe) / (1 - pe)             # 0 if pe == 1
```

where `a` = both accept, `b` = verifier accepts / label rejects, `c` = verifier
rejects / label accepts, `d` = both reject. Every κ carries a row-level bootstrap
interval (2.5/97.5 percentiles over `n_boot` resamples of the rows), because the
annotation sample is small and a bare point estimate invites over-reading.

### 7.1 Three sources, never merged

| source | labels come from | when it is the effective source | what it can and cannot show |
|---|---|---|---|
| `synthetic` | the mutant generator's own `defect` field | only when no `labels.csv` exists | an **upper bound**: §6 forces generator/verifier agreement, so `selfcheck clean` makes this 1.00 by construction. It can only reveal an accidental verifier bug, never a verifier blind spot. |
| `human` | `annotations/labels.csv`, filled blind via `python -m vci label` | whenever at least one decided human row exists | whether a person reading the same prompt agrees with the verifier. Single annotator, so it is not inter-annotator agreement. |
| `human-stability` | the same annotator's second pass, `annotations/labels_retest.csv`, re-ordered | reported always, used never as a headline | whether the **annotator** is consistent; a low value invalidates the human κ for that family, it does not improve the verifier's score. |

`results.json` carries all three (`kappa.human`, `kappa.synthetic`,
`kappa.stability`) plus the `source` flag and the row counts. A synthetic κ is
**never** reported as if it were human. When a family has fewer than
`per_family` labelled rows it borrows the pooled human κ and the row is marked
`kappa.source = pooled-human` with the borrowed `n`; that is a borrowing flag, not
evidence of per-family stability.

`undecidable` rows are stored (`labels.csv` value `undecidable`) and counted in
`n_undecidable`, but excluded from κ: they are a finding about the prompt, and
folding them into either class would turn a specification gap into fake
disagreement.

### 7.2 Sample sizes and what they support

`python -m vci annotate` emits three rows per family (an aligned paraphrase, the
highest-scoring partial, and preferably a `semantic_equivalent` or
`spec_ambiguity` probe) — 60 rows for 20 families. That is enough for a pooled κ
with a usable interval, **not** enough to certify a single family: the per-family
bootstrap interval will often span most of [0, 1]. The audit therefore keeps
`core_human_backed` separate from `core_provisional`, and the memo may only place
a family in the human-backed list when its own sheet is dense enough that the
interval excludes 0.60, or when several families share one pooled value quoted as
pooled.

Single annotator: the author. This measures whether the written spec and the
written verifier agree with a human reading of the same prompt. It is **not**
inter-annotator agreement, and it cannot detect a bias shared by the author and
the verifier. That limitation survives this round.

### 7.3 Krippendorff's α, and when it disagrees with κ

κ is computed on a two-class collapsed label (accept / reject) and is blind to
the third label. α is computed on the three-level ordinal scale
`fail < partial < yes`, using Krippendorff's ordinal distance

```
delta^2(c, k) = ( sum_{g=c..k} n_g - (n_c + n_k)/2 )^2
α = 1 - D_o / D_e
```

`undecidable` is **missing data**, not a category: it is dropped from both
`D_o` and `D_e` and counted in `n_undecidable`. Units with a single decided
rating are not pairable; when nothing is pairable α is `None`, not 1.

The two must diverge in exactly these cases, and the report states which one it
is looking at:

| situation | κ | α | why |
|---|---|---|---|
| many `undecidable` rows | unchanged, they are simply excluded | falls sharply (`n` shrinks, agreement is over fewer units) | κ cannot see how much was thrown away; α reports it |
| disagreement between adjacent levels (fail vs partial) | counted as full disagreement | down-weighted | κ collapses the scale, α keeps the distance |
| label skew (e.g. 90% accept) | collapses toward 0 and can go negative even with high raw agreement | also corrected for chance, but the ordinal marginal is smoother | κ's expected agreement is unstable when one cell dominates |
| fewer than ~30 decided rows | wide bootstrap interval | wider still, and `None` if unpairable | neither supports a per-family claim; only the pooled value does |
| perfect two-class agreement | 1.00 | 1.00 | identical by construction: with two values the ordinal distance is a constant multiple of the nominal one |

α is reported **beside** κ and never instead of it: κ is the gate quantity
(§8) because it is the one the round-1/2 protocol defined, and changing the
gate metric mid-audit would silently move the threshold. `results.json` carries
`summary.alpha_pooled` (effective, human, synthetic, oracle-on-probes,
undecidable count, unit count and CI) and each family's `alpha` block.

## 8. Reliability gate

A family is *reliable* iff all four hold:

```
TPR >= 0.90, TNR >= 0.90, FAR90 <= 0.20, κ >= 0.60
```

The gate is evaluated twice and both verdicts are published:

* `reliable` — on the aligned mutants. This is the round-1 gate; it is
  reproducible without an annotation sheet and is what the VCI `C`/`D` terms are
  scaled against.
* `reliable_non_aligned` — on the independent probes, when both classes exist.
  This is the gate that can actually fail for a real reason.

`trust = min(T_aligned, T_non_aligned)` feeds VCI, but the gate is **not** re-run
on the min; each regime is reported with its own reasons. A family that passes
aligned and fails non-aligned keeps its VCI and is listed as unreliable in the
non-aligned column — that discrepancy is the finding, and suppressing it by
gating only on aligned numbers is exactly the self-flattery this audit exists to
prevent.

Otherwise the family is reported with an explicit reason list. A family that
fails is not deleted and not patched into passing; it keeps its VCI and is
labelled untrustworthy, because a high VCI built on an unreliable verifier is
the exact failure mode this audit exists to catch.

## 8b. Core family list

A family is *core-provisional* iff `VCI >= 0.70`, `trust >= 0.90` and `density > 0`.
It is *core-human-backed* iff it is core-provisional **and** its κ source is
`human`/`pooled-human` with a non-zero human `n`. The two lists are published
separately (`summary.core_provisional`, `summary.core_human_backed`) so that a
clean checkout cannot advertise a family as validated when only synthetic labels
exist.

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

* **Aligned mutants are easy.** Round-1 mutants are authored alongside the
  verifier, so they share its notion of "wrong"; `T_aligned` is an optimistic
  upper bound. This is why round 2 adds §3.4 and takes `min`.
* **Non-aligned probes are still hand-written.** They come from a different
  module with a different code path, but the same author wrote both. They are
  more honest than the aligned mutants — they include hard-coded answers,
  test-only overfits, ambiguity, silent partials and resource failures — but they
  are not a sample of real model failures, and they cannot detect a blind spot
  shared by the author and the verifier. Only the human sheet, and eventually an
  independent annotator, can.
* **`spec_ambiguity` probes are two-sided.** A probe whose expectation is
  `accept` records that the prompt admits a second defensible reading. If the
  verifier rejects it, that is a TPR loss caused by *wording*, not necessarily by
  a verifier bug; the memo must say which reading it thinks is right instead of
  silently reclassifying the probe.
* **Small seeds.** 25 tasks per family gives wide bootstrap intervals; the
  median across 20 families is more stable than any single family's number.
* **Small annotation sample.** 60 rows pooled. Per-family κ intervals are wide
  and per-family `core_human_backed` is therefore usually empty; the pooled value
  is the honest headline.
* **Latency is hardware dependent.** Only `cost_ms` depends on the machine;
  every other number is a pure function of `(seed, family set, label sheets)`.
* **Semantic equivalence is only sampled.** Each family has 1–2 aligned
  paraphrase forms plus the probe rewrites; a verifier could accept those and
  still reject a third spelling.
* **`D` is a proxy.** Units per task is a design choice, not a property of the
  domain; a family with `K = 3` is penalised relative to `K = 5` even if both
  are equally checkable in principle.
* **Validity ceiling: synthetic mutants are not real defects.** Just et al.
  (FSE 2014, "Are mutants a valid substitute for real faults?") find mutants
  correlate with real faults, but are easier to kill and do not reproduce the
  fault distribution. Every TPR/TNR here is therefore an optimistic upper bound,
  and `T = min(T_aligned, T_non_aligned)` is still a bound over two synthetic
  sources, not a measurement of deployed behaviour. `directional` has no
  positive probe, so one third of the category table is only half measured.
  Removing this ceiling requires a sample of *observed* graded failures (§ memo
  "next round"), not more authored probes.
