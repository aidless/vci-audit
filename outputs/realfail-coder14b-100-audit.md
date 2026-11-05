# 14B audit sheet — qwen2.5-coder:14b (max_tokens=512)

## settings
- seed 20261104, temperature 0.0, max_tokens 512, samples 1, n_tasks 5, version 2.1
- model digest `9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849`

## totals
- records 100; accepted by verifier 22 (22.0%); buckets {"CALC": 35, "PARTIAL": 28, "SPEC": 15, "correct": 22}
- accepted-but-reference-wrong (equality families only) 0

## accepted tasks (manual audit)
| # | family | task | units | gold_ok | note |
|---|---|---|---|---|---|
| 1 | arith_expression | arith_expression-002 | 2 | 2/2 |  |
| 2 | arith_expression | arith_expression-003 | 2 | 2/2 |  |
| 3 | code_patch | code_patch-004 | 5 | 5/5 |  |
| 4 | csp_assign | csp_assign-003 | 3 | 3/3 |  |
| 5 | date_arith | date_arith-001 | 3 | 3/3 |  |
| 6 | date_arith | date_arith-003 | 5 | 5/5 |  |
| 7 | json_schema_extract | json_schema_extract-001 | 6 | 6/6 |  |
| 8 | json_schema_extract | json_schema_extract-002 | 6 | 6/6 |  |
| 9 | json_schema_extract | json_schema_extract-003 | 6 | 6/6 |  |
| 10 | json_schema_extract | json_schema_extract-004 | 6 | 6/6 |  |
| 11 | json_schema_extract | json_schema_extract-005 | 6 | 6/6 |  |
| 12 | log_field_extraction | log_field_extraction-001 | 15 | 15/15 |  |
| 13 | log_field_extraction | log_field_extraction-002 | 15 | 15/15 |  |
| 14 | log_field_extraction | log_field_extraction-003 | 15 | 15/15 |  |
| 15 | log_field_extraction | log_field_extraction-004 | 15 | 15/15 |  |
| 16 | log_field_extraction | log_field_extraction-005 | 15 | 15/15 |  |
| 17 | regex_construct | regex_construct-001 | 4 | 4/4 |  |
| 18 | regex_construct | regex_construct-004 | 5 | 5/5 |  |
| 19 | sql_result | sql_result-001 | 2 | 2/2 |  |
| 20 | sql_result | sql_result-003 | 2 | 2/2 |  |
| 21 | sql_result | sql_result-004 | 2 | 2/2 |  |
| 22 | sql_result | sql_result-005 | 2 | 2/2 |  |

### A1. arith_expression / arith_expression-002 (gold reference)

```
Evaluate each expression exactly.  Answer with one value per line, in order; fractions and decimals are both acceptable.
  1. (3 + 2 + 15) / 2
  2. (8 + 17 * 1) / 10

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 2 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| q1 | 10 | 10 | True | True | exact value |
| q2 | 2.5 | 5/2 | True | True | exact value |

raw: `{"answers": [10, 2.5]}`

### A2. arith_expression / arith_expression-003 (gold reference)

```
Evaluate each expression exactly.  Answer with one value per line, in order; fractions and decimals are both acceptable.
  1. 5 + 14
  2. (7) / 2

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 2 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| q1 | 19 | 19 | True | True | exact value |
| q2 | 3.5 | 7/2 | True | True | exact value |

raw: `{"answers": [19, 3.5]}`

### A3. code_patch / code_patch-004 (gold verifier)

```
Fix the function below so that it satisfies: return a/b as a float, or null when b is zero.  Return the full module source defining solve.

def solve(a, b):
    return a / b


Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 5 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| t1 | None | None | True | True | test passed |
| t2 | None | None | True | True | test passed |
| t3 | None | None | True | True | test passed |
| t4 | None | None | True | True | test passed |
| t5 | None | None | True | True | test passed |

raw: `{"answers": ["def solve(a, b):", "    if b == 0:", "        return None", "    else:", "        return float(a / b)"]}`

### A4. csp_assign / csp_assign-003 (gold verifier)

```
Colour each graph with colours 1, 2, 3 so that adjacent nodes differ and pinned nodes keep their colour.  Return a JSON array with one object {node: colour} per graph, in order.
  problems = [{'nodes': ['A', 'B', 'C', 'D'], 'edges': [('A', 'B'), ('A', 'C'), ('A', 'D'), ('C', 'D')], 'pins': {'C': 2}, 'colors': 3}, {'nodes': ['A', 'B', 'C', 'D'], 'edges': [('A', 'C'), ('B', 'D')], 'pins': {'B': 1}, 'colors': 3}, {'nodes': ['A', 'B', 'C', 'D', 'E'], 'edges': [('A', 'B'), ('A', 'C'), ('A', 'D'), ('B', 'C'), ('B', 'D'), ('B', 'E')], 'pins': {}, 'colors': 3}]

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 3 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| g1 | {'A': 1, 'B': 2, 'C': 2, 'D': 3} | {'A': 1, 'B': 2, 'C': 2, 'D': 3} | True | True | all constraints satisfied |
| g2 | {'A': 2, 'B': 1, 'C': 3, 'D': 2} | {'A': 1, 'B': 1, 'C': 2, 'D': 2} | True | True | all constraints satisfied |
| g3 | {'A': 1, 'B': 2, 'C': 3, 'D': 3, 'E': 1} | {'A': 1, 'B': 2, 'C': 3, 'D': 3, 'E': 1} | True | True | all constraints satisfied |

raw: `{ /   "answers": [ /     {"A": 1, "B": 2, "C": 2, "D": 3}, /     {"A": 2, "B": 1, "C": 3, "D": 2}, /     {"A": 1, "B": 2, "C": 3, "D": 3, "E": 1} /   ] / }`

### A5. date_arith / date_arith-001 (gold reference)

```
Shift each date by the given amount.  Month shifts clamp to the last valid day of the target month.  Answer with ISO dates (YYYY-MM-DD), one per line.
  1. 2024-08-20 -18 days
  2. 2023-03-02 -7 months
  3. 2024-01-31 +1 months

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 3 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| d1 | 2024-08-02 | 2024-08-02 | True | True | date matches |
| d2 | 2022-08-02 | 2022-08-02 | True | True | date matches |
| d3 | 2024-02-29 | 2024-02-29 | True | True | date matches |

raw: `{"answers": ["2024-08-02", "2022-08-02", "2024-02-29"]}`

### A6. date_arith / date_arith-003 (gold reference)

```
Shift each date by the given amount.  Month shifts clamp to the last valid day of the target month.  Answer with ISO dates (YYYY-MM-DD), one per line.
  1. 2024-08-31 +15 days
  2. 2023-11-01 -31 days
  3. 2023-04-11 -36 days
  4. 2024-02-02 +2 months
  5. 2024-01-31 +1 months

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 5 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| d1 | 2024-09-15 | 2024-09-15 | True | True | date matches |
| d2 | 2023-10-01 | 2023-10-01 | True | True | date matches |
| d3 | 2023-03-06 | 2023-03-06 | True | True | date matches |
| d4 | 2024-04-02 | 2024-04-02 | True | True | date matches |
| d5 | 2024-02-29 | 2024-02-29 | True | True | date matches |

raw: `{"answers": ["2024-09-15", "2023-10-01", "2023-03-06", "2024-04-02", "2024-02-29"]}`

### A7. json_schema_extract / json_schema_extract-001 (gold reference)

```
Extract the order fields below into a JSON object with exactly the keys id (int), customer (string), priority (int), total_usd (number), tags (array of strings, order-insensitive), steps (array of strings, order matters).  Do not add extra keys.

ORDER #4607
customer: Maria Curie
priority: 4
total_usd: 73.46
tags: fragile, gift, return, bulk
steps: invoice > ship


Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| id | 4607 | 4607 | True | True | integer matches |
| customer | Maria Curie | Maria Curie | True | True | string matches |
| priority | 4 | 4 | True | True | integer matches |
| total_usd | 73.46 | 73.46 | True | True | amount matches |
| tags | ['fragile', 'gift', 'return', 'bulk'] | ['fragile', 'gift', 'return', 'bulk'] | True | True | tag set matches |
| steps | ['invoice', 'ship'] | ['invoice', 'ship'] | True | True | ordered steps match |

raw: `{ /   "id": 4607, /   "customer": "Maria Curie", /   "priority": 4, /   "total_usd": 73.46, /   "tags": ["fragile", "gift", "return", "bulk"], /   "steps": ["invoice", "ship"] / }`

### A8. json_schema_extract / json_schema_extract-002 (gold reference)

```
Extract the order fields below into a JSON object with exactly the keys id (int), customer (string), priority (int), total_usd (number), tags (array of strings, order-insensitive), steps (array of strings, order matters).  Do not add extra keys.

ORDER #5517
customer: Niels Bohr
priority: 1
total_usd: 85.17
tags: urgent, return, express, fragile
steps: pack > label > ship > verify


Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| id | 5517 | 5517 | True | True | integer matches |
| customer | Niels Bohr | Niels Bohr | True | True | string matches |
| priority | 1 | 1 | True | True | integer matches |
| total_usd | 85.17 | 85.17 | True | True | amount matches |
| tags | ['urgent', 'return', 'express', 'fragile'] | ['urgent', 'return', 'express', 'fragile'] | True | True | tag set matches |
| steps | ['pack', 'label', 'ship', 'verify'] | ['pack', 'label', 'ship', 'verify'] | True | True | ordered steps match |

raw: `{ /   "id": 5517, /   "customer": "Niels Bohr", /   "priority": 1, /   "total_usd": 85.17, /   "tags": ["urgent", "return", "express", "fragile"], /   "steps": ["pack", "label", "ship", "verify"] / }`

### A9. json_schema_extract / json_schema_extract-003 (gold reference)

```
Extract the order fields below into a JSON object with exactly the keys id (int), customer (string), priority (int), total_usd (number), tags (array of strings, order-insensitive), steps (array of strings, order matters).  Do not add extra keys.

ORDER #8966
customer: Grace Hopper
priority: 3
total_usd: 336.70
tags: fragile, return, express
steps: ship > label > invoice


Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| id | 8966 | 8966 | True | True | integer matches |
| customer | Grace Hopper | Grace Hopper | True | True | string matches |
| priority | 3 | 3 | True | True | integer matches |
| total_usd | 336.7 | 336.7 | True | True | amount matches |
| tags | ['fragile', 'return', 'express'] | ['fragile', 'return', 'express'] | True | True | tag set matches |
| steps | ['ship', 'label', 'invoice'] | ['ship', 'label', 'invoice'] | True | True | ordered steps match |

raw: `{ /   "id": 8966, /   "customer": "Grace Hopper", /   "priority": 3, /   "total_usd": 336.70, /   "tags": ["fragile", "return", "express"], /   "steps": ["ship", "label", "invoice"] / }`

### A10. json_schema_extract / json_schema_extract-004 (gold reference)

```
Extract the order fields below into a JSON object with exactly the keys id (int), customer (string), priority (int), total_usd (number), tags (array of strings, order-insensitive), steps (array of strings, order matters).  Do not add extra keys.

ORDER #3955
customer: Maria Curie
priority: 4
total_usd: 799.72
tags: urgent, return
steps: pack > label > verify > ship


Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| id | 3955 | 3955 | True | True | integer matches |
| customer | Maria Curie | Maria Curie | True | True | string matches |
| priority | 4 | 4 | True | True | integer matches |
| total_usd | 799.72 | 799.72 | True | True | amount matches |
| tags | ['urgent', 'return'] | ['urgent', 'return'] | True | True | tag set matches |
| steps | ['pack', 'label', 'verify', 'ship'] | ['pack', 'label', 'verify', 'ship'] | True | True | ordered steps match |

raw: `{ /   "id": 3955, /   "customer": "Maria Curie", /   "priority": 4, /   "total_usd": 799.72, /   "tags": ["urgent", "return"], /   "steps": ["pack", "label", "verify", "ship"] / }`

### A11. json_schema_extract / json_schema_extract-005 (gold reference)

```
Extract the order fields below into a JSON object with exactly the keys id (int), customer (string), priority (int), total_usd (number), tags (array of strings, order-insensitive), steps (array of strings, order matters).  Do not add extra keys.

ORDER #5775
customer: Maria Curie
priority: 2
total_usd: 494.08
tags: urgent, gift
steps: ship > verify


Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| id | 5775 | 5775 | True | True | integer matches |
| customer | Maria Curie | Maria Curie | True | True | string matches |
| priority | 2 | 2 | True | True | integer matches |
| total_usd | 494.08 | 494.08 | True | True | amount matches |
| tags | ['urgent', 'gift'] | ['urgent', 'gift'] | True | True | tag set matches |
| steps | ['ship', 'verify'] | ['ship', 'verify'] | True | True | ordered steps match |

raw: `{ /   "id": 5775, /   "customer": "Maria Curie", /   "priority": 2, /   "total_usd": 494.08, /   "tags": ["urgent", "gift"], /   "steps": ["ship", "verify"] / }`

### A12. log_field_extraction / log_field_extraction-001 (gold reference)

```
Parse each log line into the fields ts, level, service, code, msg.  Return a JSON object keyed by record id "1", "2", ... whose values are objects with exactly those keys.  Timestamps are ISO instants, levels are upper-case, services lower-case, codes match [A-Z][0-9]{3}, messages are unquoted.

2024-05-10T11:57:53Z level=WARN service=worker code=W480 msg="retrying request"
2024-05-21T17:32:06Z level=INFO service=billing code=I234 msg="handler took 320ms"
2024-05-25T00:42:15Z level=INFO service=auth code=W501 msg="connection reset by peer"

Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| L1.ts | 2024-05-10T11:57:53Z | 2024-05-10T11:57:53Z | True | True | timestamp matches |
| L1.level | WARN | WARN | True | True | level matches |
| L1.service | worker | worker | True | True | service matches |
| L1.code | W480 | W480 | True | True | code matches |
| L1.msg | retrying request | retrying request | True | True | message matches |
| L2.ts | 2024-05-21T17:32:06Z | 2024-05-21T17:32:06Z | True | True | timestamp matches |
| L2.level | INFO | INFO | True | True | level matches |
| L2.service | billing | billing | True | True | service matches |
| L2.code | I234 | I234 | True | True | code matches |
| L2.msg | handler took 320ms | handler took 320ms | True | True | message matches |
| L3.ts | 2024-05-25T00:42:15Z | 2024-05-25T00:42:15Z | True | True | timestamp matches |
| L3.level | INFO | INFO | True | True | level matches |
| L3.service | auth | auth | True | True | service matches |
| L3.code | W501 | W501 | True | True | code matches |
| L3.msg | connection reset by peer | connection reset by peer | True | True | message matches |

raw: `{ /   "1": { /     "ts": "2024-05-10T11:57:53Z", /     "level": "WARN", /     "service": "worker", /     "code": "W480", /     "msg": "retrying request" /   }, /   "2": { /     "ts": "2024-05-21T17:32:06Z", /     "level": "INFO", /     "service": "billing", /     "code": "I234", /     "msg": "handler took 320ms" /   }, /   "3": { /     "ts": "2024-05-25T00:42:15Z", /     "level": "INFO", /     "service": "auth", /     "code": "W501", /     "msg": "connection reset by peer" /   } / }`

### A13. log_field_extraction / log_field_extraction-002 (gold reference)

```
Parse each log line into the fields ts, level, service, code, msg.  Return a JSON object keyed by record id "1", "2", ... whose values are objects with exactly those keys.  Timestamps are ISO instants, levels are upper-case, services lower-case, codes match [A-Z][0-9]{3}, messages are unquoted.

2024-05-24T17:42:24Z level=ERROR service=worker code=E737 msg="retrying request"
2024-05-02T22:44:31Z level=ERROR service=search code=D863 msg="timeout after 5s"
2024-05-15T18:39:40Z level=WARN service=worker code=I305 msg="handler took 320ms"

Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| L1.ts | 2024-05-24T17:42:24Z | 2024-05-24T17:42:24Z | True | True | timestamp matches |
| L1.level | ERROR | ERROR | True | True | level matches |
| L1.service | worker | worker | True | True | service matches |
| L1.code | E737 | E737 | True | True | code matches |
| L1.msg | retrying request | retrying request | True | True | message matches |
| L2.ts | 2024-05-02T22:44:31Z | 2024-05-02T22:44:31Z | True | True | timestamp matches |
| L2.level | ERROR | ERROR | True | True | level matches |
| L2.service | search | search | True | True | service matches |
| L2.code | D863 | D863 | True | True | code matches |
| L2.msg | timeout after 5s | timeout after 5s | True | True | message matches |
| L3.ts | 2024-05-15T18:39:40Z | 2024-05-15T18:39:40Z | True | True | timestamp matches |
| L3.level | WARN | WARN | True | True | level matches |
| L3.service | worker | worker | True | True | service matches |
| L3.code | I305 | I305 | True | True | code matches |
| L3.msg | handler took 320ms | handler took 320ms | True | True | message matches |

raw: `{ /   "1": { /     "ts": "2024-05-24T17:42:24Z", /     "level": "ERROR", /     "service": "worker", /     "code": "E737", /     "msg": "retrying request" /   }, /   "2": { /     "ts": "2024-05-02T22:44:31Z", /     "level": "ERROR", /     "service": "search", /     "code": "D863", /     "msg": "timeout after 5s" /   }, /   "3": { /     "ts": "2024-05-15T18:39:40Z", /     "level": "WARN", /     "service": "worker", /     "code": "I305", /     "msg": "handler took 320ms" /   } / }`

### A14. log_field_extraction / log_field_extraction-003 (gold reference)

```
Parse each log line into the fields ts, level, service, code, msg.  Return a JSON object keyed by record id "1", "2", ... whose values are objects with exactly those keys.  Timestamps are ISO instants, levels are upper-case, services lower-case, codes match [A-Z][0-9]{3}, messages are unquoted.

2024-05-22T12:47:38Z level=WARN service=api code=I742 msg="timeout after 5s"
2024-05-03T01:56:22Z level=WARN service=auth code=I921 msg="timeout after 5s"
2024-05-23T20:45:04Z level=INFO service=billing code=I777 msg="retrying request"

Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| L1.ts | 2024-05-22T12:47:38Z | 2024-05-22T12:47:38Z | True | True | timestamp matches |
| L1.level | WARN | WARN | True | True | level matches |
| L1.service | api | api | True | True | service matches |
| L1.code | I742 | I742 | True | True | code matches |
| L1.msg | timeout after 5s | timeout after 5s | True | True | message matches |
| L2.ts | 2024-05-03T01:56:22Z | 2024-05-03T01:56:22Z | True | True | timestamp matches |
| L2.level | WARN | WARN | True | True | level matches |
| L2.service | auth | auth | True | True | service matches |
| L2.code | I921 | I921 | True | True | code matches |
| L2.msg | timeout after 5s | timeout after 5s | True | True | message matches |
| L3.ts | 2024-05-23T20:45:04Z | 2024-05-23T20:45:04Z | True | True | timestamp matches |
| L3.level | INFO | INFO | True | True | level matches |
| L3.service | billing | billing | True | True | service matches |
| L3.code | I777 | I777 | True | True | code matches |
| L3.msg | retrying request | retrying request | True | True | message matches |

raw: `{ /   "1": { /     "ts": "2024-05-22T12:47:38Z", /     "level": "WARN", /     "service": "api", /     "code": "I742", /     "msg": "timeout after 5s" /   }, /   "2": { /     "ts": "2024-05-03T01:56:22Z", /     "level": "WARN", /     "service": "auth", /     "code": "I921", /     "msg": "timeout after 5s" /   }, /   "3": { /     "ts": "2024-05-23T20:45:04Z", /     "level": "INFO", /     "service": "billing", /     "code": "I777", /     "msg": "retrying request" /   } / }`

### A15. log_field_extraction / log_field_extraction-004 (gold reference)

```
Parse each log line into the fields ts, level, service, code, msg.  Return a JSON object keyed by record id "1", "2", ... whose values are objects with exactly those keys.  Timestamps are ISO instants, levels are upper-case, services lower-case, codes match [A-Z][0-9]{3}, messages are unquoted.

2024-05-10T18:37:21Z level=ERROR service=worker code=W622 msg="cache miss for key"
2024-05-16T06:18:30Z level=ERROR service=billing code=E375 msg="cache miss for key"
2024-05-27T12:43:50Z level=ERROR service=worker code=I408 msg="cache miss for key"

Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| L1.ts | 2024-05-10T18:37:21Z | 2024-05-10T18:37:21Z | True | True | timestamp matches |
| L1.level | ERROR | ERROR | True | True | level matches |
| L1.service | worker | worker | True | True | service matches |
| L1.code | W622 | W622 | True | True | code matches |
| L1.msg | cache miss for key | cache miss for key | True | True | message matches |
| L2.ts | 2024-05-16T06:18:30Z | 2024-05-16T06:18:30Z | True | True | timestamp matches |
| L2.level | ERROR | ERROR | True | True | level matches |
| L2.service | billing | billing | True | True | service matches |
| L2.code | E375 | E375 | True | True | code matches |
| L2.msg | cache miss for key | cache miss for key | True | True | message matches |
| L3.ts | 2024-05-27T12:43:50Z | 2024-05-27T12:43:50Z | True | True | timestamp matches |
| L3.level | ERROR | ERROR | True | True | level matches |
| L3.service | worker | worker | True | True | service matches |
| L3.code | I408 | I408 | True | True | code matches |
| L3.msg | cache miss for key | cache miss for key | True | True | message matches |

raw: `{ /   "1": { /     "ts": "2024-05-10T18:37:21Z", /     "level": "ERROR", /     "service": "worker", /     "code": "W622", /     "msg": "cache miss for key" /   }, /   "2": { /     "ts": "2024-05-16T06:18:30Z", /     "level": "ERROR", /     "service": "billing", /     "code": "E375", /     "msg": "cache miss for key" /   }, /   "3": { /     "ts": "2024-05-27T12:43:50Z", /     "level": "ERROR", /     "service": "worker", /     "code": "I408", /     "msg": "cache miss for key" /   } / }`

### A16. log_field_extraction / log_field_extraction-005 (gold reference)

```
Parse each log line into the fields ts, level, service, code, msg.  Return a JSON object keyed by record id "1", "2", ... whose values are objects with exactly those keys.  Timestamps are ISO instants, levels are upper-case, services lower-case, codes match [A-Z][0-9]{3}, messages are unquoted.

2024-05-26T04:17:29Z level=ERROR service=billing code=D201 msg="retrying request"
2024-05-04T08:59:10Z level=WARN service=search code=I841 msg="connection reset by peer"
2024-05-22T19:11:23Z level=WARN service=api code=W865 msg="handler took 320ms"

Return ONLY the JSON object described above. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| L1.ts | 2024-05-26T04:17:29Z | 2024-05-26T04:17:29Z | True | True | timestamp matches |
| L1.level | ERROR | ERROR | True | True | level matches |
| L1.service | billing | billing | True | True | service matches |
| L1.code | D201 | D201 | True | True | code matches |
| L1.msg | retrying request | retrying request | True | True | message matches |
| L2.ts | 2024-05-04T08:59:10Z | 2024-05-04T08:59:10Z | True | True | timestamp matches |
| L2.level | WARN | WARN | True | True | level matches |
| L2.service | search | search | True | True | service matches |
| L2.code | I841 | I841 | True | True | code matches |
| L2.msg | connection reset by peer | connection reset by peer | True | True | message matches |
| L3.ts | 2024-05-22T19:11:23Z | 2024-05-22T19:11:23Z | True | True | timestamp matches |
| L3.level | WARN | WARN | True | True | level matches |
| L3.service | api | api | True | True | service matches |
| L3.code | W865 | W865 | True | True | code matches |
| L3.msg | handler took 320ms | handler took 320ms | True | True | message matches |

raw: `{ /   "1": { /     "ts": "2024-05-26T04:17:29Z", /     "level": "ERROR", /     "service": "billing", /     "code": "D201", /     "msg": "retrying request" /   }, /   "2": { /     "ts": "2024-05-04T08:59:10Z", /     "level": "WARN", /     "service": "search", /     "code": "I841", /     "msg": "connection reset by peer" /   }, /   "3": { /     "ts": "2024-05-22T19:11:23Z", /     "level": "WARN", /     "service": "api", /     "code": "W865", /     "msg": "handler took 320ms" /   } / }`

### A17. regex_construct / regex_construct-001 (gold verifier)

```
For each specification write a regular expression that fully matches every 'match' string and none of the 'must not' strings.  Patterns are applied with full-string matching semantics (equivalent to re.fullmatch).  Answer with one pattern per line.
  1. four dot-separated groups of 1-3 digits
     match:     28.85.105.134 | 175.59.181.163 | 78.243.191.200
     must not:  192.168.1 | 192.168.1.10.1 | 192-168-1-10 | 1.2.3
  2. four-digit year, two-digit month and day, dash separated
     match:     2024-05-14 | 2024-02-01 | 2024-07-06
     must not:  2024-2-29 | 2024/02/29 | 24-02-29 | 2024-02-29x
  3. space-separated pairs of lower-case hex digits
     match:     0a 1b 2c | ff 00 7e | aa bb
     must not:  0a1b | 0a 1b 2 | 0a 1b 2c 3 | zz 00
  4. exactly #RRGGBB with six hex digits
     match:     #0c207a | #9cf13e | #8138e6 | #A05813
     must not:  abc123 | #abc | #abcdef0 | #12345g

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 4 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| r1 | ^\d{1,3}(\.\d{1,3}){3}$ | ^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$ | True | True | all labelled and held-out strings classified correctly |
| r2 | ^\d{4}-\d{2}-\d{2}$ | ^\d{4}-\d{2}-\d{2}$ | True | True | all labelled and held-out strings classified correctly |
| r3 | ^(?:[0-9a-f]{2} ){1,2}[0-9a-f]{2}$ | ^[0-9a-f]{2}(?: [0-9a-f]{2})*$ | True | True | all labelled and held-out strings classified correctly |
| r4 | ^#([0-9a-fA-F]{6})$ | ^#[0-9a-fA-F]{6}$ | True | True | all labelled and held-out strings classified correctly |

raw: `{ /   "answers": [ /     "^\\d{1,3}(\\.\\d{1,3}){3}$", /     "^\\d{4}-\\d{2}-\\d{2}$", /     "^(?:[0-9a-f]{2} ){1,2}[0-9a-f]{2}$", /     "^#([0-9a-fA-F]{6})$" /   ] / }`

### A18. regex_construct / regex_construct-004 (gold verifier)

```
For each specification write a regular expression that fully matches every 'match' string and none of the 'must not' strings.  Patterns are applied with full-string matching semantics (equivalent to re.fullmatch).  Answer with one pattern per line.
  1. exactly #RRGGBB with six hex digits
     match:     #5b3c79 | #4f0c7f | #c92dff | #D838DC
     must not:  abc123 | #abc | #abcdef0 | #12345g
  2. four dot-separated groups of 1-3 digits
     match:     29.115.220.102 | 164.105.199.228 | 216.187.199.12
     must not:  192.168.1 | 192.168.1.10.1 | 192-168-1-10 | 1.2.3
  3. space-separated pairs of lower-case hex digits
     match:     0a 1b 2c | ff 00 7e | aa bb
     must not:  0a1b | 0a 1b 2 | 0a 1b 2c 3 | zz 00
  4. ends in .py, base name from [A-Za-z0-9_.-]
     match:     main.py | my_script.py | lib-2.py
     must not:  main.pyc | main.PY | x | main.py.bak
  5. four-digit year, two-digit month and day, dash separated
     match:     2024-09-08 | 2024-09-27 | 2024-12-16
     must not:  2024-2-29 | 2024/02/29 | 24-02-29 | 2024-02-29x

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 5 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| r1 | ^#([0-9A-Fa-f]{6})$ | ^#[0-9a-fA-F]{6}$ | True | True | all labelled and held-out strings classified correctly |
| r2 | ^([0-9]{1,3}\.){3}[0-9]{1,3}$ | ^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$ | True | True | all labelled and held-out strings classified correctly |
| r3 | ^([0-9a-f]{2} ){1,2}[0-9a-f]{2}$ | ^[0-9a-f]{2}(?: [0-9a-f]{2})*$ | True | True | all labelled and held-out strings classified correctly |
| r4 | ^[A-Za-z0-9_.-]+\.py$ | ^[A-Za-z0-9_.-]+\.py$ | True | True | all labelled and held-out strings classified correctly |
| r5 | ^\d{4}-\d{2}-\d{2}$ | ^\d{4}-\d{2}-\d{2}$ | True | True | all labelled and held-out strings classified correctly |

raw: `{ /   "answers": [ /     "^#([0-9A-Fa-f]{6})$", /     "^([0-9]{1,3}\\.){3}[0-9]{1,3}$", /     "^([0-9a-f]{2} ){1,2}[0-9a-f]{2}$", /     "^[A-Za-z0-9_.-]+\\.py$", /     "^\\d{4}-\\d{2}-\\d{2}$" /   ] / }`

### A19. sql_result / sql_result-001 (gold verifier)

```
Write one SQL query per question for the schema orders(id, dept, region, amount, status) and depts(name, head, budget).  Answers are executed on this dataset and on a held-out dataset with the same schema.  Return a JSON array of SQL strings, one per question, in order.
  1. name, head and budget of departments with budget > 600, ordered by name (result order matters)
  2. number of orders with status 'paid' (result order matters)

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 2 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| q1 | SELECT name, head, budget FROM depts WHERE budget > 600 ORDER BY name | {'primary': [['ENG', 'Ada', 900], ['SLS', 'Grace', 700]], 'probe': [['ENG', 'Ada', 950], [... | True | True | result set matches on primary and probe data |
| q2 | SELECT COUNT(*) FROM orders WHERE status = 'paid' | {'primary': [[11]], 'probe': [[15]]} | True | True | result set matches on primary and probe data |

raw: `{"answers": ["SELECT name, head, budget FROM depts WHERE budget > 600 ORDER BY name", "SELECT COUNT(*) FROM orders WHERE status = 'paid'"]}`

### A20. sql_result / sql_result-003 (gold verifier)

```
Write one SQL query per question for the schema orders(id, dept, region, amount, status) and depts(name, head, budget).  Answers are executed on this dataset and on a held-out dataset with the same schema.  Return a JSON array of SQL strings, one per question, in order.
  1. name, head and budget of departments with budget > 600, ordered by name (result order matters)
  2. regions whose order count is strictly greater than 3, without ordering (order does not matter)

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 2 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| q1 | SELECT name, head, budget FROM depts WHERE budget > 600 ORDER BY name | {'primary': [['ENG', 'Ada', 900], ['SLS', 'Grace', 700]], 'probe': [['ENG', 'Ada', 950], [... | True | True | result set matches on primary and probe data |
| q2 | SELECT region FROM orders GROUP BY region HAVING COUNT(*) > 3 | {'primary': [['EU'], ['NA']], 'probe': [['APAC'], ['EU'], ['NA']]} | True | True | result set matches on primary and probe data |

raw: `{"answers": ["SELECT name, head, budget FROM depts WHERE budget > 600 ORDER BY name", "SELECT region FROM orders GROUP BY region HAVING COUNT(*) > 3"]}`

### A21. sql_result / sql_result-004 (gold verifier)

```
Write one SQL query per question for the schema orders(id, dept, region, amount, status) and depts(name, head, budget).  Answers are executed on this dataset and on a held-out dataset with the same schema.  Return a JSON array of SQL strings, one per question, in order.
  1. total amount per department, ordered by department ascending (result order matters)
  2. regions whose order count is strictly greater than 3, without ordering (order does not matter)

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 2 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| q1 | SELECT dept, SUM(amount) as total_amount FROM orders GROUP BY dept ORDER BY dept ASC | {'primary': [['ENG', 1755], ['HR', 1418], ['OPS', 2228], ['SLS', 879]], 'probe': [['ENG', ... | True | True | result set matches on primary and probe data |
| q2 | SELECT region FROM orders GROUP BY region HAVING COUNT(*) > 3 | {'primary': [['EU'], ['NA']], 'probe': [['APAC'], ['EU'], ['NA']]} | True | True | result set matches on primary and probe data |

raw: `{"answers": ["SELECT dept, SUM(amount) as total_amount FROM orders GROUP BY dept ORDER BY dept ASC", "SELECT region FROM orders GROUP BY region HAVING COUNT(*) > 3"]}`

### A22. sql_result / sql_result-005 (gold verifier)

```
Write one SQL query per question for the schema orders(id, dept, region, amount, status) and depts(name, head, budget).  Answers are executed on this dataset and on a held-out dataset with the same schema.  Return a JSON array of SQL strings, one per question, in order.
  1. name, head and budget of departments with budget > 600, ordered by name (result order matters)
  2. regions whose order count is strictly greater than 3, without ordering (order does not matter)

Answer with ONLY a JSON object of the form {"answers": [a1, a2, ...]} with exactly 2 entries in order. No prose, no code fences.
```

answer vs reference:
| unit | answer | reference | verifier | gold | verifier detail |
|---|---|---|---|---|---|
| q1 | SELECT name, head, budget FROM depts WHERE budget > 600 ORDER BY name | {'primary': [['ENG', 'Ada', 900], ['SLS', 'Grace', 700]], 'probe': [['ENG', 'Ada', 950], [... | True | True | result set matches on primary and probe data |
| q2 | SELECT region FROM orders GROUP BY region HAVING COUNT(*) > 3 | {'primary': [['EU'], ['NA']], 'probe': [['APAC'], ['EU'], ['NA']]} | True | True | result set matches on primary and probe data |

raw: `{"answers": ["SELECT name, head, budget FROM depts WHERE budget > 600 ORDER BY name", "SELECT region FROM orders GROUP BY region HAVING COUNT(*) > 3"]}`

## failed tasks
| family | task | bucket | detail | units ok |
|---|---|---|---|---|
| base_convert | base_convert-001 | CALC | all units wrong, no copy/spec signature | 0/5 |
| base_convert | base_convert-002 | CALC | all units wrong, no copy/spec signature | 0/6 |
| base_convert | base_convert-003 | CALC | all units wrong, no copy/spec signature | 0/6 |
| base_convert | base_convert-004 | CALC | all units wrong, no copy/spec signature | 0/5 |
| base_convert | base_convert-005 | CALC | all units wrong, no copy/spec signature | 0/4 |
| code_patch | code_patch-001 | CALC | all units wrong, no copy/spec signature | 0/5 |
| code_patch | code_patch-002 | CALC | all units wrong, no copy/spec signature | 0/5 |
| code_patch | code_patch-003 | CALC | all units wrong, no copy/spec signature | 0/4 |
| code_patch | code_patch-005 | CALC | all units wrong, no copy/spec signature | 0/4 |
| csp_assign | csp_assign-001 | CALC | all units wrong, no copy/spec signature | 0/3 |
| csp_assign | csp_assign-005 | CALC | all units wrong, no copy/spec signature | 0/3 |
| interval_merge | interval_merge-001 | CALC | all units wrong, no copy/spec signature | 0/6 |
| interval_merge | interval_merge-002 | CALC | all units wrong, no copy/spec signature | 0/5 |
| interval_merge | interval_merge-003 | CALC | all units wrong, no copy/spec signature | 0/5 |
| interval_merge | interval_merge-004 | CALC | all units wrong, no copy/spec signature | 0/5 |
| interval_merge | interval_merge-005 | CALC | all units wrong, no copy/spec signature | 0/5 |
| life_step | life_step-001 | CALC | all units wrong, no copy/spec signature | 0/5 |
| life_step | life_step-002 | CALC | all units wrong, no copy/spec signature | 0/6 |
| life_step | life_step-003 | CALC | all units wrong, no copy/spec signature | 0/6 |
| life_step | life_step-004 | CALC | all units wrong, no copy/spec signature | 0/5 |
| life_step | life_step-005 | CALC | all units wrong, no copy/spec signature | 0/6 |
| matrix_ops | matrix_ops-001 | CALC | all units wrong, no copy/spec signature | 0/4 |
| matrix_ops | matrix_ops-002 | CALC | all units wrong, no copy/spec signature | 0/9 |
| matrix_ops | matrix_ops-003 | CALC | all units wrong, no copy/spec signature | 0/9 |
| matrix_ops | matrix_ops-004 | CALC | all units wrong, no copy/spec signature | 0/9 |
| matrix_ops | matrix_ops-005 | CALC | all units wrong, no copy/spec signature | 0/9 |
| regex_construct | regex_construct-002 | CALC | all units wrong, no copy/spec signature | 0/3 |
| stats_summary | stats_summary-001 | CALC | all units wrong, no copy/spec signature | 0/5 |
| stats_summary | stats_summary-003 | CALC | all units wrong, no copy/spec signature | 0/5 |
| stats_summary | stats_summary-004 | CALC | all units wrong, no copy/spec signature | 0/5 |
| stats_summary | stats_summary-005 | CALC | all units wrong, no copy/spec signature | 0/5 |
| topo_order | topo_order-002 | CALC | all units wrong, no copy/spec signature | 0/3 |
| topo_order | topo_order-004 | CALC | all units wrong, no copy/spec signature | 0/3 |
| unit_convert | unit_convert-001 | CALC | all units wrong, no copy/spec signature | 0/2 |
| unit_convert | unit_convert-003 | CALC | all units wrong, no copy/spec signature | 0/2 |
| arith_expression | arith_expression-001 | PARTIAL | 1/2 units right | 1/2 |
| arith_expression | arith_expression-004 | PARTIAL | 3/5 units right | 3/5 |
| arith_expression | arith_expression-005 | PARTIAL | 2/5 units right | 2/5 |
| csp_assign | csp_assign-002 | PARTIAL | 2/3 units right | 2/3 |
| csp_assign | csp_assign-004 | PARTIAL | 2/3 units right | 2/3 |
| date_arith | date_arith-002 | PARTIAL | 3/4 units right | 3/4 |
| date_arith | date_arith-004 | PARTIAL | 1/4 units right | 1/4 |
| date_arith | date_arith-005 | PARTIAL | 4/5 units right | 4/5 |
| regex_construct | regex_construct-003 | PARTIAL | 3/4 units right | 3/4 |
| regex_construct | regex_construct-005 | PARTIAL | 3/4 units right | 3/4 |
| sort_multikey | sort_multikey-001 | PARTIAL | 6/8 units right | 6/8 |
| sort_multikey | sort_multikey-002 | PARTIAL | 1/6 units right | 1/6 |
| sort_multikey | sort_multikey-003 | PARTIAL | 1/8 units right | 1/8 |
| sort_multikey | sort_multikey-004 | PARTIAL | 1/9 units right | 1/9 |
| sort_multikey | sort_multikey-005 | PARTIAL | 3/7 units right | 3/7 |
| sql_result | sql_result-002 | PARTIAL | 2/3 units right | 2/3 |
| stats_summary | stats_summary-002 | PARTIAL | 1/5 units right | 1/5 |
| table_aggregate | table_aggregate-001 | PARTIAL | 5/12 units right | 5/12 |
| table_aggregate | table_aggregate-002 | PARTIAL | 1/9 units right | 1/9 |
| table_aggregate | table_aggregate-003 | PARTIAL | 2/9 units right | 2/9 |
| table_aggregate | table_aggregate-004 | PARTIAL | 5/12 units right | 5/12 |
| table_aggregate | table_aggregate-005 | PARTIAL | 6/9 units right | 6/9 |
| topo_order | topo_order-001 | PARTIAL | 1/3 units right | 1/3 |
| topo_order | topo_order-003 | PARTIAL | 2/3 units right | 2/3 |
| topo_order | topo_order-005 | PARTIAL | 1/3 units right | 1/3 |
| unit_convert | unit_convert-002 | PARTIAL | 1/2 units right | 1/2 |
| unit_convert | unit_convert-004 | PARTIAL | 1/4 units right | 1/4 |
| unit_convert | unit_convert-005 | PARTIAL | 3/4 units right | 3/4 |
| grid_path | grid_path-001 | SPEC | unit p1 answered in the wrong shape | 0/3 |
| grid_path | grid_path-002 | SPEC | unit p2 answered in the wrong shape | 1/3 |
| grid_path | grid_path-003 | SPEC | unit p1 answered in the wrong shape | 0/3 |
| grid_path | grid_path-004 | SPEC | unit p2 answered in the wrong shape | 1/3 |
| grid_path | grid_path-005 | SPEC | unit p1 answered in the wrong shape | 0/3 |
| schedule_slots | schedule_slots-001 | SPEC | unit s1 answered in the wrong shape | 0/3 |
| schedule_slots | schedule_slots-002 | SPEC | unit s1 answered in the wrong shape | 0/3 |
| schedule_slots | schedule_slots-003 | SPEC | unit s1 answered in the wrong shape | 0/3 |
| schedule_slots | schedule_slots-004 | SPEC | unit s1 answered in the wrong shape | 0/3 |
| schedule_slots | schedule_slots-005 | SPEC | unit s1 answered in the wrong shape | 0/3 |
| template_render | template_render-001 | SPEC | unit s1 answered in the wrong shape | 0/5 |
| template_render | template_render-002 | SPEC | unit s1 answered in the wrong shape | 0/5 |
| template_render | template_render-003 | SPEC | unit s1 answered in the wrong shape | 0/5 |
| template_render | template_render-004 | SPEC | unit s1 answered in the wrong shape | 0/5 |
| template_render | template_render-005 | SPEC | unit s1 answered in the wrong shape | 0/5 |

## leak candidates
- none on equality-graded families
