"""Calibrate same-link retention outside each held-out author event component."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "experiments/semantic_audit"))
from search import SEARCH_MODELS, bootstrap, event_components


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def competitors(matrix):
    """Sorted top two scores per row; ties deliberately occupy both positions."""
    return np.sort(np.partition(matrix, -2, axis=1)[:, -2:], axis=1)


def best_other(top, value):
    return top[0] if value == top[1] else top[1]


def cutoff(scores):
    """Largest observed cutoff retaining at least 9/10 of calibration positives."""
    n = len(scores)
    if not n:
        raise ValueError("No positive calibration cases outside held-out component")
    n_keep = (9*n + 9)//10
    return sorted(scores, reverse=True)[n_keep-1]


def held_out_thresholds(rows):
    families = sorted({r["family"] for r in rows})
    positives = [r for r in rows if r["label"] == "same"]
    thresholds = {}
    for family in families:
        calibration = [r for r in positives if r["family"] != family]
        thresholds[family] = dict(calibration_pairs=len(calibration),
                                  calibration_components=len({r["family"] for r in calibration}),
                                  **{f"threshold_{m}": cutoff([r[m] for r in calibration])
                                     for m in ("cosine", "margin")})
    return thresholds


def summarize(rows, label):
    selected = [r for r in rows if r["label"] == label]
    by_family = defaultdict(list)
    for row in selected:
        by_family[row["family"]].append(row)
    macro = {}
    for m in ("cosine", "margin"):
        field = f"accepted_{m}"
        macro[m] = [mean(r[field] for r in by_family[f]) for f in sorted(by_family)]
    differences = [b-a for a, b in zip(macro["cosine"], macro["margin"])]
    return {
        "pairs": len(selected), "families": len(by_family),
        "accepted": {m: sum(r[f"accepted_{m}"] for r in selected) for m in macro},
        "macro_accepted": {m: mean(v) for m, v in macro.items()},
        "macro_margin_minus_cosine": mean(differences),
        "interval95_paired_families": bootstrap(differences),
        "paired_counts": dict(Counter(f"{r['accepted_cosine']}->{r['accepted_margin']}" for r in selected)),
    }


def run(out):
    inputs = {}

    def path(name):
        p = ROOT / name
        inputs[name] = sha(p)
        return p

    rank_dir = "comparison/retrieval/"
    refs = json.loads(path("redesign/retrieval/reference_pairs.json").read_bytes())
    ids = json.loads(path(rank_dir + "embedding_row_ids.json").read_bytes())
    index = {v: {x: i for i, x in enumerate(ls)} for v, ls in ids.items()}
    assert len(refs) == 493
    assert {r["poly_id"] for r in refs} == set(index["poly"])
    assert {r["kalshi_ticker"] for r in refs} == set(index["kalshi"])
    components = event_components(refs)
    all_rows, result = [], {}
    for model in SEARCH_MODELS:
        matrix = np.load(path(rank_dir + f"{model}_event_title_scores.npy"), allow_pickle=False)
        assert matrix.shape == (493, 493) and np.isfinite(matrix).all()
        best_by_poly = competitors(matrix)
        best_by_kalshi = competitors(matrix.T)
        rows = []
        for r, family in zip(refs, components):
            p, k = index["poly"][r["poly_id"]], index["kalshi"][r["kalshi_ticker"]]
            value = float(matrix[p, k])
            runner_up = max(float(best_other(best_by_poly[p], value)),
                            float(best_other(best_by_kalshi[k], value)))
            rows.append(dict(model=model, poly_id=r["poly_id"], kalshi_ticker=r["kalshi_ticker"],
                             family=family, label=r["label"], cosine=value, margin=value-runner_up))
        thresholds = held_out_thresholds(rows)
        for row in rows:
            row.update(thresholds[row["family"]])
            for name in ("cosine", "margin"):
                row["accepted_" + name] = int(row[name] >= row["threshold_" + name])
        result[model] = {label: summarize(rows, label) for label in ("same", "different")}
        all_rows.extend(rows)

    out.mkdir(parents=True, exist_ok=True)
    with (out/"predictions.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_rows)
    summary = {
        "source_labels": dict(Counter(r["label"] for r in refs)), "components": len(set(components)),
        "random_acceptance_probability": 0.9, "models": result, "inputs_sha256": inputs,
        "predictions_sha256": sha(out/"predictions.csv"), "code_sha256": sha(Path(__file__)),
        "shared_code_sha256": sha(ROOT/"experiments/semantic_audit/search.py"),
        "protocol_sha256": sha(HERE/"PROTOCOL_RU.md"),
    }
    (out/"results.json").write_text(json.dumps(summary, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE)
    run(parser.parse_args().output)
