"""
Alerting & workflow service.

Receives a RiskScoreResult from the fusion engine when alert_triggered=True,
picks the matching workflow scenario, dispatches to the frontend over
WebSocket, and (optionally) fires SMS/email via Twilio/SendGrid.

ENHANCEMENTS v2:
  - 7 configurable workflow scenarios (banking, telecom, govt, enterprise)
  - Pre-transaction blocking warnings with MFA/callback requirements
  - Severity classification (CRITICAL/HIGH/MEDIUM/LOW)
  - Real-time score updates with trend data for the dashboard
  - In-app notification queue for mobile/desktop push
"""

import json
import os
import time
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="Alerting & Workflow Service")

WORKFLOWS_PATH = os.path.join(os.path.dirname(__file__), "workflows.json")
with open(WORKFLOWS_PATH) as f:
    WORKFLOWS = json.load(f)["scenarios"]

MOCK_NOTIFICATIONS = os.environ.get("MOCK_NOTIFICATIONS", "true").lower() == "true"
FRAUD_LEDGER_URL = os.environ.get("FRAUD_LEDGER_URL", "http://localhost:8007/ledger/append")

# active dashboard connections, keyed by session_id
_connections: dict[str, list[WebSocket]] = {}

# in-app notification queue (for mobile/desktop push -- polled by frontend)
_notification_queue: dict[str, list[dict]] = {}

# alert history for audit trail
_alert_history: list[dict] = []


def classify_severity(risk_score: float, trend: dict = None) -> dict:
    """Classify alert severity with appropriate response urgency."""
    spike = trend.get("spike_detected", False) if trend else False

    if risk_score >= 85 or spike:
        return {
            "level": "CRITICAL",
            "color": "#ff1744",
            "urgency": "IMMEDIATE",
            "description": "Voice impersonation attack highly likely. Block all pending transactions.",
            "auto_block": True,
        }
    elif risk_score >= 65:
        return {
            "level": "HIGH",
            "color": "#ff5722",
            "urgency": "URGENT",
            "description": "Significant voice anomalies detected. Require secondary verification.",
            "auto_block": False,
        }
    elif risk_score >= 45:
        return {
            "level": "MEDIUM",
            "color": "#ff9800",
            "urgency": "ELEVATED",
            "description": "Moderate voice irregularities. Monitor closely and consider verification.",
            "auto_block": False,
        }
    else:
        return {
            "level": "LOW",
            "color": "#4caf50",
            "urgency": "ROUTINE",
            "description": "Voice patterns within normal parameters.",
            "auto_block": False,
        }


def pick_workflow(scenario_name: str | None, risk_score: float = 0):
    """Select the appropriate workflow based on scenario and risk level."""
    if scenario_name:
        for w in WORKFLOWS:
            if w["name"] == scenario_name:
                return w

    # Auto-select based on risk level if no scenario specified
    for w in WORKFLOWS:
        if risk_score >= w.get("risk_threshold", 100):
            return w

    return next(w for w in WORKFLOWS if w["name"] == "default")


def send_sms(to_number: str, message: str):
    if MOCK_NOTIFICATIONS:
        print(f"[MOCK SMS] to={to_number}: {message}")
        return
    # from twilio.rest import Client
    # client = Client(os.environ["TWILIO_SID"], os.environ["TWILIO_TOKEN"])
    # client.messages.create(to=to_number, from_=os.environ["TWILIO_FROM"], body=message)


def send_email(to_address: str, subject: str, message: str):
    if MOCK_NOTIFICATIONS:
        print(f"[MOCK EMAIL] to={to_address} subject={subject}: {message}")
        return
    # SendGrid client call goes here once you have sandbox credentials


@app.websocket("/ws/alerts/{session_id}")
async def alert_socket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    _connections.setdefault(session_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; client doesn't need to send anything meaningful
    except WebSocketDisconnect:
        _connections[session_id].remove(websocket)


@app.post("/score_update")
async def score_update(payload: dict):
    """
    Called by the gateway for EVERY window (not just alerts) so the
    dashboard's live gauge and per-layer breakdown can update in real time.
    Now includes trend analysis and phase data.
    """
    session_id = payload["session_id"]
    message = {"type": "score_update", **payload}
    for ws in _connections.get(session_id, []):
        try:
            await ws.send_json(message)
        except Exception:
            pass
    return {"status": "pushed"}


async def record_to_ledger(payload: dict, recommended_action: str):
    """Sends only metadata (session id, score, rationale, recommended
    action) to the fraud ledger -- never raw audio or a voice embedding.
    A ledger failure should never block the actual alert from reaching
    the dashboard/SMS/email, so this is fire-and-forget with its own
    error handling."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(FRAUD_LEDGER_URL, json={
                "session_id": payload["session_id"],
                "risk_score": payload["risk_score"],
                "rationale": payload["rationale"],
                "recommended_action": recommended_action,
                "caller_hash": payload.get("caller_hash"),  # pre-hashed upstream, if provided
            }, timeout=5.0)
    except Exception as e:
        print(f"[fraud ledger] failed to record alert (non-fatal): {e}")


@app.post("/alert")
async def alert(payload: dict):
    """
    payload: RiskScoreResult fields, plus optional "scenario" name.
    Called by the gateway only when alert_triggered=True.
    """
    session_id = payload["session_id"]
    risk_score = payload.get("risk_score", 0)
    trend = payload.get("trend_analysis", {})

    workflow = pick_workflow(payload.get("scenario"), risk_score)
    severity = classify_severity(risk_score, trend)

    alert_message = {
        "type": "alert",
        "session_id": session_id,
        "risk_score": risk_score,
        "rationale": payload["rationale"],
        "recommended_action": workflow["recommended_action"],
        "severity": severity,
        "contributing_factors": payload.get("contributing_factors", []),
        "trend_analysis": trend,
        "enrollment_match": payload.get("enrollment_match"),
        "timestamp": time.time(),
        # Pre-transaction blocking flag -- frontend shows a blocking modal
        "block_transaction": severity["auto_block"],
        "verification_required": workflow.get("verification_required", []),
    }

    # Push to WebSocket
    for ws in _connections.get(session_id, []):
        try:
            await ws.send_json(alert_message)
        except Exception:
            pass

    # Queue for in-app notification polling
    _notification_queue.setdefault(session_id, []).append(alert_message)
    if len(_notification_queue[session_id]) > 50:
        _notification_queue[session_id].pop(0)

    # Store in alert history
    _alert_history.append(alert_message)
    if len(_alert_history) > 200:
        _alert_history.pop(0)

    # Dispatch external notifications
    if "sms" in workflow["notify_channels"]:
        send_sms(os.environ.get("ALERT_SMS_TO", "+10000000000"), alert_message["rationale"])
    if "email" in workflow["notify_channels"]:
        send_email(
            os.environ.get("ALERT_EMAIL_TO", "security@example.com"),
            f"[{severity['level']}] Voice impersonation risk alert",
            alert_message["rationale"],
        )

    await record_to_ledger(payload, workflow["recommended_action"])

    return {"status": "dispatched", "recommended_action": workflow["recommended_action"],
            "severity": severity["level"]}


@app.get("/notifications/{session_id}")
async def get_notifications(session_id: str):
    """Poll pending notifications for a session (for mobile/desktop apps)."""
    notifications = _notification_queue.pop(session_id, [])
    return {"session_id": session_id, "notifications": notifications}


@app.get("/alert-history")
async def get_alert_history(limit: int = 50):
    """Returns recent alert history for audit/review."""
    return {"alerts": _alert_history[-limit:], "total": len(_alert_history)}


@app.get("/health")
def health():
    return {"status": "ok", "mock_notifications": MOCK_NOTIFICATIONS,
            "active_connections": sum(len(v) for v in _connections.values())}
