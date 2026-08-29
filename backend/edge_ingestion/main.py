"""
Edge ingestion service.

Responsibilities:
- Accept a WebSocket audio stream from the frontend (mic capture or a
  simulated call clip)
- Buffer into ~2-second sliding windows
- Run VAD, skip silent windows
- Forward each window (as base64 PCM) to the gateway, which fans it out
  to the three analysis services

Raw audio is only ever held in-memory in the ring buffer below and is
discarded once a window is forwarded -- this is what makes the "minimal
retention" privacy requirement true in code, not just in a policy doc.
"""

import base64
import uuid
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import httpx

from vad import contains_speech

app = FastAPI(title="Edge Ingestion Service")

WINDOW_SECONDS = 2
SAMPLE_RATE = 16000
WINDOW_SIZE = WINDOW_SECONDS * SAMPLE_RATE
import os
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000/ingest/window")


@app.websocket("/ws/audio")
async def audio_stream(websocket: WebSocket):
    await websocket.accept()
    session_id = str(uuid.uuid4())
    buffer = np.array([], dtype=np.int16)
    window_index = 0

    await websocket.send_json({"session_id": session_id})

    try:
        async with httpx.AsyncClient() as client:
            while True:
                chunk = await websocket.receive_bytes()
                incoming = np.frombuffer(chunk, dtype=np.int16)
                buffer = np.concatenate([buffer, incoming])

                while len(buffer) >= WINDOW_SIZE:
                    window = buffer[:WINDOW_SIZE]
                    buffer = buffer[WINDOW_SIZE:]  # discard consumed audio immediately

                    try:
                        if contains_speech(window, SAMPLE_RATE):
                            payload = {
                                "session_id": session_id,
                                "window_index": window_index,
                                "sample_rate": SAMPLE_RATE,
                                "pcm_base64": base64.b64encode(window.tobytes()).decode(),
                            }
                            resp = await client.post(GATEWAY_URL, json=payload, timeout=15.0)
                            print(f"[edge] session={session_id[:8]} window={window_index} -> gateway {resp.status_code}")
                        else:
                            print(f"[edge] session={session_id[:8]} window={window_index} -> silent, skipped")
                    except Exception as e:
                        print(f"[edge] ERROR processing window {window_index}: {e}")

                    window_index += 1

    except WebSocketDisconnect:
        print(f"[edge] session={session_id[:8]} disconnected after {window_index} windows")


@app.get("/health")
def health():
    return {"status": "ok"}
