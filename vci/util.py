"""Small, dependency-free helpers used by the verifiers."""
import json
import math
import unicodedata
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Optional


def parse_number(value: Any) -> Optional[Fraction]:
    """Parse an answer into an exact rational, or return ``None``.

    Semantically equivalent spellings are accepted on purpose: ``3``, ``3.0``,
    ``"3"``, ``"3,000"`` and ``"7/2"``.  Booleans are rejected even though
    ``bool`` is an ``int`` subclass in Python, which is a classic silent
    false-accept source.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return Fraction(Decimal(repr(value)))
    if isinstance(value, Decimal):
        return Fraction(value)
    if isinstance(value, Fraction):
        return value
    if isinstance(value, str):
        s = unicodedata.normalize("NFKC", value).strip()
        s = s.replace("\u2212", "-")
        if not s:
            return None
        s = s.replace(",", "").replace("_", "").replace(" ", "")
        # Reject strings with residual units/words.
        try:
            return Fraction(s)
        except (ValueError, ZeroDivisionError):
            pass
        try:
            return Fraction(Decimal(s))
        except (InvalidOperation, ValueError):
            return None
    return None


def num_close(expected: Any, answer: Any, rel_tol: float = 1e-9, abs_tol: float = 0.0) -> bool:
    """Exact comparison when possible, relative tolerance otherwise."""
    exp = expected if isinstance(expected, Fraction) else parse_number(expected)
    got = parse_number(answer)
    if exp is None or got is None:
        return False
    if exp == got:
        return True
    if exp == 0:
        return abs(got) <= abs_tol
    return abs(got - exp) <= abs(exp) * rel_tol + abs_tol


def norm_text(value: Any, collapse_ws: bool = False) -> Optional[str]:
    """NFC-normalised, trimmed text.  Optionally collapse internal whitespace."""
    if isinstance(value, bool) or not isinstance(value, str):
        return None
    s = unicodedata.normalize("NFC", value).strip()
    if collapse_ws:
        s = " ".join(s.split())
    return s


def norm_iso_date(value: Any) -> Optional[str]:
    """Accept ``YYYY-MM-DD`` and midnight-datetime spellings."""
    s = norm_text(value)
    if s is None:
        return None
    s = s.replace("/", "-")
    if "T" in s:
        head, _, tail = s.partition("T")
        if head.count("-") == 2 and len(head) == 10:
            return head
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    return None


def stable_dumps(obj: Any) -> str:
    """Deterministic JSON used for hashing and for the annotation sheet."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def pct(values, q):
    """Simple percentile without numpy."""
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(xs[lo])
    return float(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo))
