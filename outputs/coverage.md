# VCI coverage table

seed=`0`  tasks/family=`25`  families=`20`  candidates=`6849`

**Median VCI 0.980** (95% bootstrap CI 0.913-1.000), **20/20 families >= 0.70**, **20/20 pass the reliability gate** (kappa source: `synthetic`).

| family | domain | VCI | 95% CI | C | T | D | TPR | TNR | FAR90 | TPR-paraphrase | kappa | kappa src | p95 ms | reliable |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stats_summary | statistics | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| matrix_ops | linear algebra | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| json_schema_extract | information extraction | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| log_field_extraction | log parsing | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| template_render | text rendering | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.0 | yes |
| table_aggregate | data analysis | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| sort_multikey | data processing | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| interval_merge | algorithms | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| life_step | cellular automata | 1.000 | 1.000-1.000 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.0 | yes |
| code_patch | software engineering | 0.981 | 0.979-0.982 | 0.92 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 56.2 | yes |
| base_convert | computer science | 0.979 | 0.965-0.993 | 1.00 | 1.00 | 0.92 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.0 | yes |
| regex_construct | text processing | 0.976 | 0.957-0.990 | 1.00 | 1.00 | 0.91 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.5 | yes |
| arith_expression | mathematics | 0.972 | 0.954-0.990 | 1.00 | 1.00 | 0.89 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| date_arith | calendar | 0.965 | 0.946-0.979 | 1.00 | 1.00 | 0.87 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.0 | yes |
| unit_convert | measurement | 0.913 | 0.865-0.950 | 1.00 | 1.00 | 0.69 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| grid_path | planning | 0.904 | 0.904-0.904 | 1.00 | 1.00 | 0.67 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| csp_assign | constraint programming | 0.904 | 0.904-0.904 | 1.00 | 1.00 | 0.67 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| schedule_slots | scheduling | 0.904 | 0.904-0.904 | 1.00 | 1.00 | 0.67 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.1 | yes |
| topo_order | graph algorithms | 0.904 | 0.904-0.904 | 1.00 | 1.00 | 0.67 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 0.0 | yes |
| sql_result | databases | 0.814 | 0.789-0.844 | 1.00 | 1.00 | 0.44 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | synthetic | 2.2 | yes |

## Why a family is marked unreliable

All families pass the gate.
