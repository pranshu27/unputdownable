"""
Write-only event log service.
Append-only — no updates, no deletes.
All agents and services import write_event() and call it at every decision point.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from linker_agent.models.event_log import AssetEvent, EventAction

logger = logging.getLogger(__name__)

# In-memory store for POC — replace with Databricks Delta write in production
_event_store: list[dict] = []

_EVENT_LOG_PATH = Path("./output/event_log.jsonl")


def write_event(
    asset_id: str,
    stage: str,
    actor: str,
    action: EventAction,
    confidence: Optional[int] = None,
    before_state: Optional[str] = None,
    after_state: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    rationale: Optional[str] = None,
) -> AssetEvent:
    """
    Write a single event to the append-only event log.
    Called by every tier decision, every enrichment completion, every state change.
    """
    event = AssetEvent(
        asset_id=asset_id,
        stage=stage,
        actor=actor,
        action=action,
        confidence=confidence,
        before_state=before_state,
        after_state=after_state,
        payload=payload,
        rationale=rationale,
    )

    _event_store.append(event.model_dump())

    try:
        _EVENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_EVENT_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event.model_dump()) + '\n')
    except Exception as e:
        logger.warning(f"Event log write failed for asset {asset_id}: {e}")

    return event


def get_events_for_asset(asset_id: str) -> list[dict]:
    """Retrieve all events for a given asset_id."""
    return [e for e in _event_store if e['asset_id'] == asset_id]


def get_all_events() -> list[dict]:
    """Retrieve full event log (for inspection/debugging)."""
    return list(_event_store)


def clear_events() -> None:
    """Clear the in-memory event store. Used in tests."""
    _event_store.clear()
