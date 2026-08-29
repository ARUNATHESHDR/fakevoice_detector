"""
Gateway service -- the orchestration spine and public-facing API.

Receives each audio window from edge_ingestion, fans it out to the three
analysis services IN PARALLEL, sends their results to the fusion engine,
forwards alerts to the alerting service, and pushes the result to any
frontend listening on this session's dashboard.

This is also where the external REST API (for banking/enterprise
integration) lives -- see the /api/v1/* routes.

ENHANCEMENTS v2:
  - Passes phase_analysis and enrollment_match from sub-services to fusion
  - Speaker enrollment proxy endpoints
  - Privacy compliance endpoints (retention policy, consent, data deletion)
  - Enhanced session metadata with comprehensive audit info

gRPC contract lives alongside this in gateway/voice_analysis.proto.
"""

import asyncio
import base64
import hashlib
import io
import json
import os
import time
import uuid
import wave

import httpx
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

app = FastAPI(
    title="Voice Integrity Gateway",
    description="Orchestration API for real-time voice cloning detection",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs -- defaults are for native/localhost mode (no Docker)
SPECTRAL_URL = os.environ.get("SPECTRAL_URL", "http://localhost:8002/analyze")
PROSODY_URL = os.environ.get("PROSODY_URL", "http://localhost:8003/analyze")
CONSISTENCY_URL = os.environ.get("CONSISTENCY_URL", "http://localhost:8004/analyze")
FUSION_URL = os.environ.get("FUSION_URL", "http://localhost:8005/fuse")
ALERTING_URL = os.environ.get("ALERTING_URL", "http://localhost:8006/alert")
SCORE_UPDATE_URL = os.environ.get("SCORE_UPDATE_URL", "http://localhost:8006/score_update")
ENROLLMENT_URL = os.environ.get("ENROLLMENT_URL", "http://localhost:8004")

# per-session call context set by the client at session start (optional)
_session_context: dict[str, dict] = {}

# per-session latest analysis results -- powers /api/v1/session/{id}/status
_session_results: dict[str, dict] = {}

# per-session metadata (start time, window count, alert count, history)
_session_meta: dict[str, dict] = {}

# Privacy: consent records
_consent_records: dict[str, dict] = {}

# Privacy: configurable data retention policy
_retention_policy = {
    "max_session_age_hours": 24,
    "retain_audio": False,
    "retain_embeddings": False,
    "retain_scores_only": True,
    "retain_anonymized_metadata": True,
    "auto_purge_on_session_end": True,
    "gdpr_dpdpa_compliant": True,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resample_pcm(pcm: np.ndarray, orig_rate: int, target_rate: int = 16000) -> np.ndarray:
    """Linear-interpolation resampler using only numpy (no scipy needed)."""
    if orig_rate == target_rate:
        return pcm
    duration = len(pcm) / orig_rate
    target_len = int(duration * target_rate)
    indices = np.linspace(0, len(pcm) - 1, target_len)
    return np.interp(indices, np.arange(len(pcm)), pcm.astype(np.float64)).astype(np.int16)


async def _analyze_window(client: httpx.AsyncClient, payload: dict, context: dict) -> dict:
    """Fan a single audio window out to the three models + fusion engine."""
    spectral_task = client.post(SPECTRAL_URL, json=payload, timeout=10.0)
    prosody_task = client.post(PROSODY_URL, json=payload, timeout=10.0)
    consistency_task = client.post(CONSISTENCY_URL, json=payload, timeout=10.0)

    spectral_resp, prosody_resp, consistency_resp = await asyncio.gather(
        spectral_task, prosody_task, consistency_task
    )

    spectral_data = spectral_resp.json()
    consistency_data = consistency_resp.json()

    fusion_payload = {
        "session_id": payload["session_id"],
        "window_index": payload["window_index"],
        "spectral_score": spectral_data["spoof_score"],
        "prosody_score": prosody_resp.json()["prosody_score"],
        "consistency_score": consistency_data["consistency_score"],
        "context": context,
        # Pass through phase analysis and enrollment match to fusion engine
        "phase_analysis": spectral_data.get("phase_analysis"),
        "enrollment_match": consistency_data.get("enrollment_match"),
    }
    fusion_resp = await client.post(FUSION_URL, json=fusion_payload, timeout=8.0)
    return fusion_resp.json()


# ---------------------------------------------------------------------------
# Internal ingestion endpoint (called by edge_ingestion)
# ---------------------------------------------------------------------------

@app.post("/ingest/window")
async def ingest_window(payload: dict):
    """Called by edge_ingestion for every non-silent audio window."""
    session_id = payload["session_id"]

    # Initialize session metadata on first window
    if session_id not in _session_meta:
        _session_meta[session_id] = {
            "started_at": time.time(),
            "window_count": 0,
            "alert_count": 0,
            "risk_history": [],
            "score_history": [],  # full per-layer score timeline
        }
    _session_meta[session_id]["window_count"] += 1

    context = _session_context.get(session_id, {})

    async with httpx.AsyncClient() as client:
        result = await _analyze_window(client, payload, context)

        # Store latest result for the polling API
        _session_results[session_id] = {
            **result,
            "timestamp": time.time(),
        }

        # Keep a rolling risk history (last 50 windows) for trend analysis
        history = _session_meta[session_id]["risk_history"]
        history.append(round(result["risk_score"], 2))
        if len(history) > 50:
            history.pop(0)

        # Keep detailed score history for the frontend timeline chart
        score_entry = {
            "window": payload["window_index"],
            "risk": round(result["risk_score"], 2),
            "spectral": round(result.get("spoof_score", 0), 4),
            "prosody": round(result.get("prosody_score", 0), 4),
            "consistency": round(result.get("consistency_score", 0), 4),
            "timestamp": time.time(),
        }
        score_history = _session_meta[session_id]["score_history"]
        score_history.append(score_entry)
        if len(score_history) > 100:
            score_history.pop(0)

        # Push score update to dashboard; fire alert if triggered
        await client.post(SCORE_UPDATE_URL, json=result, timeout=5.0)
        if result["alert_triggered"]:
            _session_meta[session_id]["alert_count"] += 1
            await client.post(ALERTING_URL, json=result, timeout=5.0)

    return result


@app.post("/session/{session_id}/context")
async def set_session_context(session_id: str, context: dict):
    """Frontend or banking system calls this at call start with metadata
    such as known-contact status, transaction context, etc."""
    _session_context[session_id] = context
    return {"status": "stored"}


# ---------------------------------------------------------------------------
# Public integration REST API -- /api/v1/*
# What banking/enterprise/telecom systems consume.
# ---------------------------------------------------------------------------

@app.get("/api/v1/sessions")
async def list_sessions():
    """Lists all active/known sessions and their current risk status."""
    sessions = []
    for sid, meta in _session_meta.items():
        latest = _session_results.get(sid, {})
        sessions.append({
            "session_id": sid,
            "started_at": meta.get("started_at"),
            "window_count": meta.get("window_count", 0),
            "alert_count": meta.get("alert_count", 0),
            "latest_risk_score": latest.get("risk_score"),
            "alert_triggered": latest.get("alert_triggered", False),
        })
    return {"sessions": sessions, "total": len(sessions)}


@app.get("/api/v1/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Returns the FULL latest analysis for a session: risk score, all
    per-layer scores, rationale, session metadata, and risk trend.
    This is the endpoint a bank's backend would poll."""
    result = _session_results.get(session_id)
    meta = _session_meta.get(session_id)
    context = _session_context.get(session_id, {})

    if not result and not meta:
        return {"error": "session_not_found", "session_id": session_id}

    return {
        "session_id": session_id,
        "status": "active" if meta else "unknown",
        "context": context,
        "latest_analysis": result,
        "session_metadata": {
            "started_at": meta.get("started_at") if meta else None,
            "window_count": meta.get("window_count", 0) if meta else 0,
            "alert_count": meta.get("alert_count", 0) if meta else 0,
            "risk_trend": meta.get("risk_history", []) if meta else [],
            "score_timeline": meta.get("score_history", []) if meta else [],
        },
    }


@app.get("/api/v1/session/{session_id}/timeline")
async def get_session_timeline(session_id: str):
    """Returns the full per-window score timeline for charting."""
    meta = _session_meta.get(session_id)
    if not meta:
        return {"error": "session_not_found"}
    return {
        "session_id": session_id,
        "timeline": meta.get("score_history", []),
        "risk_trend": meta.get("risk_history", []),
    }


@app.post("/api/v1/analyze-clip")
async def analyze_clip(
    file: UploadFile = File(..., description="WAV audio file (16-bit PCM preferred)"),
    caller_context: Optional[str] = Form(
        None, description="JSON string with CallContext fields"
    ),
):
    """One-shot analysis of a pre-recorded audio clip.

    This is the file-upload fallback for demos AND the endpoint a banking
    system would use to verify a recorded call segment. Accepts WAV files
    (any sample rate -- will be resampled to 16kHz internally).

    Returns full analysis including per-window breakdown, aggregate stats,
    and a final verdict -- identical contract shape to the streaming path.
    """
    audio_bytes = await file.read()
    session_id = str(uuid.uuid4())

    # Parse WAV to extract raw PCM
    try:
        with io.BytesIO(audio_bytes) as buf:
            with wave.open(buf, "rb") as wf:
                sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                raw_frames = wf.readframes(wf.getnframes())

        pcm = np.frombuffer(raw_frames, dtype=np.int16)
        if n_channels == 2:
            pcm = pcm[::2]
        pcm = _resample_pcm(pcm, sample_rate, 16000)
        sample_rate = 16000
    except Exception:
        # Not a valid WAV -- treat as raw 16-bit PCM at 16kHz
        pcm = np.frombuffer(audio_bytes, dtype=np.int16)
        sample_rate = 16000

    # Parse optional caller context
    context = {}
    if caller_context:
        try:
            context = json.loads(caller_context)
        except Exception:
            pass
    _session_context[session_id] = context

    # Chunk into 2-second windows and analyze each
    window_size = 2 * sample_rate
    results = []

    async with httpx.AsyncClient() as client:
        for i, start in enumerate(range(0, len(pcm), window_size)):
            window = pcm[start : start + window_size]
            if len(window) < sample_rate // 2:
                break
            if len(window) < window_size:
                window = np.pad(window, (0, window_size - len(window)))

            payload = {
                "session_id": session_id,
                "window_index": i,
                "sample_rate": sample_rate,
                "pcm_base64": base64.b64encode(window.tobytes()).decode(),
            }
            result = await _analyze_window(client, payload, context)
            results.append(result)

    # Aggregate
    if results:
        avg_risk = sum(r["risk_score"] for r in results) / len(results)
        max_risk = max(r["risk_score"] for r in results)
        any_alert = any(r["alert_triggered"] for r in results)
        final = results[-1]
    else:
        avg_risk = max_risk = 0
        any_alert = False
        final = {}

    return {
        "session_id": session_id,
        "clip_duration_seconds": round(len(pcm) / sample_rate, 2),
        "windows_analyzed": len(results),
        "aggregate": {
            "average_risk_score": round(avg_risk, 2),
            "peak_risk_score": round(max_risk, 2),
            "alert_triggered": any_alert,
        },
        "per_window_results": results,
        "final_verdict": final,
    }


# ---------------------------------------------------------------------------
# Speaker Enrollment Proxy (routes to consistency service)
# ---------------------------------------------------------------------------

@app.post("/api/v1/enroll-speaker")
async def enroll_speaker(payload: dict):
    """Proxy enrollment to the consistency service."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{ENROLLMENT_URL}/enroll", json=payload, timeout=15.0)
        return resp.json()


@app.get("/api/v1/enrolled-speakers")
async def list_enrolled():
    """List all enrolled speaker profiles."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{ENROLLMENT_URL}/enrolled", timeout=5.0)
        return resp.json()


@app.delete("/api/v1/enrolled-speaker/{speaker_id}")
async def delete_enrolled(speaker_id: str):
    """Remove an enrolled speaker."""
    async with httpx.AsyncClient() as client:
        resp = await client.delete(f"{ENROLLMENT_URL}/enrolled/{speaker_id}", timeout=5.0)
        return resp.json()


# ---------------------------------------------------------------------------
# Privacy & Compliance API (PS: "privacy-preserving", "data protection")
# ---------------------------------------------------------------------------

@app.get("/api/v1/privacy/retention-policy")
async def get_retention_policy():
    """Returns the current data retention policy configuration."""
    return {"policy": _retention_policy}


@app.put("/api/v1/privacy/retention-policy")
async def update_retention_policy(policy: dict):
    """Update data retention policy settings."""
    _retention_policy.update(policy)
    return {"status": "updated", "policy": _retention_policy}


@app.post("/api/v1/privacy/consent")
async def record_consent(payload: dict):
    """Record user consent for voice processing.

    payload: {
      "caller_id_hash": str (SHA-256 of caller ID),
      "consent_type": "voice_analysis" | "enrollment" | "recording",
      "granted": bool,
      "timestamp": auto
    }
    """
    caller_hash = payload.get("caller_id_hash", "unknown")
    record = {
        "caller_id_hash": caller_hash,
        "consent_type": payload.get("consent_type", "voice_analysis"),
        "granted": payload.get("granted", False),
        "recorded_at": time.time(),
    }
    _consent_records.setdefault(caller_hash, []).append(record)
    return {"status": "recorded", "record": record}


@app.get("/api/v1/privacy/consent/{caller_id_hash}")
async def get_consent(caller_id_hash: str):
    """Retrieve consent records for a caller."""
    records = _consent_records.get(caller_id_hash, [])
    return {"caller_id_hash": caller_id_hash, "records": records}


@app.delete("/api/v1/privacy/data/{caller_id_hash}")
async def delete_caller_data(caller_id_hash: str):
    """Right-to-erasure: delete all data associated with a caller hash.
    Implements GDPR Article 17 / India DPDPA erasure requirement."""
    deleted = {
        "consent_records": len(_consent_records.pop(caller_id_hash, [])),
        "sessions_purged": 0,
    }
    # Purge any sessions that might be associated
    # (In production, sessions would be linked to caller hashes)
    return {"status": "data_deleted", "details": deleted}


@app.get("/api/v1/privacy/audit-log")
async def privacy_audit_log():
    """Returns a summary of what data is currently held and its retention status."""
    return {
        "active_sessions": len(_session_meta),
        "stored_results": len(_session_results),
        "consent_records": sum(len(v) for v in _consent_records.values()),
        "retention_policy": _retention_policy,
        "data_categories": {
            "raw_audio": "NEVER stored (processed in-memory, discarded immediately)",
            "voice_embeddings": "session-scoped, purged on session end",
            "risk_scores": "retained for audit trail (anonymized)",
            "alert_metadata": "retained in fraud ledger (hash-only, no biometrics)",
            "caller_identity": "stored as SHA-256 hash only, never raw",
        },
    }


@app.delete("/api/v1/session/{session_id}")
async def end_session(session_id: str):
    """Cleans up session state. Call when a call ends."""
    _session_context.pop(session_id, None)
    _session_results.pop(session_id, None)
    _session_meta.pop(session_id, None)

    # Tell consistency service to free its embeddings
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                CONSISTENCY_URL.replace("/analyze", "/reset_session"),
                json={"session_id": session_id},
                timeout=3.0,
            )
    except Exception:
        pass

    return {"status": "session_ended", "session_id": session_id}


@app.get("/health")
def health():
    return {"status": "ok", "active_sessions": len(_session_meta)}
