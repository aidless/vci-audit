#!/usr/bin/env bash
# Print the three results in the README, from data committed in this repository.
# No install, no network, no model: only Python 3.9+ and the standard library.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

rule() { printf '\n=== %s ===\n' "$1"; }

rule "1/3 harness differential decomposition (archived real traces)"
"$PY" examples/decompose_realfail.py

rule "2/3 pass@1 on the archived single-sample runs"
"$PY" examples/passk_realfail.py

rule "3/3 pass@k / pass^k on 30 GSM8K tasks x 8 samples"
"$PY" -m vci passk --input outputs/gsm8k-multisample-14b.jsonl \
    --k-max 8 --bootstrap 2000

rule "conclusion"
"$PY" - <<'EOF'
import json

decomp = json.load(open("outputs/example-harness-decomp.json", encoding="utf-8"))
total = decomp["scores"]["delta"]
tool = decomp["sources"]["tool"]
print(f"1. harness delta = {total:+.4f} over "
      f"{decomp['n_tasks']} tasks; tool accounts for "
      f"{tool['share_of_abs_delta']:.0%} of it, "
      f"state/compaction/retry 0%.")

curve = json.load(open("work/passk.json", encoding="utf-8"))["curves"]["as_failure"]
p1 = curve["pass@k"][0]["value"]
pk = curve["pass^k"][-1]["value"]
print(f"2. pass@1 = {p1:.3f} but pass^{len(curve['pass^k'])} = {pk:.3f}: "
      f"one sample overstates 8-of-8 reliability by {p1 / pk:.2f}x.")

print("3. every number is one model x one benchmark x one decoding config; "
      "there is no cross-vendor ranking here and no AGI claim.")
EOF
