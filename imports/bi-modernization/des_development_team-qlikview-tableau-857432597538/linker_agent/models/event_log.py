"""
Append-only event log models.
Every agent decision and every human action writes an event.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class EventAction(str, Enum):
    # Agent actions
    TIER1_MATCH = "tier1_direct_match"
    TIER2_MATCH = "tier2_semantic_match"
    TIER3_GENERATED = "tier3_term_generated"
    NO_MATCH = "no_match"
    ENRICHMENT_COMPLETE = "enrichment_complete"
    # Human actions (future gate)
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    # Publication
    PUBLISHED_TO_ALATION = "published_to_alation"


class AssetEvent(BaseModel):
    """Single event in the audit log. Append-only — never updated."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    stage: str                          # e.g. "enrichment", "tier2_match", "gate"
    actor: str                          # agent name or steward identity
    action: EventAction
    confidence: Optional[int] = None
    before_state: Optional[str] = None
    after_state: Optional[str] = None
    payload: Optional[dict[str, Any]] = None   # the actual result data
    rationale: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    model_config = {"use_enum_values": True}
