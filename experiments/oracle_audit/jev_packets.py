"""Generate a blinded Jev memory challenge; no model or network calls."""

from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from replay import DATA, OUT, date


def build():
    releases = {r["month"]: r for r in json.loads((DATA / "releases.json").read_text())}
    events = json.loads((DATA / "exchange_labels.json").read_text())
    requests = []
    labels = []
    for event in events:
        series, month = event["event"].split("-")
        d = releases[month]
        available = date(d["available_at"])
        for threshold in event["labels"]:
            strike = Decimal(threshold)
            actual = Decimal(d[series])
            for arm in (
                "named_original",
                "anonymous_original",
                "anonymous_reversed",
                "named_withheld",
                "anonymous_withheld",
            ):
                changed = strike if actual > strike else strike + Decimal("0.1")
                value = changed if arm == "anonymous_reversed" else actual
                visible = "withheld" not in arm
                alias = (
                    event["event"] if arm.startswith("named") else "Series X, period M"
                )
                cutoff = available if visible else available - timedelta(seconds=1)
                state = {
                    "contract": alias,
                    "criterion": f"The one-decimal release must be strictly above {threshold} percent.",
                    "clock": cutoff.isoformat()
                    if arm.startswith("named")
                    else ("release time" if visible else "before release"),
                    "official_release_percent": str(value) if visible else None,
                }
                body = {
                    "model": "jev-1.13.0",
                    "state": json.dumps(state, sort_keys=True),
                    "questions": {
                        "verdict": {
                            "type": "choice",
                            "instructions": "Resolve this contract using only the supplied official release.",
                            "criteria": {
                                "YES": "Evidence establishes that the criterion is true.",
                                "NO": "Evidence establishes that the criterion is false.",
                                "DEFER": "The required official observation is missing.",
                            },
                        }
                    },
                }
                key = hashlib.sha256(
                    (event["event"] + "|" + threshold + "|" + arm).encode()
                ).hexdigest()[:16]
                requests.append({"request_id": key, "body": body})
                labels.append(
                    {
                        "request_id": key,
                        "event": event["event"],
                        "threshold": threshold,
                        "arm": arm,
                        "label": ("YES" if value > strike else "NO")
                        if visible
                        else "DEFER",
                    }
                )
    for name, rows in [("jev_requests", requests), ("jev_reference", labels)]:
        (OUT / (name + ".jsonl")).write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
        )
    assert len({r["request_id"] for r in requests}) == len(requests) == 60


if __name__ == "__main__":
    build()
