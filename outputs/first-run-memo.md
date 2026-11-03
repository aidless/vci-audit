# VCI audit — first run memo

**Run**: `python -m vci audit --families all --out outputs/` · seed `0` · 25 tasks/family ·
6,849 graded candidates · 500 bootstrap resamples · 20 families · Python 3.x on Linux.
Raw numbers: `outputs/results.json`; per-family table: `outputs/coverage.md`;
stability sweep over seeds 0–5: `work/seed_sweep.json`.

---

## 1. Headline

| quantity | value |
|---|---|
| **Median VCI** | **0.983** (95% bootstrap CI 0.913 – 1.000) |
| Mean / min / max | 0.963 / 0.814 (`sql_result`) / 1.000 (7 families) |
| **Families ≥ 0.70** | **20 / 20** |
| Families passing the reliability gate | 20 / 20 — **but κ is measured against synthetic labels** (see §5) |
| Wrong candidates accepted | **0 / 5,574** |
| Paraphrases accepted (`tpr_equiv`) | **775 / 775** |
| Partial answers scored 1.0 | 0 / 2,099 |
| Verifier exceptions | 0 |
| Median VCI across seeds 0–5 and repeated runs | 0.978 – 0.985 (never below 20/20 ≥ 0.70) |

So: **the index can be measured, it is stable, and the value sits at the ceiling.** Every
family clears 0.70. That is a much weaker result than it looks, for three reasons spelled out
below.

## 2. Where the number actually comes from

VCI is `(C · T² · D)^0.25`, and the three components are not equally informative here:

* **T (trust) = 1.000 for all 20 families.** TPR, TNR, FAR90, and `tpr_equiv` are all at their
  ideal values. This is not 20 independent findings: the mutant generator and the verifier were
  brought into exact agreement by `python -m vci selfcheck` (which rejects any mutant that
  contradicts its own label as a *generator bug*). T is therefore **saturated by construction**.
* **C (cheapness) = 1.00 everywhere except `code_patch` (0.95, p95 ≈ 44 ms).** Fine-grained
  verification is genuinely near-free: 19 of 20 families verify at p95 < 1 ms in-process.
  `code_patch` is the only family whose score moves between runs, and because its VCI (~0.987)
  happens to be one of the two middle values of the 20-family sort, that ±0.02 movement is what
  makes the reported *median* land anywhere in 0.978–0.985. The per-family numbers are stable;
  the median inherits the one hardware-dependent outlier.
* **D (density) is the only component that varies**, from 0.44 to 1.00:
  `sql_result` 0.44, four structural families 0.667, `unit_convert` 0.69, … , seven families 1.00.

That means the ranking in `coverage.md` is **a ranking of task design, not of verifiability**.
The four 0.904 families (`grid_path`, `csp_assign`, `schedule_slots`, `topo_order`) sit there
because I gave each task K = 3 units, and granularity is capped at `(K−1)/3`. Raise K to 4 and
their VCI goes to ≈0.97 without changing a single verifier. Conversely `sql_result` is lowest
(0.814) because I asked only K = 2–3 queries per task — a fixable authoring choice, not a
property of SQL.

**Implication**: within this harness, VCI is a *design dial*, not a discovered constant. The
honest reading of "0.98" is "these tasks were authored with 4–12 graded units and the verifiers
are fast", not "98% of open-domain experience is absorbable".

## 3. The result is a selection effect

The 20 families were chosen *because* they are mechanically checkable — that is what the
registry's inclusion criteria demand (`vci/registry.py`). The audit then measured verifiability
inside that set. A median of 0.98 therefore tells us the instrument works on its home turf; it
cannot be used as evidence for the P1 hypothesis ("the fraction of open-domain tasks that can be
covered determines how much experience RL absorbs"), because the conditioning already assumed
the answer.

This is the single most important caveat in this memo. To test the hypothesis rather than the
instrument, the sample has to include families picked *without* a verifiability precondition —
and that is a different, harder data-collection problem (real model rollouts, real domain
mixtures), not a bigger version of this run.

## 4. Which verifiers I would not trust yet

No family fails the gate, so the honest list is "where the *evidence* is thinnest", ordered by
how easily the current measurement could be wrong:

1. **`sql_result`** (VCI 0.814, D 0.44) — the worst-evidenced verifier in the set.
   Equivalence is decided by comparing result sets on the primary database *and* a held-out
   probe database, so it is more robust than string matching, but a wrong query that happens to
   agree on both datasets passes. Its defect mutants also needed a `_force_wrong` fallback to
   guarantee they are actually wrong — a sign that "wrong SQL" is semantically slippery in a way
   the other families are not. Treat its FAR as optimistic.
2. **`code_patch`** (VCI 0.987, C 0.95) — verified by executing the candidate in an isolated
   subprocess against 4 hidden cases with a 3 s timeout. The verifier cannot tell a real fix
   from a patch that hardcodes the expected outputs, and 4 cases is a thin boundary. Its high
   VCI is also the only one that depends on machine speed (44–56 ms p95 on this host,
   C 0.92–0.95).
3. **`regex_construct`** (VCI 0.976) — a regex is judged only against the labelled
   positive/negative strings shipped with the task. Any regex that satisfies those examples
   passes, including one that is trivially overfit to them. The spec is under-determined by
   construction; `SIGALRM` guards catastrophic backtracking but cannot check intent.

Also worth flagging: **`life_step` and `template_render`** were the two families where the audit
first found a real defect — partial answers scoring 1.0 (a corrupted item accidentally equalled
the expected one, and `"ADA"[::-1] == "ADA"`). That was a *generator* bug, fixed, and their TNR
moved 0.98/0.99 → 1.00. This is the one place in the run where the measurement caught something
real, and it is evidence for the *harness* being useful, not for the verifiers being good.

Conversely, the families I would trust most on current evidence: `matrix_ops`,
`table_aggregate`, `sort_multikey`, `interval_merge`, `log_field_extraction` — exact-value
comparison over many units, near-zero latency, unambiguous ground truth.

## 5. κ is not yet independent

Every row reports `kappa.source = synthetic`: the verifier is compared against the mutant
generator's own labels. Because `selfcheck` forces that agreement to be perfect before the audit
runs, κ = 1.00 is a tautology, not a validation. It clears the `κ ≥ 0.60` gate for all 20
families, which is exactly why I do not read the "20/20 reliable" line as a finding.

The human path is wired and one command away:

```bash
python -m vci annotate --per-family 2 --out annotations/blind.csv   # already generated: 40 rows
# fill human_label (1 = accept, 0 = reject); copy to annotations/labels.csv
python -m vci audit --families all --out outputs/                    # kappa.source becomes "human"
```

The 40 rows are deliberately the hard ones (one paraphrase and one highest-scoring partial per
family, defect class withheld, reference answer shown). Until that sheet is filled, "the
verifier agrees with humans" is **unmeasured** — the strongest honest statement is "the verifier
agrees with its own gold labels, which were tuned until it did".

## 6. Verdict

**只在部分族继续 (continue, but narrowed).** Not "continue as planned", and not "change route".

Grounds for continuing:

* The instrument runs end-to-end in one command, is deterministic under `--seed`, and is
  reproducible from a clean checkout (`selfcheck clean`, 51 tests, no private paths, no network).
* VCI is *stable*: per-family standard deviation across seeds 0–5 is ≤ 0.021 (worst:
  `arith_expression`, which is the one with a genuinely wide score distribution), and the
  ≥ 0.70 count is 20/20 on every seed. The metric is not noisy; it is merely saturated.
* The density term did real work: it is the only component that separates families, and it
  correctly identified that a K = 3 task cannot carry dense credit.

Grounds for narrowing:

* T is saturated, so four of the five required discriminative numbers (TPR, TNR, FAR90,
  `tpr_equiv`) carry no information in this run. Everything the memo can say about verifier
  *quality* rests on zero human labels and a self-consistent generator.
* The sample is conditioned on verifiability, so the headline median cannot be quoted as
  evidence about open-domain coverage.

Concrete next step (P1 second round), in priority order:

1. **Un-saturate T.** Fill the 40-row blind sheet; then build a second mutant set that is
   *not* tuned to the verifier — e.g. real model failures on 3–4 families, or hand-written
   near-misses that a family's generator does not know how to produce. Only then does a T < 1
   become possible, and only then is FAR meaningful.
2. **Stop quoting the median.** Report per-family VCI with its CI, plus `D` and `K` beside it, so
   a reader can see that a low VCI often means "too few units", not "unverifiable domain".
3. **Keep the six high-K families** (`matrix_ops`, `table_aggregate`, `sort_multikey`,
   `interval_merge`, `log_field_extraction`, `json_schema_extract`) as the stable core, and use
   them to test the *density → learning-signal* link; drop the K = 3 structural families from any
   claim about maximal achievable VCI until their unit count is raised.
4. Only after (1) and (3): revisit whether a single scalar VCI is the right object, or whether
   the honest report is a vector `(C, T, D)` per family.

## 7. Limits of this memo

* 25 tasks/family, ~340 candidates/family. Enough to rank families and to see the ceiling; not
  enough to resolve differences below ~0.02 VCI. The bootstrap CIs in `results.json` are wide
  for exactly this reason (e.g. `sql_result` 0.79–0.84).
* All mutants are **programmatic**. They are adversarial along the seven named dimensions, but
  they are not a sample of how models actually fail, so every TPR/TNR/FAR number here is
  optimistic relative to deployment.
* `D` is a proxy (granularity × partial-credit fidelity), not the information-theoretic quantity
  the hypothesis ultimately wants.
* Latency — and therefore `C` — is measured on one machine. Only `code_patch` is close enough to
  the 20 ms cheapness knee for hardware to matter.
* No training was run. This memo says nothing about whether fixing a VCI gap actually increases
  what an RL loop absorbs, which remains the untested second half of the hypothesis.
