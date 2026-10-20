"""Freeze transparent development inputs; no network, prices or model calls."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATES = ("00", "01", "10", "11")
WORDS = {"gt": "more than", "ge": "at least", "lt": "less than", "le": "at most"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def make_contract(domain, op, threshold, period="2030-01", missing=False, nonbinary=False):
    metric, source, unit = domain
    lines = [f"Metric: {metric}", f"Source: {source}", f"Period: {period}",
             f"Unit: {unit}",
             f"YES iff the observed value is {WORDS[op]} {threshold}.",
             "Settlement: binary; no exceptions."]
    if missing:
        lines.pop(1)
    if nonbinary:
        lines[-1] = "Settlement: if the source fails, the payout is 0.5; otherwise binary."
    return "\n".join(lines)


def build():
    # Expected forbidden sets are declared manually, independently of logic.py.
    # They are not labels inferred from an LLM or a real market's name.
    patterns = [
        ("equivalent", "gt", "1", "gt", "1", "2030-01", ["01", "10"]),
        ("nested", "gt", "2", "gt", "1", "2030-01", ["10"]),
        ("reverse_nested", "gt", "1", "gt", "2", "2030-01", ["01"]),
        ("complement", "gt", "1", "le", "1", "2030-01", ["00", "11"]),
        ("gap", "lt", "1", "gt", "2", "2030-01", ["11"]),
        ("inclusive_boundary", "ge", "1", "le", "1", "2030-01", ["00"]),
        ("different_period", "gt", "1", "gt", "1", "2030-02", []),
        ("strict_boundary", "gt", "1", "ge", "1", "2030-01", ["10"]),
    ]
    domains = [("Index Alpha", "Bulletin Alpha", "percent"),
               ("Metal Beta close", "Exchange Beta", "USD")]
    items = []
    for domain in domains:
        for pattern, oa, ta, ob, tb, period, forbidden in patterns:
            packet = {"scope": "CONTROLLED SCALAR; artificial contract clauses, not venue data",
                      "A": {"text": make_contract(domain, oa, ta)},
                      "B": {"text": make_contract(domain, ob, tb, period)}}
            reference = {"kind": "controlled_decidable", "family": domain[0], "pattern": pattern,
                         "states": {s: "forbidden" if s in forbidden else "possible" for s in STATES}}
            items.append((packet, reference))
        for problem in ("missing_source", "nonbinary"):
            packet = {"scope": "CONTROLLED SCALAR; artificial contract clauses, not venue data",
                      "A": {"text": make_contract(domain, "gt", "2")},
                      "B": {"text": make_contract(domain, "gt", "1",
                              missing=problem == "missing_source", nonbinary=problem == "nonbinary")}}
            items.append((packet, {"kind": "controlled_scope_guard", "family": domain[0],
                                   "pattern": problem, "states": {s: "unknown" for s in STATES}}))

    sources = ["redesign/discovery/official_probe/pairs_blind.jsonl",
               "redesign/cards/political_inputs.json"]
    real = [json.loads(line) for line in (ROOT / sources[0]).read_text().splitlines()]
    # Fixed source order is part of the frozen development selection.
    selected = [real[0], real[1]]
    for row in selected:
        def text(side):
            r = row[side]
            return "\n\n".join(str(r[k]) for k in ("title", "primary", "secondary") if r.get(k))
        packet = {"scope": "REAL SNAPSHOT FRAGMENTS; complete applicable contract rules are not verified",
                  "A": {"text": text("a")}, "B": {"text": text("b")}}
        items.append((packet, {"kind": "real_unlabeled", "family": "macro", "pattern": row["case_id"],
                               "states": None, "source": sources[0]}))
    political = json.loads((ROOT / sources[1]).read_text())
    for a, b in [("out", "kalshi_out"), ("resign", "out")]:
        packet = {"scope": "REAL SNAPSHOT FRAGMENTS; complete applicable contract rules are not verified",
                  "A": {"text": political[a]}, "B": {"text": political[b]}}
        items.append((packet, {"kind": "real_unlabeled", "family": "politics", "pattern": a + "__" + b,
                               "states": None, "source": sources[1]}))
    random.Random(20261021).shuffle(items)
    packets, references = [], []
    for i, (packet, ref) in enumerate(items, 1):
        case_id = f"pair_{i:03d}"
        payload = json.dumps(packet, ensure_ascii=False, sort_keys=True)
        packets.append({"case_id": case_id, "packet": packet,
                        "packet_sha256": hashlib.sha256(payload.encode()).hexdigest()})
        references.append({"case_id": case_id, **ref})
    return packets, references, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare rebuilt inputs to frozen files")
    args = parser.parse_args()
    packets, refs, sources = build()
    data = HERE / "data"
    for name, value in [("packets.json", packets), ("reference.json", refs)]:
        if args.check:
            assert json.loads((data / name).read_text()) == value, name + " changed"
        else:
            dump(data / name, value)
    manifest = {"experiment": "E01", "seed": 20261021, "cases": len(packets),
                "controlled_decidable": 16, "controlled_scope_guard": 4, "real_unlabeled": 4,
                "source_sha256": {p: sha(ROOT / p) for p in sources},
                "inputs_sha256": {str(p.relative_to(HERE)): sha(p) for p in
                                  [data / "packets.json", data / "reference.json", HERE / "config.json"]},
                "prompt_sha256": {str(p.relative_to(HERE)): sha(p) for p in sorted((HERE / "prompts").glob("*.txt"))},
                "reference_origin": "Explicit analyst-declared truth sets for artificial unbounded real scalars; not human market gold.",
                "source_scope": "Existing frozen development sources; no current venue freshness claim.",
                "split": "development_only; no train/test split or significance claims"}
    if args.check:
        assert json.loads((data / "manifest.json").read_text()) == manifest, "Manifest changed"
    else:
        dump(data / "manifest.json", manifest)
    print("Verified" if args.check else "Prepared", len(packets), "development pairs")


if __name__ == "__main__":
    main()
