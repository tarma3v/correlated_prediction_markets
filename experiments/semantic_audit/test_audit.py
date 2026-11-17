"""Independent fixtures and finite-world checks over emitted audit records."""

import hashlib
import itertools
import json
import random
import unittest
from collections import Counter, defaultdict
from decimal import Decimal

from common import HERE
from graph import CLAIMS, arcs, contradiction
from mutations import adjudicate
from search import event_components


def rows(file):
    return list(map(json.loads, (HERE / file).read_text().splitlines()))


def bit(value, condition):
    op, t = condition
    return {"eq": value == t, "ge": value >= t, "le": value <= t, "gt": value > t}[op]


class AuditTests(unittest.TestCase):
    def test_cpi_all_domains_and_identities(self):
        rs = rows("cpi_pairs.jsonl")
        self.assertEqual(len({(r["poly"], r["kalshi"]) for r in rs}), 385)
        for r in rs:
            a = [r["poly_predicate"][0], Decimal(r["poly_predicate"][1])]
            b = [r["kalshi_predicate"][0], Decimal(r["kalshi_predicate"][1])]
            # Independent fixed grid covers every cut, neighboring tenth, midpoint and tails.
            for name in ["normal", *r.get("scenarios", {})]:
                shared = r["same_release"] and name != "different_releases"
                b1 = ["ge", b[1]] if "inclusive" in name else b
                denominator = 20 if "continuous" in name else 10
                points = [
                    Decimal(x) / denominator
                    for x in range(-denominator, denominator * 2 + 1)
                ]
                if shared:
                    expected = {(bit(x, a), bit(x, b1)) for x in points}
                else:
                    expected = set(
                        itertools.product(
                            {bit(x, a) for x in points}, {bit(x, b1) for x in points}
                        )
                    )
                expected_set = {f"{int(x)}{int(y)}" for x, y in expected}
                observed = (
                    r["normal_forbidden"]
                    if name == "normal"
                    else r["scenarios"][name]["forbidden"]
                )
                self.assertEqual(expected_set, {"00", "01", "10", "11"} - set(observed))
                witnesses = (
                    r["normal_witnesses"]
                    if name == "normal"
                    else r["scenarios"][name]["lost_witnesses"]
                )
                for state, (x, y) in witnesses.items():
                    self.assertEqual(
                        state, f"{int(bit(Decimal(x),a))}{int(bit(Decimal(y),b1))}"
                    )
                    if shared:
                        self.assertEqual(Decimal(x), Decimal(y))

    def test_alternate_paths_match_exhaustive_boolean_worlds(self):
        rng = random.Random(17)
        nodes = list("abcde")
        for _ in range(40):
            edges = [
                (a, b, rng.choice(list(CLAIMS.values())))
                for a, b in itertools.combinations(nodes, 2)
            ]
            graph = defaultdict(list)
            for i, (a, b, claim) in enumerate(edges):
                for x, y in arcs(a, b, claim):
                    graph[x].append((y, i))
            for skip, (a, b, _) in enumerate(edges):
                attainable = set()
                for bits in itertools.product("01", repeat=len(nodes)):
                    w = dict(zip(nodes, bits))
                    if all(
                        i == skip or w[left] + w[right] not in claim
                        for i, (left, right, claim) in enumerate(edges)
                    ):
                        attainable.add(w[a] + w[b])
                for s in ("00", "01", "10", "11"):
                    self.assertEqual(
                        contradiction(graph, [(a, int(s[0])), (b, int(s[1]))], skip),
                        s not in attainable,
                    )

    def test_rank_partitions(self):
        rs = rows("cpi_pairs.jsonl")
        for p in {r["poly"] for r in rs}:
            subset = [r for r in rs if r["poly"] == p]
            for view in subset[0]["ranks"]:
                self.assertEqual(
                    sorted(r["ranks"][view] for r in subset), list(range(1, 56))
                )

    def test_graph_sampling_and_nli_counts(self):
        rs = rows("graph_edges.jsonl")
        self.assertEqual(len({(r["a"], r["b"]) for r in rs}), 839)
        for series in {r["series"] for r in rs}:
            ss = [r for r in rs if r["series"] == series]
            self.assertEqual(
                sum(r["corroborated"] for r in ss),
                sum(r["matched_confidence_selection"] for r in ss),
            )
        for r in rs:
            self.assertEqual(
                r["sound"],
                bool(r["claimed_forbidden"]) and not r["wrong_claim_witnesses"],
            )

    def test_uncertainty_and_budget_constraints(self):
        result = json.loads((HERE / "results.json").read_text())
        for m, curve in result["llm"]["metrics"].items():
            for target, row in curve.items():
                self.assertAlmostEqual(row["actual"], float(target))
        for m in ["critic", "critic_checked", "repeat"]:
            self.assertEqual(result["llm"]["cost_16_cases"][m]["calls"], 32)
        c = result["author_retrieval"]["e5_small_v2"]["known_same"]
        self.assertEqual(c["k"]["20"]["directed_hits"], [2 * c["pairs"]] * 2)
        # Similar fixed event titles join across venues only through observed links.
        ex = [
            {"poly_event_title": "P1", "kalshi_event_title": "K1"},
            {"poly_event_title": "P1", "kalshi_event_title": "K2"},
            {"poly_event_title": "P2", "kalshi_event_title": "K2"},
            {"poly_event_title": "K1", "kalshi_event_title": "P1"},
        ]
        a, b, c, d = event_components(ex)
        self.assertTrue(a == b == c and a != d)

    def test_text_challenge_balance_and_limits(self):
        rs = rows("mutation_cases.jsonl")
        self.assertEqual(len(rs), 190)
        groups = defaultdict(list)
        for r in rs:
            groups[r["family"]].append(r)
            self.assertEqual(
                adjudicate(
                    r["source_primary"],
                    r["quote"],
                    r["proposed_op"],
                    r["proposed_threshold"],
                ),
                r["accepted"],
            )
        for group in groups.values():
            self.assertEqual(Counter(r["valid"] for r in group), {True: 2, False: 8})
        # Open-set failure illustration, outside the fixed ten variants. A new payout qualification
        # still defeats the literal keyword guards and is explicitly disclosed in the report.
        p = next(r for r in rs if r["variant"] == "original")
        caveat = (
            p["source_primary"]
            + " A disputed release overrides this clause and pays one half."
        )
        self.assertTrue(
            adjudicate(caveat, p["quote"], p["proposed_op"], p["proposed_threshold"])[
                "with_scope_guards"
            ]
        )

    def test_manifest(self):
        m = json.loads((HERE / "manifest.json").read_text())
        for name, sha in {**m["output_sha256"], **m["code_sha256"]}.items():
            self.assertEqual(
                hashlib.sha256((HERE / name).read_bytes()).hexdigest(), sha
            )
        for name, sha in m["input_sha256"].items():
            self.assertEqual(
                hashlib.sha256((HERE.parents[1] / name).read_bytes()).hexdigest(), sha
            )
        for field, file in [
            ("protocol_sha256", "PROTOCOL_RU.md"),
            ("mutation_protocol_sha256", "MUTATION_PROTOCOL_RU.md"),
        ]:
            self.assertEqual(
                hashlib.sha256((HERE / file).read_bytes()).hexdigest(), m[field]
            )


if __name__ == "__main__":
    unittest.main()
