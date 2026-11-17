"""Protect partial-reference scoring and grouped data boundaries."""
import unittest

from workflow import audit_queue, evaluate, split_conflicts

STATES = ("00", "01", "10", "11")
U = {s: "unknown" for s in STATES}
P = {s: "possible_with_witness" for s in STATES}


def reference(key="x", states=None):
    return {"case_id": key, "packet_sha256": "a" * 64, "task_scope_sha256": "b" * 64,
            "states": dict(U if states is None else states)}


def prediction(key="x", states=None, error=None):
    return {"case_id": key, "packet_sha256": "a" * 64, "task_scope_sha256": "b" * 64,
            "states": None if error else dict(U if states is None else states),
            "format_error": error}


def pair(key, a, b, split="dev", templates=()):
    def contract(identity):
        return {"venue": "kalshi", "id": identity + "-T1", "event_id": identity,
                "secondary": "", "coverage": "API fields only", "provenance": {}}
    return {"pair_id": key, "A": contract(a), "B": contract(b), "split": split,
            "template_family_ids": list(templates), "annotation": {"reviewer_id": None}}


class MetricTests(unittest.TestCase):
    def test_unknown_reference_never_counts_as_exact_correct(self):
        result = evaluate([reference()], [prediction()])
        self.assertEqual(result["fully_evaluable_pairs"], 0)
        self.assertEqual(result["exact_pairs"], 0)
        self.assertIsNone(result["exact_pair_accuracy"])
        self.assertIsNone(result["selective_known_state_error"])
        self.assertEqual(result["semantic_all_unknown_pairs"], 1)

    def test_unsupported_assertion_is_separate_from_known_error(self):
        gold = {**U, "00": "possible_with_witness", "10": "forbidden"}
        pred = {s: "forbidden" for s in STATES}
        result = evaluate([reference(states=gold)], [prediction(states=pred)])
        self.assertEqual(result["predicted_forbidden_total"], 4)
        self.assertEqual(result["forbidden_on_known_reference"], 2)
        self.assertEqual(result["known_false_forbidden"], 1)
        self.assertEqual(result["unsupported_forbidden_on_unknown_reference"], 2)
        self.assertEqual(result["forbidden_precision_on_known_reference"], .5)
        self.assertEqual(result["reference_evaluability"], .5)
        self.assertEqual(result["known_state_coverage"], 1)
        self.assertEqual(result["state_coverage_all"], 1)

    def test_no_constraint_constant_has_no_forbidden_precision(self):
        gold = {**P, "10": "forbidden"}
        result = evaluate([reference(states=gold)], [prediction(states=P)])
        self.assertIsNone(result["forbidden_precision_on_known_reference"])
        self.assertEqual(result["forbidden_recall_on_known_reference"], 0)
        self.assertEqual(result["selective_known_state_error"], .25)
        self.assertEqual(result["exact_pairs"], 0)

    def test_format_failure_is_not_deliberate_abstention(self):
        result = evaluate([reference(states=P)], [prediction(error="bad_json")])
        self.assertEqual(result["format_error_pairs"], 1)
        self.assertEqual(result["semantic_all_unknown_pairs"], 0)
        self.assertEqual(result["known_state_coverage"], 0)
        self.assertEqual(result["complete_prediction_pairs"], 0)

    def test_perfect_fully_known_pair(self):
        result = evaluate([reference(states=P)], [prediction(states=P)])
        self.assertEqual(result["exact_pair_accuracy"], 1)

    def test_stale_packet_cannot_be_compared_by_case_id_only(self):
        stale = prediction()
        stale["packet_sha256"] = "b" * 64
        with self.assertRaises(ValueError):
            evaluate([reference()], [stale])

    def test_same_rules_with_different_or_missing_task_scope_rejected(self):
        pred = prediction()
        pred["task_scope_sha256"] = "c" * 64
        with self.assertRaises(ValueError):
            evaluate([reference()], [pred])
        ref = reference()
        del ref["task_scope_sha256"]
        with self.assertRaises(ValueError):
            evaluate([ref], [prediction()])

    def test_impossible_reference_rejected_model_error_retained(self):
        impossible = {s: "forbidden" for s in STATES}
        with self.assertRaises(ValueError):
            evaluate([reference(states=impossible)], [prediction(states=impossible)])
        result = evaluate([reference(states=P)], [prediction(states=impossible)])
        self.assertEqual(result["inconsistent_all_forbidden_prediction_pairs"], 1)
        self.assertEqual(result["known_false_forbidden"], 4)

    def test_duplicate_missing_extra_and_invalid_states_rejected(self):
        for refs, preds in [
            ([reference(), reference()], [prediction()]),
            ([reference()], []),
            ([reference()], [prediction("wrong")]),
            ([reference()], [prediction(), prediction()]),
            ([reference(states={**P, "11": "possible"})], [prediction()]),
            ([reference()], [prediction(states={"00": "forbidden"})]),
        ]:
            with self.subTest(refs=refs, preds=preds), self.assertRaises(ValueError):
                evaluate(refs, preds)


class ReadinessTests(unittest.TestCase):
    def test_components_include_indirect_event_connections(self):
        rows = [pair("1", "a", "b"), pair("2", "b", "c"), pair("3", "d", "e")]
        report = audit_queue(rows)
        self.assertEqual(report["event_component_sizes"], [3, 2])
        self.assertEqual(report["pairs"], 3)
        self.assertEqual(report["cross_venue_pairs"], 0)
        self.assertFalse(report["confirmatory_benchmark_ready"])
        self.assertEqual(report["completed_annotations"], 0)

    def test_event_and_contract_overlap_across_splits(self):
        result = split_conflicts([pair("1", "a", "b", "dev"), pair("2", "b", "c", "test")])
        self.assertIn("event", {x["kind"] for x in result})
        self.assertIn("contract", {x["kind"] for x in result})

    def test_template_overlap_without_shared_events(self):
        result = split_conflicts([pair("1", "a", "b", "dev", ["CPI"]),
                                  pair("2", "c", "d", "test", ["CPI"])])
        self.assertEqual([x["kind"] for x in result], ["template"])

    def test_venue_qualifies_identity(self):
        a, b = pair("1", "a", "b", "dev"), pair("2", "a", "b", "test")
        for side in ("A", "B"):
            b[side]["venue"] = "polymarket"
        self.assertEqual(split_conflicts([a, b]), [])

    def test_version_change_does_not_allow_same_contract_in_both_splits(self):
        a, b = pair("1", "a", "b", "dev"), pair("2", "a", "c", "test")
        a["A"]["input_sha256"], b["A"]["input_sha256"] = "old", "new"
        self.assertIn("contract", {x["kind"] for x in split_conflicts([a, b])})

    def test_duplicate_queue_ids_rejected(self):
        with self.assertRaises(ValueError):
            audit_queue([pair("1", "a", "b"), pair("1", "a", "b")])


if __name__ == "__main__":
    unittest.main()
