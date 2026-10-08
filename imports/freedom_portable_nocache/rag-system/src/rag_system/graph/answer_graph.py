"""LangGraph orchestration for /answer.

Phase 1 graph design:
Planner -> Executor -> Validator

Validator may request a retry, which routes back to Planner until max_retries
is reached.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, TypedDict


class AnswerGraphState(TypedDict, total=False):
    """Mutable state payload exchanged between planner, executor, and validator nodes."""

    query: str
    k: int
    mode: str
    rerank: bool
    prompt_name: str
    llm: bool
    relevancy_boost: bool
    llm_model: str | None
    llm_temperature: float
    llm_max_tokens: int
    hits: List[Dict[str, Any]]
    reranked: bool
    rerank_error: str | None
    plan: Dict[str, Any]
    resolved_mode: str
    effective_query: str
    source_file_hints: List[str]
    max_retries: int
    retry_count: int
    validator_decision: Literal["pass", "retry", "fail"]
    validator_reason: str | None
    answer_payload: Dict[str, Any]


@dataclass(frozen=True)
class AnswerGraphCallbacks:
    """Callback bundle that supplies planner/executor/validator node implementations."""

    planner: Callable[[AnswerGraphState], Dict[str, Any]]
    executor: Callable[[AnswerGraphState], Dict[str, Any]]
    validator: Callable[[AnswerGraphState], Dict[str, Any]]


def run_answer_graph(
    initial_state: AnswerGraphState,
    callbacks: AnswerGraphCallbacks,
) -> AnswerGraphState:
    """Compile and invoke planner-executor-validator graph."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(AnswerGraphState)

    def _planner_node(state: AnswerGraphState) -> Dict[str, Any]:
        return callbacks.planner(state)

    def _executor_node(state: AnswerGraphState) -> Dict[str, Any]:
        return callbacks.executor(state)

    def _validator_node(state: AnswerGraphState) -> Dict[str, Any]:
        return callbacks.validator(state)

    def _validator_route(state: AnswerGraphState) -> str:
        decision = str(state.get("validator_decision") or "pass").lower()
        if decision == "retry":
            max_retries = int(state.get("max_retries", 1) or 1)
            retry_count = int(state.get("retry_count", 0) or 0)
            if retry_count < max_retries:
                return "planner"
        return "finish"

    graph.add_node("planner", _planner_node)
    graph.add_node("executor", _executor_node)
    graph.add_node("validator", _validator_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "validator")
    graph.add_conditional_edges(
        "validator",
        _validator_route,
        {
            "planner": "planner",
            "finish": END,
        },
    )

    compiled = graph.compile()
    return compiled.invoke(initial_state)
