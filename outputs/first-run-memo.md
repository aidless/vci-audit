# VCI audit — round 2 memo

**Run**: `python -m vci audit --families all --out outputs` · seed `0` · 25 tasks/family ·
6,849 aligned candidates · **1,157 non-aligned probes (1,156 scored, 1 `observe`)**
· 500 bootstrap resamples · 20 families · Python 3.x on Linux.
Raw numbers: `outputs/results.json`; per-family table: `outputs/coverage.md`.
Round-1 memo is preserved in git history (`git show <round-1-sha>:outputs/first-run-memo.md`).

---

## 1. headline

| quantity | round 1 | **round 2** |
|---|---|---|
| Median VCI (all evidence) | 0.983 | **0.934** (95% bootstrap CI 0.904 – 1.000) |
| Median VCI (aligned mutants only) | 0.983 | 0.978 (0.913 – 1.000) |
| Median VCI (non-aligned probes only) | *not measured* | see §3 (3 families at 0) |
| Families ≥ 0.70 | 20 / 20 | **15 / 20** |
| Families passing the aligned gate | 20 / 20 | 20 / 20 (still saturated; §2.1) |
| Families passing the **non-aligned** gate | *not measured* | **15 / 20** |
| Core family list (provisional) | 20 (implicit) | **15** |
| Core family list (**human-backed**) | 0 | **0** (§5) |
| κ effective source | synthetic | synthetic, **no human sheet yet** (§5) |
| Wrong non-aligned candidates accepted | — | see failure-class table in §4 |

The headline moved because **T is no longer a single number**. `trust = min(T_aligned, T_non_aligned)`
and the second term was measured for the first time: `code_patch` 0.018, `log_field_extraction`
0.000, `unit_convert` 0.000, `template_render` 0.000, `regex_construct` 0.500. The other 15 families
kept `T_non_aligned = 1.00` and their VCI did not move at all.

## 2. where the movement came from

### 2.1 Movement table (round 1 → round 2)

| family | VCI old | VCI new | Δ | driver (probe failure class) |
|---|---|---|---|---|
| `log_field_extraction` | 1.000 | **0.000** | −1.000 | `semantic_equivalent`: 75/75 equivalent timestamps rejected (strict string equality) |
| `template_render` | 1.000 | **0.000** | −1.000 | `spec_ambiguity`: 25/25 defensible `$`-prefix readings rejected |
| `unit_convert` | 0.913 | **0.000** | −0.913 | `spec_ambiguity`: 25/25 six-significant-digit readings rejected |
| `code_patch` | 0.987 | **0.131** | −0.856 | `hardcoded_expected` 25/25 + `resource` (stateful) 25/25 accepted; only the `while True` timeout is caught |
| `regex_construct` | 0.976 | **0.690** | −0.286 | `overfit_to_tests`: 25/25 positive-sample-only regexes accepted |
| `sql_result` | 0.814 | 0.781 | −0.033 | 2/25 `hardcoded_expected` accepted |
| other 14 families | unchanged | unchanged | 0.000 | `T_non_aligned = 1.00` |

Two distinct reasons hide behind "T fell":

* **Representation vs semantics** (`log_field`): the verifier compares timestamps as strings, so
  three spellings of the *same instant* (`.000Z`, lowercase `t`/`z`, `+08:00`) all fail. This is
  a genuine verifier defect, and the probe label is unambiguous: a correct answer was rejected.
* **Prompt under-specification** (`unit_convert`, `template_render`): the prompt never states a
  precision rule or what `$` means in the template, so the probe exercises a *defensible second
  reading*. The verifier rejects it, which costs TPR. Here the finding is about the **task text**,
  not (only) the verifier; the memo refuses to call the verifier "wrong" without also saying the
  prompt is incomplete. Both are reported as they fell: TPR 0.50 → FAR90 = 1.0 → T = 0.

### 2.2 Why FAR90 = 1.0 whenever TPR = 0.50

`FAR90` is defined at the threshold that recovers 90 % of positives. If a family accepts only
half of the correct answers, no threshold above the accepted half reaches 90 % recall, so the
term is set to 1.0 and `T = min(TPR, TNR, 1 − FAR90) = 0`. That is the formula doing what it
says, not an artefact: VCI = 0 for these families because *an RL loop cannot recover enough
correct rollouts at that acceptance rule*. A one-line verifier fix (`normalise timestamp before
comparing`, `accept 6-sig-digit output inside the stated tolerance`) would restore them.

## 3. per-family result (VCI + CI + D + K + T)

`T_al` = aligned mutants, `T_na` = non-aligned probes, `TPR/TNR/FAR90` are the non-aligned values.
Families with no non-aligned positives or negatives are marked (the aligned value is used, flagged).

| family | VCI | 95% CI | D | K | T_al | T_na | TPR_na | TNR_na | FAR90_na |
|---|---|---|---|---|---|---|---|---|---|
| `unit_convert` | 0.000 | 0.000–0.000 | 0.69 | 3 | 1.00 | **0.00** | 0.50 | 1.00 | 1.00 |
| `log_field_extraction` | 0.000 | 0.000–0.000 | 1.00 | 10 | 1.00 | **0.00** | 0.00 | 1.00 | 1.00 |
| `template_render` | 0.000 | 0.000–0.000 | 1.00 | 5 | 1.00 | **0.00** | 0.50 | 1.00 | 1.00 |
| `code_patch` | 0.131 | 0.000–0.223 | 1.00 | 4 | 1.00 | **0.02** | 1.00 | 0.02 | 0.98 |
| `regex_construct` | 0.690 | 0.677–0.700 | 0.91 | 4 | 1.00 | **0.50** | 1.00 | 0.50 | 0.50 |
| `sql_result` | 0.781 | 0.716–0.838 | 0.44 | 2 | 1.00 | 0.92 | 1.00 | 0.92 | 0.08 |
| `arith_expression` | 0.972 | 0.954–0.990 | 0.89 | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `stats_summary` | 1.000 | 1.000–1.000 | 1.00 | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `base_convert` | 0.979 | 0.965–0.993 | 0.92 | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `matrix_ops` | 1.000 | 1.000–1.000 | 1.00 | 9 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `date_arith` | 0.965 | 0.946–0.979 | 0.87 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `json_schema_extract` | 1.000 | 1.000–1.000 | 1.00 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `table_aggregate` | 1.000 | 1.000–1.000 | 1.00 | 12 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `sort_multikey` | 1.000 | 1.000–1.000 | 1.00 | 8 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `interval_merge` | 1.000 | 1.000–1.000 | 1.00 | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `grid_path` | 0.904 | 0.904–0.904 | 0.67 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `csp_assign` | 0.904 | 0.904–0.904 | 0.67 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `schedule_slots` | 0.904 | 0.904–0.904 | 0.67 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `topo_order` | 0.904 | 0.904–0.904 | 0.67 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| `life_step` | 1.000 | 1.000–1.000 | 1.00 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |

*Degenerate intervals* (`0.904–0.904`, `1.000–1.000`) are not precision claims: every task in
those families has the same T and the same `D`, so every bootstrap resample reproduces the same
VCI. They mean "no between-task variance in the components", not "this number is exact to 0.001".

### 3.1 The three worst families, and the exact failure they exhibit

1. **`code_patch` — T_na = 0.02 (TNR 0.02).** 25/25 hard-coded lookup tables and 25/25
   stateful implementations (`_calls > 5 → None`) pass a one-shot subprocess check; only the
   `while True` timeout is caught. The verifier executes the candidate against 4 hidden cases;
   it cannot see that the answer was memorised, and it cannot see a second-run failure.
   This is the sharpest blind spot in the set and it is a *design* limit, not a bug: detecting it
   needs input mutation or repeated invocation, which the current contract does not include.
2. **`log_field_extraction` — T_na = 0.00 (TPR 0.00).** 75/75 independently formatted but
   equivalent timestamps are rejected. Strict string equality is too strict: the task asks for
   "the timestamp field", not "the exact byte string".
3. **`regex_construct` — T_na = 0.50 (TNR 0.50).** 25/25 regexes that match only the shipped
   positive samples (and none of the negatives) are accepted. The verifier is correct against
   its labelled examples and blind to the generalisation the task actually asks for.

`unit_convert` and `template_render` are T = 0 for a different reason (§2.1): defensible
readings of an incomplete prompt are rejected. `sql_result` is nearly robust (T 0.92, no
false rejects) but accepts 2/25 hard-coded result sets because the probe databases happen to
match the visible ones.

### 3.2 Where the verifier is genuinely robust (do not force T down)

14 families returned `T_non_aligned = 1.00` **and** `TNR_na = 1.00` with 50–100 probes each:
`arith_expression`, `stats_summary`, `base_convert`, `matrix_ops`, `date_arith`,
`json_schema_extract`, `table_aggregate`, `sort_multikey`, `interval_merge`, `grid_path`,
`csp_assign`, `schedule_slots`, `topo_order`, `life_step`. On these, the independent probes
include alternate valid colourings/schedules/topological orders, alternate shortest paths,
merged-interval rewrites, exact-fraction spelling of every statistic, and a silent partial
off by a factor of 1000 — all correctly rejected or accepted. The honest statement is: **these
verifiers survived an adversarial sample built outside their own code, and no defect was found
in this round.** `sql_result` joins them at 0.92 but with 2 accepted hard-coded probes.

## 4. Failure-class breakdown (pooled, 1,156 scored probes)

| class | n | pos | neg | TPR | TNR | accept rate | reading |
|---|---|---|---|---|---|---|---|
| `hardcoded_expected` | 50 | 0 | 50 | — | 0.46 | 0.54 | half of all memorised answers are accepted (`code_patch`, `sql_result`) |
| `overfit_to_tests` | 54 | 0 | 54 | — | 0.46 | 0.54 | half of all test-only overfits are accepted (`regex_construct`, `code_patch`) |
| `spec_ambiguity` | 50 | 50 | 0 | **0.00** | — | 0.00 | every defensible second reading is rejected (`unit_convert`, `template_render`) |
| `silent_partial` | 425 | 0 | 425 | — | **1.00** | 0.00 | no boundary error slipped through — the strongest positive result |
| `semantic_equivalent` | 550 | 550 | 0 | **0.86** | — | 0.86 | 75 misses, all `log_field` timestamps |
| `resource` | 28 | 0 | 27 (+1 observe) | — | **0.07** | 0.93 | only timeouts are caught; state and memory are invisible |

The `silent_partial` line is the reassuring one: 425 independently constructed "runs fine,
locally right, wrong at the boundary" candidates, **zero** accepted. The `resource` line is the
warning: 27/27 stateful candidates and 1/1 memory-`observe` were invisible, and only the
non-terminating one was killed by the 3 s timeout.

## 5. κ: source, size, interval

| source | n | κ | 95% CI | status |
|---|---|---|---|---|
| **synthetic** (generator's own labels) | 6,849 | **1.000** | 1.000–1.000 | **upper bound by construction**; not human |
| **human** (`annotations/labels.csv`) | **0** | — | — | **no sheet exists in this checkout** |
| **human-stability** (`labels_retest.csv`) | 0 | — | — | needs a second pass |
| **independent probe oracle** (`expectation`, not a human) | 1,156 | **0.644** | 0.600–0.688 | the only *outside* agreement number this round |

How to read it:

* The effective κ for every family is still **`synthetic`**. I am **not** substituting the
  synthetic 1.000 for a human value, and the audit prints this warning on every run.
* The synthetic 1.000 is a tautology: `selfcheck` rejects any mutant that contradicts its own
  label before the audit runs, so that number can only detect an accidental verifier bug.
* The probe oracle κ (0.644) is the first non-tautological agreement figure in the project. It
  compares the verifier against labels fixed *before* it runs. It is **not** human and it is
  reported under its own name, never as "κ from humans".
* To produce the human number, one command each (protocol: `annotations/PROTOCOL.md`):

```bash
python -m vci label --out annotations/labels.csv           # 60 rows, y/n/s, resumable
python -m vci label --out annotations/labels_retest.csv \
    --round 2 --shuffle-seed 99                            # stability pass
python -m vci score-annotations                            # prints human / stability / synthetic / oracle
python -m vci audit --families all --out outputs            # effective kappa switches to "human"
```

Until that exists, `core_human_backed` is empty and any sentence of the form "the verifier agrees
with a human" remains **unmeasured**. This is the one item round 2 was asked to close and could
not: the tooling is done and tested (`tests/test_labeler.py`), the labels require a person.

## 6. Three kinds of conclusion, kept apart

### (a) supported by labels decided outside the verifier

*(probe-derived, author-written — independent of the verifier's code, **not** human)*

1. `code_patch` accepts hard-coded and stateful answers (TNR 0.02). This is the strongest single
   finding of the round and it is reproducible: `python -m vci audit --families code_patch`.
2. `log_field_extraction` rejects semantically equivalent timestamps (TPR 0.00).
3. `regex_construct` accepts positive-sample-only regexes (TNR 0.50).
4. `unit_convert` / `template_render` reject defensible readings of an under-specified prompt
   (TPR 0.50 each) — a wording defect at least as much as a verifier defect.
5. `sql_result` accepts 2/25 hard-coded result sets.
6. 14 families show **no** defect under 50–100 independent probes and are described as robust.

### (b) supported only by synthetic (aligned) samples

1. The aligned TPR/TNR of all 20 families are 1.00. That number says the verifier is self-consistent,
   not that it is correct; §3.1–3.2 are where the real quality claims live.
2. The VCI *ranking* among families that survived both regimes is driven almost entirely by
   **D and K** (authoring choices), not by verification quality: `sql_result` 0.78 (D 0.44, K 2),
   the four K = 3 structural families 0.904, `matrix_ops`/`table_aggregate` 1.00 (K 9/12).
3. The claim "partial credit is tracked faithfully" rests on 425 independent `silent_partial`
   probes — **not** on the aligned partials, which is why I place it here with the probe caveat
   rather than in (a).

### (c) not resolved this round, needs the next one

1. **Human κ.** Zero rows labelled. Everything about "agrees with a person" is open. The CLI, resume,
   retest and reporting paths are built and tested; only the human pass is missing.
2. **Second annotator.** Even a filled sheet measures one author's reading; a bias shared by
   author and verifier stays invisible. Inter-annotator agreement needs a second person.
3. **Real model failures.** Both sample sources are hand-authored. Neither is a sample of how
   models actually fail, so FAR/TNR here remain optimistic relative to deployment.
4. **Memory policy.** 1 `observe` probe is recorded (16 MB for a five-element input) and scored
   nowhere. Deciding whether a verifier *should* enforce a memory budget is a contract question,
   deliberately left out rather than silently counted.
5. **Prompt repair.** `unit_convert` and `template_render` need a stated precision/format rule;
   until then their T = 0 is a correct measurement of an incomplete task, not a verifier bug.
6. **`D` is still a proxy** (granularity × partial-credit fidelity), and the K = 3 families are
   penalised for an authoring choice.
7. **Difficulty vs checkability.** VCI still measures checkability only; no training was run, so
   whether raising VCI raises absorbed experience remains the untested half of the hypothesis.

## 7. shrunk core list and verdict

**Core (provisional, 15)** — `VCI ≥ 0.70`, `trust ≥ 0.90`, `D > 0`:
`arith_expression`, `stats_summary`, `base_convert`, `matrix_ops`, `date_arith`,
`json_schema_extract`, `sql_result`, `table_aggregate`, `sort_multikey`, `interval_merge`,
`grid_path`, `csp_assign`, `schedule_slots`, `topo_order`, `life_step`.

**Core (human-backed, 0)** — empty, because human κ is 0 rows.

**Dropped from the core**: `unit_convert`, `template_render` (T 0 — prompt under-specified),
`log_field_extraction` (T 0 — timestamp equivalence), `code_patch` (T 0.02 — hard-coded/stateful),
`regex_construct` (T 0.50 — test-only overfit).

**Verdict: continue, narrowed to the 15, with three named repairs and one missing measurement.**

* The instrument is now able to fail a family for a real reason, which is what round 1 could not
  do. That is the substantive gain: five families moved from "reliable, 1.00" to "unreliable, 0.00".
* The 15 survivors are not merely untested — they passed an adversarial sample built in a
  different module, and `silent_partial` (the most common real RL failure) leaked 0/425.
* Priority order for round 3:
  1. Human sheet (60 rows) + a second annotator; quote human κ with its CI, drop synthetic from
     any headline.
  2. Repair `log_field` normalisation and pronounce a precision/format rule for `unit_convert`,
     `template_render`; re-measure — expect those three to return to the core.
  3. Add mutation/repeat-invocation to `code_patch` (or declare it a family whose T cannot exceed
     ~0.02 without a new contract) and add a held-out-string set to `regex_construct`.
  4. Only then re-index; keep reporting per-family VCI + CI + D + K, never the median alone.

## 8. limits of this memo

* 25 tasks/family, 1,157 probes total. Enough to rank and to detect a 0.5 TPR drop; not enough
  to certify a verifier at T = 1.00 to ±0.01 — 1.00 here means "no counterexample in 50–100
  probes", not "correct".
* Probe labels are author-written and testable; the module's independence is enforced structurally
  (AST test), not by a third party.
* Latency, and therefore `C`, is measured on one machine. Only `code_patch` sits near the 20 ms
  cheapness knee.
* No training was run. Nothing here shows that repairing a VCI gap increases what an RL loop
  absorbs.
