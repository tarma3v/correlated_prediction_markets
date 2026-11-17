"""Development annotation preparation; no model inference or human-gold claims.

E02 deliberately does not import or modify E01's frozen evaluator. Status
``possible_with_witness`` is a declaration by a reviewer/model, not a proof
checked by this module. Source completeness and annotation independence require
human review. All counters use case/state units, not independent sample sizes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

STATES = ("00", "01", "10", "11")
STATUSES = {"forbidden", "possible_with_witness", "unknown"}
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CALIBRATION_IDS = tuple(f"h1q_{n:03d}" for n in (4, 7, 10, 14, 18, 20, 25, 28, 31, 34, 37, 39))


def load_records(path):
    text = Path(path).read_text(encoding="utf-8")
    value = json.loads(text) if text.lstrip().startswith("[") else [json.loads(x) for x in text.splitlines() if x.strip()]
    if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
        raise ValueError("Expected a JSON array or JSONL objects")
    return value


def indexed(rows, key):
    result = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip() or value in result:
            raise ValueError(f"Missing/duplicate {key}")
        result[value] = row
    return result


def checked_states(states):
    if not isinstance(states, dict) or set(states) != set(STATES):
        raise ValueError("Exactly four joint-state keys required")
    if any(not isinstance(v, str) or v not in STATUSES for v in states.values()):
        raise ValueError("Use forbidden/possible_with_witness/unknown explicitly")
    return states


def ratio(n, d):
    return n / d if d else None


def evaluate(references, predictions):
    """Score one fixed cohort, with reference unknown distinct from false.

    Prediction format errors must have states=null and a nonempty string error.
    Valid full abstentions have four unknown states and no format error. Missing
    rows must be explicitly represented as format errors, never silently dropped.
    """
    refs, preds = indexed(references, "case_id"), indexed(predictions, "case_id")
    if refs.keys() != preds.keys():
        raise ValueError("Reference and prediction cohorts differ")
    c = Counter(pairs=len(refs), total_states=4 * len(refs))
    for key, ref in refs.items():
        gold = checked_states(ref.get("states"))
        if all(v == "forbidden" for v in gold.values()):
            raise ValueError("Reference cannot forbid every binary world")
        pred = preds[key]
        for field in ("packet_sha256", "task_scope_sha256"):
            fingerprint = ref.get(field)
            if not isinstance(fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
                raise ValueError("A reference " + field + " is required")
            if pred.get(field) != fingerprint:
                raise ValueError("Prediction and reference differ in " + field)
        error = pred.get("format_error")
        if error is not None and (not isinstance(error, str) or not error.strip()):
            raise ValueError("format_error must be null or a nonempty string")
        if error:
            if pred.get("states") is not None:
                raise ValueError("Format failures must have states=null")
            c["format_error_pairs"] += 1
            answer = {s: "unknown" for s in STATES}
        else:
            answer = checked_states(pred.get("states"))
            c["valid_prediction_pairs"] += 1
            c["semantic_all_unknown_pairs"] += all(v == "unknown" for v in answer.values())
            c["complete_prediction_pairs"] += all(v != "unknown" for v in answer.values())
            c["inconsistent_all_forbidden_prediction_pairs"] += all(v == "forbidden" for v in answer.values())
        full_gold = all(v != "unknown" for v in gold.values())
        c["fully_evaluable_pairs"] += full_gold
        c["exact_pairs"] += full_gold and not error and answer == gold
        for state in STATES:
            p, g = answer[state], gold[state]
            c["asserted_states"] += p != "unknown"
            c["predicted_forbidden_total"] += p == "forbidden"
            if g == "unknown":
                c["reference_unknown_states"] += 1
                c["unsupported_forbidden_on_unknown_reference"] += p == "forbidden"
                c["unsupported_possible_on_unknown_reference"] += p == "possible_with_witness"
                continue
            c["reference_known_states"] += 1
            c["reference_forbidden_states"] += g == "forbidden"
            if p != "unknown":
                c["assessed_known_states"] += 1
                c["wrong_assessed_known_states"] += p != g
            if p == "forbidden":
                c["forbidden_on_known_reference"] += 1
                c["known_true_forbidden"] += g == "forbidden"
                c["known_false_forbidden"] += g == "possible_with_witness"
    names = ("pairs total_states format_error_pairs valid_prediction_pairs semantic_all_unknown_pairs "
             "inconsistent_all_forbidden_prediction_pairs "
             "complete_prediction_pairs fully_evaluable_pairs exact_pairs asserted_states "
             "predicted_forbidden_total reference_unknown_states unsupported_forbidden_on_unknown_reference "
             "unsupported_possible_on_unknown_reference reference_known_states reference_forbidden_states "
             "assessed_known_states wrong_assessed_known_states forbidden_on_known_reference "
             "known_true_forbidden known_false_forbidden").split()
    result = {name: c[name] for name in names}
    for name, numerator, denominator in [
        ("reference_evaluability", "reference_known_states", "total_states"),
        ("state_coverage_all", "asserted_states", "total_states"),
        ("known_state_coverage", "assessed_known_states", "reference_known_states"),
        ("complete_pair_coverage", "complete_prediction_pairs", "pairs"),
        ("exact_pair_accuracy", "exact_pairs", "fully_evaluable_pairs"),
        ("selective_known_state_error", "wrong_assessed_known_states", "assessed_known_states"),
        ("forbidden_precision_on_known_reference", "known_true_forbidden", "forbidden_on_known_reference"),
        ("forbidden_recall_on_known_reference", "known_true_forbidden", "reference_forbidden_states"),
    ]:
        result[name] = ratio(c[numerator], c[denominator])
    return result


def identities(row):
    for side in ("A", "B"):
        contract = row[side]
        for key in ("venue", "id", "event_id"):
            if not isinstance(contract.get(key), str) or not contract[key].strip():
                raise ValueError(f"Missing {side}.{key}")
        yield "contract", (contract["venue"], contract["id"])
        yield "event", (contract["venue"], contract["event_id"])
    families = row.get("template_family_ids", [])
    if not isinstance(families, list) or not all(isinstance(x, str) and x.strip() for x in families):
        raise ValueError("template_family_ids must be a string list")
    for family in families:
        yield "template", (family,)


def split_conflicts(rows):
    """Versions of the same venue contract stay together; template IDs are manual.

    Empty template IDs do not demonstrate template isolation. This checks
    declared identity groups, not semantic near-duplicate discovery.
    """
    indexed(rows, "pair_id")
    memberships = defaultdict(set)
    for row in rows:
        split = row.get("split", "dev")
        if split not in {"dev", "train", "test"}:
            raise ValueError("split must be dev/train/test")
        for kind, key in identities(row):
            memberships[(kind, key)].add(split)
    return [{"kind": kind, "identity": list(key), "splits": sorted(splits)}
            for (kind, key), splits in sorted(memberships.items()) if len(splits) > 1]


def audit_queue(rows):
    indexed(rows, "pair_id")
    contracts, events, neighbors = set(), set(), defaultdict(set)
    completed, empty_secondary, cross_venue = 0, 0, 0
    for row in rows:
        links = list(identities(row))
        contracts.update(key for kind, key in links if kind == "contract")
        pair_events = [key for kind, key in links if kind == "event"]
        a, b = pair_events
        events.update((a, b)); neighbors[a].add(b); neighbors[b].add(a)
        cross_venue += row["A"]["venue"] != row["B"]["venue"]
        empty_secondary += sum(not row[s].get("secondary", "").strip() for s in ("A", "B"))
        annotation = row.get("annotation") or {}
        assessments = annotation.get("state_assessment") or {}
        completed += bool(annotation.get("reviewer_id")) and set(assessments) == set(STATES) and all(
            isinstance(assessments[s], dict) and assessments[s].get("status") in STATUSES for s in STATES)
    unseen, sizes = set(events), []
    while unseen:
        stack, component = [min(unseen)], set()
        while stack:
            event = stack.pop()
            if event in component:
                continue
            component.add(event)
            stack.extend(neighbors[event] - component)
        unseen -= component
        sizes.append(len(component))
    return {"pairs": len(rows), "unique_contracts": len(contracts), "unique_events": len(events),
            "cross_venue_pairs": cross_venue, "completed_annotations": completed,
            "empty_secondary_occurrences": empty_secondary, "contract_occurrences": 2 * len(rows),
            "event_component_sizes": sorted(sizes, reverse=True),
            "split_conflicts": split_conflicts(rows), "confirmatory_benchmark_ready": False,
            "blockers": ["Independent blind annotations and adjudication not verified",
                         "Complete governing documents and version scopes not certified",
                         "Existing inspected queue is development, not untouched holdout",
                         "Template-family grouping requires manual review",
                         "Cross-venue retrieval recall needs an opposing corpus and exhaustive blocks"],
            "note": "Empty secondary is a recorded field value, not proof of missing or complete governing terms."}


def prepare(queue_path, output):
    rows = load_records(queue_path)
    report = audit_queue(rows)
    by_id = indexed(rows, "pair_id")
    if set(CALIBRATION_IDS) - by_id.keys():
        raise ValueError("Calibration IDs missing from frozen queue")
    output.mkdir(parents=True, exist_ok=False)
    report.update(schema_version="e02-preparation-v1", status="development_preparation_only",
                  created_at_utc=datetime.now(timezone.utc).isoformat(),
                  source_queue=str(Path(queue_path).resolve().relative_to(ROOT)),
                  source_sha256=hashlib.sha256(Path(queue_path).read_bytes()).hexdigest(),
                  calibration_pair_ids=list(CALIBRATION_IDS),
                  calibration_selection="Deliberate development contrasts; not random or representative")
    (output / "readiness.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    # Files are identical, intentionally unlabeled and contain no model scores.
    selected = []
    for key in CALIBRATION_IDS:
        item = by_id[key]
        packet = {side: item[side] for side in ("A", "B")}
        packet_hash = hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        selected.append({"pair_id": key, "packet_sha256": packet_hash, "task_scope": None,
                         "task_scope_sha256": None, "split": "dev", "template_family_ids": [],
                         "A": item["A"], "B": item["B"],
                         "annotation": {"reviewer_id": None, "reviewed_at_utc": None,
                                        "source_completeness": None, "binary_payoff_scope": None,
                                        "assumptions": [], "missing_evidence": [],
                                        "state_assessment": {s: {"status": None, "evidence": [], "witness": None,
                                                                  "unknown_reason": None} for s in STATES}}})
    content = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in selected)
    for name in ("reviewer_a.jsonl", "reviewer_b.jsonl"):
        (output / name).write_text(content)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--queue", type=Path, default=ROOT / "experiments/week1/h1_queue/blind_queue.jsonl")
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("score")
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--predictions", type=Path, required=True)
    p = commands.add_parser("check-splits")
    p.add_argument("--pairs", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.queue, args.output)
    elif args.command == "score":
        print(json.dumps(evaluate(load_records(args.reference), load_records(args.predictions)), indent=2))
    else:
        conflicts = split_conflicts(load_records(args.pairs))
        print(json.dumps({"conflicts": conflicts, "template_isolation_verified": False}, indent=2))
        return int(bool(conflicts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
