"""Controlled, labeled counterfactual errors in archived natural-language rule clauses."""

from collections import defaultdict
from decimal import Decimal
import re

from common import div, read, write

NUMBER = r"(-?\d+(?:\.\d+)?)"
CMP = re.compile(
    r"\b(strictly greater than|greater than|no less than|at least|more than|above|at most|below)\s+"
    + NUMBER
    + r"(?![\d.])",
    re.I,
)
OPS = {
    "strictly greater than": ">",
    "greater than": ">",
    "more than": ">",
    "above": ">",
    "no less than": ">=",
    "at least": ">=",
    "at most": "<=",
    "below": "<",
}


def adjudicate(text, quote, op, number):
    literal = bool(quote) and quote in text
    match = CMP.fullmatch(quote)
    predicate = (
        literal
        and bool(match)
        and OPS[match[1].lower()] == op
        and Decimal(match[2]) == Decimal(number)
    )
    paid_yes = bool(re.search(r"\bthen the market resolves to Yes\.", text))
    semantic = predicate and paid_yes
    scope = semantic and not any(
        s in text.casefold()
        for s in ("it is false that", "except", "nonbinary", "0.5 instead")
    )
    return dict(literal=literal, predicate_and_payout=semantic, with_scope_guards=scope)


def variants(r):
    primary = r["primary_evidence"]
    op = r["operator"]
    quote = r["operator_evidence"] + " " + r["threshold_lexical"]
    t = r["threshold_lexical"]
    swapped_op = ">=" if op == ">" else ">"
    paraphrase = ("strictly greater than" if op == ">" else "no less than") + " " + t
    reverse = ("at most" if op == ">" else "below") + " " + t
    assert (
        quote in primary
        and "then the market resolves to Yes." in primary
        and primary.startswith("If ")
    )
    return [
        ("original", True, primary, quote, op, t),
        (
            "valid_paraphrase",
            True,
            primary.replace(quote, paraphrase, 1),
            paraphrase,
            op,
            t,
        ),
        ("wrong_operator", False, primary, quote, swapped_op, t),
        ("wrong_value", False, primary, quote, op, str(Decimal(t) + Decimal(".1"))),
        ("fabricated_evidence", False, primary, "published exactly as " + quote, op, t),
        (
            "irrelevant_literal",
            False,
            primary,
            "then the market resolves to Yes",
            op,
            t,
        ),
        (
            "payout_no",
            False,
            primary.replace(
                "then the market resolves to Yes.", "then the market resolves to No."
            ),
            quote,
            op,
            t,
        ),
        (
            "negated_antecedent",
            False,
            "If it is false that " + primary[3:],
            quote,
            op,
            t,
        ),
        ("source_reversed", False, primary.replace(quote, reverse, 1), reverse, op, t),
        (
            "payout_exception",
            False,
            primary
            + " Exception: if there is a correction, this contract pays 0.5 instead.",
            quote,
            op,
            t,
        ),
    ]


def mutation_audit():
    extractions = {
        r["id"]: r for r in read("extension/retrieval/results/extractions.json")
    }
    selected = defaultdict(set)
    for r in read("extension/nlp/conditional_consistency.json")["records"]:
        selected[r["template_group"]].update([r["a"], r["b"]])
    records = []
    for family, ids in sorted(selected.items()):
        market = min(ids)
        series = market.split("-")[0]
        split = "development" if series in ("KXCPI", "KXPALLADIUMH") else "transfer"
        for name, truth, source, quote, op, t in variants(extractions[market]):
            accepted = adjudicate(source, quote, op, t)
            records.append(
                dict(
                    market=market,
                    family=family,
                    series=series,
                    split=split,
                    variant=name,
                    valid=truth,
                    source_primary=source,
                    quote=quote,
                    proposed_op=op,
                    proposed_threshold=t,
                    accepted=accepted,
                )
            )
    out = {}
    for split in ("all", "development", "transfer"):
        rows = [r for r in records if split == "all" or r["split"] == split]
        out[split] = dict(
            groups=len({r["family"] for r in rows}),
            series=len({r["series"] for r in rows}),
            n=len(rows),
            methods={},
        )
        for m in records[0]["accepted"]:
            valid = [r for r in rows if r["valid"]]
            invalid = [r for r in rows if not r["valid"]]
            yes = sum(r["accepted"][m] for r in valid)
            bad = sum(r["accepted"][m] for r in invalid)
            out[split]["methods"][m] = dict(
                valid=len(valid),
                invalid=len(invalid),
                accepted_valid=yes,
                accepted_invalid=bad,
                valid_acceptance=div(yes, len(valid)),
                invalid_acceptance=div(bad, len(invalid)),
            )
    write("mutation_cases.jsonl", records, lines=True)
    return out
