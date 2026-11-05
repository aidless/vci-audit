# Examples — real traces, nothing fabricated

The first two scripts read traces that are already committed under `outputs/`. They
make no network calls and need no model. Every number printed below comes from those files.

The third script (`gsm8k_multisample.py`) is a **runner**: it needs a local ollama
server and a model, and it downloads the GSM8K test file once. Its output is already
committed, so you can read the result without re-running it.

Run them from the repository root or from anywhere else (paths are resolved relative to
this file):

```bash
python3 examples/decompose_realfail.py
python3 examples/passk_realfail.py
```

## 1. Decompose a harness change — `decompose_realfail.py`

**Question:** the archived qwen2.5:7b run scored 10/100. A later harness change (round 10,
`realfail_adapt`) handed the model's reply to the execution layer differently. Which
mechanism accounts for the difference?

**Data:** `outputs/realfail-real.json` (the archived verdicts) and
`outputs/realfail-real-check.json` (`code_patch_regrade` — the *same archived replies*
replayed through the new envelope). The model was not re-run; only the harness layer changed.
That is exactly one factor, `tool`.

**Expected output:**

```
delta = +0.0300  (A 0.1000 -> B 0.1300, n=100 tasks)
  tool         tasks=   5  delta=+0.0300  share=100.0%
  state/compaction/retry/ambiguous  0 tasks
  unexplained  tasks=  95  delta=+0.0000
top divergence: code_patch-001, code_patch-002, code_patch-004  (each 0 -> 1)
```

The second block in the same script feeds the 7B/14B *aggregate* accept rates (0.10 / 0.22)
to the same function. It prints:

```
not decomposable (aggregate_only): only aggregate scores were supplied ...
observed delta: 0.12
```

That is deliberate: the two numbers come from **different models**, so no harness
decomposition would be valid — and with aggregates alone there is nothing per-task to
attribute anyway.

## 2. pass@1 on two real batches — `passk_realfail.py`

**Data:** `outputs/realfail-real.json` (qwen2.5:7b) and `outputs/realfail-coder14b-100.json`
(qwen2.5-coder:14b) — 100 identical tasks, one greedy sample per task each.

**Expected output:**

```
qwen2.5:7b           pass@1 = 0.100 [0.050-0.160]   k=2,3 n/a
qwen2.5-coder:14b    pass@1 = 0.220 [0.140-0.310]   k=2,3 n/a
```

The script asks for `k_max=3` on purpose. Both traces have **one** attempt per task, so
`pass@2` and `pass@3` are not estimable and print `n/a`; the calculator will not invent
repeats to fill the curve. Feed it N run files from your own harness to get the full curve.

The `pass@1` values match the archived acceptance rates (10/100 and 22/100), which is a
sanity check that the calculator reads the same operating point the audit reported.

## 3. Multi-sample pass^k on GSM8K — `gsm8k_multisample.py`

**Question:** how far apart are pass@1 and pass^k on real repeated sampling, and does a
single sample overstate reliability?

**Data (already committed):** `outputs/gsm8k-multisample-14b.jsonl` — 30 GSM8K test tasks
× 8 samples (qwen2.5-coder:14b, answer-only prompt, temperature 1.1, seeds 9000–9007),
with every raw response, pass flag, wall time and token count. Full write-up:
`outputs/multisample-run.md`.

**Expected output** (`outputs/gsm8k-multisample-14b.json`):

```
pass@1 = 0.317 [0.179-0.458]   pass@8 = 0.533 [0.367-0.700]
pass^k: 0.317 -> 0.245 -> 0.218 -> 0.203 -> 0.192 -> 0.183 -> 0.175 -> 0.167
pass@1 / pass^8 = 1.90x   (curve still falling at k=8, not saturated)
```

Re-run it against your own local model (resumable; skips attempts already on disk):

```bash
python3 examples/gsm8k_multisample.py --n-tasks 30 --samples 8 \
    --model qwen2.5-coder:14b --out outputs/my-runs.jsonl
```

## Bring your own benchmark

Decomposer — one JSON file, both harnesses per task:

```json
{"benchmark": "your-suite", "model": "your-model",
 "harness_a": "old", "harness_b": "new",
 "tasks": [
   {"task_id": "q1",
    "a": {"passed": false, "state_retained": false, "compaction_events": 0,
          "tool_sig": "bash-v1", "retries": 0},
    "b": {"passed": true,  "state_retained": true,  "compaction_events": 1,
          "tool_sig": "bash-v2", "retries": 1}}]}
```

pass^k — one JSON file, N runs per task:

```json
{"tasks": [
  {"task_id": "q1", "seed": 42,
   "runs": ["pass", "fail", "pass", "timeout"]}]}
```

Then either import (`from vci import decompose, compute`) or use the CLI:

```bash
vci harness-decomp --input mine.json --out work/decomp.json
vci passk          --input runs.json --k-max 4 --out work/passk.json
```

## What these examples do not establish

* They do not rank models. The 7B vs 14B numbers are two observations of two different
  models on the same 100 tasks; nothing here supports a cross-vendor or cross-model
  ranking claim.
* The decomposition is an attribution over *measured* per-task mechanism flags, not a
  causal proof. Confirming `tool` as the cause needs a third arm that toggles only the
  envelope.
* Single-sample traces cannot say anything about reliability (`pass^k`, k ≥ 2).
