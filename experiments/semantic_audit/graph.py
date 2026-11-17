"""Leave-one-edge-out inference on archived, unedited NLI predictions."""

from collections import Counter, defaultdict
from decimal import Decimal
import re
from statistics import mean

from common import STATES, read, write
from search import bootstrap

CLAIMS = {
    "exclusion_candidate": {"11"},
    "equivalence_candidate": {"01", "10"},
    "a_implies_b_candidate": {"10"},
    "b_implies_a_candidate": {"01"},
    "abstain": set(),
}


def confidence(p):
    a, b = p["a_to_b"], p["b_to_a"]
    strength = {
        "exclusion_candidate": (a["contradiction"] + b["contradiction"]) / 2,
        "equivalence_candidate": min(a["entailment"], b["entailment"]),
        "a_implies_b_candidate": a["entailment"],
        "b_implies_a_candidate": b["entailment"],
    }
    return strength.get(p["nli_candidate_type"])


def scalar(m):
    match = re.search(
        r"(at least|more than|above)\s+(-?\d+(?:\.\d+)?)", m["primary"], re.I
    )
    if not match:
        raise ValueError(m["id"])
    return match[1].lower() == "at least", Decimal(match[2])


def reference(a, b):
    incl_a, t_a = scalar(a)
    incl_b, t_b = scalar(b)
    values = {min(t_a, t_b) - 1, t_a, t_b, (t_a + t_b) / 2, max(t_a, t_b) + 1}
    witnesses = {}
    for x in sorted(values):
        key = str(int(x > t_a or incl_a and x == t_a)) + str(
            int(x > t_b or incl_b and x == t_b)
        )
        witnesses.setdefault(key, str(x))
    return witnesses


def arcs(a, b, forbidden):
    for s in forbidden:
        x, y = map(int, s)
        yield (a, x), (b, 1 - y)
        yield (b, y), (a, 1 - x)


def contradiction(graph, assumptions, skip):
    todo, visited = list(assumptions), set()
    while todo:
        vertex = todo.pop()
        if vertex in visited:
            continue
        name, bit = vertex
        if (name, 1 - bit) in visited:
            return True
        visited.add(vertex)
        todo.extend(
            dest
            for dest, edge in graph.get(vertex, ())
            if edge != skip and dest not in visited
        )
    return False


def evaluate_graph():
    markets = {r["id"]: r for r in read("pilot/markets.json")}
    provenance = read("extension/nlp/corpus_run_manifest.json")
    preds = read("extension/nlp/corpus_nli_predictions.json")
    templates = {
        tuple(sorted((r["a"], r["b"]))): r["group_key"]
        for r in read("extension/retrieval/results/threshold_candidates.json")
    }
    groups = defaultdict(list)
    for p in preds:
        key = tuple(sorted([p["a"], p["b"]]))
        if key in templates:
            groups[templates[key]].append(p)
    records = []
    for group, rows in groups.items():
        graph = defaultdict(list)
        for idx, p in enumerate(rows):
            claim = CLAIMS[p["nli_candidate_type"]]
            for source, dest in arcs(p["a"], p["b"], claim):
                graph[source].append((dest, idx))
        assert len({tuple(sorted((p["a"], p["b"]))) for p in rows}) == len(rows)
        for idx, p in enumerate(rows):
            a, b = p["a"], p["b"]
            assert markets[a]["event_id"] == markets[b]["event_id"]
            wit = reference(markets[a], markets[b])
            gold = set(STATES) - wit.keys()
            assert len(gold) == 1 and "11" in wit
            claim = CLAIMS[p["nli_candidate_type"]]
            blocked = {
                s
                for s in STATES
                if contradiction(graph, [(a, int(s[0])), (b, int(s[1]))], idx)
            }
            forced_false = [n for n in (a, b) if contradiction(graph, [(n, 1)], idx)]
            assert "00" not in blocked
            record = dict(
                a=a,
                b=b,
                series=a.split("-")[0],
                family=group,
                claim=p["nli_candidate_type"],
                confidence=confidence(p),
                claimed_forbidden=sorted(claim),
                witnesses=wit,
                ref_forbidden=sorted(gold),
                wrong_claim_witnesses={s: wit[s] for s in sorted(claim - gold)},
                alternate_forbidden=sorted(blocked),
                alternate_forced_false=forced_false,
                corroborated=bool(claim) and claim <= blocked,
                exact=claim == gold,
                sound=bool(claim) and claim <= gold,
            )
            records.append(record)
    summary = {}
    for series in sorted({r["series"] for r in records}):
        rows = [r for r in records if r["series"] == series]
        active = [r for r in rows if r["claim"] != "abstain"]
        corroborated = [r for r in active if r["corroborated"]]
        plain = sorted(active, key=lambda r: (-r["confidence"], r["a"], r["b"]))[
            : len(corroborated)
        ]
        baseline = {(r["a"], r["b"]) for r in plain}
        for r in rows:
            r["matched_confidence_selection"] = (r["a"], r["b"]) in baseline
        summary[series] = dict(
            n=len(rows),
            n_active=len(active),
            raw_sound=sum(r["sound"] for r in active),
            n_selected=len(corroborated),
            graph_sound=sum(r["sound"] for r in corroborated),
            confidence_sound=sum(r["sound"] for r in plain),
            forced_false_among_selected=sum(
                bool(r["alternate_forced_false"]) for r in corroborated
            ),
        )
    total = {
        k: sum(v[k] for v in summary.values()) for k in next(iter(summary.values()))
    }
    delta = [
        (v["graph_sound"] - v["confidence_sound"]) / v["n_selected"]
        for v in summary.values()
        if v["n_selected"]
    ]
    # Precision of the restricted rule-only control is measured against enumerated worlds.
    rule_agrees = 0
    for r in records:
        ai, at = scalar(markets[r["a"]])
        bi, bt = scalar(markets[r["b"]])
        assert ai == bi and at != bt
        inferred = "10" if at > bt else "01"
        rule_agrees += [inferred] == r["ref_forbidden"]
    write("graph_edges.jsonl", records, lines=True)
    return dict(
        model=provenance["model"],
        raw_pairs=len(preds),
        template_groups=len(groups),
        by_series=summary,
        totals=total,
        macro_graph_minus_confidence=mean(delta),
        descriptive_family_ci95=bootstrap(delta),
        threshold_order_exact=rule_agrees,
        both_yes_control_flags_exclusion=sum(
            r["claim"] == "exclusion_candidate" for r in records
        ),
        corroborated_error_types=dict(
            Counter(r["claim"] for r in records if r["corroborated"] and not r["sound"])
        ),
    )
