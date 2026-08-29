# ML Training — Datasets & Workflow (upgraded, no time constraint)

You train two of the three models on **Kaggle** (free GPU), download the
resulting checkpoint files, and drop them into the matching
`backend/*_service/models/` folder. Nothing in `backend/` needs internet
access to a training platform — it just loads whatever file you place
there.

Since we have two weeks and are optimizing for accuracy rather than
speed, both trainable models here are upgraded versions of what you'd
build under hackathon time pressure:

- **Spectral model**: RawNet2-style architecture (SincNet front-end +
  residual blocks + GRU) operating on raw waveform, trained with
  RawBoost-style augmentation, evaluated by EER (not just AUC).
- **Prosody model**: ~40 hand-crafted features (up from 6) + LightGBM
  with a proper Optuna hyperparameter search over 5-fold CV.

## Datasets

### 1. ASVspoof 2019 LA — for both trainable models
- **Official source:** https://datashare.ed.ac.uk/handle/10283/3336
- **On Kaggle:** search "ASVspoof 2019" — verify the exact folder layout
  when you add it, since community mirrors occasionally reorganize
  paths. These scripts assume the official `LA/LA/...` layout.
- ~25,000 bonafide + spoofed training utterances, 6 known spoof
  algorithms in train/dev. Standard benchmark for this exact problem.

### 2. Indian-accent fine-tuning set — for both models
The PS explicitly calls out "diverse Indian accents." ASVspoof alone
won't cover this on its own.
- Record 20-30 short Hindi-English code-switched sentences per team
  member (bonafide class)
- Clone the same sentences with a free/low-cost TTS tool (spoof class)
- Fine-tune both models on top of the ASVspoof-trained checkpoints for
  a handful of epochs on this supplementary set

### 3. Speaker consistency model — no dataset needed
Uses pretrained **ECAPA-TDNN** (VoxCeleb, via SpeechBrain) as-is — see
`speaker_consistency/download_ecapa.py`. No training required.

## Workflow

**Spectral model (RawNet2):**
1. New Kaggle Notebook, GPU accelerator on
2. Add the ASVspoof 2019 LA dataset as input
3. Paste `rawboost.py`, `model.py`, `dataset.py` as earlier cells, then
   `train.py` as the final cell
4. Fix `DATA_ROOT` in `train.py`
5. Run — trains up to 100 epochs with early stopping on dev EER, saves
   `rawnet2_spectral.pth` whenever EER improves. Expect several hours
   on a T4 — this is a genuinely heavier model than a simple CNN, by
   design, since we're optimizing for accuracy over speed.
6. Download the checkpoint, rename to `spectral_model.pth`, place in
   `backend/spectral_service/models/`

**Prosody model:**
1. Same notebook/dataset input
2. Run `extract_features.py` (slow — CPU-bound Praat + librosa feature
   extraction across the whole dataset; let it finish)
3. Run `train_lightgbm.py` — runs a 50-trial Optuna search with 5-fold
   CV per trial, then refits on the full training set. This takes a
   while by design; you're trading compute time for a properly tuned
   model instead of default hyperparameters.
4. Download `prosody_model.pkl`, place in
   `backend/prosody_service/models/`

**Speaker consistency model:**
1. Run `download_ecapa.py` locally (no GPU needed)
2. Copy `pretrained_ecapa/` into `backend/consistency_service/models/ecapa/`

## What "good" looks like

Published RawNet2 results on ASVspoof 2019 LA eval land in the
low single-digit EER range; your dev-set EER during training should
trend down into a similar range as training progresses. If EER plateaus
above ~10-15% after many epochs, something's likely off in the data
pipeline (check `DATA_ROOT`, check that file IDs are actually resolving
to real files) rather than the architecture being at fault.
