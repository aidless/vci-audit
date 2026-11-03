# VCI coverage table (round 3)

seed=`0`  tasks/family=`25`  families=`20`  aligned candidates=`6849`  non-aligned probes=`1232`  generator version=`3.0`

**Median VCI 0.934** (95% bootstrap CI 0.904-1.000); aligned-only median 0.984 (0.913-1.000). **16/20 families >= 0.70**.

Median trust: aligned `1.000`, non-aligned `1.000`. kappa in use: `synthetic (no human labels yet)` (human rows n=0, undecidable 0; synthetic upper bound 1.000 is reported separately and is not a human value).

**Krippendorff alpha (ordinal) alongside:** `1.000` (source `synthetic`, decided values n=13698, undecidable 0, 95% CI 1.000-1.000). Independent-probe oracle alpha `0.664` (n=2462).

`alpha` and `kappa` are reported side by side, never merged. With two coders and two labels they answer the same question; they diverge when (a) undecidable rows exist -- kappa drops them, alpha keeps them as missing units and still counts them in the expected disagreement; (b) prevalence is extreme -- kappa's expected agreement is pinned by the marginals while alpha estimates it from the pooled distribution with a finite-sample correction; (c) more than two coders or ordinal labels are used, where kappa is not defined. If they disagree, trust neither until the undecidable count is reported.

## Per family: VCI, components, aligned vs non-aligned trust

| family | VCI | 95% CI | C | D | K | T | T-aligned | T-non-aligned | TPR al | TNR al | FAR90 al | TPR na | TNR na | FAR90 na | kappa (src) | alpha (src) | gate al | gate na |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stats_summary | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 5.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| matrix_ops | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 9.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| json_schema_extract | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 6.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| table_aggregate | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 12.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| sort_multikey | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 8.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| interval_merge | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 5.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| life_step | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 6.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| base_convert | 0.979 | 0.965-0.993 | 1.00 | 0.92 | 5.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| arith_expression | 0.972 | 0.954-0.990 | 1.00 | 0.89 | 5.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| date_arith | 0.965 | 0.946-0.979 | 1.00 | 0.87 | 4.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| grid_path | 0.904 | 0.904-0.904 | 1.00 | 0.67 | 3.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| csp_assign | 0.904 | 0.904-0.904 | 1.00 | 0.67 | 3.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| schedule_slots | 0.904 | 0.904-0.904 | 1.00 | 0.67 | 3.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| topo_order | 0.904 | 0.904-0.904 | 1.00 | 0.67 | 3.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| sql_result | 0.781 | 0.716-0.838 | 1.00 | 0.44 | 2.0 | 0.92 | 1.00 | 0.92 | 1.00 | 1.00 | 0.00 | 1.00 | 0.92 | 0.08 | 1.00 (synthetic) | 1.00 (synthetic) | yes | yes |
| code_patch | 0.756 | 0.746-0.764 | 0.95 | 1.00 | 4.0 | 0.58 | 1.00 | 0.58 | 1.00 | 1.00 | 0.00 | 1.00 | 0.58 | 0.42 | 1.00 (synthetic) | 1.00 (synthetic) | yes | NO |
| regex_construct | 0.690 | 0.677-0.700 | 1.00 | 0.91 | 4.0 | 0.50 | 1.00 | 0.50 | 1.00 | 1.00 | 0.00 | 1.00 | 0.50 | 0.50 | 1.00 (synthetic) | 1.00 (synthetic) | yes | NO |
| unit_convert | 0.000 | 0.000-0.000 | 1.00 | 0.69 | 3.0 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.50 | 1.00 | 1.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | NO |
| log_field_extraction | 0.000 | 0.000-0.000 | 1.00 | 1.00 | 10.0 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | NO |
| template_render | 0.000 | 0.000-0.000 | 1.00 | 1.00 | 5.0 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.50 | 1.00 | 1.00 | 1.00 (synthetic) | 1.00 (synthetic) | yes | NO |

## CheckList categories: TPR / TNR / FAR90

`minimum_functionality` = at least handle the stated function; `invariance` = a meaning-preserving change must not change the verdict (includes state/non-determinism); `directional` = a specific input change must move the answer in the specified direction. Pooled row is over every family; a family cell is `-` when that category was not sampled.

| family | category | n | pos | neg | TPR | TNR | FAR90 |
|---|---|---|---|---|---|---|---|
| **pooled** | minimum_functionality | 154 | 50 | 104 | 0.00 | 0.46 | 1.00 |
| **pooled** | invariance | 652 | 550 | 102 | 0.86 | 0.75 | 0.25 |
| **pooled** | directional | 425 | 0 | 425 | - | 1.00 | 0.00 |
| stats_summary | invariance | 25 | 25 | 0 | 1.00 | - | - |
| stats_summary | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| matrix_ops | invariance | 25 | 25 | 0 | 1.00 | - | - |
| matrix_ops | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| json_schema_extract | invariance | 25 | 25 | 0 | 1.00 | - | - |
| json_schema_extract | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| table_aggregate | invariance | 25 | 25 | 0 | 1.00 | - | - |
| table_aggregate | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| sort_multikey | invariance | 25 | 25 | 0 | 1.00 | - | - |
| sort_multikey | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| interval_merge | invariance | 25 | 25 | 0 | 1.00 | - | - |
| interval_merge | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| life_step | invariance | 25 | 25 | 0 | 1.00 | - | - |
| life_step | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| base_convert | invariance | 25 | 25 | 0 | 1.00 | - | - |
| base_convert | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| arith_expression | invariance | 25 | 25 | 0 | 1.00 | - | - |
| arith_expression | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| date_arith | invariance | 25 | 25 | 0 | 1.00 | - | - |
| date_arith | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| grid_path | invariance | 26 | 25 | 1 | 1.00 | 1.00 | 0.00 |
| grid_path | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| csp_assign | invariance | 25 | 25 | 0 | 1.00 | - | - |
| csp_assign | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| schedule_slots | invariance | 25 | 25 | 0 | 1.00 | - | - |
| schedule_slots | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| topo_order | invariance | 25 | 25 | 0 | 1.00 | - | - |
| topo_order | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| sql_result | minimum_functionality | 25 | 0 | 25 | - | 0.92 | 0.08 |
| sql_result | invariance | 25 | 25 | 0 | 1.00 | - | - |
| code_patch | minimum_functionality | 29 | 0 | 29 | - | 0.00 | 1.00 |
| code_patch | invariance | 126 | 25 | 101 | 1.00 | 0.75 | 0.25 |
| regex_construct | minimum_functionality | 50 | 0 | 50 | - | 0.50 | 0.50 |
| regex_construct | invariance | 25 | 25 | 0 | 1.00 | - | - |
| unit_convert | minimum_functionality | 25 | 25 | 0 | 0.00 | - | - |
| unit_convert | invariance | 25 | 25 | 0 | 1.00 | - | - |
| unit_convert | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| log_field_extraction | invariance | 75 | 75 | 0 | 0.00 | - | - |
| log_field_extraction | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |
| template_render | minimum_functionality | 25 | 25 | 0 | 0.00 | - | - |
| template_render | invariance | 25 | 25 | 0 | 1.00 | - | - |
| template_render | directional | 25 | 0 | 25 | - | 1.00 | 0.00 |

`-` in TPR/TNR/FAR90 means the denominator is empty (no such probe was authored), not zero. `directional` currently has no positive probe, so its TPR is unmeasured; see the memo, §validity ceiling.

## Attribution: where a disagreement lands

Three buckets: `verifier_too_strict` (a correct answer rejected because of its spelling/form), `task_under_specified` (a defensible second reading rejected -- the prompt, not the verifier, is incomplete), `true_defect` (the candidate really is wrong; split into caught/missed). `agreement` means the verifier did what the probe expected.

| bucket | n | caught | missed | false-reject | accepted |
|---|---|---|---|---|---|
| verifier_too_strict | 75 | 0 | 0 | 75 | 0 |
| task_under_specified | 50 | 0 | 0 | 50 | 0 |
| true_defect | 631 | 550 | 81 | 0 | 0 |
| agreement | 475 | 0 | 0 | 0 | 475 |
| observe | 1 | 0 | 0 | 0 | 0 |

First examples per bucket (full list in `attribution.csv`):

- **verifier_too_strict** `log_field_extraction-001-x00` (EQUIV, invariance) timestamps with explicit millisecond precision (.000Z): the same instant -- basis: own datetime rendering, ISO-8601 fractional seconds; verifier said: expected 2024-05-24T14:11:30Z, got '2024-05-24T14:11:30.000Z'
- **verifier_too_strict** `log_field_extraction-001-x01` (EQUIV, invariance) lower-case t/z designators: RFC 3339 allows them, the instant is unchanged -- basis: own RFC 3339 re-spelling; verifier said: expected 2024-05-24T14:11:30Z, got '2024-05-24t14:11:30z'
- **task_under_specified** `unit_convert-001-x01` (AMB, minimum_functionality) six significant digits: the prompt never states a precision requirement -- basis: defensible second reading of an under-specified prompt; verifier said: expected 0.00012082761671836474986081285293883719080569474270261671836475, got '0.000120828'
- **task_under_specified** `unit_convert-002-x01` (AMB, minimum_functionality) six significant digits: the prompt never states a precision requirement -- basis: defensible second reading of an under-specified prompt; verifier said: expected 0.3385289, got '0.338529'
- **true_defect** `arith_expression-001-x01` (CR, directional) first value moved by +1/2 (6.375 -> 6.875) -- basis: reference value + an independent offset; verifier said: expected 6.375, got '6.875'
- **true_defect** `arith_expression-002-x01` (CR, directional) first value moved by +1/2 (4.5 -> 5) -- basis: reference value + an independent offset; verifier said: expected 4.5, got '5'

## Non-aligned acceptance by failure class

Cell = share of that class the verifier accepted. `n` is the number of probes in the class. `-` means the class was not sampled for the family.

| family | semantic_equivalent | spec_ambiguity | hardcoded_expected | overfit_to_tests | silent_partial | resource |
|---|---|---|---|---|---|---|
| arith_expression | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| stats_summary | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| base_convert | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| matrix_ops | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| date_arith | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| json_schema_extract | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| table_aggregate | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| sort_multikey | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| interval_merge | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| grid_path | 1.00 (n=25) | - | - | - | 0.00 (n=25) | 0.00 (n=1) |
| csp_assign | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| schedule_slots | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| topo_order | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| life_step | 1.00 (n=25) | - | - | - | 0.00 (n=25) | - |
| sql_result | 1.00 (n=25) | - | 0.08 (n=25) | - | - | - |
| code_patch | 1.00 (n=25) | - | 1.00 (n=25) | 1.00 (n=4) | - | 0.25 (n=102) |
| regex_construct | 1.00 (n=25) | - | - | 0.50 (n=50) | - | - |
| unit_convert | 1.00 (n=25) | 0.00 (n=25) | - | - | 0.00 (n=25) | - |
| log_field_extraction | 0.00 (n=75) | - | - | - | 0.00 (n=25) | - |
| template_render | 1.00 (n=25) | 0.00 (n=25) | - | - | 0.00 (n=25) | - |

## Why a family is marked unreliable

- **unit_convert** (non-aligned gate): TPR 0.50 < 0.90 (valid variants rejected); FAR90 1.00 > 0.20 (tolerance admits wrong answers)
- **log_field_extraction** (non-aligned gate): TPR 0.00 < 0.90 (valid variants rejected); FAR90 1.00 > 0.20 (tolerance admits wrong answers)
- **regex_construct** (non-aligned gate): TNR 0.50 < 0.90 (wrong answers accepted); FAR90 0.50 > 0.20 (tolerance admits wrong answers)
- **template_render** (non-aligned gate): TPR 0.50 < 0.90 (valid variants rejected); FAR90 1.00 > 0.20 (tolerance admits wrong answers)
- **code_patch** (non-aligned gate): TNR 0.58 < 0.90 (wrong answers accepted); FAR90 0.42 > 0.20 (tolerance admits wrong answers)
