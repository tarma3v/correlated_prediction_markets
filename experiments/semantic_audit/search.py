"""Paired event-component resampling and a closed cross-venue CPI challenge."""

import calendar
import hashlib
import itertools
import math
import operator
import random
import re
from collections import Counter, defaultdict
from decimal import Decimal
from statistics import mean

from common import STATES, div, read, tokens, write

VIEWS = ("title", "event_outcome", "full_rules", "structured")
SEARCH_MODELS = ("e5_small_v2", "bge_small_en_v1_5")


def event_components(rows):
    graph = defaultdict(set)

    def vertices(row):
        return (
            "P " + row["poly_event_title"].strip().casefold(),
            "K " + row["kalshi_event_title"].strip().casefold(),
        )

    for r in rows:
        a, b = vertices(r)
        assert len(a) > 2 and len(b) > 2
        graph[a].add(b)
        graph[b].add(a)
    mapping = {}
    for node in sorted(graph):
        if node in mapping:
            continue
        todo, component = [node], set()
        while todo:
            n = todo.pop()
            if n not in component:
                component.add(n)
                todo.extend(graph[n] - component)
        key = hashlib.sha256("\n".join(sorted(component)).encode()).hexdigest()[:16]
        mapping.update(dict.fromkeys(component, key))
    return [mapping[vertices(r)[0]] for r in rows]


def bootstrap(values):
    rng = random.Random(20261117)
    draws = sorted(mean(rng.choices(values, k=len(values))) for _ in range(2000))
    return [draws[49], draws[1949]]


def retrieval():
    refs = read("redesign/retrieval/reference_pairs.json")
    keys = [(r["poly_id"], r["kalshi_ticker"]) for r in refs]
    assert len(set(keys)) == len(keys)
    audit = []
    for r, key, component in zip(refs, keys, event_components(refs)):
        a, b = map(lambda t: set(tokens(t)), (r["poly_title"], r["kalshi_title"]))
        audit.append(
            dict(
                poly=key[0],
                kalshi=key[1],
                family=component,
                category=r["category"],
                label=r["label"],
                title_jaccard=len(a & b) / len(a | b),
                ranks={},
            )
        )
    summary = {}
    for model in SEARCH_MODELS:
        for view in ("title", "event_title"):
            file = f"comparison/retrieval/{model}_{view}_pair_ranks.json"
            by_key = {(x["poly_id"], x["kalshi_ticker"]): x for x in read(file)}
            assert set(by_key) == set(keys)
            for key, rec in zip(keys, audit):
                r = by_key[key]
                assert r["reference_label"] == rec["label"]
                rec["ranks"][f"{model}_{view}"] = [
                    r["kalshi_rank_for_poly"],
                    r["poly_rank_for_kalshi"],
                ]
        summary[model] = {}
        for cohort, rows in [
            ("known_same", [r for r in audit if r["label"] == "same"]),
            (
                "low_jaccard_same",
                [
                    r
                    for r in audit
                    if r["label"] == "same" and r["title_jaccard"] <= 0.25
                ],
            ),
            ("known_different", [r for r in audit if r["label"] == "different"]),
        ]:
            groups = defaultdict(list)
            for r in rows:
                groups[r["family"]].append(r)
            by_k = {}
            for k in (1, 5, 20):
                families = []
                for g in sorted(groups):
                    families.append(
                        [
                            mean(
                                rank <= k
                                for r in groups[g]
                                for rank in r["ranks"][f"{model}_{v}"]
                            )
                            for v in ("title", "event_title")
                        ]
                    )
                diff = [b - a for a, b in families]
                by_k[str(k)] = {
                    "title_macro": mean(a for a, b in families),
                    "event_macro": mean(b for a, b in families),
                    "delta": mean(diff),
                    "ci95_family": bootstrap(diff),
                    "family_win_tie_loss": [
                        sum(x > 0 for x in diff),
                        sum(x == 0 for x in diff),
                        sum(x < 0 for x in diff),
                    ],
                    "directed_hits": [
                        sum(n <= k for r in rows for n in r["ranks"][f"{model}_{v}"])
                        for v in ("title", "event_title")
                    ],
                }
            summary[model][cohort] = {
                "pairs": len(rows),
                "components": len(groups),
                "k": by_k,
            }
    write("author_ranks.jsonl", audit, lines=True)
    return summary


MONTH = "|".join(calendar.month_name[1:])
DATE = re.compile(r"\b(" + MONTH + r") (20\d\d)\b", re.I)


def contextual_key(r):
    p = r["primary"]
    assert "food and energy" in p.lower() and "seasonally adjusted" in p.lower()
    assert "bureau of labor statistics" in p.lower()
    period = DATE.search(p)
    if not period:
        raise ValueError(r["id"])
    return "corecpi_us_bls_sa_mom " + "period" + "".join(period.groups()).lower()


def view(r, v):
    if v == "title":
        return r["title"]
    key = contextual_key(r)
    # Kalshi's E02 schema omits event title; it does include an outcome subtitle.
    event = r.get("event_title", "")
    outcome = r.get("subtitle", "")
    base = " ".join([event, r["title"], outcome]).strip()
    if v == "event_outcome":
        return base
    if v == "full_rules":
        # The event description repeats the Polymarket market description verbatim.
        return " ".join(dict.fromkeys([base, r["primary"], r["secondary"]]))
    return base + (" " + key) * 4


def vectors(corpus):
    counts = [Counter(tokens(t)) for t in corpus]
    df = Counter(token for doc in counts for token in doc)
    vectors = []
    for doc in counts:
        vec = {
            t: n * (math.log((1 + len(counts)) / (1 + df[t])) + 1)
            for t, n in doc.items()
        }
        norm = math.sqrt(sum(v * v for v in vec.values()))
        vectors.append({t: v / norm for t, v in vec.items()})
    return vectors


def condition(r):
    if r["venue"] == "polymarket":
        m = re.search(r"be ([-\d.]+)%( or lower| or higher)?\?", r["title"])
        return {None: "eq", " or lower": "le", " or higher": "ge"}[m[2]], Decimal(m[1])
    m = re.search(r"increases by above ([-\d.]+)%", r["primary"])
    return "gt", Decimal(m[1])


OPS = {"le": operator.le, "ge": operator.ge, "eq": operator.eq, "gt": operator.gt}


def truth_table(a, b, shared, continuous=False):
    # Include each boundary, exterior tails and each nonempty interval cell.
    bounds = sorted({a[1], b[1]})
    points = [bounds[0] - 1, *bounds, bounds[-1] + 1]
    for left, right in zip(bounds, bounds[1:]):
        mid = (left + right) / 2 if continuous else left + Decimal(".1")
        if mid < right:
            points.append(mid)
    values = ((x, x) for x in points) if shared else itertools.product(points, repeat=2)
    out = {}
    for x, y in values:
        s = f"{int(OPS[a[0]](x,a[1]))}{int(OPS[b[0]](y,b[1]))}"
        out.setdefault(s, [str(x), str(y)])
    return out


def typed(forbid):
    f = frozenset(forbid)
    mapping = {
        (): "free",
        ("01",): "B_implies_A",
        ("10",): "A_implies_B",
        ("11",): "exclusive",
        ("00",): "exhaustive",
        ("01", "10"): "equivalent",
        ("00", "11"): "complement",
    }
    return mapping[tuple(sorted(f))]


def cpi():
    corpus = read("experiments/e02/acquisition/2026-11-14/corpus.jsonl", lines=True)
    poly = [r for r in corpus if r["venue"] == "polymarket"]
    kal = [r for r in corpus if r["venue"] == "kalshi"]
    assert len(poly) == 7 and len(kal) == 55 and len({r["id"] for r in corpus}) == 62
    raw_poly = read("experiments/e02/acquisition/2026-11-14/raw/polymarket_event.json")
    raw_kal = read("experiments/e02/acquisition/2026-11-14/raw/kalshi_markets.json")
    assert raw_poly["title"] == "Core CPI MoM - November 2026"
    # External identifiers / independently stored outcome/strike fields cross-check text parsing.
    tags = {m["id"]: m["groupItemTitle"] for m in raw_poly["markets"]}
    kal_strikes = {m["ticker"]: m for m in raw_kal["markets"]}
    pairs, by_poly = [], defaultdict(list)
    for p, k in itertools.product(poly, kal):
        ap, bk = condition(p), condition(k)
        tag = tags[p["id"]]
        value = Decimal(re.search(r"-?\d+\.\d+", tag)[0])
        assert value == ap[1]
        assert (tag.startswith("≤") or "lower" in tag.lower()) == (ap[0] == "le") and (
            tag.endswith("+") or tag.startswith("≥") or "higher" in tag.lower()
        ) == (ap[0] == "ge")
        raw = kal_strikes[k["id"]]
        assert (
            raw["strike_type"] == "greater"
            and Decimal(str(raw["floor_strike"])) == bk[1]
        )
        shared = k["event_id"] == "KXCPICORE-26NOV"
        truth = truth_table(ap, bk, shared)
        forbidden = sorted(set(STATES) - truth.keys())
        row = dict(
            poly=p["id"],
            kalshi=k["id"],
            same_release=shared,
            poly_predicate=[ap[0], str(ap[1])],
            kalshi_predicate=[bk[0], str(bk[1])],
            normal_witnesses=truth,
            normal_forbidden=forbidden,
            normal_type=typed(forbidden),
            ranks={},
        )
        if shared:
            mutations = {}
            for name, b_mut, shared_mut, cont in [
                ("different_releases", bk, False, False),
                ("inclusive", ("ge", bk[1]), True, False),
                ("continuous", bk, True, True),
                ("inclusive_continuous", ("ge", bk[1]), True, True),
            ]:
                new = truth_table(ap, b_mut, shared_mut, cont)
                f = sorted(set(STATES) - new.keys())
                mutations[name] = dict(
                    type=typed(f),
                    forbidden=f,
                    lost_witnesses={s: new[s] for s in forbidden if s in new},
                    new_forbidden=sorted(set(f) - set(forbidden)),
                )
            row["scenarios"] = mutations
        pairs.append(row)
        by_poly[p["id"]].append(row)
    assert all(bool(r["normal_forbidden"]) == r["same_release"] for r in pairs)
    for v in VIEWS:
        docs = vectors([view(m, v) for m in poly + kal])
        for i, p in enumerate(poly):
            q = docs[i]

            def score(j):
                return sum(w * docs[len(poly) + j].get(t, 0.0) for t, w in q.items())

            order = sorted(range(len(kal)), key=lambda j: (-score(j), kal[j]["id"]))
            ranks = {kal[j]["id"]: idx + 1 for idx, j in enumerate(order)}
            for r in by_poly[p["id"]]:
                r["ranks"][v] = ranks[r["kalshi"]]
    stats = {}
    for v in VIEWS:
        stats[v] = {}
        for k in (1, 5, 20):
            hits = sum(
                bool(r["normal_forbidden"]) and r["ranks"][v] <= k for r in pairs
            )
            stats[v][str(k)] = dict(
                hits=hits, recall=div(hits, 77), precision=div(hits, len(poly) * k)
            )
    shared = [r for r in pairs if r["same_release"]]
    mutation = {}
    for name in shared[0]["scenarios"]:
        m = [r["scenarios"][name] for r in shared]
        mutation[name] = dict(
            changed_pairs=sum(x["type"] != r["normal_type"] for x, r in zip(m, shared)),
            lost_forbidden=sum(len(x["lost_witnesses"]) for x in m),
            gained_forbidden=sum(len(x["new_forbidden"]) for x in m),
            types=dict(Counter(x["type"] for x in m)),
        )
    write("cpi_pairs.jsonl", pairs, lines=True)
    return dict(
        pairs=len(pairs),
        shared_pairs=len(shared),
        normal_types=dict(Counter(r["normal_type"] for r in shared)),
        forbidden_normal=sum(len(r["normal_forbidden"]) for r in shared),
        retrieval=stats,
        mutations=mutation,
    )
