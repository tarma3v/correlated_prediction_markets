"""Use Sep 28 executable quote snapshots and original BLS releases in restricted replay."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from audit import ROOT, DATA, OUT, binary_metrics
from prepare import write_csv


def date(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def wire(now):
    return now.isoformat(timespec="seconds").replace("+00:00", "Z")


def run_child(packet=None, probe=False):
    args = [sys.executable, "-I", "-S", str(ROOT / "worker.py")]
    if probe:
        args.append("--probe")
    run = subprocess.run(
        args,
        input=json.dumps(packet),
        text=True,
        capture_output=True,
        check=True,
        env={},
        cwd=ROOT,
        timeout=10,
    )
    return json.loads(run.stdout)


def packet(series, month, threshold, now, releases):
    # Pass only releases available by the requested clock time.
    return dict(
        series=series,
        month=month,
        threshold=str(threshold),
        asof=wire(now),
        releases=[r for r in releases if date(r["available_at"]) <= now],
    )


def replay():
    docs = json.loads((DATA / "releases.json").read_text())
    official = {r["month"]: r for r in docs}
    quote_rows = []
    snapshot_sha = {}
    for series in ("KXCPI", "KXCPICORE"):
        path = ROOT.parent.parent / "pilot" / "raw" / ("kalshi_" + series + ".json")
        snapshot_sha[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        file = json.loads(path.read_text())
        stamp = date(file["fetched_at_utc"])
        prior = max(
            (r for r in docs if date(r["available_at"]) <= stamp),
            key=lambda r: r["available_at"],
        )
        for row in file["response"]["markets"]:
            month = row["event_ticker"].split("-")[-1]
            if month not in ("26SEP", "26OCT"):
                continue
            assert row["result"] == "" and row["strike_type"] == "greater"
            cutoff = date(official[month]["available_at"])
            assert stamp < cutoff
            strike = Decimal(str(row["floor_strike"]))
            bid, ask = map(Decimal, [row["yes_bid_dollars"], row["yes_ask_dollars"]])
            assert 0 <= bid <= ask <= 1
            original = packet(series, month, strike, stamp, docs)
            before = packet(series, month, strike, cutoff - timedelta(seconds=1), docs)
            after = packet(series, month, strike, cutoff, docs)
            assert run_child(original) == run_child(before) == "DEFER"
            answer = run_child(after)
            assert answer in ("YES", "NO")
            quote_rows.append(
                dict(
                    ticker=row["ticker"],
                    event=row["event_ticker"],
                    strike=str(strike),
                    quote_at=wire(stamp),
                    bid=float(bid),
                    ask=float(ask),
                    mid=float((bid + ask) / 2),
                    month=month,
                    previous_release=int(Decimal(prior[series]) > strike),
                    at_release=answer,
                    bls_reference=int(Decimal(official[month][series]) > strike),
                )
            )
    write_csv(OUT / "cpi_by_contract.csv", quote_rows)
    truth = [r["bls_reference"] for r in quote_rows]
    scores = {}
    for w in (0, 0.25, 0.5, 0.75, 1):
        ps = [r["mid"] * w + (1 - w) * r["previous_release"] for r in quote_rows]
        scores[str(w)] = binary_metrics(ps, truth)
    # Direct exchange results were read independently from four event pages. They need not match the quote sample.
    exchange = json.loads((DATA / "exchange_labels.json").read_text())
    checked = []
    for e in exchange:
        series, month = e["event"].split("-")
        for threshold, value in e["labels"].items():
            claim = run_child(
                packet(
                    series,
                    month,
                    threshold,
                    date(official[month]["available_at"]),
                    docs,
                )
            )
            in_snapshot = any(
                r["event"] == e["event"] and Decimal(r["strike"]) == Decimal(threshold)
                for r in quote_rows
            )
            checked.append(
                dict(
                    event=e["event"],
                    threshold=threshold,
                    exchange=value,
                    oracle=claim,
                    available_in_price_snapshot=in_snapshot,
                )
            )
    write_csv(OUT / "cpi_exchange_check.csv", checked)
    # Mutation, reversal, canary and fresh-state controls run on the identical executable.
    observed = date("2026-11-10T13:29:59Z")
    polluted = [dict(x, KXCPI="99") if x["month"] == "26OCT" else x for x in docs]
    cold = packet("KXCPI", "26OCT", ".4", observed, docs)
    assert cold == packet("KXCPI", "26OCT", ".4", observed, polluted)
    out_before = run_child(cold)
    historical = packet("KXCPI", "26OCT", ".4", observed + timedelta(seconds=1), docs)
    mutated = packet("KXCPI", "26OCT", ".4", observed + timedelta(seconds=1), polluted)
    after_change = (run_child(historical), run_child(mutated))
    after_reversal = run_child(cold)
    assert out_before == after_reversal == "DEFER" and after_change == ("NO", "YES")
    os.environ["ORACLE_CANARY"] = "sentinel"
    probes = run_child(probe=True)
    assert probes == {
        "file_read": "denied",
        "socket_creation": "denied",
        "environment_contains_canary": False,
    }
    shadow = json.loads((DATA / "shadow_market.json").read_text())
    shadow_output = {
        k: run_child(
            packet(
                "KXCPI",
                "26NOV",
                k,
                date(shadow["observed_date_utc"] + "T23:59:59Z"),
                docs,
            )
        )
        for k in shadow["observed_page_chances"]
    }
    return dict(
        n_rows=len(quote_rows),
        events=len({r["event"] for r in quote_rows}),
        release_dates=len(set(r["month"] for r in quote_rows)),
        yes=sum(truth),
        forecast_sensitivity_market_weight=scores,
        release_before_deferred=len(quote_rows),
        release_at_decided=len(quote_rows),
        exchange_checked=len(checked),
        exchange_correct=sum((r["oracle"] == "YES") == r["exchange"] for r in checked),
        exchange_overlap_with_quotes=sum(
            r["available_in_price_snapshot"] for r in checked
        ),
        isolation=dict(
            **probes,
            at_minus_one=out_before,
            after_valid_then_previous=after_reversal,
            changed_visible_value_changes_decision=list(after_change),
            mutated_future_packet_identical=True,
        ),
        prospective_shadow=shadow_output,
        snapshot_sha256=snapshot_sha,
    )


if __name__ == "__main__":
    (OUT / "cpi.json").write_text(json.dumps(replay(), indent=2) + "\n")
