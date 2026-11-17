"""Optional no-key LangGraph entry point for previously frozen CPI packets."""

from typing import TypedDict
from replay import DATA, date, json, packet, run_child


class GateState(TypedDict, total=False):
    blind_packet: dict
    verdict: str
    status: str


def run(packet_):
    from langgraph.graph import StateGraph, START, END

    graph = StateGraph(GateState)
    graph.add_node(
        "resolve", lambda state: {"verdict": run_child(state["blind_packet"])}
    )
    graph.add_node("review", lambda state: {"status": "deferred"})
    graph.add_node("record", lambda state: {"status": "resolved"})
    graph.add_edge(START, "resolve")
    graph.add_conditional_edges(
        "resolve",
        lambda state: "review" if state["verdict"] == "DEFER" else "record",
        {"review": "review", "record": "record"},
    )
    graph.add_edge("review", END)
    graph.add_edge("record", END)
    # A fresh graph per invocation; no checkpointer or shared store.
    return graph.compile().invoke({"blind_packet": packet_})


if __name__ == "__main__":
    docs = json.loads((DATA / "releases.json").read_text())
    for s in ("2026-11-10T13:29:59Z", "2026-11-10T13:30:00Z"):
        answer = run(packet("KXCPI", "26OCT", "0.4", date(s), docs))
        print(s, answer["verdict"], answer["status"])
