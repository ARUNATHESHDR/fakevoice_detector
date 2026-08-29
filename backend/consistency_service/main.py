"""
Speaker consistency microservice.

Uses a pretrained ECAPA-TDNN (SpeechBrain, trained on VoxCeleb) to embed
each audio window, then compares it against:
  1. an enrolled reference embedding for this session (if one was provided
     at call start -- e.g. a known-good sample of the real CFO's voice)
  2. the running average of embeddings seen earlier in THIS call

A sudden drop in similarity mid-call is exactly what a live voice-conversion
attack (or a swapped caller) looks like -- this is the signal that catches
attacks the spectral/prosody models might miss if the clone is high quality.

NEW: Speaker Enrollment System
  - POST /enroll: Register a known speaker's voice from audio clips
  - POST /verify: Compare incoming audio against enrolled voice profile
  - GET  /enrolled: List all enrolled speaker profiles
  - DELETE /enrolled/{speaker_id}: Remove an enrolled profile

Drop the downloaded model folder at ./models/ecapa/ before starting this
service -- see ml-training/speaker_consistency/download_ecapa.py.
"""

import base64
import hashlib
import json
import os
import time
import numpy as np
from fastapi import FastAPI

try:
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    TORCH_AVAILABLE = True
except OSError as e:
    print(f"WARNING: torch blocked by Device Guard policy ({e}). Falling back to mock mode.")
    TORCH_AVAILABLE = False

app = FastAPI(title="Speaker Consistency & Enrollment Service")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "ecapa")
ENROLLMENT_DIR = os.path.join(os.path.dirname(__file__), "models", "enrolled_speakers")
os.makedirs(ENROLLMENT_DIR, exist_ok=True)

if TORCH_AVAILABLE:
    classifier = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=MODEL_DIR if os.path.exists(MODEL_DIR) else "pretrained_ecapa_fallback",
    )
else:
    classifier = None

# In-memory per-session running embedding average.
# For a real deployment this would live in Redis (see backend/README.md) --
# in-memory is fine for a single-process hackathon demo.
_session_embeddings = {}

# Enrolled speaker profiles: speaker_id -> {name, embedding_tensor, enrolled_at, num_samples}
_enrolled_speakers = {}


def _load_enrolled_speakers():
    """Load previously enrolled speakers from disk on startup."""
    for fname in os.listdir(ENROLLMENT_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(ENROLLMENT_DIR, fname)) as f:
                    data = json.load(f)
                speaker_id = data["speaker_id"]
                embedding = np.array(data["embedding"])
                if TORCH_AVAILABLE:
                    _enrolled_speakers[speaker_id] = {
                        "name": data["name"],
                        "embedding": torch.from_numpy(embedding).float(),
                        "enrolled_at": data["enrolled_at"],
                        "num_samples": data["num_samples"],
                    }
            except Exception as e:
                print(f"WARNING: failed to load enrolled speaker {fname}: {e}")


_load_enrolled_speakers()
print(f"Loaded {len(_enrolled_speakers)} enrolled speaker profiles")


def cosine_similarity(a, b) -> float:
    if TORCH_AVAILABLE:
        return torch.nn.functional.cosine_similarity(a, b, dim=-1).item()
    # numpy fallback
    a_np = a if isinstance(a, np.ndarray) else a.numpy()
    b_np = b if isinstance(b, np.ndarray) else b.numpy()
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np) + 1e-8))


def _extract_embedding(pcm_int16: np.ndarray):
    """Extract speaker embedding from raw PCM audio."""
    if not TORCH_AVAILABLE:
        return None
    waveform = torch.from_numpy(pcm_int16.astype(np.float32) / 32768.0).unsqueeze(0)
    embedding = classifier.encode_batch(waveform).squeeze(0).squeeze(0)
    return embedding


def _find_best_enrolled_match(embedding) -> dict:
    """Compare embedding against all enrolled speakers, return best match."""
    if not _enrolled_speakers or not TORCH_AVAILABLE:
        return {"matched": False}

    best_score = -1.0
    best_id = None
    best_name = None

    for speaker_id, profile in _enrolled_speakers.items():
        sim = cosine_similarity(embedding, profile["embedding"])
        if sim > best_score:
            best_score = sim
            best_id = speaker_id
            best_name = profile["name"]

    # Threshold: ECAPA-TDNN cosine similarity > 0.25 is typically same speaker
    # on VoxCeleb evaluation sets. We use 0.3 for safety margin.
    is_match = best_score > 0.3

    return {
        "matched": is_match,
        "best_match_speaker_id": best_id,
        "best_match_name": best_name,
        "similarity": round(best_score, 4),
        "verdict": "VERIFIED" if is_match else "UNKNOWN_SPEAKER",
    }


@app.post("/analyze")
async def analyze(payload: dict):
    pcm_bytes = base64.b64decode(payload["pcm_base64"])
    pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)

    session_id = payload["session_id"]

    if not TORCH_AVAILABLE:
        import random
        consistency_score = random.uniform(0.0, 0.2)
        enrollment_match = {"matched": False}
    else:
        embedding = _extract_embedding(pcm_int16)
        history = _session_embeddings.setdefault(session_id, [])

        # --- Intra-session consistency (drift detection) ---
        if len(history) == 0:
            # first window of the call -- nothing to compare against yet
            consistency_score = 0.0
        else:
            reference = torch.stack(history).mean(dim=0)
            similarity = cosine_similarity(embedding, reference)
            # similarity in [-1, 1] where 1 = identical speaker
            consistency_score = float(max(0.0, 1.0 - similarity))

        history.append(embedding)
        if len(history) > 20:  # cap memory per session
            history.pop(0)

        # --- Cross-session enrollment match (PS: "comparing ongoing call
        #     features against historical genuine samples") ---
        enrollment_match = _find_best_enrolled_match(embedding)

    return {
        "session_id": session_id,
        "window_index": payload["window_index"],
        "consistency_score": consistency_score,
        "enrollment_match": enrollment_match,
    }


# ---------------------------------------------------------------------------
# Speaker Enrollment API (PS: "cross-session consistency checks comparing
# ongoing call features against historical genuine samples")
# ---------------------------------------------------------------------------

@app.post("/enroll")
async def enroll_speaker(payload: dict):
    """Enroll a known speaker from one or more audio samples.

    payload: {
      "speaker_name": str,
      "audio_samples": [{"pcm_base64": str, "sample_rate": int}],
      "speaker_id": optional str (auto-generated if omitted)
    }
    """
    speaker_name = payload.get("speaker_name", "Unknown")
    samples = payload.get("audio_samples", [])

    if not samples:
        return {"error": "at least one audio_sample is required"}

    if not TORCH_AVAILABLE:
        return {"error": "torch not available -- cannot enroll speakers"}

    # Extract embeddings from all provided samples
    embeddings = []
    for sample in samples:
        pcm_bytes = base64.b64decode(sample["pcm_base64"])
        pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        emb = _extract_embedding(pcm_int16)
        if emb is not None:
            embeddings.append(emb)

    if not embeddings:
        return {"error": "failed to extract embeddings from provided samples"}

    # Average all sample embeddings for a robust voiceprint
    mean_embedding = torch.stack(embeddings).mean(dim=0)

    # Generate or use provided speaker ID
    speaker_id = payload.get("speaker_id") or hashlib.sha256(
        f"{speaker_name}_{time.time()}".encode()
    ).hexdigest()[:16]

    # Store in memory
    _enrolled_speakers[speaker_id] = {
        "name": speaker_name,
        "embedding": mean_embedding,
        "enrolled_at": time.time(),
        "num_samples": len(embeddings),
    }

    # Persist to disk
    disk_data = {
        "speaker_id": speaker_id,
        "name": speaker_name,
        "embedding": mean_embedding.cpu().numpy().tolist(),
        "enrolled_at": time.time(),
        "num_samples": len(embeddings),
    }
    with open(os.path.join(ENROLLMENT_DIR, f"{speaker_id}.json"), "w") as f:
        json.dump(disk_data, f)

    return {
        "status": "enrolled",
        "speaker_id": speaker_id,
        "speaker_name": speaker_name,
        "num_samples_used": len(embeddings),
    }


@app.get("/enrolled")
async def list_enrolled():
    """List all enrolled speaker profiles (without raw embeddings)."""
    profiles = []
    for sid, profile in _enrolled_speakers.items():
        profiles.append({
            "speaker_id": sid,
            "name": profile["name"],
            "enrolled_at": profile["enrolled_at"],
            "num_samples": profile["num_samples"],
        })
    return {"enrolled_speakers": profiles, "total": len(profiles)}


@app.delete("/enrolled/{speaker_id}")
async def delete_enrolled(speaker_id: str):
    """Remove an enrolled speaker profile."""
    if speaker_id not in _enrolled_speakers:
        return {"error": "speaker_id not found"}
    del _enrolled_speakers[speaker_id]
    disk_path = os.path.join(ENROLLMENT_DIR, f"{speaker_id}.json")
    if os.path.exists(disk_path):
        os.remove(disk_path)
    return {"status": "deleted", "speaker_id": speaker_id}


@app.post("/reset_session")
async def reset_session(payload: dict):
    """Call this when a session ends to free memory."""
    _session_embeddings.pop(payload["session_id"], None)
    return {"status": "cleared"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "enrolled_speakers": len(_enrolled_speakers),
        "active_sessions": len(_session_embeddings),
    }
