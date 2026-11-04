"""Text / structured-output families: schema extraction, log parsing, regex
construction and template rendering."""
import html
import re
from typing import Any, Dict, List

from ..schema import Task
from ..util import norm_text, num_close, parse_number
from .base import Family


def _norm_ts(value: Any):
    s = norm_text(value, collapse_ws=True)
    if s is None:
        return None
    s = s.replace(" ", "T", 1)
    if s.endswith("+00:00"):
        s = s[:-6] + "Z"
    if s.endswith(".000000Z"):
        s = s[:-9] + "Z"
    return s


class JsonSchemaExtract(Family):
    name = "json_schema_extract"
    domain = "information extraction"
    task_shape = "extract a fixed set of typed fields from a short document into JSON"
    premise = "closed schema with explicit per-field comparison rules"
    scoring = "fraction of schema fields that match (set semantics for tags, order for steps)"
    item_unit = "one schema field"
    payload_kind = "mapping"

    FIELDS = ("id", "customer", "priority", "total_usd", "tags", "steps")

    def make_one(self, rng, idx):
        oid = rng.randint(1000, 9999)
        names = ["Ada Lovelace", "Grace Hopper", "Alan Turing", "Katherine Johnson",
                 "Linus Pauling", "Maria Curie", "Niels Bohr", "Emmy Noether"]
        customer = rng.choice(names)
        priority = rng.randint(1, 5)
        cents = rng.randint(1000, 99999)
        tags = rng.sample(["urgent", "gift", "fragile", "bulk", "return", "express"],
                          rng.randint(2, 4))
        steps = rng.sample(["pack", "label", "ship", "invoice", "verify"],
                           rng.randint(2, 4))
        text = (
            f"ORDER #{oid}\n"
            f"customer: {customer}\n"
            f"priority: {priority}\n"
            f"total_usd: {cents // 100}.{cents % 100:02d}\n"
            f"tags: {', '.join(tags)}\n"
            f"steps: {' > '.join(steps)}\n"
        )
        expected = {"id": oid, "customer": customer, "priority": priority,
                    "total_usd": cents / 100.0, "tags": tags, "steps": steps}
        items = [{"unit": f, "expected": expected[f]} for f in self.FIELDS]
        prompt = ("Extract the order fields below into a JSON object with exactly the "
                  "keys id (int), customer (string), priority (int), total_usd "
                  "(number), tags (array of strings, order-insensitive), steps "
                  "(array of strings, order matters).  Do not add extra keys.\n\n"
                  + text)
        return self.task(f"json_schema_extract-{idx:03d}", prompt, items,
                         {"source": text})

    def canonical(self, task):
        return {it["unit"]: it["expected"] for it in task.items}

    def equivalents(self, task, rng):
        base = self.canonical(task)
        a = dict(base)
        a["tags"] = list(reversed(a["tags"]))
        a["id"] = str(a["id"])
        b = dict(base)
        b["customer"] = f"  {b['customer']}  "
        b["total_usd"] = f"{b['total_usd']:.2f}"
        b["tags"] = list(reversed(b["tags"]))
        return [(a, "tags reordered, id as numeric string"), (b, "padded text, cents spelling, tags reordered")]

    def wrongs(self, task, rng):
        base = dict(self.canonical(task))
        steps = list(base["steps"])
        tags = list(base["tags"])
        return [
            ("boundary", dict(base, total_usd=base["total_usd"] * 100),
             "dollars reported as cents"),
            ("off_by_one", dict(base, priority=base["priority"] + 1), "priority off by one"),
            ("type_mismatch", dict(base, id={"value": base["id"]}), "id wrapped in an object"),
            ("order", dict(base, steps=list(reversed(steps))), "steps reversed (order matters)"),
            ("missing", {k: v for k, v in base.items() if k != "customer"}, "customer field omitted"),
            ("extra", dict(base, notes="see attachments"), "extra top-level key"),
            ("semantic_wrong", dict(base, tags=tags[:-1] + ["damaged"]), "one tag replaced"),
        ]

    def corrupt_item(self, task, item, rng):
        if item["unit"] == "tags":
            return list(item["expected"][:-1]) + ["other"]
        if item["unit"] == "steps":
            return list(reversed(item["expected"]))
        if item["unit"] in ("id", "priority"):
            return int(item["expected"]) + 1
        if item["unit"] == "total_usd":
            return round(float(item["expected"]) + 1, 2)
        return str(item["expected"]) + "?"

    def grade_item(self, task, item, answer):
        field, exp = item["unit"], item["expected"]
        if field in ("id", "priority"):
            v = parse_number(answer)
            good = v is not None and v.denominator == 1 and int(v) == int(exp)
            return self.ok(good, "integer matches", f"expected int {exp}, got {answer!r}")
        if field == "total_usd":
            return self.ok(num_close(exp, answer, rel_tol=1e-9), "amount matches",
                           f"expected {exp}, got {answer!r}")
        if field == "customer":
            s = norm_text(answer)
            return self.ok(s == exp, "string matches", f"expected {exp!r}, got {answer!r}")
        if field == "tags":
            if not isinstance(answer, list) or not all(isinstance(x, str) for x in answer):
                return False, f"expected an array of strings, got {answer!r}"
            if len(set(answer)) != len(answer):
                return False, "duplicate tags are not allowed"
            return self.ok(set(answer) == set(exp), "tag set matches",
                           f"expected {exp}, got {answer!r}")
        if field == "steps":
            if not isinstance(answer, list) or not all(isinstance(x, str) for x in answer):
                return False, f"expected an array of strings, got {answer!r}"
            return self.ok(answer == exp, "ordered steps match",
                           f"expected {exp}, got {answer!r}")
        return False, "unknown field"


class LogFieldExtraction(Family):
    name = "log_field_extraction"
    domain = "log parsing"
    task_shape = "parse 2-3 semi-structured log lines into typed records"
    premise = "explicit timestamp/level/code normalisation rules"
    scoring = "fraction of record fields that match after normalisation"
    item_unit = "one record field"
    payload_kind = "mapping"

    FIELDS = ("ts", "level", "service", "code", "msg")
    SERVICES = ("api", "auth", "billing", "worker", "search")

    def make_one(self, rng, idx):
        n_rec = rng.randint(2, 3)
        items, lines = [], []
        for r in range(1, n_rec + 1):
            day = rng.randint(1, 28)
            hour, minute, sec = rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)
            ts = f"2024-05-{day:02d}T{hour:02d}:{minute:02d}:{sec:02d}Z"
            level = rng.choice(["INFO", "WARN", "ERROR"])
            service = rng.choice(self.SERVICES)
            code = f"{rng.choice('EWID')}{rng.randint(100, 999)}"
            msgs = ["connection reset by peer", "timeout after 5s", "retrying request",
                    "cache miss for key", "quota exceeded", "handler took 320ms"]
            msg = rng.choice(msgs)
            lines.append(f'{ts} level={level} service={service} code={code} msg="{msg}"')
            exp = {"ts": ts, "level": level, "service": service, "code": code, "msg": msg}
            for f in self.FIELDS:
                items.append({"unit": f"L{r}.{f}", "expected": exp[f], "record": r})
        prompt = ("Parse each log line into the fields ts, level, service, code, msg.  "
                  "Return a JSON object keyed by record id \"1\", \"2\", ... whose "
                  "values are objects with exactly those keys.  Timestamps are ISO "
                  "instants, levels are upper-case, services lower-case, codes match "
                  "[A-Z][0-9]{3}, messages are unquoted.\n\n" + "\n".join(lines))
        return self.task(f"log_field_extraction-{idx:03d}", prompt, items,
                         {"lines": lines, "records": n_rec})

    def canonical(self, task):
        return {f"{r}": {f: next(it["expected"] for it in task.items
                                 if it["unit"] == f"L{r}.{f}")
                         for f in self.FIELDS}
                for r in range(1, task.meta["records"] + 1)}

    def extract_answers(self, task, payload):
        if not isinstance(payload, dict):
            return {}, [], f"payload is {type(payload).__name__}, expected an object"
        answers, extras = {}, []
        for r in range(1, task.meta["records"] + 1):
            rec = payload.get(str(r))
            if not isinstance(rec, dict):
                continue
            for f in self.FIELDS:
                if f in rec:
                    answers[f"L{r}.{f}"] = rec[f]
            for k in rec:
                if k not in self.FIELDS:
                    extras.append(f"L{r}.{k}")
        valid_keys = {str(r) for r in range(1, task.meta["records"] + 1)}
        for k in payload:
            if k not in valid_keys:
                extras.append(str(k))
        return answers, extras, None

    def set_units(self, task, payload, replacements):
        import copy
        out = copy.deepcopy(payload)
        for unit, value in replacements.items():
            r, f = unit[1:].split(".", 1)
            out[r][f] = value
        return out

    def equivalents(self, task, rng):
        base = self.canonical(task)
        a = {r: dict(v) for r, v in base.items()}
        b = {r: dict(v) for r, v in base.items()}
        for v in a.values():
            v["ts"] = v["ts"].replace("Z", "+00:00").replace("T", " ")
        for v in b.values():
            v["msg"] = "  " + v["msg"].replace(" ", "  ") + "  "
        return [(a, "offset timestamp spelling"), (b, "message with redundant whitespace")]

    def wrongs(self, task, rng):
        base = self.canonical(task)
        recs = list(base)
        a = {r: dict(v) for r, v in base.items()}
        b = {r: dict(v) for r, v in base.items()}
        c = {r: dict(v) for r, v in base.items()}
        d = {r: dict(v) for r, v in base.items()}
        e = {r: dict(v) for r, v in base.items()}
        f = {r: dict(v) for r, v in base.items()}
        g = {r: dict(v) for r, v in base.items()}
        # boundary: numeric carry on the first code
        code = a[recs[0]]["code"]
        a[recs[0]]["code"] = code[0] + f"{max(0, int(code[1:]) - 3):03d}"
        # off by one on the second record's code
        code2 = b[recs[-1]]["code"]
        b[recs[-1]]["code"] = code2[0] + f"{int(code2[1:]) + 1:03d}"
        c[recs[0]]["msg"] = [c[recs[0]]["msg"]]
        d[recs[0]], d[recs[-1]] = d[recs[-1]], d[recs[0]]
        del e[recs[-1]]["msg"]
        for v in f.values():
            v["user"] = "u-42"
        g[recs[0]]["level"] = "DEBUG"
        return [("boundary", a, "code crosses a numeric boundary"),
                ("off_by_one", b, "code off by one"),
                ("type_mismatch", c, "message as an array"),
                ("order", d, "records swapped"),
                ("missing", e, "message field omitted"),
                ("extra", f, "extra key in every record"),
                ("semantic_wrong", g, "level label altered")]

    def corrupt_item(self, task, item, rng):
        return item["expected"] + "!"

    def grade_item(self, task, item, answer):
        field, exp = item["unit"].split(".", 1)[1], item["expected"]
        if field == "ts":
            s = _norm_ts(answer)
            return self.ok(s == exp, "timestamp matches", f"expected {exp}, got {answer!r}")
        if field in ("level", "service", "code"):
            s = norm_text(answer)
            if s is None:
                return False, f"expected a string, got {answer!r}"
            if field == "level":
                s = s.upper()
            elif field == "service":
                s = s.lower()
            else:
                s = s.upper()
            return self.ok(s == exp, f"{field} matches", f"expected {exp}, got {answer!r}")
        if field == "msg":
            s = norm_text(answer, collapse_ws=True)
            if s is not None and s.startswith('"') and s.endswith('"') and len(s) >= 2:
                s = s[1:-1].strip()
            return self.ok(s == exp, "message matches", f"expected {exp!r}, got {answer!r}")
        return False, "unknown field"


class _Spec:
    __slots__ = ("kind", "rule", "pos", "neg", "pattern", "loose", "tight",
                 "held_pos", "held_neg")

    def __init__(self, kind, rule, pos, neg, pattern, loose, tight,
                 held_pos=(), held_neg=()):
        self.kind, self.rule, self.pos, self.neg = kind, rule, pos, neg
        self.pattern, self.loose, self.tight = pattern, loose, tight
        # Held-out strings: never shown in the prompt, never read by the probe
        # builder.  A pattern that enumerates the labelled examples fails here;
        # a pattern that encodes the stated rule passes.
        self.held_pos, self.held_neg = list(held_pos), list(held_neg)


def _regex_specs(rng) -> List[_Spec]:
    hexp = [f"#{rng.randint(0, 255):02x}{rng.randint(0, 255):02x}{rng.randint(0, 255):02x}"
            for _ in range(3)]
    hexq = [f"#{rng.randint(0, 255):02X}{rng.randint(0, 255):02X}{rng.randint(0, 255):02X}"
            for _ in range(1)]
    hexn = ["abc123", "#abc", "#abcdef0", "#12345g"]
    ip = [f"{rng.randint(1, 254)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
          for _ in range(3)]
    ipn = ["192.168.1", "192.168.1.10.1", "192-168-1-10", "1.2.3"]
    ids = [f"{rng.choice('abcdefgh')}{rng.choice(['x_1', 'tag9', 'item_2', 'main7'])}"
           for _ in range(3)]
    idn = ["1abc", "ab", "ABC_DEF", "a-b"]
    dates = [f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}" for _ in range(3)]
    daten = ["2024-2-29", "2024/02/29", "24-02-29", "2024-02-29x"]
    files = ["main.py", "my_script.py", "lib-2.py"]
    filen = ["main.pyc", "main.PY", "x", "main.py.bak"]
    bytepairs = ["0a 1b 2c", "ff 00 7e", "aa bb"]
    byten = ["0a1b", "0a 1b 2", "0a 1b 2c 3", "zz 00"]
    specs = [
        _Spec("hex_color", "exactly #RRGGBB with six hex digits",
              hexp + hexq, hexn, r"^#[0-9a-fA-F]{6}$",
              r"^#?[0-9a-fA-F]{1,8}$", r"^#[0-9a-f]{6}$",
              held_pos=["#4B2E11", "#aBcDeF"], held_neg=["#4B2E1", "#4B2E1Z"]),
        _Spec("ipv4_shape", "four dot-separated groups of 1-3 digits",
              ip, ipn, r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$",
              r"^\d{1,3}(?:\.\d{1,3}){2,4}$", r"^\d{1,3}\.\d{1,3}\.\d{1,3}$",
              held_pos=["7.7.7.7", "123.45.6.78"], held_neg=["7.7.7", "7.7.7.7.7"]),
        _Spec("identifier", "starts with a lower-case letter, then 3-16 chars of [a-z0-9_]",
              ids, idn, r"^[a-z][a-z0-9_]{3,16}$",
              r"^[a-z0-9_]+$", r"^[a-z][a-z0-9_]{4,16}$",
              held_pos=["zz_001", "item_x7"], held_neg=["ZZ_001", "a_b"]),
        _Spec("iso_date_shape", "four-digit year, two-digit month and day, dash separated",
              dates, daten, r"^\d{4}-\d{2}-\d{2}$",
              r"^\d{4}-\d{1,2}-\d{1,2}$", r"^\d{2}-\d{2}-\d{2}$",
              held_pos=["2001-02-03", "2030-12-31"], held_neg=["2001-2-3", "20010203"]),
        _Spec("python_file", "ends in .py, base name from [A-Za-z0-9_.-]",
              files, filen, r"^[A-Za-z0-9_.-]+\.py$",
              r"^[A-Za-z0-9_.-]+\.py\.bak$", r"^[A-Za-z0-9_-]{1,2}\.py$",
              held_pos=["notes.py", "draft-v3.py"], held_neg=["notes.pyc", "notes.PY"]),
        _Spec("hex_bytes", "space-separated pairs of lower-case hex digits",
              bytepairs, byten, r"^[0-9a-f]{2}(?: [0-9a-f]{2})*$",
              r"^[0-9a-f]{2}.*$", r"^[0-9a-f]{2}(?: [0-9a-f]{2}){3,}$",
              held_pos=["01 02 03", "ab cd"], held_neg=["01 02 0", "AB CD"]),
    ]
    # The canonical rule must itself classify the held-out set correctly; a
    # held-out string that the reference pattern cannot handle would make every
    # candidate wrong for a reason unrelated to overfitting.
    for sp in specs:
        for s in sp.held_pos:
            assert re.fullmatch(sp.pattern, s) is not None, (sp.kind, s)
        for s in sp.held_neg:
            assert re.fullmatch(sp.pattern, s) is None, (sp.kind, s)
    return specs


class RegexConstruct(Family):
    name = "regex_construct"
    domain = "text processing"
    task_shape = "write K regular expressions, each labelled with positive/negative examples"
    premise = "executable pattern semantics against a labelled string set, including held-out probes"
    scoring = "fraction of specifications that classify every labelled string correctly"
    item_unit = "one regex specification"
    payload_kind = "list"

    def make_one(self, rng, idx):
        specs = _regex_specs(rng)
        k = rng.randint(3, 5)
        chosen = rng.sample(specs, k)
        items, lines = [], []
        for j, sp in enumerate(chosen, 1):
            items.append({"unit": f"r{j}", "expected": sp.pattern})
            lines.append(f"  {j}. {sp.rule}\n     match:     " +
                         " | ".join(sp.pos) + "\n     must not:  " +
                         " | ".join(sp.neg))
        prompt = ("For each specification write a regular expression that fully matches "
                  "every 'match' string and none of the 'must not' strings.  Patterns "
                  "are applied with full-string matching semantics (equivalent to "
                  "re.fullmatch).  Answer with one pattern per line.\n" + "\n".join(lines))
        meta = {"specs": [{"kind": sp.kind, "pos": sp.pos, "neg": sp.neg,
                           "loose": sp.loose, "tight": sp.tight,
                           "held_pos": sp.held_pos, "held_neg": sp.held_neg}
                          for sp in chosen]}
        return self.task(f"regex_construct-{idx:03d}", prompt, items, meta)

    def canonical(self, task):
        return [it["expected"] for it in task.items]

    def equivalents(self, task, rng):
        def variant(p):
            if r"\d" in p:
                return p.replace(r"\d", "[0-9]")
            if "[0-9a-f]" in p:
                return p.replace("[0-9a-f]", "[a-f0-9]")
            if "[0-9a-fA-F]" in p:
                return p.replace("[0-9a-fA-F]", "[a-fA-F0-9]")
            return f"(?:{p})"
        alt = [f"(?:{it['expected']})" for it in task.items]
        alt2 = [variant(it["expected"]) for it in task.items]
        return [(alt, "non-capturing group wrapper"), (alt2, "character-class spelling")]

    def wrongs(self, task, rng):
        specs = task.meta["specs"]
        loose = [sp["loose"] for sp in specs]
        tight = [sp["tight"] for sp in specs]
        base = [it["expected"] for it in task.items]
        return [
            ("boundary", loose, "quantifiers widened at the boundary (matches a negative)"),
            ("off_by_one", tight, "quantifier range narrowed (rejects a positive)"),
            ("type_mismatch", [None] + base[1:], "null pattern"),
            ("order", list(reversed(base)), "patterns reversed"),
            ("missing", base[:-1], "last pattern omitted"),
            ("extra", base + [r".*"], "extra permissive pattern"),
            ("semantic_wrong", [base[-1]] + base[1:], "first pattern replaced by another specification's pattern"),
        ]

    def corrupt_item(self, task, item, rng):
        return task.meta["specs"][0]["loose"]

    def grade_item(self, task, item, answer):
        if not isinstance(answer, str):
            return False, f"expected a pattern string, got {type(answer).__name__}"
        sp = next(s for s, it in zip(task.meta["specs"], task.items) if it["unit"] == item["unit"])
        try:
            compiled = re.compile(answer)
        except re.error as ex:
            return False, f"pattern does not compile: {ex}"
        bad = []
        for s in sp["pos"]:
            if not _guarded_fullmatch(compiled, s):
                bad.append(f"rejects {s!r}")
        for s in sp["neg"]:
            if _guarded_fullmatch(compiled, s):
                bad.append(f"accepts {s!r}")
        # Held-out strings: a pattern that merely enumerates the labelled
        # examples with ``|`` passes the loops above yet fails here.
        for s in sp.get("held_pos", ()):
            if not _guarded_fullmatch(compiled, s):
                bad.append(f"rejects held-out {s!r}")
        for s in sp.get("held_neg", ()):
            if _guarded_fullmatch(compiled, s):
                bad.append(f"accepts held-out {s!r}")
        return (not bad), ("all labelled and held-out strings classified correctly"
                           if not bad else "; ".join(bad[:3]))


def _guarded_fullmatch(compiled, s: str) -> bool:
    """Fullmatch with a 50 ms alarm so a pathological pattern cannot hang the audit."""
    import signal

    def _boom(signum, frame):
        raise TimeoutError("regex timeout")

    old = signal.signal(signal.SIGALRM, _boom)
    signal.setitimer(signal.ITIMER_REAL, 0.05)
    try:
        return compiled.fullmatch(s) is not None
    except TimeoutError:
        return False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


class TemplateRender(Family):
    name = "template_render"
    domain = "text rendering"
    task_shape = "render a K-line template with formatting and escaping rules"
    premise = "closed placeholder alphabet with explicit filters"
    scoring = "fraction of rendered lines that match exactly"
    item_unit = "one rendered line"
    payload_kind = "list"

    def make_one(self, rng, idx):
        name = rng.choice(["Ada", "Grace", "Alan", "Katherine", "Linus"])
        amount = rng.randint(100, 99999) / 100.0
        note = rng.choice(['<b>fast & "safe"</b>', 'say "hi" & <ok>', 'a > b & "c"'])
        code = f"{rng.choice('ABC')}-{rng.randint(100, 999)}"
        data = {"name": name, "amount": amount, "note": note, "code": code}
        lines_spec = [
            ("NAME", "name", "upper"),
            ("TOTAL", "amount", "money"),
            ("NOTE", "note", "html"),
            ("CODE", "code", "raw"),
            ("STATUS", "missing_key", "default:UNKNOWN"),
        ]
        expected = [self._render(f"{{v:{f}}}", data, v, f) for _, v, f in lines_spec]
        items = [{"unit": f"s{i + 1}", "expected": line} for i, line in enumerate(expected)]
        prompt = ("Render each template line.  Filters: upper = upper-case, money = "
                  "two decimals with thousands separators, html = escape &, <, >, \" and ', "
                  "raw = unchanged, default:X = X when the key is absent.  Return the "
                  "rendered lines as a JSON array of strings.\n" +
                  "\n".join(f"  {label}: {{v:{f}}}" for label, v, f in lines_spec)
                  + "\n  data = " + repr(data))
        return self.task(f"template_render-{idx:03d}", prompt, items,
                         {"data": data, "spec": lines_spec[0][0]})

    def _render(self, template, data, key, filt):
        if filt.startswith("default:"):
            value = data.get(key, filt.split(":", 1)[1])
            return template.replace("{v:" + filt + "}", str(value))
        raw = data[key]
        if filt == "upper":
            s = str(raw).upper()
        elif filt == "money":
            s = f"{float(raw):,.2f}"
        elif filt == "html":
            s = html.escape(str(raw), quote=True)
        else:
            s = str(raw)
        return template.replace("{v:" + filt + "}", s)

    def canonical(self, task):
        return [it["expected"] for it in task.items]

    def equivalents(self, task, rng):
        a = [line + "   " for line in self.canonical(task)]
        b = ["\t" + line + " " for line in self.canonical(task)]
        return [(a, "trailing whitespace"), (b, "leading tab and trailing space")]

    def wrongs(self, task, rng):
        base = self.canonical(task)
        bad_escape = [html.escape(x, quote=False) for x in base]
        cents = base[:]
        cents[1] = cents[1].replace(".", "")
        return [
            ("boundary", bad_escape, "quotes not escaped at the boundary"),
            ("off_by_one", cents, "decimal point lost in the money line"),
            ("type_mismatch", [None] + base[1:], "null line"),
            ("order", list(reversed(base)), "lines reversed"),
            ("missing", base[:-1], "last line omitted"),
            ("extra", base + [""], "extra blank line"),
            ("semantic_wrong", [base[0].lower()] + base[1:], "upper-case filter not applied"),
        ]

    def corrupt_item(self, task, item, rng):
        exp = item["expected"]
        cand = exp[::-1]
        if cand == exp:  # palindromes would make a partial look fully correct
            cand = exp[:-1] + ("X" if exp[-1:] != "X" else "Y")
        return cand

    def grade_item(self, task, item, answer):
        s = norm_text(answer)
        if s is None:
            return False, f"expected a string, got {answer!r}"
        exp = item["expected"].rstrip()
        return self.ok(s.rstrip() == exp, "line matches", f"expected {exp!r}, got {answer!r}")
