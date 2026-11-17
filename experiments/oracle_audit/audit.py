"""Replay saved decisions and evaluate a group-disjoint temporal split offline."""

import json
from collections import defaultdict
from itertools import product
from statistics import mean, median
from random import Random
from prepare import ROOT, DATA, MODELS, read_csv

OUT = ROOT / "results"


def binary_metrics(probs, labels):
    n = len(labels)
    return dict(
        n=n,
        correct=sum((p >= 0.5) == y for p, y in zip(probs, labels)),
        accuracy=mean((p >= 0.5) == y for p, y in zip(probs, labels)),
        brier=mean((p - y) ** 2 for p, y in zip(probs, labels)),
    )


def select(rows, probs, keep):
    accepted = [(r, p) for r, p, k in zip(rows, probs, keep) if k]
    return dict(
        accepted=len(accepted),
        total=len(rows),
        coverage=len(accepted) / len(rows),
        errors=sum((p >= 0.5) != int(r["y"]) for r, p in accepted),
        accuracy=mean((p >= 0.5) == int(r["y"]) for r, p in accepted)
        if accepted
        else None,
    )


def p_yes(row, model):
    confidence = float(row[model + "_conf"])
    return confidence if row[model] == "YES" else 1 - confidence


def weighted_decision(row):
    yes = sum(float(row[m + "_conf"]) for m in MODELS if row[m] == "YES")
    no = sum(float(row[m + "_conf"]) for m in MODELS if row[m] == "NO")
    return int(yes >= no)


def paired_rounds(expected_n, expected_final_correct):
    team = json.loads((DATA / "team_archive_audit.json").read_text())
    counts = team["paired"]["B_round1_majority_vs_B_final"]
    both = counts["both_correct"]
    first_only = counts["a_only_correct"]
    final_only = counts["b_only_correct"]
    neither = counts["both_wrong"]
    total = both + first_only + final_only + neither
    if total != counts["valid_pairs"] or total != expected_n:
        raise ValueError("Paired round counts disagree with the archived sample size")
    if both + final_only != expected_final_correct:
        raise ValueError("Paired final-round total disagrees with the archived curve")
    return dict(
        source="data/team_archive_audit.json",
        pairs=total,
        both_correct=both,
        first_only_correct=first_only,
        final_only_correct=final_only,
        both_wrong=neither,
        first_correct=both + first_only,
        final_correct=both + final_only,
        net_correct_change=final_only - first_only,
    )


def kota():
    rows = read_csv(DATA / "kota_votes.csv")
    b_final = read_csv(DATA / "kota_b_final.csv")
    groups = defaultdict(list)
    for r in rows:
        groups[r["group"]].append(r)
    train, test, excluded = [], [], []
    for group in groups.values():
        dates = [r["close_date"] for r in group]
        if not all(dates):
            excluded.extend(group)
        elif max(dates) < "2025-10-01":
            train.extend(group)
        elif min(dates) >= "2025-10-01":
            test.extend(group)
        else:
            excluded.extend(group)
    assert set(r["group"] for r in train).isdisjoint(r["group"] for r in test)
    y = [int(r["y"]) for r in rows]
    paper = {m: sum((r[m] == "YES") == v for r, v in zip(rows, y)) for m in MODELS}
    paper.update(
        saved_A=sum((r["saved"] == "YES") == v for r, v in zip(rows, y)),
        weighted_A=sum(weighted_decision(r) == v for r, v in zip(rows, y)),
        curve_B_final=sum(int(r["correct"]) for r in b_final),
    )
    sets = {
        name: dict(rows=len(data), groups=len({r["group"] for r in data}))
        for name, data in [("train", train), ("test", test), ("excluded", excluded)]
    }
    train_y = [int(r["y"]) for r in train]
    test_y = [int(r["y"]) for r in test]

    def predict(data, weights):
        return [sum(w * p_yes(r, m) for w, m in zip(weights, MODELS)) for r in data]

    # Fit on early families. Deterministic grid; prefer equal weights in exact ties.
    grid = [
        (a / 10, b / 10, (10 - a - b) / 10)
        for a, b in product(range(11), repeat=2)
        if a + b <= 10
    ]
    weights = min(
        grid,
        key=lambda w: (
            binary_metrics(predict(train, w), train_y)["brier"],
            sum((x - 1 / 3) ** 2 for x in w),
            w,
        ),
    )
    ensemble = predict(test, weights)
    scores = {
        "training_prevalence": binary_metrics([mean(train_y)] * len(test), test_y),
        **{m: binary_metrics([p_yes(r, m) for r in test], test_y) for m in MODELS},
        "equal_p_yes": binary_metrics(predict(test, [1 / 3] * 3), test_y),
        "fitted_p_yes": binary_metrics(ensemble, test_y),
    }
    scores["paper_confidence_vote"] = {
        "n": len(test),
        "correct": sum(weighted_decision(r) == y for r, y in zip(test, test_y)),
    }

    def conf(r):
        return mean(float(r[m + "_conf"]) for m in MODELS)

    threshold = median(conf(r) for r in train)
    unanimity = [len({r[m] for m in MODELS}) == 1 for r in test]
    high_confidence = [conf(r) >= threshold for r in test]
    intersection = [u and h for u, h in zip(unanimity, high_confidence)]
    decisions = [weighted_decision(r) for r in test]
    ablations = {}
    for name, mask in (
        ("all", [True] * len(test)),
        ("unanimity_only", unanimity),
        ("confidence_only", high_confidence),
        ("intersection", intersection),
    ):
        metrics = select(test, decisions, mask)
        metrics["correct"] = metrics["accepted"] - metrics["errors"]
        metrics["deferred"] = len(test) - metrics["accepted"]
        ablations[name] = metrics
    gate = ablations["intersection"].copy()
    blocks = defaultdict(list)
    for j, row in enumerate(test):
        blocks[row["group"]].append(j)
    block_stats = []
    for indices in blocks.values():
        accepted = [j for j in indices if intersection[j]]
        block_stats.append(
            (
                len(accepted),
                sum(weighted_decision(test[j]) == test_y[j] for j in accepted),
            )
        )
    rng = Random(20261117)
    replicates = []
    for _ in range(4000):
        sample = rng.choices(block_stats, k=len(block_stats))
        n = sum(x[0] for x in sample)
        if n:
            replicates.append(sum(x[1] for x in sample) / n)
    replicates.sort()
    gate["series_bootstrap_percentile_95"] = [
        replicates[int(q * (len(replicates) - 1))] for q in (0.025, 0.975)
    ]
    full_gate = select(
        rows,
        [int(r["saved"] == "YES") for r in rows],
        [len({r[m] for m in MODELS}) == 1 and conf(r) >= 0.91 for r in rows],
    )
    lat = [float(r["wall_ms"]) for r in rows if r["wall_ms"]]
    return dict(
        n=len(rows),
        n_B_curve=len(b_final),
        archive_correct=paper,
        full_posthoc_gate=full_gate,
        split=sets,
        cut="2025-10-01",
        weights=dict(zip(MODELS, weights)),
        heldout=scores,
        training_confidence_median=threshold,
        heldout_gate=gate,
        heldout_selection_ablations=ablations,
        archive_B_rounds=paired_rounds(len(b_final), paper["curve_B_final"]),
        archive_A_wall_ms=dict(n=len(lat), median=median(lat), mean=mean(lat)),
    )


def nel():
    rows = read_csv(DATA / "nel_votes.csv")
    published = json.loads((DATA / "nel_published.json").read_text())
    out = {}
    for model in published:
        group = [r for r in rows if r["model"] == model]
        tagged = [r for r in group if r["raw_tag_p"] and r["answer"] in ("yes", "no")]
        safe = [r for r in tagged if r["y"] != ""]
        labels = [int(r["y"]) for r in safe]

        def disagreement(r, field):
            return (r["answer"] == "yes") != (float(r[field]) >= 0.5)

        out[model] = dict(
            archive_reported=published[model],
            n_rows=len(group),
            n_tagged=len(tagged),
            raw_disagrees_with_answer=sum(disagreement(r, "raw_tag_p") for r in tagged),
            stored_disagrees_with_answer=sum(
                disagreement(r, "stored_p") for r in tagged
            ),
            same_id_label_unambiguous=len(safe),
            distinct_groups=len({r["group"] for r in safe}),
            stored=binary_metrics([float(r["stored_p"]) for r in safe], labels),
            literal_tag=binary_metrics([float(r["raw_tag_p"]) for r in safe], labels),
            explicit_answer_correct=sum(
                (r["answer"] == "yes") == y for r, y in zip(safe, labels)
            ),
        )
    return out


def jev():
    rows = read_csv(DATA / "jev_choices.csv")
    # Each item was run twice. First repetition only for selective accuracy.
    unique = [r for r in rows if r["rep"] == "0"]

    def stats(rs):
        return dict(
            n=len(rs),
            correct=sum(r["answer"] == r["label"] for r in rs),
            accuracy=mean(r["answer"] == r["label"] for r in rs),
        )

    return dict(
        raw_calls=len(rows),
        unique_inputs=len({r["id"] for r in rows}),
        first_repeat=stats(unique),
        threshold_095=stats([r for r in unique if float(r["confidence"]) >= 0.95]),
        mean_recorded_usd=mean(float(r["usd"]) for r in rows),
        median_observed_ms=median(float(r["latency_ms"]) for r in rows),
    )


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, fn in [("kota", kota), ("nel", nel), ("jev", jev)]:
        (OUT / (name + ".json")).write_text(
            json.dumps(fn(), ensure_ascii=False, indent=2) + "\n"
        )
