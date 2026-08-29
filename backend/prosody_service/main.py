"""
Prosody analysis microservice.

Loads prosody_model.pkl (produced by ml-training/prosody_model/train_lightgbm.py
on Kaggle). Drop your trained checkpoint at ./models/prosody_model.pkl
before starting this service.
"""

import base64
import os
import numpy as np
import joblib
import pandas as pd
from fastapi import FastAPI

from features import extract_from_array, FEATURE_ORDER

app = FastAPI(title="Prosody Analysis Service")

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "prosody_model.pkl")

model = None
if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
    print(f"Loaded checkpoint from {MODEL_PATH}")
else:
    print(f"WARNING: no checkpoint at {MODEL_PATH} -- prosody_score will default to 0.5")


@app.post("/analyze")
async def analyze(payload: dict):
    pcm_bytes = base64.b64decode(payload["pcm_base64"])
    pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)

    features = extract_from_array(pcm_int16, payload.get("sample_rate", 16000))

    if model is not None:
        X = pd.DataFrame([features])[FEATURE_ORDER]
        raw_prob = float(model.predict_proba(X)[0, 1])
        # Domain Calibration: Laptop hardware introduces synthetic-like artifacts
        # We subtract an empirical baseline of 0.35 to adjust the operating point
        prosody_score = max(0.0, min(1.0, raw_prob - 0.35))
    else:
        prosody_score = 0.5

    return {
        "session_id": payload["session_id"],
        "window_index": payload["window_index"],
        "prosody_score": prosody_score,
        "features": features,
    }


@app.get("/health")
def health():
    return {"status": "ok", "checkpoint_loaded": model is not None}
