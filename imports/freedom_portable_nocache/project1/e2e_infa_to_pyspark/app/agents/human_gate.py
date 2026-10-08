"""Human-in-the-loop approval gate.

Final sign-off pattern: the CriticAgent (machine) validates first; then a HUMAN approves
before the artifact is accepted. This module provides the gate with two modes:

- interactive : prompt a real reviewer on the console (UserProxy-style).
- auto        : non-blocking CI mode — auto-approve only when the critic is confident and
                raised no blocking issues; otherwise mark as requiring human review.

The gate is intentionally a plain async callable (not a RoutedAgent) so it can wrap a real
queue/web-approval system in production. It mirrors AutoGen's UserProxyAgent intent while
staying runnable headless.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from app.communication.pyspark_types import HumanReviewDecision, HumanReviewRequest
from app.utils.logger import get_logger

logger = get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.85


def _parse_critic(critic: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(critic, str):
        try:
            return json.loads(critic)
        except Exception:
            return {"requires_human_review": True, "confidence": 0.0}
    return critic or {"requires_human_review": True, "confidence": 0.0}


async def human_review_gate(
    request: HumanReviewRequest, mode: str = "auto"
) -> HumanReviewDecision:
    """Run the final human approval gate.

    In 'auto' mode, the critic's verdict drives an automatic decision suitable for CI.
    In 'interactive' mode, a console reviewer makes the call.
    """
    critic = _parse_critic(request.critic)
    confidence = float(critic.get("confidence", 0.0) or 0.0)
    blocking = critic.get("blocking_issues", []) or []
    needs_human = bool(critic.get("requires_human_review", True)) or bool(blocking)

    if mode == "interactive":
        return _interactive_gate(request, critic, confidence, needs_human)

    # auto mode (CI / headless)
    if not needs_human and confidence >= CONFIDENCE_THRESHOLD:
        logger.info(
            "Auto-approved %s (confidence=%.2f, no blocking issues)",
            request.mapping_name,
            confidence,
        )
        return HumanReviewDecision(
            approved=True,
            reviewer="auto:ci",
            comments=f"auto-approved at confidence {confidence:.2f}",
        )

    logger.warning(
        "%s requires human review (confidence=%.2f, blocking=%s)",
        request.mapping_name,
        confidence,
        blocking,
    )
    return HumanReviewDecision(
        approved=False,
        reviewer="auto:ci",
        comments="held for human review: " + "; ".join(blocking) if blocking else
        "held for human review: low confidence",
    )


def _interactive_gate(
    request: HumanReviewRequest,
    critic: Dict[str, Any],
    confidence: float,
    needs_human: bool,
) -> HumanReviewDecision:
    print("\n=========== HUMAN REVIEW GATE ===========")
    print(f"Mapping       : {request.mapping_name}")
    print(f"Critic verdict: {critic.get('verdict')}  confidence={confidence:.2f}")
    if critic.get("blocking_issues"):
        print("Blocking issues:")
        for issue in critic["blocking_issues"]:
            print(f"  - {issue}")
    print("Artifact keys :", list(request.artifact.keys()))
    reviewer = os.getenv("USERNAME") or os.getenv("USER") or "reviewer"
    try:
        answer = input("Approve this PySpark migration? [y/N]: ").strip().lower()
    except EOFError:
        answer = "n"
    approved = answer in ("y", "yes")
    comments = input("Comments (optional): ").strip() if approved is not None else ""
    return HumanReviewDecision(approved=approved, reviewer=reviewer, comments=comments)
