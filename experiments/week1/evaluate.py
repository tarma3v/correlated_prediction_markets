"""Rescore saved E01 outputs offline, retaining errors, abstentions and denominators."""
from __future__ import annotations
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import time

from logic import extract_contract, possible_states

HERE = Path(__file__).resolve().parent
STATES = ("00", "01", "10", "11")
UNKNOWN = {s: "unknown" for s in STATES}
FORBIDDEN = {"equivalent": {"01", "10"}, "a_implies_b": {"10"},
             "b_implies_a": {"01"}, "disjoint": {"11"}, "exhaustive": {"00"},
             "complement": {"00", "11"}, "no_hard_relation": set()}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prediction_states(row):
    if row.get("error") or not row.get("parsed"):
        return dict(UNKNOWN)
    obj = row["parsed"]
    if row["branch"] == "direct":
        if obj["relation"] == "unknown":
            return dict(UNKNOWN)
        forbidden = FORBIDDEN[obj["relation"]]
        return {s: "forbidden" if s in forbidden else "possible" for s in STATES}
    return dict(obj["states"])


def check_prediction(row, packet):
    """Check a prediction against its text, never against reference labels.

    The formal component is intentionally a very narrow rule-based baseline.
    It cannot certify natural-language venue rules or fill missing evidence.
    """
    begun = time.perf_counter()
    result = {"states": dict(UNKNOWN), "reason": None, "evidence": [], "witnesses": {}}
    if row.get("error") or not row.get("parsed"):
        result["reason"] = "invalid_starting_response"
    elif not packet["scope"].startswith("CONTROLLED SCALAR"):
        result["reason"] = "outside_formal_scope"
    else:
        extracted = {}
        for side in ("A", "B"):
            text = packet[side]["text"]
            expected = extract_contract(text)
            proposed = row["parsed"].get(side)
            if expected is None or proposed is None:
                result["reason"] = "incomplete_or_unsupported_predicate"
                break
            quote = proposed.get("predicate_quote", "")
            exact = bool(quote) and quote in text
            result["evidence"].append({"side": side, "exact_substring": exact})
            same = all(proposed.get(k) == expected[k] for k in
                       ("metric", "source", "period", "unit", "op"))
            try:
                number = Decimal(proposed.get("threshold", "NaN"))
                same = same and number.is_finite() and number == Decimal(expected["threshold"])
            except (InvalidOperation, ValueError, TypeError):
                same = False
            if not exact or not same:
                result["reason"] = "extraction_not_supported_by_text"
                break
            # The prompt permits any exact quote, not necessarily the entire
            # predicate sentence. Use the independently parsed text values after
            # validating semantic equality, never an unchecked model number.
            extracted[side] = expected
        if len(extracted) == 2:
            worlds = possible_states(extracted["A"], extracted["B"])
            result.update(states={s: "possible" if s in worlds else "forbidden" for s in STATES},
                          witnesses=worlds, reason="formal_scalar_recomputation")
    result["seconds"] = time.perf_counter() - begun
    return result


def rule_only(packet):
    if not packet["scope"].startswith("CONTROLLED SCALAR"):
        return dict(UNKNOWN)
    a, b = (extract_contract(packet[s]["text"]) for s in ("A", "B"))
    if a is None or b is None:
        return dict(UNKNOWN)
    worlds = possible_states(a, b)
    return {s: "possible" if s in worlds else "forbidden" for s in STATES}


def audit_model_witnesses(row, packet):
    """Validate raw model witnesses in the stipulated scope without reading gold."""
    if row["branch"] == "direct" or row.get("error") or not row.get("parsed"):
        return []
    a, b = (extract_contract(packet[s]["text"]) for s in ("A", "B"))
    in_scope = packet["scope"].startswith("CONTROLLED SCALAR") and a is not None and b is not None
    records = []
    for state in STATES:
        status = row["parsed"]["states"][state]
        witness = row["parsed"]["witnesses"][state]
        if status != "possible":
            if witness is not None:
                records.append({"state": state, "status": "unexpected_witness_for_nonpossible_state"})
            continue
        if not in_scope:
            verdict = "outside_checkable_scope"
        elif witness is None:
            verdict = "missing_witness"
        else:
            try:
                xa, xb = Decimal(witness["x_a"]), Decimal(witness["x_b"])
                valid = xa.is_finite() and xb.is_finite()
                if all(a[k] == b[k] for k in ("metric", "source", "period", "unit")):
                    valid = valid and xa == xb
                def bit(value, contract):
                    t = Decimal(contract["threshold"])
                    op = contract["op"]
                    return str(int(value > t if op == "gt" else value >= t if op == "ge"
                                   else value < t if op == "lt" else value <= t))
                valid = valid and bit(xa, a) + bit(xb, b) == state
                verdict = "valid_witness" if valid else "invalid_witness"
            except (InvalidOperation, ValueError, KeyError, TypeError):
                verdict = "invalid_witness"
        records.append({"state": state, "status": verdict})
    return records


def metrics(rows):
    n = len(rows)
    known = [(r["states"][s], r["reference"][s]) for r in rows for s in STATES
             if r["reference"][s] != "unknown"]
    assessed = [(p, g) for p, g in known if p != "unknown"]
    forbidden = [(p, g) for p, g in known if p == "forbidden"]
    tp = sum(p == g == "forbidden" for p, g in known)
    fp = sum(p == "forbidden" and g == "possible" for p, g in known)
    positive_reference = sum(g == "forbidden" for _, g in known)
    complete = [r for r in rows if all(v != "unknown" for v in r["states"].values())]
    correct = sum(r["states"] == r["reference"] for r in rows)
    return {"pairs": n, "reference_states": len(known), "assessed_states": len(assessed),
            "state_coverage": len(assessed) / len(known) if known else None,
            "complete_pairs": len(complete), "pair_coverage": len(complete) / n if n else None,
            "exact_pairs": correct, "exact_pair_fraction_all": correct / n if n else None,
            "wrong_assessed_states": sum(p != g for p, g in assessed),
            "selective_state_error": sum(p != g for p, g in assessed) / len(assessed) if assessed else None,
            "predicted_forbidden": len(forbidden), "false_forbidden": fp,
            "forbidden_precision": tp / len(forbidden) if forbidden else None,
            "forbidden_recall": tp / positive_reference if positive_reference else None,
            "reference_forbidden": positive_reference}


def transition_counts(before, after):
    counts = Counter()
    for key in sorted(before):
        a, b = before[key], after[key]
        if a["reference"] is None or any(s == "unknown" for s in a["reference"].values()):
            continue
        if a.get("format_error") or b.get("format_error"):
            if a.get("format_error") and b.get("format_error"):
                counts["both_format_error_pairs"] += 1
            elif a.get("format_error"):
                counts["format_error_to_valid_pairs"] += 1
            else:
                counts["valid_to_format_error_pairs"] += 1
            # A format failure is not a deliberate semantic abstention.
            continue
        for state in STATES:
            old, new, ref = a["states"][state], b["states"][state], a["reference"][state]
            if old == new:
                counts["unchanged"] += 1
            elif new == "unknown":
                counts["to_abstain_from_correct" if old == ref else "to_abstain_from_wrong"] += 1
            elif old == "unknown":
                counts["from_abstain_to_correct" if new == ref else "from_abstain_to_wrong"] += 1
            elif new == ref:
                counts["repaired_known_error"] += 1
            else:
                counts["introduced_known_error"] += 1
    return dict(counts)


def summarize(run_dir, destination=None):
    packets = {x["case_id"]: x for x in json.loads((HERE / "data/packets.json").read_text())}
    refs = {x["case_id"]: x for x in json.loads((HERE / "data/reference.json").read_text())}
    config = json.loads((HERE / "config.json").read_text())
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    raw_path = run_dir / "predictions.jsonl"
    if manifest["status"] != "complete":
        raise ValueError("Run incomplete; no final summary is allowed")
    if hashlib.sha256(raw_path.read_bytes()).hexdigest() != manifest["predictions_sha256"]:
        raise ValueError("Saved predictions changed")
    if hashlib.sha256((HERE / "data/manifest.json").read_bytes()).hexdigest() != manifest["data_manifest_sha256"]:
        raise ValueError("Dataset manifest differs from the run")
    frozen = json.loads((HERE / "data/manifest.json").read_text())
    for name, expected_hash in {**frozen["inputs_sha256"], **frozen["prompt_sha256"]}.items():
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != expected_hash:
            raise ValueError("Frozen input changed: " + name)
    raw = [json.loads(x) for x in raw_path.read_text().splitlines()]
    expected = {(key, method) for key in packets for method in config["branches"]}
    actual = [(r["case_id"], r["branch"]) for r in raw]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Incomplete or duplicate output rows")
    evaluated = []
    checks = []
    witness_audit = []
    for row in raw:
        key = row["case_id"]
        if row["packet_sha256"] != packets[key]["packet_sha256"]:
            raise ValueError("Packet hash mismatch")
        base = {"case_id": key, "kind": refs[key]["kind"], "pattern": refs[key]["pattern"],
                "reference": refs[key]["states"], "method": row["branch"],
                "states": prediction_states(row), "format_error": row.get("error"),
                "confidence": row["parsed"]["confidence"] if row.get("parsed") and not row.get("error") else 0}
        evaluated.append(base)
        witness_audit.extend({"case_id": key, "method": row["branch"], **record}
                             for record in audit_model_witnesses(row, packets[key]["packet"]))
        if row["branch"] in ("structured", "critic"):
            check = check_prediction(row, packets[key]["packet"])
            checks.append({"case_id": key, "method": row["branch"] + "_checked", **check})
            evaluated.append({**base, "method": row["branch"] + "_checked", "states": check["states"]})
    for key, case in packets.items():
        base = {"case_id": key, "kind": refs[key]["kind"], "pattern": refs[key]["pattern"],
                "reference": refs[key]["states"], "format_error": None, "confidence": 1}
        for method, states in [("always_unknown", dict(UNKNOWN)),
                               ("always_no_constraint", {s: "possible" for s in STATES}),
                               ("rule_only", rule_only(case["packet"]))]:
            evaluated.append({**base, "method": method, "states": states})
    by_method = {m: [r for r in evaluated if r["method"] == m] for m in sorted({r["method"] for r in evaluated})}
    result = {"scope": "Development diagnostic; reference accuracy only on 16 stipulated scalar pairs",
              "real_market_accuracy": None, "h1_cross_venue_recall": None,
              "source_predictions_sha256": manifest["predictions_sha256"], "methods": {}, "transitions": {},
              "risk_coverage_note": "All equal-confidence items enter together. Scores uncalibrated. No dev threshold optimization, no CI or significance with two constructed families.",
              "cost_note": "repeat/critic totals include their common structured first call. checked costs are CPU-only additions. Equal caps are not equal actual spend."}
    for method, rows in by_method.items():
        decidable = [r for r in rows if r["kind"] == "controlled_decidable"]
        guards = [r for r in rows if r["kind"] == "controlled_scope_guard"]
        real = [r for r in rows if r["kind"] == "real_unlabeled"]
        curve = []
        for threshold in sorted({r["confidence"] for r in decidable}, reverse=True):
            chosen = [{**r, "states": r["states"] if r["confidence"] >= threshold else dict(UNKNOWN)} for r in decidable]
            curve.append({"confidence_threshold": threshold, **metrics(chosen)})
        evidence = []
        for r in raw:
            if r["branch"] != method or not r.get("parsed") or method == "direct" or r.get("error"):
                continue
            for side in ("A", "B"):
                obj = r["parsed"].get(side)
                if obj:
                    evidence.append(bool(obj["predicate_quote"]) and obj["predicate_quote"] in packets[r["case_id"]]["packet"][side]["text"])
        # Cost is per complete pipeline, not merely the final response.
        origin = method.replace("_checked", "")
        branches = ["structured", origin] if origin in ("repeat", "critic") else [origin]
        calls = [r for r in raw if r["branch"] in branches]
        method_checks = [c for c in checks if c["method"] == method]
        result["methods"][method] = {"controlled": metrics(decidable),
              "scope_guards": {"n": len(guards), "all_unknown": sum(r["states"] == UNKNOWN for r in guards),
                               "valid_all_unknown": sum(r["states"] == UNKNOWN and not r["format_error"] for r in guards),
                               "format_errors": sum(bool(r["format_error"]) for r in guards),
                               "unsupported_forbidden_states": sum(v == "forbidden" for r in guards for v in r["states"].values())},
              "real_unlabeled": {"n": len(real), "all_unknown": sum(r["states"] == UNKNOWN for r in real),
                                 "valid_all_unknown": sum(r["states"] == UNKNOWN and not r["format_error"] for r in real),
                                 "format_errors": sum(bool(r["format_error"]) for r in real),
                                 "asserted_forbidden_states_unvalidated": sum(v == "forbidden" for r in real for v in r["states"].values())},
              "format_errors_all_24": dict(Counter(r["format_error"] for r in rows if r["format_error"])),
              "evidence_substrings": {"checked": len(evidence), "exact": sum(evidence),
                                      "not_semantic_precision": True},
              "raw_model_witnesses": dict(Counter(w["status"] for w in witness_audit if w["method"] == method)),
              "cost": {"llm_calls": len(calls), "input_tokens": sum(r["input_tokens"] for r in calls),
                       "output_tokens": sum(r["output_tokens"] or 0 for r in calls),
                       "llm_seconds": sum(r["seconds"] for r in calls),
                       "checker_seconds": sum(r["seconds"] for r in method_checks)},
              "risk_coverage": curve}
    lookup = {m: {r["case_id"]: r for r in rows} for m, rows in by_method.items()}
    for before, after in [("direct", "structured"), ("structured", "structured_checked"),
                          ("structured", "repeat"), ("structured", "critic"), ("critic", "critic_checked")]:
        result["transitions"][before + "__" + after] = transition_counts(lookup[before], lookup[after])
    destination = destination or run_dir
    destination.mkdir(parents=True, exist_ok=True)
    dump(destination / "summary.json", result)
    dump(destination / "evaluated.json", evaluated)
    dump(destination / "checker_audit.json", checks)
    dump(destination / "witness_audit.json", witness_audit)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=HERE / "results/observed")
    parser.add_argument("--output", type=Path, help="Optional destination for recalculated summaries")
    args = parser.parse_args()
    result = summarize(args.run, args.output)
    for method, data in result["methods"].items():
        m = data["controlled"]
        print(f"{method:24} exact={m['exact_pairs']:2}/{m['pairs']} complete={m['complete_pairs']:2} "
              f"false_forbidden={m['false_forbidden']:2}/{m['predicted_forbidden']:2}")


if __name__ == "__main__":
    main()
