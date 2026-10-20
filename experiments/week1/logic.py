"""Reference logic for controlled unary-comparison contracts.

This module certifies only the supplied mathematical model. It does not certify
real market rules, source equivalence, or settlement procedures. No gold labels
are read. Thresholds are finite Decimal values and the domain is the real line.
"""
from decimal import Context, Decimal, InvalidOperation, MAX_EMAX, MIN_EMIN, Overflow, localcontext
from itertools import product
import re


CONTEXT_FIELDS = ("metric", "source", "period", "unit")
STATES = ("00", "01", "10", "11")
_OPS = {
    "gt": lambda x, t: x > t,
    "ge": lambda x, t: x >= t,
    "lt": lambda x, t: x < t,
    "le": lambda x, t: x <= t,
}
_PHRASES = {
    "more than": "gt",
    "at least": "ge",
    "less than": "lt",
    "at most": "le",
}
_NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_NUMBER_RE = re.compile(_NUMBER)
_TEXT_RE = re.compile(
    r"Metric: (?P<metric>[^\r\n]+)\n"
    r"Source: (?P<source>[^\r\n]+)\n"
    r"Period: (?P<period>[^\r\n]+)\n"
    r"Unit: (?P<unit>[^\r\n]+)\n"
    r"(?P<predicate_quote>YES iff the observed value is "
    r"(?P<phrase>more than|at least|less than|at most) "
    r"(?P<threshold>" + _NUMBER + r")\.)\n"
    r"Settlement: binary; no exceptions\.\n?"
)


def _finite_decimal(value):
    """Parse decimal notation; finite floats use their shortest str form.

    Decimal/string inputs are preferred when precision must survive JSON input.
    A float cannot recover digits already lost by the caller's float conversion.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("threshold must be a finite decimal number")
    text = str(value)
    if _NUMBER_RE.fullmatch(text) is None:
        raise ValueError("invalid decimal threshold")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError("invalid decimal threshold") from exc
    if not number.is_finite():
        raise ValueError("threshold must be finite")
    return number


def _validate(contract):
    if not isinstance(contract, dict):
        raise ValueError("contract must be a dictionary")
    for field in CONTEXT_FIELDS:
        if not isinstance(contract.get(field), str) or not contract[field].strip():
            raise ValueError("missing or invalid context field: " + field)
    op = contract.get("op")
    if not isinstance(op, str) or op not in _OPS:
        raise ValueError("op must be one of gt, ge, lt, le")
    return op, _finite_decimal(contract.get("threshold"))


def _representatives(thresholds):
    """Cover each boundary and every open cell of the real-line partition.

    Predicate truth is constant on each open cell. Simple exterior tail values
    are preferred; Decimal neighbors cover extreme finite values if doubling
    overflows. Midpoints are checked strictly interior even if arithmetic rounds.
    """
    bounds = sorted(set(thresholds))
    precision = max(80, max(len(x.as_tuple().digits) for x in bounds) + 16)
    with localcontext(Context(prec=precision, Emax=MAX_EMAX, Emin=MIN_EMIN)) as ctx:
        try:
            below = bounds[0] * 2 if bounds[0] < 0 else Decimal(-1)
        except Overflow:
            below = bounds[0].next_minus(context=ctx)
        try:
            above = bounds[-1] * 2 if bounds[-1] > 0 else Decimal(1)
        except Overflow:
            above = bounds[-1].next_plus(context=ctx)
        if not below.is_finite() or not above.is_finite():
            raise ValueError("threshold exceeds supported Decimal witness range")
        if not below < bounds[0] or not above > bounds[-1]:
            raise ValueError("cannot construct finite tail witnesses")
        values = [below]
        for i, bound in enumerate(bounds):
            values.append(bound)
            if i + 1 < len(bounds):
                upper = bounds[i + 1]
                # Halve first to avoid overflowing an otherwise finite mean.
                middle = bound / 2 + upper / 2
                if not middle.is_finite() or not bound < middle < upper:
                    raise ValueError("cannot construct an interior Decimal witness")
                values.append(middle)
        values.append(above)
    return values


def possible_states(a, b):
    """Return possible binary states with JSON-safe decimal witnesses.

    Inputs contain metric, source, period, unit, op and threshold. If the four
    context fields are exactly equal, both predicates share one real variable.
    Otherwise their variables are stipulated to be freely independent, which is
    a controlled-model assumption, not an empirical claim about real sources.

    Returns e.g. {"00": {"x_a": "0", "x_b": "0"}, ...}. A missing state is
    impossible in this model. Invalid inputs raise ValueError. Additional input
    keys, such as predicate_quote, are ignored.
    """
    op_a, threshold_a = _validate(a)
    op_b, threshold_b = _validate(b)
    shared = all(a[field] == b[field] for field in CONTEXT_FIELDS)
    if shared:
        pairs = ((x, x) for x in _representatives([threshold_a, threshold_b]))
    else:
        pairs = product(_representatives([threshold_a]),
                        _representatives([threshold_b]))
    witnesses = {}
    for x_a, x_b in pairs:
        state = ("1" if _OPS[op_a](x_a, threshold_a) else "0")
        state += "1" if _OPS[op_b](x_b, threshold_b) else "0"
        if state not in witnesses:
            witnesses[state] = {"x_a": str(x_a), "x_b": str(x_b)}
    return {state: witnesses[state] for state in STATES if state in witnesses}


def label_from_forbidden(forbidden):
    """Map an exact set of forbidden states to the requested coarse label.

    Implication labels do not assert strict subset. Unsupported combinations,
    malformed inputs, and the inconsistent all-forbidden set return unsupported.
    """
    if forbidden is None or isinstance(forbidden, (str, bytes)):
        return "unsupported"
    try:
        states = frozenset(forbidden)
    except TypeError:
        return "unsupported"
    labels = {
        frozenset(): "no_hard_relation",
        frozenset({"01", "10"}): "equivalent",
        frozenset({"10"}): "a_implies_b",
        frozenset({"01"}): "b_implies_a",
        frozenset({"11"}): "disjoint",
        frozenset({"00"}): "exhaustive",
        frozenset({"00", "11"}): "complement",
    }
    return labels.get(states, "unsupported")


def extract_contract(text):
    """Parse the entire fixed six-line controlled template, or return None.

    One final newline is accepted. No other surrounding text, missing lines,
    alternative settlements, whitespace normalization or inferred fields are
    accepted. predicate_quote is an exact substring of the supplied text.
    """
    if not isinstance(text, str):
        return None
    match = _TEXT_RE.fullmatch(text)
    if match is None:
        return None
    fields = {field: match.group(field) for field in CONTEXT_FIELDS}
    if any(not value or value != value.strip()
           or any(ord(char) < 32 or ord(char) == 127 for char in value)
           for value in fields.values()):
        return None
    try:
        _finite_decimal(match.group("threshold"))
    except ValueError:
        return None
    fields.update(op=_PHRASES[match.group("phrase")],
                  threshold=match.group("threshold"),
                  predicate_quote=match.group("predicate_quote"))
    return fields
