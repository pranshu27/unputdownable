"""Message types for the agentic PySpark codegen pipeline.

Combines the message-contract style of both des_ reference repos:
- CLIENT_B_backend pc_types.py: PCMessage / PCFlowExtractionResponse (pub/sub).
- dbt_codegen dbt_types.py: UserTask / WorkerTask / WorkerTaskResult / FinalResult
  (orchestrator request/response).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


# --- Pub/sub extraction contracts (CLIENT_B_backend style) ---


@dataclass
class PCMessage:
    """One unit of work published to the extractor topic (a transformation node,
    optionally field-batched)."""

    content: str


@dataclass
class PCFlowExtractionResponse:
    """Extractor result published back to the response/collector topic."""

    content: Dict[str, Any]


# --- PySpark generation contracts ---


@dataclass
class PySparkNodeRequest:
    """A single canonical node (Source / Transformation / Target) to compile to PySpark."""

    content: Dict[str, Any]


@dataclass
class PySparkGenerationResponse:
    """Generated PySpark code fragment for one node."""

    content: Dict[str, Any]


# --- Orchestrator request/response contracts (dbt_codegen style) ---


@dataclass
class UserTask:
    """Top-level task handed to the OrchestratorAgent."""

    task: Dict[str, Any]
    meta_data: Dict[str, Any]


@dataclass
class WorkerTask:
    """Task dispatched from orchestrator to a worker agent."""

    task: str
    previous_results: List[str] = field(default_factory=list)
    meta_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerTaskResult:
    """Worker agent result returned to the orchestrator."""

    result: str


@dataclass
class FinalResult:
    """Final aggregated result returned by the orchestrator."""

    result: Dict[str, Any]


@dataclass
class HumanReviewRequest:
    """Bundle handed to a human (or auto-approver) for the final sign-off gate."""

    mapping_name: str
    artifact: Dict[str, Any]
    critic: Dict[str, Any]


@dataclass
class HumanReviewDecision:
    """Outcome of the human-in-the-loop gate."""

    approved: bool
    reviewer: str
    comments: str = ""
