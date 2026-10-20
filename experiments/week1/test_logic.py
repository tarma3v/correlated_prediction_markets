"""Independent expected-state and parser checks for the controlled solver."""
from decimal import Decimal, Inexact, ROUND_UP, localcontext
import unittest

try:
    from .logic import extract_contract, label_from_forbidden, possible_states
except ImportError:
    from logic import extract_contract, label_from_forbidden, possible_states


def contract(op, threshold, **changes):
    value = {"metric": "fictional continuous index", "source": "source A",
             "period": "2026-10", "unit": "units", "op": op,
             "threshold": threshold}
    value.update(changes)
    return value


def template(phrase="more than", threshold="1.25"):
    return ("Metric: fictional continuous index\n"
            "Source: source A\n"
            "Period: 2026-10\n"
            "Unit: units\n"
            f"YES iff the observed value is {phrase} {threshold}.\n"
            "Settlement: binary; no exceptions.")


class SolverTests(unittest.TestCase):
    def assert_states(self, a, b, expected):
        result = possible_states(a, b)
        self.assertEqual(set(result), set(expected))
        # Verify witnesses without reusing the implementation's operator map.
        for state, witness in result.items():
            for side, record, bit in [("a", a, state[0]), ("b", b, state[1])]:
                value = Decimal(witness["x_" + side])
                bound = Decimal(str(record["threshold"]))
                self.assertTrue(value.is_finite())
                op = record["op"]
                if op == "gt":
                    truth = value > bound
                elif op == "ge":
                    truth = value >= bound
                elif op == "lt":
                    truth = value < bound
                else:
                    truth = value <= bound
                self.assertEqual(truth, bit == "1")
            if all(a[f] == b[f] for f in ("metric", "source", "period", "unit")):
                self.assertEqual(Decimal(witness["x_a"]), Decimal(witness["x_b"]))
        return result

    def test_identical_predicates(self):
        for op in ["gt", "ge", "lt", "le"]:
            with self.subTest(op=op):
                self.assert_states(contract(op, "2"), contract(op, "2.00"), ["00", "11"])

    def test_strictness_at_shared_boundary(self):
        self.assert_states(contract("gt", "2"), contract("ge", "2"), ["00", "01", "11"])
        self.assert_states(contract("ge", "2"), contract("gt", "2"), ["00", "10", "11"])
        self.assert_states(contract("lt", "2"), contract("le", "2"), ["00", "01", "11"])
        self.assert_states(contract("le", "2"), contract("lt", "2"), ["00", "10", "11"])

    def test_opposite_comparisons(self):
        self.assert_states(contract("gt", "0"), contract("lt", "0"), ["00", "01", "10"])
        self.assert_states(contract("ge", "0"), contract("le", "0"), ["01", "10", "11"])
        self.assert_states(contract("gt", "0"), contract("le", "0"), ["01", "10"])
        self.assert_states(contract("ge", "0"), contract("lt", "0"), ["01", "10"])

    def test_all_operator_pairs_against_integer_scaled_oracle(self):
        # Integer thresholds in [-2, 2]: half-step witnesses from -3 to 3
        # exhaust every boundary, intervening cell and both tails. This oracle
        # uses only integer arithmetic, independently of Decimal candidates.
        def holds(op, x_twice, threshold):
            if op == "gt":
                return x_twice > 2 * threshold
            if op == "ge":
                return x_twice >= 2 * threshold
            if op == "lt":
                return x_twice < 2 * threshold
            return x_twice <= 2 * threshold
        for op_a in ["gt", "ge", "lt", "le"]:
            for op_b in ["gt", "ge", "lt", "le"]:
                for ta in range(-2, 3):
                    for tb in range(-2, 3):
                        expected = {str(int(holds(op_a, x2, ta))) + str(int(holds(op_b, x2, tb)))
                                    for x2 in range(-6, 7)}
                        with self.subTest(op_a=op_a, op_b=op_b, ta=ta, tb=tb):
                            self.assert_states(contract(op_a, ta), contract(op_b, tb), expected)

    def test_negative_thresholds_and_interiors(self):
        self.assert_states(contract("gt", "-2"), contract("gt", "-1"), ["00", "10", "11"])
        self.assert_states(contract("lt", "-2"), contract("lt", "-1"), ["00", "01", "11"])
        self.assert_states(contract("gt", "-2"), contract("lt", "-1"), ["01", "10", "11"])
        self.assert_states(contract("gt", "-1"), contract("lt", "-2"), ["00", "01", "10"])

    def test_independent_context_fields(self):
        for field in ["metric", "source", "period", "unit"]:
            with self.subTest(field=field):
                self.assert_states(contract("gt", "1"),
                                   contract("gt", "1", **{field: "different"}),
                                   ["00", "01", "10", "11"])

    def test_context_is_exact_not_normalized(self):
        self.assert_states(contract("gt", "1"), contract("gt", "1", source="Source A"),
                           ["00", "01", "10", "11"])

    def test_precision_beyond_default_context(self):
        prefix = "1234567890" * 12
        a = contract("gt", prefix + ".0000000000000000000001")
        b = contract("lt", prefix + ".0000000000000000000002")
        with localcontext() as ctx:
            ctx.prec = 2
            self.assert_states(a, b, ["01", "10", "11"])

    def test_tiny_interval_and_large_exponent_span(self):
        self.assert_states(contract("gt", "1e-1000000"), contract("lt", "2e-1000000"),
                           ["01", "10", "11"])
        self.assert_states(contract("gt", "-1e1000000"), contract("lt", "1e1000000"),
                           ["01", "10", "11"])

    def test_caller_rounding_and_traps_do_not_change_solver(self):
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.rounding = ROUND_UP
            ctx.traps[Inexact] = True
            self.assert_states(contract("gt", "1e-1000000"), contract("lt", "1e1000000"),
                               ["01", "10", "11"])

    def test_numeric_types_and_signed_zero(self):
        self.assert_states(contract("gt", Decimal("-0")), contract("gt", 0), ["00", "11"])
        self.assert_states(contract("ge", 0.125), contract("ge", "0.125"), ["00", "11"])

    def test_reject_nonfinite_or_malformed_thresholds(self):
        for bad in ["NaN", "sNaN", "Infinity", "-Infinity", Decimal("NaN"),
                    Decimal("Infinity"), float("nan"), float("inf"), True, None,
                    " 1", "1 ", "1_000", "1,000", {}, []]:
            with self.subTest(value=repr(bad)):
                with self.assertRaises(ValueError):
                    possible_states(contract("gt", bad), contract("le", "0"))

    def test_reject_invalid_contracts(self):
        for bad in [None, {}, contract("eq", "1"), contract("gt", "1", metric=""),
                    contract("gt", "1", source=None)]:
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    possible_states(bad, contract("gt", "0"))

    def test_labels_use_exact_forbidden_sets(self):
        examples = [(set(), "no_hard_relation"), ({"01", "10"}, "equivalent"),
                    ({"10"}, "a_implies_b"), ({"01"}, "b_implies_a"),
                    ({"11"}, "disjoint"), ({"00"}, "exhaustive"),
                    ({"00", "11"}, "complement"), ({"00", "01", "10", "11"}, "unsupported"),
                    ({"00", "01"}, "unsupported"), ({"bad"}, "unsupported")]
        for states, expected in examples:
            with self.subTest(states=states):
                self.assertEqual(label_from_forbidden(states), expected)
        for bad in [None, "10", 1, [["00"]]]:
            self.assertEqual(label_from_forbidden(bad), "unsupported")


class ParserTests(unittest.TestCase):
    def test_all_phrases_and_exact_evidence(self):
        for phrase, op in [("more than", "gt"), ("at least", "ge"),
                           ("less than", "lt"), ("at most", "le")]:
            text = template(phrase, "-1.2500e+2")
            result = extract_contract(text)
            self.assertIsNotNone(result)
            self.assertEqual(result["op"], op)
            self.assertEqual(result["threshold"], "-1.2500e+2")
            self.assertEqual(result["predicate_quote"],
                             f"YES iff the observed value is {phrase} -1.2500e+2.")
            self.assertIn(result["predicate_quote"], text)
            self.assertEqual(result["source"], "source A")
            self.assertEqual(result["period"], "2026-10")
            self.assertEqual(result["unit"], "units")
            self.assertEqual(extract_contract(text + "\n"), result)

    def test_parsed_records_work_without_gold_fields(self):
        a, b = extract_contract(template("at least", "1")), extract_contract(template("less than", "1"))
        self.assertEqual(set(possible_states(a, b)), {"01", "10"})

    def test_reject_incomplete_nonbinary_and_extra_clauses(self):
        text = template()
        variants = [text.replace("Source: source A\n", ""),
                    text.replace("Settlement: binary; no exceptions.", "Settlement: 50/50."),
                    text.replace("no exceptions", "with exceptions"),
                    text.replace("binary", "nonbinary"),
                    text + "\nException: postponed events settle differently.",
                    "Title: another field\n" + text,
                    text + "\n\n", text.replace("\n", "\r\n"),
                    text.replace("Metric: ", "Metric:  "),
                    text.replace("source A", ""), text.replace("source A", "source\tA"),
                    text.replace("more than", "above"),
                    text.replace("YES iff", "Yes iff"),
                    text.replace("Unit: units\n", "Unit: units\nUnit: units\n")]
        for variant in variants:
            with self.subTest(text=variant):
                self.assertIsNone(extract_contract(variant))

    def test_reject_nonfinite_and_nonstandard_number_text(self):
        for number in ["NaN", "sNaN", "Infinity", "-Infinity", "1_000", "1,000", "--1", " 1"]:
            with self.subTest(number=number):
                self.assertIsNone(extract_contract(template(threshold=number)))
        self.assertIsNone(extract_contract(None))


if __name__ == "__main__":
    unittest.main()
