"""Voice activity detection.

Prefers Silero VAD (torch-based) for accuracy, but falls back to a simple
energy-threshold VAD when torch is unavailable (e.g. blocked by Device Guard).
"""

import numpy as np

try:
    import torch
    TORCH_AVAILABLE = True
except OSError:
    TORCH_AVAILABLE = False

_model = None
_utils = None


def _load_silero():
    global _model, _utils
    if _model is None:
        _model, _utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad", model="silero_vad", trust_repo=True
        )
    return _model, _utils


def _energy_vad(pcm_int16: np.ndarray, threshold: float = 100.0) -> bool:
    """Simple RMS energy-based voice activity detection.
    Works without torch -- good enough for a demo."""
    rms = np.sqrt(np.mean(pcm_int16.astype(np.float64) ** 2))
    return rms > threshold


def contains_speech(pcm_int16: np.ndarray, sample_rate: int = 16000, threshold: float = 0.5) -> bool:
    """pcm_int16: 1-D numpy array of int16 samples."""
    if not TORCH_AVAILABLE:
        return _energy_vad(pcm_int16)

    try:
        model, utils = _load_silero()
        get_speech_timestamps = utils[0]
        audio_float = torch.from_numpy(pcm_int16.astype(np.float32) / 32768.0)
        timestamps = get_speech_timestamps(audio_float, model, sampling_rate=sample_rate, threshold=threshold)
        return len(timestamps) > 0
    except Exception:
        # Silero download failed or model error -- fall back to energy VAD
        return _energy_vad(pcm_int16)
