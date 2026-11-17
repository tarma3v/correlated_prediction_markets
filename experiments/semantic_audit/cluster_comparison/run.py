"""Matched-budget retrieval with or without an unsupervised hard topic partition."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUTS = {}


def input_path(name):
    path = ROOT / name
    INPUTS[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


def read(name, lines=False):
    s = input_path(name).read_text()
    return [json.loads(line) for line in s.splitlines()] if lines else json.loads(s)


def tfidf(texts):
    words = [Counter(re.findall("[a-z0-9]+", t.casefold())) for t in texts]
    vocab = sorted(set().union(*(r.keys() for r in words)))
    index = {v: i for i, v in enumerate(vocab)}
    data = np.zeros((len(texts), len(vocab)), dtype=np.float64)
    for i, r in enumerate(words):
        for term, count in r.items():
            data[i, index[term]] = count
    data *= 1 + np.log((len(texts)+1) / (1+(data > 0).sum(axis=0)))
    return normalize(data)


def normalize(a):
    return a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1.e-15)


def clusters(x, n, seed):
    """Spherical Lloyd updates with k-means++ initialization on unit vectors."""
    rng = np.random.default_rng(seed)
    centers = [x[rng.integers(len(x))]]
    for _ in range(n-1):
        distances = np.maximum(0., 1-(x @ np.stack(centers).T).max(axis=1))
        if not distances.sum():
            raise ValueError("Insufficient distinct vectors")
        centers.append(x[rng.choice(len(x), p=distances/distances.sum())])
    centers = np.stack(centers)
    old = None
    for _ in range(100):
        labels = (x @ centers.T).argmax(axis=1)
        if old is not None and np.array_equal(old, labels):
            return labels
        if len(set(labels)) != n:
            raise ValueError("Empty cluster")
        centers = normalize(np.stack([x[labels == i].mean(axis=0) for i in range(n)]))
        old = labels
    raise ValueError("Failed to converge")


def union_order(a, b):
    seen, out = set(), []
    for x, y in zip(a, b):
        for item in (x, y):
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def orders(first, second):
    a = np.argsort(-first, axis=1, kind="stable")
    b = np.argsort(-second, axis=1, kind="stable")
    return [(list(x), list(y), union_order(x, y)) for x, y in zip(a, b)]


def evaluate(orders_by_query, truth, src, target, limit):
    counts = Counter(queries=len(truth), possible_hits=sum(map(len, truth.values())))
    for q, relevant in truth.items():
        channel_a, channel_b, merged = orders_by_query[q]
        cluster = set(np.where(target == src[q])[0])
        restricted = [j for j in merged if j in cluster][:limit]
        budget = len(restricted)
        assert budget == min(len(cluster), limit) and set(restricted) <= cluster
        counts["budget_per_method"] += budget
        counts["empty_queries"] += int(not budget)
        counts["known_outside_cluster"] += len(relevant-cluster)
        selections = dict(cluster=restricted, union=merged[:budget], first=channel_a[:budget],
                          second=channel_b[:budget], union_full_budget=merged[:limit])
        for m, selected in selections.items():
            if m != "union_full_budget":
                assert len(set(selected)) == budget
            counts["hits_"+m] += len(relevant.intersection(selected))
    return counts


def author_data():
    ref = read("redesign/retrieval/reference_pairs.json")
    markets = read("redesign/retrieval/markets.json")
    ids = read("comparison/retrieval/embedding_row_ids.json")
    assert ids == {v: [x["id"] for x in markets[v]] for v in markets}
    emb = np.load(input_path("comparison/retrieval/e5_small_v2_event_title_embeddings.npz"))
    vectors = normalize(np.concatenate((emb["poly"], emb["kalshi"])).astype(float))
    n = len(ids["poly"])
    score = np.load(input_path("comparison/retrieval/e5_small_v2_event_title_scores.npy"))
    assert np.allclose(vectors[:n] @ vectors[n:].T, score, atol=1.e-6)
    words = tfidf([r["event_title"]+" "+r["title"] for v in ("poly","kalshi") for r in markets[v]])
    gold = {(ids["poly"].index(r["poly_id"]), ids["kalshi"].index(r["kalshi_ticker"]))
            for r in ref if r["label"] == "same"}
    return vectors, score, words[:n] @ words[n:].T, gold, (8, 16, 32)


def cpi_data():
    corpus = read("experiments/e02/acquisition/2026-11-14/corpus.jsonl", True)
    pairs = read("experiments/semantic_audit/cpi_pairs.jsonl", True)
    p, k = (sorted((r for r in corpus if r["venue"] == v), key=lambda r:r["id"])
            for v in ("polymarket","kalshi"))
    title = tfidf([r["title"] for r in p+k])
    full = tfidf([" ".join(r.get(f,"") for f in ("event_title","title","subtitle","primary","secondary"))
                  for r in p+k])
    pi, ki = {r["id"]:i for i,r in enumerate(p)}, {r["id"]:i for i,r in enumerate(k)}
    gold = {(pi[r["poly"]],ki[r["kalshi"]]) for r in pairs if r["normal_forbidden"]}
    assert len(pairs) == len(p)*len(k) == 385 and len(gold) == 77
    n = len(p)
    return full, full[:n] @ full[n:].T, title[:n] @ title[n:].T, gold, (2, 3, 5)


def main(out):
    rows = []
    for data, builder in (("author",author_data),("author_centered",author_data),("cpi",cpi_data)):
        vec, a, b, gold, counts = builder()
        n = a.shape[0]
        if data == "author_centered":
            # Exploratory sensitivity after observing single-venue clusters.
            vec = normalize(np.concatenate([v - v.mean(axis=0) for v in (vec[:n], vec[n:])]))
        for forward in ((True, False) if data.startswith("author") else (True,)):
            order = orders(a, b) if forward else orders(a.T, b.T)
            truth = {}
            for i,j in sorted(gold):
                source, dest = (i,j) if forward else (j,i)
                truth.setdefault(source,set()).add(dest)
            for c in counts:
                for seed in (17,29,53):
                    labels = clusters(vec,c,seed)
                    source, target = (labels[:n], labels[n:]) if forward else (labels[n:], labels[:n])
                    for budget in (5,20):
                        rows.append(dict(data=data, direction="P_to_K" if forward else "K_to_P",
                                         clusters=c, seed=seed, k=budget,
                                         **evaluate(order,truth,source,target,budget)))
    out.mkdir(parents=True,exist_ok=True)
    with (out/"results.csv").open("w",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (HERE/"run.py", HERE/"PROTOCOL_RU.md",out/"results.csv")}
    (out/"manifest.json").write_text(json.dumps({"input_sha256":INPUTS,"file_sha256":hashes,
                                                 "numpy":np.__version__},indent=2)+"\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE)
