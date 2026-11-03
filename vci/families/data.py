"""Data families: SQL execution, group-by aggregation, multi-key sorting and
interval merging."""
import sqlite3
from fractions import Fraction
from typing import Any, Dict, List

from ..util import norm_text, num_close, parse_number
from .base import Family


SCHEMA = """
CREATE TABLE orders (id INTEGER PRIMARY KEY, dept TEXT, region TEXT,
                     amount INTEGER, status TEXT);
CREATE TABLE depts (name TEXT PRIMARY KEY, head TEXT, budget INTEGER);
"""

DEPTS = [
    ("ENG", "Ada", 900),
    ("SLS", "Grace", 700),
    ("OPS", "Linus", 500),
    ("HR", "Maria", 300),
]
REGIONS = ["NA", "EU", "APAC"]
STATUSES = ["paid", "pending", "refund"]


def _rows_equal(expected: List[List[Any]], got: List[List[Any]], ordered: bool) -> bool:
    def norm(rows):
        out = []
        for row in rows:
            cells = []
            for c in row:
                if isinstance(c, float):
                    cells.append(round(c, 9))
                elif isinstance(c, str):
                    cells.append(c.strip())
                else:
                    cells.append(c)
            out.append(tuple(cells))
        return out if ordered else sorted(out, key=lambda r: repr(r))

    e, g = norm(expected), norm(got)
    return len(e) == len(g) and all(a == b for a, b in zip(e, g))


def _make_db(rows: List[List[Any]]):
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO orders (id, dept, region, amount, status) VALUES (?,?,?,?,?)",
                    rows)
    con.executemany("INSERT INTO depts (name, head, budget) VALUES (?,?,?)", DEPTS)
    return con


def _run(rows: List[List[Any]], sql: str) -> List[List[Any]]:
    con = _make_db(rows)
    try:
        cur = con.execute(sql)
        return [list(r) for r in cur.fetchall()]
    finally:
        con.close()


QUESTION_TEMPLATES = {
    "sum_by_dept": ("total amount per department, ordered by department ascending",
                    "SELECT dept, SUM(amount) FROM orders GROUP BY dept ORDER BY dept ASC", True),
    "count_paid": ("number of orders with status 'paid'",
                   "SELECT COUNT(*) FROM orders WHERE status = 'paid'", True),
    "top2_depts": ("the two departments with the highest total amount, ordered by total descending",
                   "SELECT dept, SUM(amount) AS total FROM orders GROUP BY dept "
                   "ORDER BY total DESC LIMIT 2", True),
    "regions_over_3": ("regions whose order count is strictly greater than 3, without ordering",
                       "SELECT region FROM orders GROUP BY region HAVING COUNT(*) >= 4", False),
    "rich_depts": ("name, head and budget of departments with budget > 600, ordered by name",
                   "SELECT name, head, budget FROM depts WHERE budget > 600 ORDER BY name ASC", True),
    "avg_by_region": ("average amount per region, ordered by region",
                      "SELECT region, AVG(amount) FROM orders GROUP BY region ORDER BY region", True),
}


class SqlResult(Family):
    name = "sql_result"
    domain = "databases"
    task_shape = "write K SQL queries against a small schema"
    premise = "queries are executed on a visible dataset and a held-out probe dataset"
    scoring = "fraction of queries whose result set matches on both datasets"
    item_unit = "one query"
    payload_kind = "list"

    def make_one(self, rng, idx):
        rows = []
        for i in range(1, 31):
            rows.append([i, rng.choice([d[0] for d in DEPTS]), rng.choice(REGIONS),
                         rng.randint(10, 500), rng.choice(STATUSES)])
        # probe rows deliberately include counts at the HAVING boundary
        probe = [list(r) for r in rows]
        for j in range(12):
            probe.append([31 + j, rng.choice([d[0] for d in DEPTS]),
                          REGIONS[j % 3], rng.randint(10, 500),
                          rng.choice(STATUSES)])
        keys = rng.sample(list(QUESTION_TEMPLATES), rng.randint(2, 3))
        items, lines, meta_q = [], [], []
        for j, key in enumerate(keys, 1):
            text, ref_sql, ordered = QUESTION_TEMPLATES[key]
            exp_primary = _run(rows, ref_sql)
            exp_probe = _run(probe, ref_sql)
            items.append({"unit": f"q{j}", "expected": {"primary": exp_primary,
                                                        "probe": exp_probe},
                          "ordered": ordered, "key": key})
            lines.append(f"  {j}. {text}" + (" (result order matters)" if ordered
                                             else " (order does not matter)"))
            meta_q.append({"key": key, "ref": ref_sql, "ordered": ordered})
        prompt = ("Write one SQL query per question for the schema orders(id, dept, "
                  "region, amount, status) and depts(name, head, budget).  Answers "
                  "are executed on this dataset and on a held-out dataset with the "
                  "same schema.  Return a JSON array of SQL strings, one per "
                  "question, in order.\n" + "\n".join(lines))
        return self.task(f"sql_result-{idx:03d}", prompt, items,
                         {"rows": rows, "probe": probe, "questions": meta_q})

    def canonical(self, task):
        return [q["ref"] for q in task.meta["questions"]]

    def _results_match(self, task, item, sql):
        """Independent oracle check: does this query reproduce the reference result?"""
        try:
            if not self._safe(sql):
                return False
            got = _run(task.meta["rows"], sql)
            got_probe = _run(task.meta["probe"], sql)
        except sqlite3.Error:
            return False
        exp = item["expected"]
        return (_rows_equal(exp["primary"], got, item["ordered"])
                and _rows_equal(exp["probe"], got_probe, item["ordered"]))

    #: Last-resort rewrites used only when a class-specific mutant happened to
    #: reproduce the reference result.  Each is unambiguously wrong for its key.
    _GUARANTEED_WRONG = {
        "sum_by_dept": "SELECT 'X' AS dept, SUM(amount) FROM orders GROUP BY orders.dept ORDER BY 1, 2",
        "count_paid": "SELECT COUNT(*) + 1 FROM orders WHERE status = 'paid'",
        "top2_depts": "SELECT 'X', SUM(amount) FROM orders GROUP BY dept ORDER BY 2 DESC LIMIT 2",
        "regions_over_3": "SELECT region, COUNT(*) FROM orders GROUP BY region HAVING COUNT(*) >= 4",
        "rich_depts": "SELECT name, head, budget FROM depts WHERE budget > 600 ORDER BY name DESC",
        "avg_by_region": "SELECT region, SUM(amount) FROM orders GROUP BY region ORDER BY region",
    }

    def _force_wrong(self, task, payload):
        """Make sure every wrong-class mutant really differs from the reference."""
        out = list(payload)
        for i, sql in enumerate(out):
            if i < len(task.items) and self._results_match(task, task.items[i], sql):
                out[i] = self._GUARANTEED_WRONG[task.items[i]["key"]]
        return out

    def equivalents(self, task, rng):
        alt = []
        for q, item in zip(task.meta["questions"], task.items):
            ref = q["ref"]
            if q["key"] == "sum_by_dept":
                cand = ("SELECT o.dept, total FROM (SELECT dept, SUM(amount) AS total "
                        "FROM orders GROUP BY dept) AS o ORDER BY o.dept")
            elif q["key"] == "count_paid":
                cand = "SELECT COUNT(id) FROM orders WHERE status = 'paid'"
            elif q["key"] == "top2_depts":
                cand = ("WITH t AS (SELECT dept, SUM(amount) AS s FROM orders GROUP BY dept) "
                        "SELECT dept, s FROM t ORDER BY s DESC LIMIT 2")
            elif q["key"] == "regions_over_3":
                cand = ("SELECT region FROM (SELECT region, COUNT(*) AS c FROM orders "
                        "GROUP BY region) WHERE c >= 4")
            elif q["key"] == "rich_depts":
                cand = "SELECT name, head, budget FROM depts WHERE budget >= 601 ORDER BY name"
            else:
                cand = ("SELECT region, SUM(amount) * 1.0 / COUNT(*) FROM orders "
                        "GROUP BY region ORDER BY region")
            alt.append(cand if self._results_match(task, item, cand) else ref)
        return [(alt, "equivalent query rewrite (subquery/CTE or equivalent predicate)")]

    def wrongs(self, task, rng):
        base = self.canonical(task)
        keys = [q["key"] for q in task.meta["questions"]]
        # boundary: strict/inclusive comparison flipped on the first question that uses one
        b = list(base)
        for i, k in enumerate(keys):
            if k == "regions_over_3":
                b[i] = "SELECT region FROM orders GROUP BY region HAVING COUNT(*) > 3"
            elif k == "rich_depts":
                b[i] = "SELECT name, head, budget FROM depts WHERE budget >= 600 ORDER BY name"
        off = list(base)
        for i, k in enumerate(keys):
            if k == "top2_depts":
                off[i] = base[i].replace("LIMIT 2", "LIMIT 3")
            elif k == "count_paid":
                off[i] = "SELECT COUNT(*) FROM orders WHERE status = 'paid' OR status = 'pending'"
        typ = list(base)
        typ[0] = "SELECT dept, CAST(SUM(amount) AS TEXT) FROM orders GROUP BY dept ORDER BY dept"
        # order: drop ORDER BY on the first ordered question
        order = list(base)
        for i, q in enumerate(task.meta["questions"]):
            if q["ordered"] and "ORDER BY" in order[i]:
                order[i] = order[i].split(" ORDER BY")[0]
                break
        miss = base[:-1]
        extra = base + ["SELECT COUNT(*) FROM depts"]
        wrong = list(base)
        for i, k in enumerate(keys):
            if k == "count_paid":
                wrong[i] = "SELECT COUNT(*) FROM orders WHERE status = 'refund'"
            elif k == "sum_by_dept":
                wrong[i] = ("SELECT d.name, SUM(o.amount) FROM depts d JOIN orders o "
                            "ON d.head = o.region GROUP BY d.name ORDER BY d.name")
            elif k == "rich_depts":
                wrong[i] = "SELECT name, head, budget FROM depts WHERE budget < 600 ORDER BY name"
        if wrong == base:
            wrong = list(base)
            wrong[-1] = "SELECT " + ", ".join(["1"] * len(base)) + " FROM depts LIMIT 1"
        # A mutant must genuinely differ from the reference on at least one unit;
        # otherwise the "false accept" we would measure is the mutant's fault.
        return [("boundary", self._force_wrong(task, b), "inclusive/exclusive comparison flipped"),
                ("off_by_one", self._force_wrong(task, off), "LIMIT or predicate widened by one"),
                ("type_mismatch", self._force_wrong(task, typ), "numeric aggregate cast to text"),
                ("order", self._force_wrong(task, order), "ORDER BY dropped"),
                ("missing", miss, "last query omitted"),
                ("extra", extra, "extra query appended"),
                ("semantic_wrong", self._force_wrong(task, wrong), "wrong predicate or join key")]

    def corrupt_item(self, task, item, rng):
        return "SELECT 1"

    @staticmethod
    def _safe(sql: Any) -> bool:
        if not isinstance(sql, str) or len(sql) > 600:
            return False
        s = sql.strip().lower()
        if not (s.startswith("select") or s.startswith("with")):
            return False
        banned = ("attach", "pragma", "insert", "update", "delete", "drop",
                  "create", "alter", ";")
        return not any(b in s for b in banned)

    def grade_item(self, task, item, answer):
        if not self._safe(answer):
            return False, f"not an accepted read-only SQL query: {answer!r}"
        try:
            got_primary = _run(task.meta["rows"], answer)
            got_probe = _run(task.meta["probe"], answer)
        except sqlite3.Error as ex:
            return False, f"query failed: {ex}"
        exp = item["expected"]
        ordered = item["ordered"]
        okp = _rows_equal(exp["primary"], got_primary, ordered)
        okq = _rows_equal(exp["probe"], got_probe, ordered)
        if okp and okq:
            return True, "result set matches on primary and probe data"
        detail = []
        if not okp:
            detail.append(f"primary mismatch: expected {exp['primary']} got {got_primary}")
        if not okq:
            detail.append(f"probe mismatch: expected {exp['probe']} got {got_probe}")
        return False, "; ".join(detail)


class TableAggregate(Family):
    name = "table_aggregate"
    domain = "data analysis"
    task_shape = "compute count/sum/mean per group from a small table"
    premise = "closed aggregation semantics with documented rounding"
    scoring = "fraction of group-metric cells that match"
    item_unit = "one group-metric cell"
    payload_kind = "mapping"

    METRICS = ("count", "sum", "mean")

    def make_one(self, rng, idx):
        depts = ["ENG", "SLS", "OPS", "HR"][: rng.randint(3, 4)]
        rows = [(d, rng.choice(REGIONS), rng.randint(10, 900)) for d in depts]
        for _ in range(rng.randint(9, 14)):
            rows.append((rng.choice(depts), rng.choice(REGIONS), rng.randint(10, 900)))
        rng.shuffle(rows)
        expected = {}
        for d in depts:
            amounts = [r[2] for r in rows if r[0] == d]
            expected[d] = {"count": len(amounts), "sum": sum(amounts),
                           "mean": Fraction(sum(amounts), len(amounts))}
        items = [{"unit": f"{d}.{m}", "expected": expected[d][m], "dept": d}
                 for d in depts for m in self.METRICS]
        prompt = ("Aggregate the table below by department.  Return a JSON object "
                  "mapping each department name to {count, sum, mean}; mean may have "
                  "at most 1e-6 relative error.\n  (dept, region, amount)\n" +
                  "\n".join(f"  {r}" for r in rows))
        return self.task(f"table_aggregate-{idx:03d}", prompt, items,
                         {"rows": rows, "depts": depts})

    def canonical(self, task):
        out: Dict[str, Dict[str, Any]] = {}
        for it in task.items:
            d, m = it["unit"].split(".", 1)
            v = it["expected"]
            out.setdefault(d, {})[m] = (str(v) if isinstance(v, Fraction) else v)
        return out

    def extract_answers(self, task, payload):
        if not isinstance(payload, dict):
            return {}, [], f"payload is {type(payload).__name__}, expected an object"
        answers, extras = {}, []
        for d, obj in payload.items():
            if not isinstance(obj, dict):
                extras.append(f"extra[{d}]")
                continue
            for m, v in obj.items():
                unit = f"{d}.{m}"
                if unit in task.units:
                    answers[unit] = v
                else:
                    extras.append(unit)
        return answers, extras, None

    def set_units(self, task, payload, replacements):
        import copy
        out = copy.deepcopy(payload)
        for unit, value in replacements.items():
            d, m = unit.split(".", 1)
            out[d][m] = value
        return out

    def equivalents(self, task, rng):
        a = {d: {m: (float(parse_number(v)) if m == "mean" else int(parse_number(v)))
                 for m, v in obj.items()} for d, obj in self.canonical(task).items()}
        b = {d: {m: (f"{float(parse_number(v)):.6f}" if m == "mean" else str(v))
                 for m, v in obj.items()} for d, obj in self.canonical(task).items()}
        return [(a, "numeric floats instead of strings"), (b, "six-decimal mean spelling")]

    def wrongs(self, task, rng):
        base = self.canonical(task)
        first = task.meta["depts"][0]
        second = task.meta["depts"][-1]
        rows = task.meta["rows"]
        uniq = {d: len({r[1] for r in rows if r[0] == d}) for d in task.meta["depts"]}
        amt = [r[2] for r in rows if r[0] == first]
        card = {d: dict(v) for d, v in base.items()}
        # "distinct regions instead of rows" only differs when a department has
        # repeated regions; fall back to dropping one row from the count.
        wrong_count = uniq[first] if uniq[first] != len(amt) else len(amt) - 1
        card[first]["count"] = str(wrong_count)
        nofirst = {d: dict(v) for d, v in base.items()}
        nofirst[first]["sum"] = str(sum(amt) - amt[0])
        typ = {d: dict(v) for d, v in base.items()}
        typ[first]["mean"] = None
        miss = {d: dict(v) for d, v in base.items() if d != second}
        extra = {d: dict(v) for d, v in base.items()}
        extra["MARKETING"] = {"count": "3", "sum": "100", "mean": "33.333333"}
        swapped = {d: dict(v) for d, v in base.items()}
        pair = next(((a, b) for a in task.meta["depts"] for b in task.meta["depts"]
                     if a < b and base[a] != base[b]), None)
        if pair:
            swapped[pair[0]], swapped[pair[1]] = swapped[pair[1]], swapped[pair[0]]
        else:
            swapped[first] = dict(base[first],
                                  count=str(int(parse_number(base[first]["count"])) + 1))
        wrongmean = {d: dict(v) for d, v in base.items()}
        target = next((d for d in task.meta["depts"]
                       if sum(1 for r in rows if r[0] == d) >= 2), first)
        vals = sorted(r[2] for r in rows if r[0] == target)
        cand = vals[0]
        if Fraction(cand) == Fraction(sum(vals), len(vals)):
            cand += 1
        wrongmean[target]["mean"] = str(cand)
        return [("boundary", card, "count of distinct regions instead of rows"),
                ("off_by_one", nofirst, "sum drops the first row"),
                ("type_mismatch", typ, "mean is null"),
                ("order", swapped, "two group payloads swapped"),
                ("missing", miss, "one department omitted"),
                ("extra", extra, "unknown department added"),
                ("semantic_wrong", wrongmean, "mean replaced by the minimum entry")]

    def corrupt_item(self, task, item, rng):
        return "0"

    def grade_item(self, task, item, answer):
        exp = item["expected"]
        if isinstance(exp, int):
            v = parse_number(answer)
            good = v is not None and v.denominator == 1 and int(v) == exp
            return self.ok(good, "integer matches", f"expected {exp}, got {answer!r}")
        good = num_close(exp, answer, rel_tol=1e-6)
        return self.ok(good, "within tolerance", f"expected {float(exp):.6f}, got {answer!r}")


class SortMultikey(Family):
    name = "sort_multikey"
    domain = "data processing"
    task_shape = "sort K records by up to three keys with stable ties"
    premise = "total order specified explicitly; stability is part of the answer"
    scoring = "fraction of output positions holding the expected record"
    item_unit = "one output position"
    payload_kind = "list"

    KEYSETS = [
        (("score", "desc"), ("name", "asc"), ("ts", "asc")),
        (("dept", "asc"), ("score", "desc")),
        (("name", "asc"), ("ts", "desc")),
        (("ts", "asc"), ("score", "desc")),
    ]

    def make_one(self, rng, idx):
        n = rng.randint(6, 9)
        keys = rng.choice(self.KEYSETS)
        names = ["Ada", "grace", "Linus", "alan"]
        recs = [{"id": i, "name": rng.choice(names), "dept": rng.choice(["ENG", "SLS", "OPS"]),
                 "score": rng.choice([70, 80, 90]), "ts": rng.randint(1, 5)}
                for i in range(1, n + 1)]
        expected = self._stable_sort(recs, keys)
        items = [{"unit": f"p{i + 1}", "expected": expected[i]["id"]} for i in range(n)]
        desc = "; ".join(f"{k} {'descending' if o == 'desc' else 'ascending (case-insensitive)'}"
                         for k, o in keys)
        prompt = (f"Sort the records below by {desc}, preserving input order when all "
                  "sort keys are equal (stable sort).  Name comparisons are "
                  "case-insensitive.  Return the record ids as a JSON array, one "
                  "per output position.\n  records = " +
                  str([{k: r[k] for k in ("id", "name", "dept", "score", "ts")} for r in recs]))
        return self.task(f"sort_multikey-{idx:03d}", prompt, items, {"records": recs, "keys": keys})

    def _keyf(self, keys, case_sensitive: bool = False):
        def f(r):
            parts = []
            for k, order in keys:
                v = r[k]
                if isinstance(v, str):
                    v = v if case_sensitive else v.lower()
                    if order == "desc":
                        v = self._neg_str(v)
                elif order == "desc":
                    v = -v
                parts.append(v)
            return tuple(parts)
        return f

    def _stable_sort(self, recs, keys):
        return sorted(recs, key=self._keyf(keys))

    @staticmethod
    def _neg_str(s: str) -> str:
        return "".join(chr(0x10FFFF - ord(c)) for c in s)

    def canonical(self, task):
        return [it["expected"] for it in task.items]

    def equivalents(self, task, rng):
        return [([str(x) for x in self.canonical(task)], "ids as numeric strings"),
                ([float(x) for x in self.canonical(task)], "ids as floats")]

    def wrongs(self, task, rng):
        base = self.canonical(task)
        swapped = list(base)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        rotated = base[1:] + base[:1]
        typ = [{"id": base[0]}] + base[1:]
        recs = task.meta["records"]
        keys = task.meta["keys"]
        expected = self._stable_sort(recs, keys)
        # boundary: swap a pair of records whose sort keys are fully tied (violates stability)
        tie = list(base)
        kf = self._keyf(keys)
        found = False
        for i in range(len(expected) - 1):
            if kf(expected[i]) == kf(expected[i + 1]):
                tie[i], tie[i + 1] = tie[i + 1], tie[i]
                found = True
                break
        if not found:
            # no fully tied pair; swapping the last two positions still breaks
            # the required ordering (otherwise they would have been tied).
            tie[-1], tie[-2] = tie[-2], tie[-1]
        asc = self._stable_sort(recs, tuple((k, "asc" if o == "desc" else "desc")
                                           for k, o in keys))
        return [("order", swapped, "two adjacent positions swapped"),
                ("off_by_one", rotated, "one-position rotation"),
                ("type_mismatch", typ, "id wrapped in an object"),
                ("boundary", tie, "stable tie broken differently / case-sensitive ordering"),
                ("missing", base[:-1], "last record omitted"),
                ("extra", [base[0]] + base, "duplicate first record"),
                ("semantic_wrong", [r["id"] for r in asc], "sort directions inverted")]

    def corrupt_item(self, task, item, rng):
        return int(item["expected"]) + 100

    def grade_item(self, task, item, answer):
        v = parse_number(answer)
        good = v is not None and v.denominator == 1 and int(v) == item["expected"]
        return self.ok(good, "record id matches", f"expected {item['expected']}, got {answer!r}")


class IntervalMerge(Family):
    name = "interval_merge"
    domain = "algorithms"
    task_shape = "merge overlapping half-open intervals"
    premise = "half-open [a,b) semantics; touching endpoints are not merged"
    scoring = "fraction of expected merged intervals present at the right position"
    item_unit = "one merged interval"
    payload_kind = "list"

    def make_one(self, rng, idx):
        # two fixtures guarantee a touching pair (must stay separate) and an
        # overlapping pair (must merge); extras are placed far away.
        a = rng.randint(0, 8)
        b = a + rng.randint(14, 24)
        raw = [(a, a + 2), (a + 2, a + 4), (b, b + 2), (b + 1, b + 3)]
        for _ in range(rng.randint(1, 3)):
            c = rng.randint(60, 90)
            raw.append((c, c + rng.randint(1, 6)))
        merged = self._merge(raw)
        items = [{"unit": f"m{i + 1}", "expected": list(iv)} for i, iv in enumerate(merged)]
        prompt = ("Merge the half-open intervals [start, end) below.  Intervals that only "
                  "touch at an endpoint stay separate.  Return a JSON array of "
                  "[start, end] pairs in ascending order.\n  input = " + str(raw))
        return self.task(f"interval_merge-{idx:03d}", prompt, items, {"raw": raw,
                                                                     "n_merged": len(merged)})

    @staticmethod
    def _merge(raw):
        out = []
        for a, b in sorted(raw):
            if out and a <= out[-1][1] and a != out[-1][1]:
                out[-1][1] = max(out[-1][1], b)
            elif out and out[-1][1] == a:
                out.append([a, b])
            else:
                out.append([a, b])
        return out

    def canonical(self, task):
        return [list(it["expected"]) for it in task.items]

    def equivalents(self, task, rng):
        objs = [{"start": it["expected"][0], "end": it["expected"][1]} for it in task.items]
        return [(objs, "object form {start,end}")]

    def wrongs(self, task, rng):
        base = self.canonical(task)
        raw = task.meta["raw"]
        # boundary: merge intervals that only touch
        touched = []
        for a, b in sorted(raw):
            if touched and a <= touched[-1][1]:
                touched[-1][1] = max(touched[-1][1], b)
            else:
                touched.append([a, b])
        shift = [list(base[0])]
        shift[0][1] += 1
        shift += base[1:]
        return [("boundary", touched, "touching intervals merged"),
                ("off_by_one", shift, "first interval end off by one"),
                ("type_mismatch", [[None, base[0][1]]] + base[1:], "null endpoint"),
                ("order", list(reversed(base)), "merged intervals reversed"),
                ("missing", base[:-1], "last merged interval omitted"),
                ("extra", base + [[90, 99]], "extra interval appended"),
                ("semantic_wrong", [list(x) for x in sorted(raw)], "input returned unmerged")]

    def extract_answers(self, task, payload):
        if isinstance(payload, dict) and set(payload) == {"answers"}:
            payload = payload["answers"]
        if not isinstance(payload, (list, tuple)):
            return {}, [], f"payload is {type(payload).__name__}, expected a list"
        answers, extras = {}, []
        for i, val in enumerate(payload):
            if i < len(task.items):
                answers[task.items[i]["unit"]] = val
            else:
                extras.append(f"extra[{i}]")
        return answers, extras, None

    def set_units(self, task, payload, replacements):
        import copy
        out = copy.deepcopy(payload)
        for unit, value in replacements.items():
            out[task.units.index(unit)] = value
        return out

    def corrupt_item(self, task, item, rng):
        return [item["expected"][0] + 5, item["expected"][0] + 8]

    def grade_item(self, task, item, answer):
        exp = item["expected"]
        if isinstance(answer, dict) and set(answer) >= {"start", "end"}:
            a, b = parse_number(answer["start"]), parse_number(answer["end"])
        elif isinstance(answer, (list, tuple)) and len(answer) == 2:
            a, b = parse_number(answer[0]), parse_number(answer[1])
        else:
            return False, f"expected [start, end] or {{start, end}}, got {answer!r}"
        if a is None or b is None:
            return False, f"non-numeric endpoint: {answer!r}"
        return self.ok([a, b] == [Fraction(exp[0]), Fraction(exp[1])], "interval matches",
                       f"expected {exp}, got {answer!r}")
