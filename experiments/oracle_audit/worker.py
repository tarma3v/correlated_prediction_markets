"""Stateless, stdlib-only resolver. Input is one filtered observation packet per process."""

import json
import os
import socket
import sys
from decimal import Decimal


def deny_io(event, args):
    if event == "open" or event.startswith(
        ("socket.", "subprocess.", "os.system", "os.spawn", "os.exec")
    ):
        raise PermissionError(event)


def decide(packet):
    if set(packet) != {"threshold", "month", "series", "asof", "releases"}:
        raise ValueError("Unexpected packet fields")
    relevant = [
        r
        for r in packet["releases"]
        if r["month"] == packet["month"] and r["available_at"] <= packet["asof"]
    ]
    if not relevant:
        return "DEFER"
    if len(relevant) != 1:
        raise ValueError("Ambiguous first release")
    return (
        "YES"
        if Decimal(relevant[0][packet["series"]]) > Decimal(packet["threshold"])
        else "NO"
    )


if __name__ == "__main__":
    # Defense in depth for this fixed trusted worker, not an OS sandbox for arbitrary code.
    sys.addaudithook(deny_io)
    if sys.argv[1:] == ["--probe"]:
        checks = {}
        for name, action in [
            ("file_read", lambda: open(__file__)),
            ("socket_creation", socket.socket),
        ]:
            try:
                action()
                checks[name] = "allowed"
            except PermissionError:
                checks[name] = "denied"
        checks["environment_contains_canary"] = "ORACLE_CANARY" in os.environ
        print(json.dumps(checks))
    else:
        print(json.dumps(decide(json.load(sys.stdin))))
