"""Daily walk-forward prediction of prices of explicitly identified related contracts."""
import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
POLY_IDS = {"GA": 630692, "KS": 630746, "ME": 630772, "TX": 630963}
FED_OUTCOMES = ["no_change", "25_bp_cut", "50plus_bp_cut"]
DATES = {"senate": ("2026-01-01", "2026-11-02"), "fomc": ("2025-12-03", "2026-04-28")}
OWN = ["own", "own_change"]
CROSS = ["source_change", "gap"]
RNG_SEED = 49871
PLACEBOS = 199


def read_files(cache, offline):
    cache.mkdir(parents=True, exist_ok=True)
    objects = {}
    for entry in json.loads((ROOT / "sources.json").read_text()):
        path = cache / entry["file"]
        if not path.exists():
            if offline:
                raise FileNotFoundError(path)
            url = "https://raw.githubusercontent.com/{repo}/{revision}/{path}".format(**entry)
            with urlopen(url, timeout=90) as response:
                payload = response.read()
        else:
            payload = path.read_bytes()
        blob_header = f"blob {len(payload)}\0".encode()
        if hashlib.sha1(blob_header + payload).hexdigest() != entry["git_blob"] or (
            hashlib.sha256(payload).hexdigest() != entry["sha256"]
        ):
            raise ValueError(f"Source hash mismatch: {path}")
        if not path.exists():
            path.write_bytes(payload)
        objects[path.name] = pd.read_csv(io.BytesIO(payload),
                                         compression="gzip" if path.suffix == ".gz" else None)
    return objects


def series_by_date(data, date, columns):
    subset = data[[date, *columns]].copy()
    subset.index = pd.to_datetime(subset.pop(date), utc=True).dt.tz_convert(None).dt.normalize()
    if not subset.index.is_unique:
        raise ValueError("Duplicate contract day")
    return subset.sort_index()


def contract_prices(objects):
    for state, market_id in POLY_IDS.items():
        pm = objects[f"election_{state}_polymarket.csv.gz"]
        pm = pm[(pm.market_id == market_id) & (pm.outcome == "Yes")]
        k = objects[f"election_{state}_kalshi.csv.gz"]
        k = k[k.ticker == f"SENATE{state}-26-D"]
        prices = series_by_date(k, "date", ["price_close", "volume", "yes_bid_close", "yes_ask_close"])
        prices["kalshi"] = prices.price_close.where(prices.volume > 0)
        prices["spread"] = prices.yes_ask_close - prices.yes_bid_close
        pm = series_by_date(pm, "date", ["price"]).rename(columns={"price": "polymarket"})
        yield "senate", state, prices.join(pm, how="outer")
    for name in FED_OUTCOMES:
        df = objects[f"fomc_{name}.csv"]
        if not np.allclose(df.basis, df.polymarket_yes - df.kalshi_yes):
            raise ValueError("Source basis does not reconcile")
        df = series_by_date(df, "timestamp", ["polymarket_yes", "kalshi_yes"])
        yield "fomc", name, df.rename(columns={"polymarket_yes": "polymarket", "kalshi_yes": "kalshi"})


def build_examples(prices, target, delay):
    # An index t denotes the forecast origin after the UTC day t. Price labels are
    # observed at t+1, including only adjacent calendar days through reindexing.
    source = "kalshi" if target == "polymarket" else "polymarket"
    own, other = prices[target], prices[source].shift(delay)
    out = pd.DataFrame({
        "own": own, "own_change": own.diff(), "source_change": other.diff(),
        "gap": other - own, "actual": own.shift(-1),
        "both_changed": (own.diff().abs() > 1e-9) & (prices[source].diff().abs() > 1e-9),
    })
    if "spread" in prices:
        out["tight"] = prices.spread.between(0, 0.01 + 1e-9) & (prices.volume > 0)
    else:
        out["tight"] = False
    out["target_date"] = out.index + pd.Timedelta(days=1)
    return out.dropna(subset=OWN + CROSS + ["actual"])


def predict(train, test, columns, shift=0):
    x_train = train[columns].to_numpy(copy=True)
    if shift:
        shifted_level = np.roll((train.gap + train.own).to_numpy(), shift)
        x_train[:, -2] = np.roll(train.source_change.to_numpy(), shift)
        x_train[:, -1] = shifted_level - train.own.to_numpy()
    x_train = np.column_stack((np.ones(len(train)), x_train))
    x_test = np.column_stack((np.ones(len(test)), test[columns]))
    beta = np.linalg.lstsq(x_train, train.actual - train.own, rcond=None)[0]
    return np.clip(test.own.to_numpy() + x_test @ beta, 0, 1)


def evaluate(cohort, pair, prices, target, rng):
    dates = prices.index
    oos_dates = dates[len(dates) // 2:]
    same_day = build_examples(prices, target, 0)
    all_predictions, placebos, fold_sizes = [], [], []
    for fold, dates_part in enumerate(np.array_split(oos_dates.to_numpy(), 4), 1):
        first, last = map(pd.Timestamp, (dates_part[0], dates_part[-1]))
        for delay in (0, 1, 7):
            examples = same_day if delay == 0 else build_examples(prices, target, delay)
            # Same dates for all four models within a variant. Delay sensitivity uses
            # intersection with the main target dates AND available delayed signals.
            examples = examples.loc[examples.index.intersection(same_day.index)]
            train = examples[examples.target_date < first]
            test = examples[examples.target_date.between(first, last)]
            if test.empty:
                continue
            if len(train) < 15:
                raise ValueError(f"Insufficient data: {cohort}/{pair}/{target}/{fold}/{delay}")
            if not (train.target_date.max() <= test.index.min() and
                    (test.target_date - test.index == pd.Timedelta(days=1)).all()):
                raise ValueError("Time order violated")
            out = test[["target_date", "actual", "both_changed", "tight"]].copy()
            out["cohort"], out["pair"], out["target"], out["fold"], out["delay"] = cohort, pair, target, fold, delay
            out["persist"] = test.own
            out["own_only"] = predict(train, test, OWN)
            out["cross_change"] = predict(train, test, OWN + ["source_change"])
            out["cross_full"] = predict(train, test, OWN + CROSS)
            if delay:
                same_train, same_test = same_day.loc[train.index], same_day.loc[test.index]
                out["matched_current_change"] = predict(same_train, same_test, OWN + ["source_change"])
                out["matched_current_full"] = predict(same_train, same_test, OWN + CROSS)
            all_predictions.append(out)
            if delay == 0:
                fold_sizes.append(dict(cohort=cohort, pair=pair, target=target, fold=fold,
                                       train_n=len(train), test_n=len(test), last_train_label=str(train.target_date.max().date()),
                                       first_test_origin=str(test.index.min().date()), last_test_target=str(test.target_date.max().date())))
                ref_loss = np.abs(out.own_only - out.actual).sum()
                rolled = []
                # Shift only the training source feature vectors. Held-out data
                # retain their original temporal order for every placebo.
                for _ in range(PLACEBOS):
                    offset = int(rng.integers(7, len(train) - 6))
                    forecast = predict(train, test, OWN + CROSS, shift=offset)
                    rolled.append(float(ref_loss - np.abs(forecast - out.actual).sum()))
                placebos.append((len(test), np.array(rolled)))
    return pd.concat(all_predictions), placebos, fold_sizes


def metrics(df):
    errors = {m: 100 * (df[m] - df.actual) for m in ("persist", "own_only", "cross_change", "cross_full")}
    vals = {"rows": len(df), "dates": df.target_date.nunique()}
    vals.update({f"mae_{m}": e.abs().mean() for m, e in errors.items()})
    vals.update({f"rmse_{m}": np.sqrt(np.mean(e**2)) for m, e in errors.items()})
    vals["gain_pp"] = vals["mae_own_only"] - vals["mae_cross_full"]
    vals["gain_pct"] = 100 * vals["gain_pp"] / vals["mae_own_only"]
    vals["gain_vs_persist_pp"] = vals["mae_persist"] - vals["mae_cross_full"]
    return vals


def block_interval(df, rng, block_days=7, repetitions=2000):
    by_day = pd.DataFrame({
        "gain": 100 * ((df.own_only - df.actual).abs() - (df.cross_full - df.actual).abs()),
        "gain_vs_persist": 100 * ((df.persist - df.actual).abs() - (df.cross_full - df.actual).abs()),
        "count": 1, "date": df.target_date,
    }).groupby("date")[["gain", "gain_vs_persist", "count"]].sum()
    by_day = by_day.reindex(pd.date_range(by_day.index.min(), by_day.index.max()), fill_value=0)
    pairs = by_day.to_numpy()
    n = len(pairs)
    nblocks = (n + block_days - 1) // block_days
    starts = rng.integers(0, n, (repetitions, nblocks))
    ix = ((starts[:, :, None] + np.arange(block_days)) % n).reshape(repetitions, -1)[:, :n]
    totals = pairs[ix].sum(axis=1)
    sampled = totals[totals[:, 2] > 0]
    return np.quantile(sampled[:, :2] / sampled[:, 2:3], [0.025, 0.975], axis=0)


def describe(prices, cohort, pair):
    paired = prices.dropna(subset=["kalshi", "polymarket"])
    basis = 100 * (paired.polymarket - paired.kalshi)
    out = dict(cohort=cohort, pair=pair, n_paired=len(paired),
               mean_gap_pp=basis.mean(), mean_abs_gap_pp=basis.abs().mean(), max_abs_gap_pp=basis.abs().max())
    for venue in ("kalshi", "polymarket"):
        changes = 100 * prices[venue].diff().dropna()
        out[f"n_changes_{venue}"] = len(changes)
        out[f"sd_change_{venue}_pp"] = changes.std(ddof=1)
        out[f"unchanged_{venue}_pct"] = 100 * (changes.abs() <= 1e-9).mean()
    return out


def save(data, path):
    pd.DataFrame(data).to_csv(path, index=False, float_format="%.8f")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT.parents[1] / "sources" / "lead_lag")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    objects = read_files(args.cache, args.offline)
    rng = np.random.default_rng(RNG_SEED)
    forecasts, descriptive, fold_sizes, negatives = [], [], [], {}
    for cohort, pair, prices in contract_prices(objects):
        prices = prices.reindex(pd.date_range(*DATES[cohort]))
        if ((prices[["kalshi", "polymarket"]] < 0) | (prices[["kalshi", "polymarket"]] > 1)).any().any():
            raise ValueError("Invalid price")
        descriptive.append(describe(prices, cohort, pair))
        for target in ("polymarket", "kalshi"):
            pred, placebo, sizes = evaluate(cohort, pair, prices, target, rng)
            forecasts.append(pred)
            fold_sizes.extend(sizes)
            negatives.setdefault((cohort, target), []).extend(placebo)
    forecasts = pd.concat(forecasts, ignore_index=True)
    summary, by_contract, by_fold, placebos, sensitivity = [], [], [], [], []
    for (cohort, target), group in forecasts.groupby(["cohort", "target"]):
        main_panel = group[group.delay == 0]
        labels = dict(cohort=cohort, target=target)
        for key, sub in [("all", main_panel), ("both_changed", main_panel[main_panel.both_changed]),
                         ("kalshi_spread_le_1pp", main_panel[main_panel.tight])]:
            if sub.empty:
                continue
            lo, hi = block_interval(sub, rng)
            summary.append(dict(**labels, sample=key, **metrics(sub), ci_low_pp=lo[0], ci_high_pp=hi[0],
                                ci_vs_persist_low_pp=lo[1], ci_vs_persist_high_pp=hi[1]))
        for pair, sub in main_panel.groupby("pair"):
            by_contract.append(dict(**labels, pair=pair, **metrics(sub)))
        for fold, sub in main_panel.groupby("fold"):
            by_fold.append(dict(**labels, fold=fold, **metrics(sub)))
        for delay in (1, 7):
            delayed = group[group.delay == delay]
            common = delayed.assign(cross_full=delayed.matched_current_full, cross_change=delayed.matched_current_change)
            for variant, subset in [("current",common),("delayed",delayed)]:
                sensitivity.append(dict(**labels, delay_days=delay, variant=variant, **metrics(subset)))
        draws = negatives[cohort, target]
        null_gain = 100 * sum(row[1] for row in draws) / sum(row[0] for row in draws)
        measured = metrics(main_panel)["gain_pp"]
        placebos.append(dict(**labels, measured_pp=measured, placebo_draws=len(null_gain),
                             placebo_median_pp=np.median(null_gain), placebo_q025_pp=np.quantile(null_gain,.025),
                             placebo_q975_pp=np.quantile(null_gain,.975),
                             placebo_ge_actual=int(np.sum(null_gain >= measured))))
    for name, data in [("forecast_metrics", summary),("contract_metrics", by_contract),("fold_metrics", by_fold),
                       ("fold_dates", fold_sizes),("delay_sensitivity",sensitivity),("placebo",placebos),
                       ("price_descriptives",descriptive)]:
        save(data, args.output / f"{name}.csv")
    print(pd.DataFrame(summary).query('sample == "all"')[
        ["cohort","target","rows","dates","mae_persist","mae_own_only","mae_cross_change","mae_cross_full",
         "gain_pct","ci_low_pp","ci_high_pp"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
