"""Numeric families: arithmetic, unit conversion, statistics, base conversion,
matrix algebra and calendar arithmetic."""
import datetime as _dt
import math
import random
from decimal import Decimal, localcontext
from fractions import Fraction

from ..schema import Task
from ..util import norm_iso_date, num_close, parse_number
from .base import Family


def fmt_num(value, dp: int = 12) -> str:
    """Exact-looking decimal string for a Fraction or float."""
    if isinstance(value, float):
        return repr(value)
    fr = value if isinstance(value, Fraction) else Fraction(value)
    if fr.denominator == 1:
        return str(fr.numerator)
    with localcontext() as ctx:
        ctx.prec = 60
        d = Decimal(fr.numerator) / Decimal(fr.denominator)
        s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


class ArithExpression(Family):
    name = "arith_expression"
    domain = "mathematics"
    task_shape = "evaluate K arithmetic expressions with precedence"
    premise = "exact rational arithmetic, no external tools"
    scoring = "fraction of expressions whose value matches exactly (rel tol 1e-9)"
    item_unit = "one expression"
    payload_kind = "list"
    rel_tol = 1e-9

    def _expr(self, rng):
        nums = [rng.randint(1, 19) for _ in range(rng.randint(2, 3))]
        ops = [rng.choice(["+", "-", "*"]) for _ in range(len(nums) - 1)]
        parts = [str(nums[0])]
        # Standard precedence: '*' binds tighter than '+'/'-'.  The reference
        # value must equal what a reader computes from the printed expression
        # (round 6 found the previous left-to-right accumulator contradicting
        # the rendered text on 7/25 tasks).
        terms = [Fraction(nums[0])]
        for op, n in zip(ops, nums[1:]):
            parts.extend([op, str(n)])
            if op == "*":
                terms[-1] = terms[-1] * n
            elif op == "+":
                terms.append(Fraction(n))
            else:
                terms.append(Fraction(-n))
        text = " ".join(parts)
        val = sum(terms, Fraction(0))
        if rng.random() < 0.85:
            div = rng.choice([2, 4, 5, 8, 10])
            text = f"({text}) / {div}"
            val = val / div
        return text, val

    def make_one(self, rng, idx):
        k = rng.randint(2, 5)
        items, lines = [], []
        for j in range(k):
            text, val = self._expr(rng)
            items.append({"unit": f"q{j + 1}", "expected": val, "expr": text})
            lines.append(f"  {j + 1}. {text}")
        if all(it["expected"].denominator == 1 for it in items):
            odd = rng.choice([1, 3, 5, 7, 9, 11])
            items[-1] = {"unit": f"q{k}", "expected": Fraction(odd, 2),
                         "expr": f"({odd}) / 2"}
            lines[-1] = f"  {k}. ({odd}) / 2"
        prompt = ("Evaluate each expression exactly.  Answer with one value per "
                  "line, in order; fractions and decimals are both acceptable.\n"
                  + "\n".join(lines))
        return self.task(f"arith_expression-{idx:03d}", prompt, items,
                         {"exprs": [it["expr"] for it in items]})

    def canonical(self, task):
        return [fmt_num(it["expected"]) for it in task.items]

    def equivalents(self, task, rng):
        frac = [str(it["expected"]) if it["expected"].denominator != 1 else str(it["expected"].numerator)
                for it in task.items]
        padded = []
        for it in task.items:
            s = fmt_num(it["expected"], 6)
            padded.append(s if "." in s else s + ".00")
        return [(frac, "fraction spelling"), (padded, "trailing zeros / decimal spelling")]

    def wrongs(self, task, rng):
        base = [Fraction(it["expected"]) for it in task.items]
        off = base[:]
        off[0] = off[0] + 1
        floor = [Fraction(math.floor(v)) for v in base]
        neg = base[:]
        neg[0] = (-neg[0]) if neg[0] else (neg[0] + 7)
        return [
            ("off_by_one", [fmt_num(v) for v in off], "one expression off by 1"),
            ("boundary", [fmt_num(v) for v in floor], "floor rounding at the integer boundary"),
            ("type_mismatch", [fmt_num(v) if i else None for i, v in enumerate(base)],
             "null in place of a number"),
            ("order", list(reversed([fmt_num(v) for v in base])), "answers in reverse order"),
            ("missing", [fmt_num(v) for v in base[:-1]], "last answer omitted"),
            ("extra", [fmt_num(v) for v in base] + ["42"], "one extra answer appended"),
            ("semantic_wrong", [fmt_num(v) for v in neg], "sign error"),
        ]

    def corrupt_item(self, task, item, rng):
        return fmt_num(Fraction(item["expected"]) + rng.choice([1, 2, -1]))

    def grade_item(self, task, item, answer):
        ok = num_close(item["expected"], answer, rel_tol=self.rel_tol)
        return self.ok(ok, "exact value", f"expected {fmt_num(item['expected'])}, got {answer!r}")


LENGTH = {"m": Fraction(1), "km": Fraction(1000), "cm": Fraction(1, 100),
          "mm": Fraction(1, 1000), "in": Fraction(254, 10000),
          "ft": Fraction(3048, 10000), "mi": Fraction(1609344, 1000),
          "yd": Fraction(9144, 10000)}
MASS = {"kg": Fraction(1), "g": Fraction(1, 1000), "mg": Fraction(1, 1000000),
        "lb": Fraction(45359237, 100000000), "oz": Fraction(28349523125, 1000000000000)}
TIME = {"s": Fraction(1), "min": Fraction(60), "h": Fraction(3600), "day": Fraction(86400)}
VOLUME = {"L": Fraction(1), "mL": Fraction(1, 1000), "m3": Fraction(1000),
          "gal_us": Fraction(3785411784, 1000000000)}
UNIT_SYSTEMS = [LENGTH, MASS, TIME, VOLUME]


class UnitConvert(Family):
    name = "unit_convert"
    domain = "measurement"
    task_shape = "convert K quantities between units of the same dimension"
    premise = "closed set of exact rational conversion factors"
    scoring = "fraction of conversions within 1e-9 relative tolerance"
    item_unit = "one conversion"
    payload_kind = "list"
    rel_tol = 1e-9

    def make_one(self, rng, idx):
        k = rng.randint(2, 5)
        items, lines = [], []
        for j in range(k):
            system = rng.choice(UNIT_SYSTEMS)
            src, dst = rng.sample(sorted(system), 2)
            raw = Fraction(rng.randint(1, 9999), 10000) + rng.randint(1, 500)
            expected = raw * system[src] / system[dst]
            items.append({"unit": f"q{j + 1}", "expected": expected,
                          "src": src, "dst": dst, "value": raw})
            lines.append(f"  {j + 1}. {fmt_num(raw)} {src} -> {dst}")
        prompt = ("Convert each quantity into the target unit.  Give one numeric "
                  "answer per line, in order (no unit suffix).\n" + "\n".join(lines))
        return self.task(f"unit_convert-{idx:03d}", prompt, items, {"systems": "SI/imperial"})

    def canonical(self, task):
        return [fmt_num(it["expected"], 14) for it in task.items]

    def equivalents(self, task, rng):
        frac = [str(it["expected"]) for it in task.items]
        grouped = []
        for it in task.items:
            s = fmt_num(it["expected"], 14)
            if "." in s and len(s.split(".")[0]) > 3:
                head, tail = s.split(".")
                head = f"{int(head):,}"
                grouped.append(f"{head}.{tail}")
            else:
                grouped.append(s)
        return [(frac, "rational spelling"), (grouped, "thousands separators")]

    def wrongs(self, task, rng):
        base = [it["expected"] for it in task.items]
        order_mag = [base[0] * 10] + list(base[1:])
        s0 = task.items[0]
        # value squared over the true answer is the "forgot to convert" value
        inverse = [(s0["value"] * s0["value"] / base[0]) if base[0] else s0["value"] * 1000]
        rounded = [Fraction(round(float(v), 2)) if i == 0 else v for i, v in enumerate(base)]
        if base[0] and abs(rounded[0] - base[0]) / abs(base[0]) <= Fraction(1, 10 ** 6):
            # rounding a large number to 2 decimals is still inside a 1e-9 *relative*
            # tolerance, so it is not a defect.  Use a 1e-6 relative shift instead.
            rounded[0] = base[0] * Fraction(1000001, 1000000)
        return [
            ("boundary", [fmt_num(v, 14) for v in rounded],
             "first answer rounded at the precision boundary"),
            ("off_by_one", [fmt_num(v, 14) for v in order_mag], "first factor off by 10x"),
            ("type_mismatch", [None] + [fmt_num(v, 14) for v in base[1:]], "null answer"),
            ("order", list(reversed([fmt_num(v, 14) for v in base])), "answers reversed"),
            ("missing", [fmt_num(v, 14) for v in base[:-1]], "last conversion omitted"),
            ("extra", [fmt_num(v, 14) for v in base] + ["0"], "extra answer"),
            ("semantic_wrong", [fmt_num(inverse[0], 14)] + [fmt_num(v, 14) for v in base[1:]],
             "inverse conversion used for the first quantity"),
        ]

    def corrupt_item(self, task, item, rng):
        return fmt_num(item["expected"] * rng.choice([10, 100, Fraction(1, 10)]), 14)

    def grade_item(self, task, item, answer):
        ok = num_close(item["expected"], answer, rel_tol=self.rel_tol)
        return self.ok(ok, "within tolerance",
                       f"expected {fmt_num(item['expected'], 14)}, got {answer!r}")


class StatsSummary(Family):
    name = "stats_summary"
    domain = "statistics"
    task_shape = "compute 5 descriptive statistics for a small numeric sample"
    premise = "explicit percentile and ddof conventions"
    scoring = "fraction of statistics within 1e-6 relative tolerance"
    item_unit = "one statistic"
    payload_kind = "mapping"
    rel_tol = 1e-6

    def make_one(self, rng, idx):
        # an even sample size keeps "lower middle value" distinct from the true
        # median, and the two middle values are forced apart so the boundary
        # mutant (lower-middle median) cannot accidentally be correct.
        n = rng.choice([10, 12, 14])
        mid = n // 2
        while True:
            xs = sorted(rng.randint(0, 100) for _ in range(n))
            if xs[mid - 1] != xs[mid]:
                break
        s = sorted(xs)
        mean = Fraction(sum(xs), n)

        def median(vals):
            m = len(vals)
            if m % 2:
                return Fraction(vals[m // 2])
            return Fraction(vals[m // 2 - 1] + vals[m // 2], 2)

        def quantile(vals, q):
            pos = (len(vals) - 1) * q
            lo, hi = int(math.floor(pos)), int(math.ceil(pos))
            if lo == hi:
                return Fraction(vals[lo])
            return Fraction(vals[lo]) + (Fraction(vals[hi]) - Fraction(vals[lo])) * Fraction(pos - lo)

        var = sum((x - float(mean)) ** 2 for x in xs) / (n - 1)
        items = [
            {"unit": "mean", "expected": mean},
            {"unit": "median", "expected": median(s)},
            {"unit": "std_sample", "expected": math.sqrt(var)},
            {"unit": "q1", "expected": quantile(s, 0.25)},
            {"unit": "q3", "expected": quantile(s, 0.75)},
        ]
        prompt = ("Given the sample below compute mean, median, sample standard "
                  "deviation (ddof=1), Q1 and Q3 (linear interpolation, "
                  "position=(n-1)*q).  Answer as a JSON object with keys "
                  "mean, median, std_sample, q1, q3.\n  data = " + str(xs))
        return self.task(f"stats_summary-{idx:03d}", prompt, items, {"data": xs})

    def canonical(self, task):
        out = {}
        for it in task.items:
            v = it["expected"]
            out[it["unit"]] = (repr(v) if isinstance(v, float) else fmt_num(v, 10))
        return out

    def equivalents(self, task, rng):
        a = {it["unit"]: (float(it["expected"]) if it["unit"] == "std_sample"
                          else float(it["expected"])) for it in task.items}
        b = {it["unit"]: (f"{float(it['expected']):.6f}" if it["unit"] == "std_sample"
                          else fmt_num(it["expected"], 6)) for it in task.items}
        return [(a, "numeric floats instead of strings"),
                (b, "six-decimal rounding (inside tolerance)")]

    def wrongs(self, task, rng):
        xs = sorted(task.meta["data"])
        n = len(xs)
        base = self.canonical(task)
        lo_med = Fraction(xs[n // 2 - 1] if n % 2 == 0 else xs[n // 2])
        pop_std = math.sqrt(sum((x - sum(xs) / n) ** 2 for x in xs) / n)
        mean_wo_first = Fraction(sum(xs[1:]), n - 1)
        return [
            ("boundary", dict(base, median=fmt_num(lo_med, 10)),
             "even-length median uses the lower middle value instead of the average"),
            ("off_by_one", dict(base, mean=fmt_num(mean_wo_first, 10)),
             "mean drops one observation"),
            ("type_mismatch", dict(base, std_sample=None), "null for std_sample"),
            ("missing", {k: v for k, v in base.items() if k != "q3"}, "q3 omitted"),
            ("extra", dict(base, **{"range": "100"}), "extra statistic added"),
            ("semantic_wrong", dict(base, std_sample=repr(pop_std)),
             "population std (ddof=0) reported as sample std"),
        ]

    def corrupt_item(self, task, item, rng):
        if item["unit"] == "std_sample":
            return repr(float(item["expected"]) * 2)
        return fmt_num(Fraction(item["expected"]) + 5, 10)

    def grade_item(self, task, item, answer):
        ok = num_close(item["expected"], answer, rel_tol=self.rel_tol)
        return self.ok(ok, "within tolerance",
                       f"expected {item['expected']!r}, got {answer!r}")


class BaseConvert(Family):
    name = "base_convert"
    domain = "computer science"
    task_shape = "represent K integers in a requested base"
    premise = "positional notation with a small, closed digit alphabet"
    scoring = "fraction of representations that parse to the correct integer"
    item_unit = "one integer"
    payload_kind = "list"

    BASES = [2, 8, 16]
    DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"

    def make_one(self, rng, idx):
        k = rng.randint(3, 6)
        items, lines = [], []
        for j in range(k):
            base = rng.choice(self.BASES)
            value = rng.randint(1, 4095)
            items.append({"unit": f"q{j + 1}", "expected": value, "base": base})
            lines.append(f"  {j + 1}. {value} -> base {base}")
        prompt = ("Represent each decimal integer in the requested base.  One "
                  "answer per line, in order, digits only (no prefix).\n"
                  + "\n".join(lines))
        return self.task(f"base_convert-{idx:03d}", prompt, items, {})

    def _digits(self, value, base):
        out = ""
        v = int(value)
        if v == 0:
            return "0"
        while v:
            v, r = divmod(v, base)
            out = self.DIGITS[r] + out
        return out

    def canonical(self, task):
        return [self._digits(it["expected"], it["base"]).upper() for it in task.items]

    def equivalents(self, task, rng):
        lower = [self._digits(it["expected"], it["base"]).lower() for it in task.items]
        pref = []
        for it in task.items:
            d = self._digits(it["expected"], it["base"])
            prefix = {2: "0b", 8: "0o", 16: "0x"}[it["base"]]
            pref.append(prefix + d)
        return [(lower, "lower-case digits"),
                (pref, "explicit base prefix")]

    def wrongs(self, task, rng):
        base = [it["expected"] for it in task.items]
        shifted = [base[0] + 1] + list(base[1:])
        return [
            ("off_by_one", [self._digits(v, it["base"]).upper()
                            for v, it in zip(shifted, task.items)], "first integer off by one"),
            ("boundary", [self._digits(it["expected"] if i else it["expected"] * 2, it["base"]).upper()
                          for i, it in enumerate(task.items)], "carry boundary crossed"),
            ("type_mismatch", [None] + [self._digits(it["expected"], it["base"]).upper()
                                        for it in task.items[1:]], "null representation"),
            ("order", list(reversed([self._digits(it["expected"], it["base"]).upper()
                                     for it in task.items])), "lines reversed"),
            ("missing", [self._digits(it["expected"], it["base"]).upper()
                         for it in task.items[:-1]], "last line omitted"),
            ("extra", [self._digits(it["expected"], it["base"]).upper()
                       for it in task.items] + ["0"], "extra line"),
            ("semantic_wrong", [self._digits(it["expected"] * it["base"], it["base"]).upper()
                                for it in task.items], "each value scaled by its own base"),
        ]

    def corrupt_item(self, task, item, rng):
        return self._digits(int(item["expected"]) + rng.choice([1, 2, 16]), item["base"])

    def grade_item(self, task, item, answer):
        if not isinstance(answer, str):
            return False, f"expected a digit string, got {type(answer).__name__}"
        s = answer.strip().lower().replace("_", "")
        base = item["base"]
        if base == 16 and s.startswith("0x"):
            s = s[2:]
        elif base == 2 and s.startswith("0b"):
            s = s[2:]
        elif base == 8 and s.startswith("0o"):
            s = s[2:]
        s = s.lstrip("0") or "0"
        try:
            value = int(s, base)
        except ValueError:
            return False, f"not a base-{base} numeral: {answer!r}"
        return self.ok(value == item["expected"], "parses to the expected integer",
                       f"expected {self._digits(item['expected'], base)}, got {answer!r}")


class MatrixOps(Family):
    name = "matrix_ops"
    domain = "linear algebra"
    task_shape = "multiply or transpose small integer matrices"
    premise = "exact integer arithmetic, fully specified operation"
    scoring = "fraction of correct output cells"
    item_unit = "one matrix cell"
    payload_kind = "list"

    def make_one(self, rng, idx):
        op = rng.choice(["multiply", "transpose", "add"])
        n = rng.randint(2, 3)
        a = [[rng.randint(-9, 9) for _ in range(n)] for _ in range(n)]
        if op == "transpose":
            expected = [[a[j][i] for j in range(n)] for i in range(n)]
            prompt_op = f"transpose the {n}x{n} matrix"
        elif op == "add":
            b = [[rng.randint(-9, 9) for _ in range(n)] for _ in range(n)]
            expected = [[a[i][j] + b[i][j] for j in range(n)] for i in range(n)]
            prompt_op = f"add the two {n}x{n} matrices A and B"
        else:
            b = [[rng.randint(-9, 9) for _ in range(n)] for _ in range(n)]
            expected = [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(n)]
                        for i in range(n)]
            prompt_op = f"multiply the two {n}x{n} matrices A and B"
        items = [{"unit": f"r{i}c{j}", "expected": expected[i][j], "row": i, "col": j}
                 for i in range(n) for j in range(n)]
        prompt = (f"Given A = {a}" + (f" and B = {b}" if op != "transpose" else "")
                  + f", {prompt_op}.  Reply with a JSON array of rows of integers.")
        return self.task(f"matrix_ops-{idx:03d}", prompt, items, {"n": n, "op": op})

    def canonical(self, task):
        n = task.meta["n"]
        out = [[None] * n for _ in range(n)]
        for it in task.items:
            out[it["row"]][it["col"]] = it["expected"]
        return out

    def extract_answers(self, task, payload):
        n = task.meta["n"]
        if not isinstance(payload, (list, tuple)) or not all(
                isinstance(r, (list, tuple)) for r in payload):
            return {}, [], f"payload is not an array of rows: {type(payload).__name__}"
        answers, extras = {}, []
        for i, row in enumerate(payload):
            for j, cell in enumerate(row):
                if i < n and j < n:
                    answers[f"r{i}c{j}"] = cell
                else:
                    extras.append(f"extra[{i}][{j}]")
        return answers, extras, None

    def equivalents(self, task, rng):
        strs = [[str(v) for v in row] for row in self.canonical(task)]
        return [(strs, "cells as numeric strings")]

    def wrongs(self, task, rng):
        base = self.canonical(task)
        n = task.meta["n"]
        plus = [[v + (1 if i == 0 and j == 0 else 0) for j, v in enumerate(row)]
                for i, row in enumerate(base)]
        trans = [[base[j][i] for j in range(n)] for i in range(n)]
        if trans == base:
            # a symmetric result transposes to itself; perturb a row instead
            trans = [[v + (1 if i == 0 else 0) for j, v in enumerate(row)]
                     for i, row in enumerate(base)]
        zero = [[0] * n for _ in range(n)]
        boundary = zero if any(v for row in base for v in row) else [[1 if (i == j) else 0
                                                                     for j in range(n)]
                                                                    for i in range(n)]
        if boundary == base:
            boundary = [[v + (1 if i == 0 else 0) for j, v in enumerate(row)]
                        for i, row in enumerate(base)]
        doubled = [[v * 2 for v in row] for row in base]
        if doubled == base:
            doubled = [[v + 1 for v in row] for row in base]
        return [
            ("off_by_one", plus, "top-left cell off by one"),
            ("boundary", boundary, "degenerate result at the zero boundary"),
            ("type_mismatch", [[None] + row[1:] for row in base], "null in the first column"),
            ("order", trans, "result transposed"),
            ("missing", base[:-1], "last row missing"),
            ("extra", base + [[0] * n], "extra zero row appended"),
            ("semantic_wrong", doubled, "cell values doubled"),
        ]

    def set_units(self, task, payload, replacements):
        import copy
        out = copy.deepcopy(payload)
        for unit, value in replacements.items():
            it = next(i for i in task.items if i["unit"] == unit)
            out[it["row"]][it["col"]] = value
        return out

    def corrupt_item(self, task, item, rng):
        return int(item["expected"]) + rng.choice([1, -1, 5])

    def grade_item(self, task, item, answer):
        v = parse_number(answer)
        if v is None:
            return False, f"cell is not numeric: {answer!r}"
        return self.ok(v == item["expected"], "cell matches",
                       f"expected {item['expected']}, got {answer!r}")


class DateArith(Family):
    name = "date_arith"
    domain = "calendar"
    task_shape = "shift K dates by days or months with end-of-month clamping"
    premise = "ISO-8601 civil calendar, documented clamping rule"
    scoring = "fraction of dates that match exactly"
    item_unit = "one date"
    payload_kind = "list"

    def _add_months(self, d: _dt.date, months: int, clamp: bool) -> _dt.date:
        total = d.year * 12 + (d.month - 1) + months
        year, month = divmod(total, 12)
        month += 1
        if clamp:
            import calendar
            day = min(d.day, calendar.monthrange(year, month)[1])
        else:
            day = d.day  # deliberately overflows
        try:
            return _dt.date(year, month, day)
        except ValueError:
            # rollover convention used only by the boundary mutant
            return _dt.date(year, month, 1) + _dt.timedelta(days=d.day - 1)

    def _clamps(self, it) -> bool:
        """True when dropping the end-of-month clamp really changes this item."""
        if it["kind"][0] != "months":
            return False
        start = _dt.date.fromisoformat(it["start"])
        return self._add_months(start, it["kind"][1], clamp=False) != \
            _dt.date.fromisoformat(it["expected"])

    def make_one(self, rng, idx):
        k = rng.randint(3, 5)
        items, lines = [], []
        for j in range(k):
            start = _dt.date(2023, 1, 1) + _dt.timedelta(days=rng.randint(0, 700))
            if rng.random() < 0.5:
                delta = rng.randint(-40, 60)
                op_text = f"{delta:+d} days"
                expected = start + _dt.timedelta(days=delta)
                kind = ("days", delta)
            else:
                delta = rng.randint(1, 18) * rng.choice([1, -1])
                op_text = f"{delta:+d} months"
                expected = self._add_months(start, delta, clamp=True)
                kind = ("months", delta)
            items.append({"unit": f"d{j + 1}", "expected": expected.isoformat(),
                          "start": start.isoformat(), "kind": kind, "op": op_text})
            lines.append(f"  {j + 1}. {start.isoformat()} {op_text}")
        if not any(self._clamps(it) for it in items):
            # guarantee at least one case where clamping actually changes the date
            items[-1] = dict(items[-1], start="2024-01-31", kind=("months", 1), op="+1 months",
                             expected="2024-02-29")
            lines[-1] = f"  {k}. 2024-01-31 +1 months"
        prompt = ("Shift each date by the given amount.  Month shifts clamp to the "
                  "last valid day of the target month.  Answer with ISO dates "
                  "(YYYY-MM-DD), one per line.\n" + "\n".join(lines))
        return self.task(f"date_arith-{idx:03d}", prompt, items, {})

    def canonical(self, task):
        return [it["expected"] for it in task.items]

    def equivalents(self, task, rng):
        slash = [it["expected"].replace("-", "/") for it in task.items]
        midnight = [it["expected"] + "T00:00:00" for it in task.items]
        return [(slash, "slashed date spelling"), (midnight, "midnight datetime spelling")]

    def wrongs(self, task, rng):
        base = [it["expected"] for it in task.items]
        # target the first item where the clamp actually matters; otherwise use a
        # plain off-by-one, which is wrong for every kind.
        idx = next((i for i, it in enumerate(task.items) if self._clamps(it)), None)
        bad_first = list(base)
        if idx is None:
            idx = 0
            bad_first[idx] = (_dt.date.fromisoformat(base[0])
                              + _dt.timedelta(days=1)).isoformat()
            note = "one day off at the boundary"
        else:
            it = task.items[idx]
            s = _dt.date.fromisoformat(it["start"])
            bad_first[idx] = self._add_months(s, it["kind"][1], clamp=False).isoformat()
            note = "no end-of-month clamping at the boundary"
        plus1 = [_dt.date.fromisoformat(x) + _dt.timedelta(days=1) for x in base]
        swapped = list(reversed(base))
        return [
            ("boundary", bad_first, note),
            ("off_by_one", [d.isoformat() for d in plus1], "every date shifted one extra day"),
            ("type_mismatch", [None] + base[1:], "null date"),
            ("order", swapped, "results reversed"),
            ("missing", base[:-1], "last date omitted"),
            ("extra", base + ["2024-01-01"], "extra date"),
            ("semantic_wrong", [(_dt.date.fromisoformat(x) - _dt.timedelta(days=2)).isoformat()
                                for x in base], "days shifted in the wrong direction"),
        ]

    def corrupt_item(self, task, item, rng):
        d = _dt.date.fromisoformat(item["expected"])
        return (d + _dt.timedelta(days=rng.choice([1, -1, 7]))).isoformat()

    def grade_item(self, task, item, answer):
        s = norm_iso_date(answer)
        if s is None:
            return False, f"not an ISO date: {answer!r}"
        try:
            _dt.date.fromisoformat(s)
        except ValueError:
            return False, f"invalid calendar date: {answer!r}"
        return self.ok(s == item["expected"], "date matches",
                       f"expected {item['expected']}, got {answer!r}")
