"""
Risk fusion engine.

Takes the three per-window scores (spectral, prosody, consistency) plus
optional call context, and produces one final risk_score (0-100) with a
human-readable rationale.

ENHANCEMENTS over v1:
  1. Temporal trend anomaly detection -- detects sudden risk spikes that
     indicate a mid-call voice swap (attacker joins partway through).
  2. Phase analysis integration -- incorporates the new phase-domain
     scores from the spectral service for a richer fusion.
  3. Enrollment match integration -- if the consistency service reports
     the speaker doesn't match an enrolled voiceprint, the risk multiplier
     increases significantly.
  4. Risk velocity tracking -- rate-of-change of risk score triggers
     earlier alerts for rapidly escalating threats.
"""

import json
import os
import time
import numpy as np
import httpx
from fastapi import FastAPI

app = FastAPI(title="Risk Fusion Engine")

RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")
with open(RULES_PATH) as f:
    RULES = json.load(f)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# per-session count of consecutive windows above threshold
_consecutive_high_risk: dict[str, int] = {}

# per-session risk history for trend analysis
_risk_history: dict[str, list[float]] = {}


def weighted_fusion(spectral: float, prosody: float, consistency: float,
                    context: dict, phase_analysis: dict = None,
                    enrollment_match: dict = None) -> tuple[float, list[str]]:
    """Compute fused risk score with contextual enrichment.

    Returns (risk_score, contributing_factors) where contributing_factors
    is a list of strings explaining what drove the score up.
    """
    w = RULES["weights"]
    base = (
        spectral * w["spectral"]
        + prosody * w["prosody"]
        + consistency * w["consistency"]
    ) * 100  # scale to 0-100

    factors = []
    multiplier = 1.0

    # --- Context multipliers ---
    if context.get("is_known_contact") is False:
        multiplier *= RULES["context_multipliers"]["unknown_caller"]
        factors.append("unknown_caller")
    if context.get("transaction_keywords_detected"):
        multiplier *= RULES["context_multipliers"]["transaction_keywords_present"]
        factors.append(f"transaction_keywords: {context['transaction_keywords_detected']}")
    if context.get("prior_fraud_flags", 0) > 0:
        multiplier *= RULES["context_multipliers"]["prior_fraud_flag"]
        factors.append(f"prior_fraud_flags: {context['prior_fraud_flags']}")

    # --- Call origin enrichment ---
    call_origin = context.get("call_origin", "")
    if call_origin in ("voip_unknown", "international_spoofed"):
        multiplier *= 1.2
        factors.append(f"suspicious_call_origin: {call_origin}")

    # --- Phase analysis integration (NEW) ---
    if phase_analysis:
        phase_score = phase_analysis.get("phase_score", 0)
        if phase_score > 0.6:
            multiplier *= 1.15
            factors.append(f"phase_anomaly_detected (score={phase_score:.2f})")

        gdd = phase_analysis.get("gdd_score", 0)
        if gdd > 0.7:
            factors.append("unnaturally_smooth_group_delay")

        pri = phase_analysis.get("pri_score", 0)
        if pri > 0.5:
            factors.append("random_phase_spectrum (synthesis artifact)")

    # --- Enrollment match integration (NEW) ---
    if enrollment_match and enrollment_match.get("matched") is False:
        if enrollment_match.get("similarity", 1.0) < 0.15:
            multiplier *= 1.3
            factors.append("speaker_NOT_matching_enrolled_voiceprint")
        elif enrollment_match.get("similarity", 1.0) < 0.25:
            multiplier *= 1.15
            factors.append("speaker_weak_match_to_enrolled_voiceprint")

    return min(100.0, base * multiplier), factors


def detect_risk_spike(session_id: str, current_risk: float) -> dict:
    """Temporal trend analysis: detect sudden risk score spikes that
    indicate a mid-call voice swap or live voice-conversion attack.

    Returns anomaly info including velocity and whether a spike was detected.
    """
    history = _risk_history.setdefault(session_id, [])
    history.append(current_risk)

    # Keep last 30 windows (~60 seconds at 2s windows)
    if len(history) > 30:
        history.pop(0)

    result = {
        "trend": "stable",
        "risk_velocity": 0.0,
        "spike_detected": False,
        "moving_average": current_risk,
    }

    if len(history) < 3:
        return result

    # Moving average (last 5 windows)
    window = min(5, len(history) - 1)
    recent_avg = float(np.mean(history[-window:]))
    older_avg = float(np.mean(history[:-window])) if len(history) > window else recent_avg

    result["moving_average"] = round(recent_avg, 2)

    # Risk velocity: rate of change per window
    velocity = (history[-1] - history[-2])
    result["risk_velocity"] = round(velocity, 2)

    # Spike detection: current score jumps > 20 points and reaches >= 85
    if current_risk - older_avg > 20 and current_risk >= 85 and len(history) > 5:
        result["spike_detected"] = True
        result["trend"] = "spike_detected"
    elif velocity > 10:
        result["trend"] = "rapidly_rising"
    elif velocity < -10:
        result["trend"] = "rapidly_falling"
    elif recent_avg > older_avg + 5:
        result["trend"] = "gradually_rising"

    return result


async def generate_rationale(spectral, prosody, consistency, risk_score,
                             factors: list[str] = None, phase_analysis: dict = None) -> str:
    """Uses Groq to turn the raw scores into a plain-language explanation.
    Falls back to a templated string if no API key is configured yet."""
    factor_str = ", ".join(factors) if factors else "none"
    phase_str = ""
    if phase_analysis:
        phase_str = (f", phase_score={phase_analysis.get('phase_score', 0):.2f}"
                     f" (GDD={phase_analysis.get('gdd_score', 0):.2f},"
                     f" IFD={phase_analysis.get('ifd_score', 0):.2f},"
                     f" PRI={phase_analysis.get('pri_score', 0):.2f})")

    fallback = (
        f"Risk score {risk_score:.0f}/100 — spectral artifacts: {spectral:.2f}, "
        f"prosody irregularity: {prosody:.2f}, speaker drift: {consistency:.2f}"
        f"{phase_str}. Contributing factors: {factor_str}."
    )
    if not GROQ_API_KEY:
        return fallback

    prompt = (
        f"In one short sentence, explain to a bank fraud analyst why a call "
        f"scored {risk_score:.0f}/100 risk, given spectral_spoof_score={spectral:.2f}, "
        f"prosody_irregularity_score={prosody:.2f}, speaker_consistency_drift={consistency:.2f}"
        f"{phase_str}. "
        f"Contributing factors: {factor_str}. "
        f"Be concrete and factual, no hedging."
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "qwen/qwen3-27b",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                },
                timeout=5.0,
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return fallback


@app.post("/fuse")
async def fuse(payload: dict):
    """
    payload:
    {
      "session_id": str, "window_index": int,
      "spectral_score": float, "prosody_score": float, "consistency_score": float,
      "context": {optional CallContext fields},
      "phase_analysis": {optional phase analysis from spectral service},
      "enrollment_match": {optional enrollment match from consistency service}
    }
    """
    session_id = payload["session_id"]
    context = payload.get("context", {})
    phase_analysis = payload.get("phase_analysis")
    enrollment_match = payload.get("enrollment_match")

    risk_score, factors = weighted_fusion(
        payload["spectral_score"],
        payload["prosody_score"],
        payload["consistency_score"],
        context,
        phase_analysis,
        enrollment_match,
    )

    # --- Temporal trend analysis ---
    trend_info = detect_risk_spike(session_id, risk_score)

    # Spike detection can independently trigger alerts (mid-call swap)
    spike_alert = trend_info["spike_detected"]

    if risk_score >= RULES["alert_threshold"]:
        _consecutive_high_risk[session_id] = _consecutive_high_risk.get(session_id, 0) + 1
    else:
        _consecutive_high_risk[session_id] = 0

    alert_triggered = (
        _consecutive_high_risk.get(session_id, 0) >= RULES["min_consecutive_windows_above_threshold"]
        or spike_alert  # immediate alert on detected spike
    )

    rationale = await generate_rationale(
        payload["spectral_score"], payload["prosody_score"],
        payload["consistency_score"], risk_score,
        factors, phase_analysis,
    )

    return {
        "session_id": session_id,
        "window_index": payload["window_index"],
        "risk_score": risk_score,
        "spoof_score": payload["spectral_score"],
        "prosody_score": payload["prosody_score"],
        "consistency_score": payload["consistency_score"],
        "phase_analysis": phase_analysis,
        "enrollment_match": enrollment_match,
        "rationale": rationale,
        "alert_triggered": alert_triggered,
        "contributing_factors": factors,
        "trend_analysis": trend_info,
        "timestamp": time.time(),
    }


@app.get("/health")
def health():
    return {"status": "ok", "active_sessions": len(_risk_history)}
