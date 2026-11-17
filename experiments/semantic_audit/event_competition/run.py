"""Score archived cross-venue retrieval globally and inside each reference event."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from search import SEARCH_MODELS, bootstrap, event_components


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def top_one(row, target, indices):
    """Expected success under uniform tie-breaking among maxima in this pool."""
    scores = row[indices]
    value = row[target]
    return 0.0 if np.any(scores > value) else 1.0 / np.count_nonzero(scores == value)


def competition_groups(markets):
    groups = defaultdict(list)
    for i, market in enumerate(markets):
        event = market["event_title"].strip().casefold()
        if not event:
            raise ValueError(f"Missing event title for {market['id']}")
        groups[event].append(i)
    return {i: members for members in groups.values() for i in members}


def family_means(rows, metric):
    links = defaultdict(lambda: defaultdict(list))
    for row in rows:
        links[row["family"]][row["poly_id"], row["kalshi_ticker"]].append(row[metric])
    return [mean(mean(v) for v in links[f].values()) for f in sorted(links)]


def summarize(rows):
    if not rows:
        return None
    global_title, global_context, within_title, within_context, event_only = [
        family_means(rows, name) for name in
        ("global_title", "global_event_title", "within_title", "within_event_title", "event_only")
    ]
    global_gain = [b-a for a, b in zip(global_title, global_context)]
    within_gain = [b-a for a, b in zip(within_title, within_context)]
    differences = {
        "global_context_gain": global_gain,
        "within_context_gain": within_gain,
        "global_minus_within_gain": [g-w for g, w in zip(global_gain, within_gain)],
    }
    return {
        "directions": len(rows),
        "pairs": len({(r["poly_id"], r["kalshi_ticker"]) for r in rows}),
        "families": len(within_gain),
        "pool_sizes": dict(sorted(Counter(r["pool_size"] for r in rows).items())),
        "macro_top1": dict(global_title=mean(global_title), global_event_title=mean(global_context),
                          within_title=mean(within_title), within_event_title=mean(within_context),
                          within_event_only=mean(event_only)),
        "paired": {key: {"delta": mean(values), "family_interval95": bootstrap(values)}
                   for key, values in differences.items()},
    }


def run(out):
    inputs = {}

    def path(name):
        p = ROOT / name
        inputs[name] = digest(p)
        return p

    def read(name):
        return json.loads(path(name).read_bytes())

    ranks_dir = "comparison/retrieval/"
    refs = read("redesign/retrieval/reference_pairs.json")
    markets = read("redesign/retrieval/markets.json")
    row_ids = read(ranks_dir + "embedding_row_ids.json")
    assert row_ids == {venue: [r["id"] for r in rows] for venue, rows in markets.items()}
    indices = {v: {key: i for i, key in enumerate(keys)} for v, keys in row_ids.items()}
    groups = {venue: competition_groups(rows) for venue, rows in markets.items()}
    assert len(refs) == 493
    assert all(len(index) == len(refs) for index in indices.values())
    assert set(indices["poly"]) == {r["poly_id"] for r in refs}
    assert set(indices["kalshi"]) == {r["kalshi_ticker"] for r in refs}
    components = event_components(refs)
    full = np.arange(len(refs))
    records = []
    results = {}
    for model in SEARCH_MODELS:
        scores = {}
        for view in ("title", "event_title"):
            matrix = np.load(path(ranks_dir + f"{model}_{view}_scores.npy"), allow_pickle=False)
            assert matrix.shape == (len(full), len(full)) and np.isfinite(matrix).all()
            scores[view] = matrix

        rows = []
        for ref, family in zip(refs, components):
            if ref["label"] != "same":
                continue
            p = indices["poly"][ref["poly_id"]]
            k = indices["kalshi"][ref["kalshi_ticker"]]
            for target_venue, target in (("poly", p), ("kalshi", k)):
                members = groups[target_venue][target]
                row = dict(model=model, family=family, poly_id=ref["poly_id"],
                           kalshi_ticker=ref["kalshi_ticker"], target_venue=target_venue,
                           pool_size=len(members), event_only=1.0/len(members))
                for view, matrix in scores.items():
                    query_scores = matrix[:, k] if target_venue == "poly" else matrix[p, :]
                    row["global_" + view] = top_one(query_scores, target, full)
                    row["within_" + view] = top_one(query_scores, target, members)
                rows.append(row)

        assert len(rows) == 922
        ambiguous = [r for r in rows if r["pool_size"] > 1]
        results[model] = {
            "competing_outcomes": summarize(ambiguous),
            "competing_by_target": {v: summarize([r for r in ambiguous if r["target_venue"] == v])
                                    for v in ("poly", "kalshi")},
            "singleton": summarize([r for r in rows if r["pool_size"] == 1]),
        }
        records.extend(rows)
    out.mkdir(parents=True, exist_ok=True)
    with (out/"directions.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    summary = {
        "source_pairs": len(refs), "same_pairs": sum(r["label"] == "same" for r in refs),
        "models": results, "inputs_sha256": inputs, "code_sha256": digest(Path(__file__)),
        "shared_code_sha256": digest(HERE.parent/"search.py"),
        "protocol_sha256": digest(HERE/"PROTOCOL_RU.md"),
        "directions_sha256": digest(out/"directions.csv"),
    }
    (out/"results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE)
    run(parser.parse_args().output)
