"""Train a new, small information-restricted predictor. Offline, deterministic, no pretrained LLM."""

from collections import Counter, defaultdict
from math import exp, log
from statistics import mean
import json
from prepare import ROOT, DATA, read_csv
from audit import binary_metrics


def fit(train):
    counts = [Counter(), Counter()]
    terms = set()
    class_count = Counter()
    for feats, y in train:
        counts[y].update(feats)
        terms.update(feats)
        class_count[y] += 1
    # Binary features with multinomial Naive Bayes, Laplace smoothing.
    mass = [sum(c.values()) + len(terms) for c in counts]
    weights = {
        t: log((counts[1][t] + 1) / mass[1]) - log((counts[0][t] + 1) / mass[0])
        for t in terms
    }
    return log((class_count[1] + 1) / (class_count[0] + 1)), weights


def score(model, feats):
    intercept, weights = model
    z = intercept + sum(weights.get(t, 0) for t in sorted(feats))
    return 1 / (1 + exp(-max(-700, min(z, 700))))


def evaluate():
    rows = read_csv(DATA / "kota_votes.csv")
    features = {
        r["row"]: set(map(int, r["buckets"].split()))
        for r in read_csv(DATA / "blind_features.csv")
    }
    groups = defaultdict(list)
    for r in rows:
        groups[r["group"]].append(r)
    train, test = [], []
    for group in groups.values():
        dates = [r["close_date"] for r in group]
        if all(dates) and max(dates) < "2025-10-01":
            train.extend(group)
        elif all(dates) and min(dates) >= "2025-10-01":
            test.extend(group)
    samples = [(features[r["row"]], int(r["y"])) for r in train]
    gold = [int(r["y"]) for r in test]
    clean = fit(samples)
    predictions = [score(clean, features[r["row"]]) for r in test]

    # Positive control deliberately encodes the gold label as eight synthetic tokens.
    def canary(y):
        return set(range(8192 + 8 * y, 8200 + 8 * y))

    contaminated = fit([(x | canary(y), y) for x, y in samples])
    leaky = [
        score(contaminated, features[r["row"]] | canary(y)) for r, y in zip(test, gold)
    ]
    flipped = [
        score(contaminated, features[r["row"]] | canary(1 - y))
        for r, y in zip(test, gold)
    ]
    correct_by_group = defaultdict(list)
    for row, p, y in zip(test, predictions, gold):
        correct_by_group[row["group"]].append((p >= 0.5) == y)
    return dict(
        method="binary-term multinomial NB, 8192 fixed hash buckets, alpha=1",
        train=len(train),
        test=len(test),
        test_groups=len(correct_by_group),
        text_only=binary_metrics(predictions, gold),
        macro_group_accuracy=mean(mean(v) for v in correct_by_group.values()),
        training_prevalence=binary_metrics(
            [mean(y for x, y in samples)] * len(gold), gold
        ),
        artificial_positive_control=binary_metrics(leaky, gold),
        flipped_canary=binary_metrics(flipped, gold),
    )


if __name__ == "__main__":
    (ROOT / "results" / "text_baseline.json").write_text(
        json.dumps(evaluate(), indent=2) + "\n"
    )
