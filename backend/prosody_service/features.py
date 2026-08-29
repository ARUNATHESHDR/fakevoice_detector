"""
Must extract the SAME ~40 features, in the SAME order, as
ml-training/prosody_model/extract_features.py -- the LightGBM model was
trained on this exact feature vector shape. If you change one side,
change the other.
"""

import numpy as np
import librosa
import parselmouth
from parselmouth.praat import call

N_MFCC = 13

FEATURE_ORDER = (
    ["f0_mean", "f0_std", "f0_min", "f0_max", "f0_range",
     "jitter", "shimmer", "hnr",
     "f1_mean", "f2_mean", "f3_mean",
     "spectral_centroid", "spectral_rolloff", "zcr",
     "pause_ratio", "speech_rate_proxy"]
    + [f"mfcc{i+1}_{stat}" for i in range(N_MFCC) for stat in ("mean", "std")]
)


def extract_from_array(pcm_int16: np.ndarray, sample_rate: int = 16000) -> dict:
    audio_float = pcm_int16.astype(np.float64) / 32768.0
    snd = parselmouth.Sound(audio_float, sampling_frequency=sample_rate)
    y = audio_float.astype(np.float32)
    sr = sample_rate

    pitch = snd.to_pitch()
    f0 = pitch.selected_array["frequency"]
    f0 = f0[f0 > 0]
    f0_mean = float(np.mean(f0)) if len(f0) else 0.0
    f0_std = float(np.std(f0)) if len(f0) else 0.0
    f0_min = float(np.min(f0)) if len(f0) else 0.0
    f0_max = float(np.max(f0)) if len(f0) else 0.0

    try:
        point_process = call(snd, "To PointProcess (periodic, cc)", 75, 500)
        jitter = call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3) or 0.0
        shimmer = call([snd, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6) or 0.0
    except Exception:
        jitter, shimmer = 0.0, 0.0

    try:
        harmonicity = call(snd, "To Harmonicity (cc)", 0.01, 75, 0.1, 1.0)
        hnr = call(harmonicity, "Get mean", 0, 0)
        hnr = 0.0 if (hnr is None or np.isnan(hnr)) else float(hnr)
    except Exception:
        hnr = 0.0

    try:
        formant = snd.to_formant_burg()
        f1_vals, f2_vals, f3_vals = [], [], []
        for t in np.arange(0, snd.duration, 0.01):
            f1_vals.append(formant.get_value_at_time(1, t))
            f2_vals.append(formant.get_value_at_time(2, t))
            f3_vals.append(formant.get_value_at_time(3, t))
        f1_vals = [v for v in f1_vals if v and not np.isnan(v)]
        f2_vals = [v for v in f2_vals if v and not np.isnan(v)]
        f3_vals = [v for v in f3_vals if v and not np.isnan(v)]
        f1_mean = float(np.mean(f1_vals)) if f1_vals else 0.0
        f2_mean = float(np.mean(f2_vals)) if f2_vals else 0.0
        f3_mean = float(np.mean(f3_vals)) if f3_vals else 0.0
    except Exception:
        f1_mean, f2_mean, f3_mean = 0.0, 0.0, 0.0

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC)
    mfcc_mean = mfcc.mean(axis=1)
    mfcc_std = mfcc.std(axis=1)

    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y=y)))

    intensity = snd.to_intensity()
    threshold = intensity.values.mean() - 10
    voiced_frames = intensity.values[intensity.values > threshold]
    pause_ratio = 1.0 - (len(voiced_frames) / max(intensity.values.size, 1))
    speech_rate_proxy = len(f0) / max(snd.duration, 0.01)

    features = {
        "f0_mean": f0_mean, "f0_std": f0_std, "f0_min": f0_min, "f0_max": f0_max,
        "f0_range": f0_max - f0_min,
        "jitter": float(jitter), "shimmer": float(shimmer), "hnr": hnr,
        "f1_mean": f1_mean, "f2_mean": f2_mean, "f3_mean": f3_mean,
        "spectral_centroid": centroid, "spectral_rolloff": rolloff, "zcr": zcr,
        "pause_ratio": float(pause_ratio), "speech_rate_proxy": float(speech_rate_proxy),
    }
    for i in range(N_MFCC):
        features[f"mfcc{i+1}_mean"] = float(mfcc_mean[i])
        features[f"mfcc{i+1}_std"] = float(mfcc_std[i])

    return features
