"""Guard evaluation against rewarding abstention or a no-constraint constant."""
import copy
import unittest
from evaluate import UNKNOWN, audit_model_witnesses, check_prediction, metrics, prediction_states, transition_counts
from logic import extract_contract
from prepare import make_contract


class EvaluationTests(unittest.TestCase):
    def row(self, states):
        return {"states": states, "reference": {"00": "possible", "01": "possible",
                "10": "forbidden", "11": "possible"}}

    def test_abstention_has_no_precision_and_no_recall(self):
        m = metrics([self.row(dict(UNKNOWN))])
        self.assertEqual(m["state_coverage"], 0)
        self.assertIsNone(m["forbidden_precision"])
        self.assertEqual(m["forbidden_recall"], 0)
        self.assertEqual(m["exact_pairs"], 0)

    def test_no_constraints_is_not_perfect(self):
        m = metrics([self.row({s: "possible" for s in UNKNOWN})])
        self.assertEqual(m["false_forbidden"], 0)
        self.assertEqual(m["forbidden_recall"], 0)
        self.assertEqual(m["exact_pairs"], 0)
        self.assertEqual(m["selective_state_error"], 0.25)

    def test_false_constraint_denominator(self):
        m = metrics([self.row({"00": "possible", "01": "unknown", "10": "forbidden", "11": "forbidden"})])
        self.assertEqual(m["predicted_forbidden"], 2)
        self.assertEqual(m["false_forbidden"], 1)
        self.assertEqual(m["forbidden_precision"], 0.5)
        self.assertEqual(m["state_coverage"], 0.75)
        self.assertEqual(m["complete_pairs"], 0)

    def test_abstention_is_not_a_repair(self):
        old = self.row({s: "forbidden" for s in UNKNOWN})
        new = self.row(dict(UNKNOWN))
        result = transition_counts({"x": old}, {"x": new})
        self.assertEqual(result, {"to_abstain_from_wrong": 3, "to_abstain_from_correct": 1})

    def test_known_repair_and_new_error(self):
        before = self.row({s: "possible" for s in UNKNOWN})
        after = self.row({s: "forbidden" for s in UNKNOWN})
        result = transition_counts({"x": before}, {"x": after})
        self.assertEqual(result["repaired_known_error"], 1)
        self.assertEqual(result["introduced_known_error"], 3)

    def test_format_repair_is_not_semantic_repair_or_abstention(self):
        before = {**self.row(dict(UNKNOWN)), "format_error": "schema_error"}
        after = self.row(self.row({})["reference"])
        self.assertEqual(transition_counts({"x": before}, {"x": after}),
                         {"format_error_to_valid_pairs": 1})

    def test_invalid_response_is_abstention(self):
        row = {"branch": "direct", "parsed": {"relation": "disjoint"}, "error": "output_token_limit"}
        self.assertEqual(prediction_states(row), UNKNOWN)

    def test_checker_repairs_only_text_supported_extractions(self):
        domain = ("Index", "Source", "2030")
        packet = {"scope": "CONTROLLED SCALAR", "A": {"text": make_contract(domain, "gt", "2")},
                  "B": {"text": make_contract(domain, "gt", "1")}}
        row = {"parsed": {s: extract_contract(packet[s]["text"]) for s in ("A", "B")}, "error": None}
        row["parsed"]["states"] = {s: "forbidden" for s in UNKNOWN}
        result = check_prediction(row, packet)
        self.assertEqual(result["states"], self.row({})["reference"])
        altered = copy.deepcopy(row)
        altered["parsed"]["A"]["threshold"] = "0"
        self.assertEqual(check_prediction(altered, packet)["states"], UNKNOWN)
        altered = copy.deepcopy(row)
        altered["parsed"]["A"]["predicate_quote"] = "Invented evidence"
        self.assertEqual(check_prediction(altered, packet)["states"], UNKNOWN)
        shorter = copy.deepcopy(row)
        shorter["parsed"]["A"]["predicate_quote"] = "the observed value is more than 2"
        self.assertEqual(check_prediction(shorter, packet)["states"], result["states"])

    def test_formal_solver_cannot_certify_real_packet(self):
        domain = ("Index", "Source", "unit")
        packet = {"scope": "REAL SNAPSHOT FRAGMENTS", "A": {"text": make_contract(domain, "gt", "2")},
                  "B": {"text": make_contract(domain, "gt", "1")}}
        row = {"parsed": {s: extract_contract(packet[s]["text"]) for s in ("A", "B")}, "error": None}
        self.assertEqual(check_prediction(row, packet)["states"], UNKNOWN)

    def test_witness_must_match_the_requested_joint_state(self):
        domain = ("Index", "Source", "unit")
        packet = {"scope": "CONTROLLED SCALAR", "A": {"text": make_contract(domain, "gt", "2")},
                  "B": {"text": make_contract(domain, "gt", "1")}}
        row = {"branch": "structured", "error": None,
               "parsed": {"states": {**UNKNOWN, "01": "possible"},
                          "witnesses": {s: None for s in UNKNOWN}}}
        row["parsed"]["witnesses"]["01"] = {"x_a": "2", "x_b": "2"}
        self.assertEqual(audit_model_witnesses(row, packet)[0]["status"], "valid_witness")
        row["parsed"]["witnesses"]["01"] = {"x_a": "3", "x_b": "3"}
        self.assertEqual(audit_model_witnesses(row, packet)[0]["status"], "invalid_witness")
        row["parsed"]["witnesses"]["01"] = {"x_a": "0", "x_b": "2"}
        self.assertEqual(audit_model_witnesses(row, packet)[0]["status"], "invalid_witness")


if __name__ == "__main__":
    unittest.main()
