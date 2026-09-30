#!/usr/bin/env python3
"""Exhaustive synthetic demonstrations; NOT a market/ML performance evaluation.

Run from the project directory: python3 logic/metric_demo.py
No third-party dependencies. All finite worlds below are explicitly stipulated.
"""
import itertools
import json
from pathlib import Path


def relation_labels(feasible):
    """Classify a COMPLETE stipulated feasible-state set, not partial observations."""
    states = set(map(tuple, feasible))
    if not states:
        raise ValueError("An empty world set makes implications vacuous")
    if not states.issubset({(0,0), (0,1), (1,0), (1,1)}):
        raise ValueError("Only complete binary states are supported")
    labels = []
    for name, forbidden in {
        "equivalent": {(0, 1), (1, 0)},
        "a_implies_b": {(1, 0)},
        "b_implies_a": {(0, 1)},
        "mutually_exclusive": {(1, 1)},
        "collectively_exhaustive": {(0, 0)},
        "complements": {(0, 0), (1, 1)},
    }.items():
        if states.isdisjoint(forbidden):
            labels.append(name)
    return labels


def run():
    # Values of the SAME measurement, source and instant; hypothetical contracts.
    values = [0, 101, 151]
    states = sorted({(int(x > 150), int(x > 100)) for x in values})
    implication = {
        "definition": "A: x>150; B: x>100; same source/time; binary, no exceptions",
        "feasible_states": states,
        "labels": relation_labels(states),
        "counterexample_to_equality": [0, 1],
        "positive_sign_equality_proxy_uniform_worlds": sum(a == b for a,b in states)/len(states),
        "implication_violation_rate": sum(a == 1 and b == 0 for a,b in states)/len(states),
    }
    # Exactly one winner from three. All pairwise exclusions are true.
    worlds = [(1,0,0), (0,1,0), (0,0,1)]
    edges = [(0,1), (0,2), (1,2)]
    frustrated_counts = [sum(s[i]*s[j] != -1 for i,j in edges)
                         for s in itertools.product([-1,1], repeat=3)]
    triangle = {
        "stipulated_worlds": worlds,
        "exclusion_violations": sum(w[i] == w[j] == 1 for w in worlds for i,j in edges),
        "minimum_signed_frustrated_edges": min(frustrated_counts),
        "signed_frustration_rate": min(frustrated_counts)/len(edges),
        "opposite_outcome_proxy_uniform_worlds": sum(w[i] != w[j] for w in worlds for i,j in edges)/(len(worlds)*len(edges)),
        "both_no_witness_for_first_pair": [0,0,1],
    }
    # Independence is explicitly assumed here; equal settlement isn't dependence.
    p = 0.1
    null = {"p_a":p, "p_b":p, "independent":True,
            "always_positive_sign_expected_equality":p*p+(1-p)*(1-p),
            "covariance":0.0}
    # A superset YES + subset NO bundle has a lower bound of 1, not constant 1.
    bundle = [{"a_subset":a,"b_superset":b,"yes_b_plus_no_a":b+1-a} for a,b in states]
    result = {"kind":"synthetic_exact_enumeration_not_empirical_benchmark",
              "implication":implication,"exclusive_triangle":triangle,
              "independent_base_rate_null":null,"subset_bundle_payoffs":bundle}
    # Meaningful mathematical invariants, independent of market labels.
    assert states == [(0,0),(0,1),(1,1)]
    assert "a_implies_b" in implication["labels"] and "equivalent" not in implication["labels"]
    assert triangle["exclusion_violations"] == 0
    assert triangle["minimum_signed_frustrated_edges"] == 1
    assert abs(null["always_positive_sign_expected_equality"]-0.82) < 1e-12
    assert [row["yes_b_plus_no_a"] for row in bundle] == [1,2,1]
    return result


if __name__ == "__main__":
    result = run()
    path = Path(__file__).resolve().parents[1]/"output"/"metric_demo.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
