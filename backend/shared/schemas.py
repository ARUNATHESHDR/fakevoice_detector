"""
Shared request/response contracts used across every backend service.

This file should be copied identically into each service's folder (or
installed as a shared local package) so nobody's service silently drifts
out of sync with another's. If you change a field here, tell the whole
team in standup before you change it -- see the project README's rule
about contract changes.
"""

from pydantic import BaseModel
from typing import Optional


class AudioWindow(BaseModel):
    """One ~2-second chunk of audio sent from edge ingestion to each
    analysis model."""
    session_id: str
    window_index: int
    sample_rate: int = 16000
    pcm_base64: str  # raw 16-bit PCM audio, base64-encoded


class SpectralResult(BaseModel):
    session_id: str
    window_index: int
    spoof_score: float  # 0.0 = genuine, 1.0 = synthetic


class ProsodyResult(BaseModel):
    session_id: str
    window_index: int
    prosody_score: float  # 0.0 = natural, 1.0 = unnatural
    features: dict  # raw feature values, used for the explanation


class ConsistencyResult(BaseModel):
    session_id: str
    window_index: int
    consistency_score: float  # 0.0 = consistent speaker, 1.0 = identity drift
    similarity_to_reference: Optional[float] = None


class CallContext(BaseModel):
    """Optional metadata used by the fusion engine's contextual enrichment."""
    caller_number: Optional[str] = None
    is_known_contact: bool = False
    transaction_keywords_detected: list[str] = []
    prior_fraud_flags: int = 0


class RiskScoreResult(BaseModel):
    session_id: str
    window_index: int
    risk_score: float  # 0-100, final fused + contextualized score
    spoof_score: float
    prosody_score: float
    consistency_score: float
    rationale: str  # human-readable explanation
    alert_triggered: bool


class AlertPayload(BaseModel):
    session_id: str
    risk_score: float
    rationale: str
    recommended_action: str  # e.g. "require_callback", "escalate_supervisor"
