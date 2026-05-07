"""Async DAG runner — topological execution with parallel fan-out
(workflow 06 §3, §6.2).

The shape mirrors LangGraph's StateGraph (add_node, add_edge,
add_conditional_edges) so this module can be replaced with langgraph
later without changing the DAG definitions. Kept custom to avoid the
heavyweight langchain-core transitive dep at this stage.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

log = logging.getLogger(__name__)

State = TypeVar("State")
NodeFn = Callable[[Any], Awaitable[Any]]
ConditionalFn = Callable[[Any], Sequence[str]]


@dataclass(slots=True)
class Node(Generic[State]):
    name: str
    fn: NodeFn
    soft_timeout_s: float | None = None
    hard_timeout_s: float | None = None


@dataclass(slots=True)
class NodeResult:
    name: str
    started_at: float
    finished_at: float
    ok: bool
    output: Any = None
    error: str | None = None
    timed_out: bool = False

    @property
    def duration_s(self) -> float:
        return self.finished_at - self.started_at


@dataclass(slots=True)
class DagResult(Generic[State]):
    dag_id: str
    trace_id: str
    state: State
    nodes: list[NodeResult] = field(default_factory=list)
    ok: bool = True

    def by_name(self, name: str) -> NodeResult | None:
        for r in self.nodes:
            if r.name == name:
                return r
        return None


class StateGraph(Generic[State]):
    """Minimal LangGraph-shaped DAG.

    Edges are directed; cycles are rejected at run time. Multiple outgoing
    edges from a node fan out; multiple incoming edges fan in (the receiver
    runs only after all predecessors finish).
    """

    def __init__(self, dag_id: str) -> None:
        self.dag_id = dag_id
        self._nodes: dict[str, Node[State]] = {}
        self._edges: dict[str, list[str]] = {}
        self._conditional: dict[str, ConditionalFn] = {}
        self._entry: str | None = None

    def add_node(
        self,
        name: str,
        fn: NodeFn,
        *,
        soft_timeout_s: float | None = None,
        hard_timeout_s: float | None = None,
    ) -> None:
        if name in self._nodes:
            raise ValueError(f"duplicate node: {name}")
        self._nodes[name] = Node(
            name=name,
            fn=fn,
            soft_timeout_s=soft_timeout_s,
            hard_timeout_s=hard_timeout_s,
        )

    def add_edge(self, src: str, dst: str) -> None:
        self._edges.setdefault(src, []).append(dst)

    def add_conditional_edges(self, src: str, condition: ConditionalFn) -> None:
        """`condition(state)` returns the list of node names to fan out to."""
        self._conditional[src] = condition

    def set_entry(self, name: str) -> None:
        self._entry = name

    def nodes(self) -> dict[str, Node[State]]:
        return dict(self._nodes)

    def successors(self, name: str, state: State) -> list[str]:
        out = list(self._edges.get(name, []))
        if name in self._conditional:
            out.extend(self._conditional[name](state))
        return out


async def execute(
    graph: StateGraph[State],
    initial_state: State,
    *,
    trace_id: str,
    timeout_s: float = 600.0,
    sla_runner: (
        Callable[[Node[State], State], Awaitable[tuple[bool, Any, str | None, bool]]] | None
    ) = None,
) -> DagResult[State]:
    """Run `graph` to completion.

    sla_runner is the per-node executor — defaults to direct call. Tests
    inject a mock; the production wiring uses execute.sla.with_sla_timeout.
    """
    if graph._entry is None:
        raise ValueError(f"DAG {graph.dag_id} has no entry node")

    state = initial_state
    results: list[NodeResult] = []
    pending = {graph._entry}
    completed: set[str] = set()
    parents: dict[str, set[str]] = _compute_parents(graph)

    overall_deadline = asyncio.get_event_loop().time() + timeout_s

    while pending:
        if asyncio.get_event_loop().time() > overall_deadline:
            raise TimeoutError(f"DAG {graph.dag_id} exceeded overall timeout {timeout_s}s")

        # Pick all nodes whose parents are satisfied.
        ready = [name for name in pending if parents.get(name, set()).issubset(completed)]
        if not ready:
            raise RuntimeError(f"DAG {graph.dag_id} stalled — no ready nodes among {pending}")

        # Run all ready nodes in parallel.
        async def _run_one(node_name: str) -> NodeResult:
            node = graph._nodes[node_name]
            started = asyncio.get_event_loop().time()
            if sla_runner is not None:
                ok, output, error, timed_out = await sla_runner(node, state)
            else:
                try:
                    output = await node.fn(state)
                    ok, error, timed_out = True, None, False
                except Exception as exc:
                    ok, output, error, timed_out = False, None, str(exc), False
            finished = asyncio.get_event_loop().time()
            return NodeResult(
                name=node_name,
                started_at=started,
                finished_at=finished,
                ok=ok,
                output=output,
                error=error,
                timed_out=timed_out,
            )

        finished_results = await asyncio.gather(*(_run_one(n) for n in ready))
        results.extend(finished_results)

        for r in finished_results:
            completed.add(r.name)
            pending.discard(r.name)
            for nxt in graph.successors(r.name, state):
                if nxt not in completed:
                    pending.add(nxt)

    overall_ok = all(r.ok for r in results)
    return DagResult(
        dag_id=graph.dag_id,
        trace_id=trace_id,
        state=state,
        nodes=results,
        ok=overall_ok,
    )


def _compute_parents(graph: StateGraph[Any]) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = {name: set() for name in graph._nodes}
    for src, dsts in graph._edges.items():
        for dst in dsts:
            parents.setdefault(dst, set()).add(src)
    return parents
