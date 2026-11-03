# Blind annotation protocol

This is the written rule the annotator follows when labelling
`annotations/blind.csv`. It exists so that the resulting κ is a property of the
verifier and the task wording, not of the annotator's mood on a given day.

## What you are looking at

Each row shows exactly four things:

1. `row_id` — an opaque id, so answers can be rejoined to the audit.
2. `family` — the task shape (e.g. `regex_construct`). It tells you what kind of
   artefact is being judged, never whether this candidate is right.
3. `task_prompt` — the literal instruction a solver would receive.
4. `candidate` — one answer produced either by the mutant generator or by the
   independent probe module.

The sheet deliberately contains no `defect`, `failure_class`, `expectation`,
reference value, or verifier verdict. **Do not** open `work/candidates.jsonl`,
`work/probes.jsonl` or `outputs/results.json` while labelling: those files carry
the true labels and would turn a blind pass into a self-fulfilling one.

The sheet also carries `reference_answer`, which lists **unit names only** (never
values). It is used when rejoining labels to the audit and is not displayed by
the CLI.

## The single question

> **If this candidate were submitted to the task as written, would a careful
> expert accept it as a correct, complete answer?**

Answer `y` (pass) only when all three hold:

* every required unit is present — no missing line, key, row or element;
* every value is right — under the tolerance the prompt states, not under a
  tolerance you infer;
* the format is acceptable — the prompt's own shape rules (one answer per line,
  in order; mapping keys as given; no unit suffix when "no unit suffix" is
  stated). Format choices the prompt does not constrain are *not* failures.

Answer `n` (fail) when any of these hold:

* a value is wrong, even if the candidate runs and looks plausible;
* a unit is missing, duplicated, or extra;
* the stated format is violated in a way that changes what a downstream reader
  gets (e.g. a timestamp re-spelled so it no longer matches the expected string
  contract, a fractional result where a decimal was demanded);
* the candidate is right on the visible cases only, or has resource/state behaviour
  that would fail a second run — judge the **implementation**, not one lucky
  execution.

Answer `s` (undecidable) when the prompt genuinely does not determine the answer
and you cannot pick a reading without guessing. Typical cases:

* precision is unspecified and two defensible roundings differ (6 significant
  digits vs exact decimal);
* the task allows two checkable interpretations (e.g. `.000Z` milliseconds vs a
  plain timestamp) and only one is accepted by the reference;
* the reference and the candidate disagree on a convention the prompt never
  states (inclusive/exclusive at a boundary).

If you might accept it under one reading and reject it under another, and the
prompt does not rank the readings, it is `s`, not `y` and not `n`.

## Boundary cases

| situation | decision |
|---|---|
| semantically equivalent spelling (fractions vs decimals, key order, `(?:…)` wrapper) | `y` — the prompt fixes the value, not the spelling |
| correct value inside the stated tolerance | `y` |
| correct value, tolerance not stated, difference is below 1e-9 relative | `y` (numeric noise, not a different answer) |
| correct multiset, wrong order, and the prompt says "in order" | `n` |
| correct multiset, wrong order, prompt silent on order | `y` |
| extra explanatory text around an otherwise complete answer | `y` if it is unambiguous which part is the answer, else `s` |
| implementation hard-codes the visible answers | `n` — it is not a solution of the stated task |
| implementation would fail on a second invocation | `n` — resource/state failure |
| prompt is ambiguous and you would need the author's intent | `s` |

## Why keep `undecidable`

`s` is not a cop-out and is not dropped from the record:

* it is stored in `labels.csv` as `undecidable` and **counted** (`n_undecidable`)
  but **excluded** from κ. Dropping it silently would overstate the sample size;
  folding it into `n` would manufacture disagreement that is really a defect of
  the prompt.
* it is the useful signal. A cluster of `s` on one family means the **task
  wording** is under-specified, which is a fixable finding — a verifier cannot be
  blamed for a contract nobody wrote.
* the protocol needs it to stay honest: forcing a binary answer on a genuinely
  ambiguous row teaches the annotator to guess, and κ would then measure guessing
  consistency rather than verifier agreement.

## Two passes and stability

1. First pass, in sheet order:

   ```bash
   python -m vci label --sheet annotations/blind.csv \
       --out annotations/labels.csv --round 1 --user <you>
   ```

2. Second pass, **re-ordered**, ideally on another day and without looking at the
   first file:

   ```bash
   python -m vci label --sheet annotations/blind.csv \
       --out annotations/labels_retest.csv --round 2 --shuffle-seed 99 --user <you>
   ```

   The seed changes the order, so agreement between the passes cannot come from
   remembering the sequence.

3. `python -m vci score-annotations` prints three separate numbers and never
   merges them: human vs verifier κ, human test–retest κ (annotator stability),
   and the synthetic upper bound. The audit uses the human value when it exists.

Skipping (`k` / empty Enter) writes nothing, so the row stays pending and is
offered again next session; `q` saves and exits. Answers are appended one row at
a time, so an interrupt never loses completed work.
