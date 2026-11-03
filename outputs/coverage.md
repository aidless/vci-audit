# VCI coverage table (round 2)

seed=`0`  tasks/family=`25`  families=`20`  aligned candidates=`6849`  non-aligned probes=`1157`

**Median VCI 0.934** (95% bootstrap CI 0.904-1.000); aligned-only median 0.978 (0.913-1.000). **15/20 families >= 0.70**.

Median trust: aligned `1.000`, non-aligned `1.000`. kappa in use: `synthetic (no human labels yet)` (human rows n=0, undecidable 0; synthetic upper bound 1.000 is reported separately and is not a human value).

## Per family: VCI, components, aligned vs non-aligned trust

| family | VCI | 95% CI | C | D | K | T | T-aligned | T-non-aligned | TPR al | TNR al | FAR90 al | TPR na | TNR na | FAR90 na | kappa (src) | gate al | gate na |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stats_summary | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 5.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| matrix_ops | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 9.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| json_schema_extract | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 6.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| table_aggregate | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 12.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| sort_multikey | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 8.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| interval_merge | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 5.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| life_step | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 6.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| base_convert | 0.979 | 0.965-0.993 | 1.00 | 0.92 | 5.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| arith_expression | 0.972 | 0.954-0.990 | 1.00 | 0.89 | 5.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| date_arith | 0.965 | 0.946-0.979 | 1.00 | 0.87 | 4.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| grid_path | 0.904 | 0.904-0.904 | 1.00 | 0.67 | 3.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| csp_assign | 0.904 | 0.904-0.904 | 1.00 | 0.67 | 3.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| schedule_slots | 0.904 | 0.904-0.904 | 1.00 | 0.67 | 3.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| topo_order | 0.904 | 0.904-0.904 | 1.00 | 0.67 | 3.0 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 (synthetic) | yes | yes |
| sql_result | 0.781 | 0.716-0.838 | 1.00 | 0.44 | 2.0 | 0.92 | 1.00 | 0.92 | 1.00 | 1.00 | 0.00 | 1.00 | 0.92 | 0.08 | 1.00 (synthetic) | yes | yes |
| regex_construct | 0.690 | 0.677-0.700 | 1.00 | 0.91 | 4.0 | 0.50 | 1.00 | 0.50 | 1.00 | 1.00 | 0.00 | 1.00 | 0.50 | 0.50 | 1.00 (synthetic) | yes | NO |
| code_patch | 0.131 | 0.000-0.223 | 0.89 | 1.00 | 4.0 | 0.02 | 1.00 | 0.02 | 1.00 | 1.00 | 0.00 | 1.00 | 0.02 | 0.98 | 1.00 (synthetic) | yes | NO |
| unit_convert | 0.000 | 0.000-0.000 | 1.00 | 0.69 | 3.0 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.50 | 1.00 | 1.00 | 1.00 (synthetic) | yes | NO |
| log_field_extraction | 0.000 | 0.000-0.000 | 1.00 | 1.00 | 10.0 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 (synthetic) | yes | NO |
| template_render | 0.000 | 0.000-0.000 | 1.00 | 1.00 | 5.0 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.50 | 1.00 | 1.00 | 1.00 (synthetic) | yes | NO |

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
| regex_construct | 1.00 (n=25) | - | - | 0.50 (n=50) | - | - |
| code_patch | 1.00 (n=25) | - | 1.00 (n=25) | 1.00 (n=4) | - | 0.96 (n=27) |
| unit_convert | 1.00 (n=25) | 0.00 (n=25) | - | - | 0.00 (n=25) | - |
| log_field_extraction | 0.00 (n=75) | - | - | - | 0.00 (n=25) | - |
| template_render | 1.00 (n=25) | 0.00 (n=25) | - | - | 0.00 (n=25) | - |

## Why a family is marked unreliable

- **unit_convert** (non-aligned gate): TPR 0.50 < 0.90 (valid variants rejected); FAR90 1.00 > 0.20 (tolerance admits wrong answers)
- **log_field_extraction** (non-aligned gate): TPR 0.00 < 0.90 (valid variants rejected); FAR90 1.00 > 0.20 (tolerance admits wrong answers)
- **regex_construct** (non-aligned gate): TNR 0.50 < 0.90 (wrong answers accepted); FAR90 0.50 > 0.20 (tolerance admits wrong answers)
- **template_render** (non-aligned gate): TPR 0.50 < 0.90 (valid variants rejected); FAR90 1.00 > 0.20 (tolerance admits wrong answers)
- **code_patch** (non-aligned gate): TNR 0.02 < 0.90 (wrong answers accepted); FAR90 0.98 > 0.20 (tolerance admits wrong answers)
