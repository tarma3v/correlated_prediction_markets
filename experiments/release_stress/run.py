"""Enumerate joint releases for the two CPI payout mappings using integer tenths."""
import csv
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "market_audit/november_cross_venue.csv"


def tenth(number):
    value = Decimal(number) * 10
    if value != value.to_integral_value():
        raise ValueError(f"Not on the release grid: {number}")
    return int(value)


def bucket_definition(label):
    match = re.fullmatch(r"(≤)?([0-9.]+)%(\+)?", label)
    if not match or (match[1] and match[3]):
        raise ValueError(f"Unknown bucket {label}")
    threshold = tenth(match[2])
    if match[1]:
        return threshold, lambda x: x <= threshold
    if match[3]:
        return threshold, lambda x: x >= threshold
    return threshold, lambda x: x == threshold


def stress(row, gap):
    boundary, belongs = bucket_definition(row["label"])
    terms = []
    for token in row["kalshi_terms"].split():
        item = re.fullmatch(r"([+-]\d+)\*T(-?[\d.]+)", token)
        if item is None:
            raise ValueError(f"Unknown leg {token}")
        terms.append((int(item[1]), tenth(item[2])))
    constant = int(row["constant"])
    limits = [boundary] + [t for _, t in terms]
    witnesses = {}
    for a in range(min(limits) - gap - 1, max(limits) + gap + 2):
        for b in range(a - gap, a + gap + 1):
            bucket = int(belongs(a))
            replica = constant + sum(w * (b > t) for w, t in terms)
            difference = replica - bucket
            witnesses.setdefault(difference, dict(poly_tenths=a, kalshi_tenths=b,
                                                  poly_payout=bucket, replica_payout=replica))
    low, high = min(witnesses), max(witnesses)
    return dict(mapping=row["rule"], bucket=row["label"], max_gap_tenths=gap,
                min_difference=low, max_difference=high,
                at_min=witnesses[low], at_max=witnesses[high])


def main():
    with SOURCE.open() as f:
        rows = list(csv.DictReader(f))
    mappings = {r["rule"] for r in rows}
    if mappings != {"same_number", "ordinary_release"} or len({(r["rule"], r["label"]) for r in rows}) != 14 or len(rows) != 14:
        raise ValueError("Expected two mappings for seven distinct November buckets")
    results = [stress(row, gap) for gap in (0, 1, 2) for row in rows]
    counts = []
    for gap in (0, 1, 2):
        for mapping in sorted(mappings):
            group = [r for r in results if (r["max_gap_tenths"], r["mapping"]) == (gap, mapping)]
            counts.append(dict(mapping=mapping, max_gap_tenths=gap, buckets=len(group),
                               identical=sum(r["min_difference"] == r["max_difference"] == 0 for r in group),
                               replica_can_underpay=sum(r["min_difference"] < 0 for r in group),
                               replica_can_overpay=sum(r["max_difference"] > 0 for r in group)))
    output = dict(source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  difference="replica payout minus Polymarket payout per unit", summary=counts, cases=results)
    (HERE / "results.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    for count in counts:
        print(count)


if __name__ == "__main__":
    main()
