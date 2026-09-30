#!/usr/bin/env python3
"""Exact aggregate audit of arXiv:2512.02436v2 payoff compatibility.

Standard library only. This reconstructs arithmetic from published aggregates;
it does not reproduce the unavailable pm_relations_code.zip E1 experiment.
Run: python3 research/metric_null.py
"""
from fractions import Fraction as F
from itertools import combinations
import json
from pathlib import Path

SOURCE = "https://arxiv.org/html/2512.02436v2"
INPUTS = {
    "AAI": {"resolved_edges": 1039, "compatible_edges": 653,
            "positive_edges": 893, "positive_percent_displayed": "66.7"},
    "NLI": {"resolved_edges": 113198, "compatible_edges": 45997,
            "positive_edges": 662, "positive_percent_displayed": "60.6"},
}


def number(x):
    x = F(x)
    return {"exact": str(x), "value": float(x)}


def recover_numerator(denominator, displayed_percent):
    """Unique count consistent with nearest 0.1 percentage-point rounding.

    Half-open rounding interval is conventional half-up; no boundary candidate
    occurs for these inputs, so half-even gives the same reconstructed counts.
    """
    center = F(displayed_percent)
    lo, hi = center - F(1, 20), center + F(1, 20)
    possible = [k for k in range(denominator + 1)
                if lo <= 100 * F(k, denominator) < hi]
    assert len(possible) == 1, possible
    k = possible[0]
    assert 100 * F(k, denominator) not in (lo, hi)
    return k


def method(row):
    n, total, pos = (row[k] for k in
                     ("resolved_edges", "compatible_edges", "positive_edges"))
    cp = recover_numerator(pos, row["positive_percent_displayed"])
    neg, cn = n - pos, total - cp
    assert 0 <= cp <= pos and 0 <= cn <= neg
    q, a, b, score = F(pos, n), F(cp, pos), F(cn, neg), F(total, n)
    assert score == q * a + (1 - q) * b
    # Positive-compatible edges have equal outcomes. Negative-compatible edges
    # have unequal outcomes, so negative-incompatible edges have equal outcomes.
    same = cp + neg - cn
    r = F(same, n)
    null = q * r + (1 - q) * (1 - r)
    # Uniform fixed-count sign shuffle: X ~ Hypergeom(N=n, R=same, K=pos),
    # C=(n-same-pos+2X)/n. This variance assumes that global shuffle null only.
    null_variance = F(4, n*n) * pos * r * (1-r) * F(n-pos, n-1)
    out = dict(row)
    out.update({
        "positive_compatible_edges_inferred_from_rounding": cp,
        "negative_edges_derived": neg,
        "negative_compatible_edges_derived": cn,
        "same_outcome_edges_derived": same,
        "positive_share": number(q), "positive_score": number(a),
        "negative_score": number(b), "observed_score": number(score),
        "constant_positive_score_on_own_selected_edges": number(r),
        "constant_negative_score_on_own_selected_edges": number(1-r),
        "uniform_fixed_count_sign_shuffle_mean": number(null),
        "uniform_fixed_count_sign_shuffle_variance": number(null_variance),
        "observed_minus_shuffle_mean_pp": number(100*(score-null)),
    })
    return out, (q, a, b, score, null)


def small_enumeration_check():
    """Independently verify expectation/variance by enumerating a toy pool."""
    n, same, pos = 6, 4, 2
    values = []
    for chosen in combinations(range(n), pos):
        chosen = set(chosen)
        correct = sum((i in chosen) == (i < same) for i in range(n))
        values.append(F(correct, n))
    mean = sum(values) / len(values)
    var = sum((x-mean)**2 for x in values) / len(values)
    q, r = F(pos, n), F(same, n)
    assert mean == q*r + (1-q)*(1-r)
    assert var == F(4, n*n)*pos*r*(1-r)*F(n-pos, n-1)
    return {"enumerated_assignments": len(values), "expectation_verified": True,
            "variance_verified": True}


def main():
    methods, internal = {}, {}
    for name, row in INPUTS.items():
        methods[name], internal[name] = method(row)
    qA, aA, bA, sA, nullA = internal["AAI"]
    qN, aN, bN, sN, nullN = internal["NLI"]
    gap, dq = sA-sN, qA-qN
    components = {
        "NLI_stratum_rates_reference": (dq*(aN-bN), qA*(aA-aN)+(1-qA)*(bA-bN)),
        "AAI_stratum_rates_reference": (dq*(aA-bA), qN*(aA-aN)+(1-qN)*(bA-bN)),
        "symmetric_reference": (dq*((aA+aN)-(bA+bN))/2,
                                (qA+qN)*(aA-aN)/2+(2-qA-qN)*(bA-bN)/2),
    }
    for comp, within in components.values():
        assert comp + within == gap
    result = {
        "analysis_type": "published_aggregate_reconstruction_and_mathematical_null",
        "source": {"url": SOURCE, "version": "v2", "date": "2026-08-08",
                   "locations": ["section 4, equation (3)", "section 5.2, Table 3 and adjacent prose"]},
        "archive": {"requested": "pm_relations_code.zip", "found_in_accessible_home": False,
                    "raw_E1_reproduced": False,
                    "search_scope": "accessible local files; some OS-protected directories were inaccessible"},
        "unverified_external_claim": {"TF_IDF_percent": "72.9",
                                           "status": "not found in v2 text; archive unavailable"},
        "inputs": INPUTS,
        "reconstruction_assumptions": [
            "Published totals and positive-only denominators refer to the same pooled resolved selected-edge populations.",
            "Positive percentages are rounded to nearest 0.1 percentage point; the compatible numerators are inferred, not provided raw data.",
            "A positive sign is compatible exactly for equal binary outcomes and a negative sign exactly for unequal binary outcomes."
        ],
        "methods": methods,
        "observed_AAI_minus_NLI_pp": number(100*gap),
        "descriptive_decompositions_pp": {
            name: {"composition": number(100*comp), "within_sign": number(100*within)}
            for name, (comp, within) in components.items()},
        "equal_half_sign_weights_AAI_minus_NLI_pp": number(50*((aA-aN)+(bA-bN))),
        "shuffle_mean_AAI_minus_NLI_pp": number(100*(nullA-nullN)),
        "excess_over_own_shuffle_AAI_minus_NLI_pp": number(100*((sA-nullA)-(sN-nullN))),
        "independent_common_probability_toys": [
            {"event_probability": number(p), "equal_outcome_probability": number(p*p+(1-p)**2),
             "expected_score_by_published_resolved_sign_mix": {
                 name: number(q*(p*p+(1-p)**2)+(1-q)*2*p*(1-p))
                 for name, (q, _, _, _, _) in internal.items()}}
            for p in [F(1,20), F(1,10), F(1,5), F(1,2)]],
        "checks": {"exact_mixture_identity": True, "exact_decomposition_identity": True,
                   "rounding_counts_unique": True, "toy_sign_shuffle": small_enumeration_check()},
        "limits": ["No raw-data replication, human semantic accuracy estimate, causal attribution, confidence interval or p-value.",
                   "The methods select different endpoint sets, including within each sign stratum.",
                   "Global sign exchangeability is a diagnostic stipulation, not justified by the aggregates; block-aware resampling requires pair-level data.",
                   "Uniform-shuffle variance is mathematical under that null and is not a graph-aware sampling uncertainty estimate."]
    }
    path = Path(__file__).with_name("metric_null_results.json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(path), "observed_gap_pp": float(100*gap),
                      "symmetric_composition_pp": float(100*components["symmetric_reference"][0]),
                      "shuffle_means_percent": {k: 100*v[4].numerator/v[4].denominator for k,v in internal.items()},
                      "all_checks_passed": True}, indent=2))


if __name__ == "__main__":
    main()
