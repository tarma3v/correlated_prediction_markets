"""Score the original branches at the same expected state coverage within tie blocks."""

from collections import Counter, defaultdict
from common import STATES, div, read

METHODS = (
    "direct",
    "structured",
    "repeat",
    "critic",
    "structured_checked",
    "critic_checked",
    "rule_only",
)
TARGETS = (0.50, 0.75, 0.90)


def coverage(rows, target):
    groups = defaultdict(list)
    capacity = len(rows) * 4
    for r in rows:
        if r["format_error"]:
            continue
        for key, value in r["states"].items():
            if value != "unknown":
                groups[r["confidence"]].append((r["reference"][key], value))
    remaining = target * capacity
    counts = Counter()
    for conf, states in sorted(groups.items(), reverse=True):
        w = min(1.0, remaining / len(states))
        if w <= 0:
            break
        for ref, decision in states:
            counts[ref, decision] += w
        remaining -= w * len(states)
    tp = counts["forbidden", "forbidden"]
    fp = counts["possible", "forbidden"]
    answered = sum(counts.values())
    return dict(
        target=target,
        actual=div(answered, capacity),
        eligible_capacity=sum(map(len, groups.values())) / capacity,
        expected_false_forbidden=fp,
        expected_forbidden=tp + fp,
        false_forbidden_risk=div(fp, fp + counts["possible", "possible"]),
        precision_forbidden=div(tp, tp + fp),
        any_error=div(fp + counts["forbidden", "possible"], answered),
    )


def transitions(before, after):
    counts = Counter()
    for k in before:
        a, b = before[k], after[k]
        if a["format_error"] or b["format_error"]:
            counts[
                "format_pair:"
                + str(bool(a["format_error"]))
                + "->"
                + str(bool(b["format_error"]))
            ] += 1
            continue

        def status(row, state):
            submitted = row["states"][state]
            if submitted == "unknown":
                return submitted
            return "correct" if submitted == row["reference"][state] else "wrong"

        for state in STATES:
            counts[status(a, state) + "->" + status(b, state)] += 1
    return dict(sorted(counts.items()))


def llm():
    base = "experiments/week1/"
    summaries = read(base + "results/observed/summary.json")
    calls = read(base + "results/observed/predictions.jsonl", lines=True)
    config = read(base + "config.json")
    preds = read(base + "results/observed/evaluated.json")
    refs = {
        r["case_id"]: r
        for r in read(base + "data/reference.json")
        if r["kind"] == "controlled_decidable"
    }
    packets = {r["case_id"]: r for r in read(base + "data/packets.json")}
    assert all(
        c["packet_sha256"] == packets[c["case_id"]]["packet_sha256"] for c in calls
    )
    assert len({(c["branch"], c["case_id"]) for c in calls}) == 96
    by = {}
    by_pattern = defaultdict(dict)
    metrics = {}
    for method in METHODS:
        rs = [r for r in preds if r["method"] == method and r["case_id"] in refs]
        by[method] = {r["case_id"]: r for r in rs}
        assert len(rs) == len(refs) == 16 and all(
            refs[r["case_id"]]["states"] == r["reference"] for r in rs
        )
        metrics[method] = {str(q): coverage(rs, q) for q in TARGETS}
        for pattern in sorted({r["pattern"] for r in rs}):
            by_pattern[pattern][method] = coverage(
                [r for r in rs if r["pattern"] == pattern], 0.75
            )
    common = [
        k
        for k in refs
        if all(
            not by[m][k]["format_error"]
            and set(by[m][k]["states"].values()) <= {"possible", "forbidden"}
            for m in ("direct", "structured")
        )
    ]
    comparisons = [
        ("direct", "structured"),
        ("structured", "repeat"),
        ("structured", "critic"),
        ("structured", "structured_checked"),
        ("critic", "critic_checked"),
        ("repeat", "critic_checked"),
    ]
    paired = {a + "__" + b: transitions(by[a], by[b]) for a, b in comparisons}
    cost = {}
    for m in METHODS:
        orig = m.replace("_checked", "")
        steps = [orig] if orig not in ("repeat", "critic") else ["structured", orig]
        subset = [c for c in calls if c["case_id"] in refs and c["branch"] in steps]
        cost[m] = dict(
            calls=len(subset),
            input_tokens=sum(c["input_tokens"] for c in subset),
            output_tokens=sum(c["output_tokens"] or 0 for c in subset),
            llm_seconds=sum(c["seconds"] for c in subset),
        )
    checks = read(base + "results/observed/checker_audit.json")
    for m in METHODS:
        cost[m]["checker_seconds"] = sum(
            c["seconds"] for c in checks if c["method"] == m and c["case_id"] in refs
        )
    return dict(
        model=config["model"],
        cap_per_call=config["max_new_tokens_per_call"],
        cases=len(refs),
        templates=len(by_pattern),
        metrics=metrics,
        template_metrics=by_pattern,
        template_false_risk_structured_minus_direct={
            k: v["structured"]["false_forbidden_risk"]
            - v["direct"]["false_forbidden_risk"]
            for k, v in by_pattern.items()
            if v["structured"]["false_forbidden_risk"] is not None
            and v["direct"]["false_forbidden_risk"] is not None
        },
        common_complete_pairs=common,
        common_exact={
            m: sum(by[m][k]["states"] == by[m][k]["reference"] for k in common)
            for m in ("direct", "structured")
        },
        state_transitions=paired,
        cost_16_cases=cost,
        format_errors_24={
            m: summaries["methods"][m]["format_errors_all_24"] for m in METHODS
        },
    )
