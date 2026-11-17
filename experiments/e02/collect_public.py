"""Bounded read-only public API acquisition, with frozen raw responses.

Default Polymarket event was discovered via official public-search on 2026-11-14.
This convenience sample is not a complete market universe or certified rule pack.
No credentials, inference, trading endpoints, or background polling are used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def required(record, key):
    value = record.get(key)
    if value is None or not str(value).strip():
        raise ValueError("Missing official identifier: " + key)
    return str(value)


def finish(record, provenance):
    record.update(provenance=provenance, governing_rules_certified=False,
                  coverage="Available official API text only; governing documents, clarification history and payout exceptions require review.")
    record["input_sha256"] = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return record


def normalize_polymarket(event, market, provenance):
    outcomes = market.get("outcomes", [])
    if isinstance(outcomes, str):
        outcomes = json.loads(outcomes)
    return finish({"venue": "polymarket", "id": required(market, "id"),
                   "condition_id": market.get("conditionId"), "event_id": required(event, "id"),
                   "event_title": event.get("title", ""), "title": market.get("question", ""),
                   "primary": market.get("description", ""), "secondary": event.get("description", ""),
                   "resolution_source": market.get("resolutionSource"), "end_date": market.get("endDate"),
                   "outcomes": outcomes}, provenance)


def normalize_kalshi(market, provenance):
    return finish({"venue": "kalshi", "id": required(market, "ticker"),
                   "event_id": required(market, "event_ticker"), "title": market.get("title", ""),
                   "subtitle": market.get("yes_sub_title", market.get("subtitle", "")),
                   "primary": market.get("rules_primary", ""), "secondary": market.get("rules_secondary", ""),
                   "close_time": market.get("close_time"), "expiration_time": market.get("expiration_time"),
                   "market_type": market.get("market_type")}, provenance)


def now():
    return datetime.now(timezone.utc).isoformat()


def acquire(output, poly_event, kalshi_series):
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    urls = {
        "polymarket_event": "https://gamma-api.polymarket.com/events/" + quote(poly_event, safe=""),
        "kalshi_markets": "https://external-api.kalshi.com/trade-api/v2/markets?" + urlencode({"series_ticker": kalshi_series, "limit": 100}),
        "kalshi_series": "https://external-api.kalshi.com/trade-api/v2/series/" + quote(kalshi_series, safe=""),
    }
    manifest = {"schema_version": "e02-acquisition-v1", "started_at_utc": now(),
                "status": "development_convenience_sample", "requests": [],
                "polymarket_event_id": poly_event, "kalshi_series": kalshi_series,
                "full_pagination": False, "governing_rules_certified": False,
                "human_gold": False, "historical_rules_reconstructed": False,
                "limitations": ["One selected Polymarket event and at most 100 Kalshi markets",
                                "Current API text does not establish historical completeness",
                                "Raw responses include market metadata; model corpus excludes prices, results and volume",
                                "Different fetch times do not constitute synchronized price data"]}
    fetched = {}
    for name, url in urls.items():
        record = {"name": name, "url": url, "request_started_at_utc": now()}
        try:
            with urlopen(Request(url, headers={"User-Agent": "ITMO-resolution-research-readonly/1.0"}), timeout=25) as response:
                content = response.read(5_000_001)
                if len(content) > 5_000_000:
                    raise ValueError("Response exceeds bounded acquisition limit")
                record.update(http_status=response.status,
                              headers={k: response.headers[k] for k in ("Date", "ETag", "Last-Modified") if k in response.headers})
            record.update(received_at_utc=now(), raw_file="raw/" + name + ".json",
                          raw_sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
            (output / record["raw_file"]).write_bytes(content)
            fetched[name] = json.loads(content)
        except Exception as exc:
            record.update(received_at_utc=now(), error=type(exc).__name__ + ": " + str(exc))
        manifest["requests"].append(record)
    requests = {r["name"]: r for r in manifest["requests"]}
    corpus = []
    def provenance(name, locator):
        r = requests[name]
        return {key: r[key] for key in ("url", "raw_file", "raw_sha256", "received_at_utc")} | {"raw_locator": locator}
    event = fetched.get("polymarket_event")
    if isinstance(event, dict) and str(event.get("id")) == poly_event:
        for market in event.get("markets", []):
            corpus.append(normalize_polymarket(event, market, provenance("polymarket_event", "markets[id=" + str(market.get("id")) + "]")))
    elif event is not None:
        manifest["normalization_error"] = "Polymarket event identity mismatch"
    kalshi = fetched.get("kalshi_markets", {})
    for market in kalshi.get("markets", []):
        corpus.append(normalize_kalshi(market, provenance("kalshi_markets", "markets[ticker=" + market["ticker"] + "]")))
    manifest["kalshi_has_next_page"] = bool(kalshi.get("cursor"))
    manifest["counts"] = {v: sum(x["venue"] == v for x in corpus) for v in ("polymarket", "kalshi")}
    manifest["finished_at_utc"] = now()
    manifest["acquisition_succeeded"] = not any("error" in r for r in manifest["requests"]) and "normalization_error" not in manifest
    content = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in corpus)
    (output / "corpus.jsonl").write_text(content)
    manifest["corpus_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return int(not manifest["acquisition_succeeded"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--polymarket-event", default="1366218")
    parser.add_argument("--kalshi-series", default="KXCPICORE")
    args = parser.parse_args()
    raise SystemExit(acquire(args.output, args.polymarket_event, args.kalshi_series))
