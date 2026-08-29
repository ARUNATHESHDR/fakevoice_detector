"""
RawNet2-style spoof-detection model (Tak et al., "End-to-End anti-spoofing
with RawNet2", ICASSP 2021). This is a real, published architecture used
as a strong baseline throughout the ASVspoof literature -- not a
simplified stand-in.

Architecture, top to bottom:
  1. SincConv front-end -- learnable band-pass filters applied directly
     to the raw waveform (no hand-crafted spectrogram step at all). Each
     filter learns its own center frequency and bandwidth during training.
  2. A stack of residual blocks, each with Filter-wise Feature Map Scaling
     (FMS) -- a lightweight attention mechanism that lets the network
     emphasize whichever filters are currently most discriminative.
  3. A GRU that aggregates the sequence of learned features over time.
  4. A small classifier head producing one logit (sigmoid -> spoof_score).

Operating on raw waveform (rather than a spectrogram) lets the network
learn its own frequency decomposition instead of inheriting the biases
baked into a fixed mel-filterbank -- this is a meaningful part of why
RawNet2-family models outperform plain spectrogram CNNs on this task.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class SincConv(nn.Module):
    """Learnable sinc band-pass filterbank (SincNet-style front end)."""

    def __init__(self, out_channels: int, kernel_size: int, sample_rate: int = 16000,
                 min_low_hz: float = 50.0, min_band_hz: float = 50.0):
        super().__init__()
        if kernel_size % 2 == 0:
            kernel_size += 1
        self.out_channels = out_channels
        self.kernel_size = kernel_size
        self.sample_rate = sample_rate
        self.min_low_hz = min_low_hz
        self.min_band_hz = min_band_hz

        low_hz, high_hz = 30.0, sample_rate / 2 - (min_low_hz + min_band_hz)
        mel = np.linspace(self._to_mel(low_hz), self._to_mel(high_hz), out_channels + 1)
        hz = self._to_hz(mel)

        self.low_hz_ = nn.Parameter(torch.Tensor(hz[:-1]).view(-1, 1))
        self.band_hz_ = nn.Parameter(torch.Tensor(np.diff(hz)).view(-1, 1))

        n_lin = torch.linspace(0, self.kernel_size / 2 - 1, steps=int(self.kernel_size / 2))
        window = 0.54 - 0.46 * torch.cos(2 * np.pi * n_lin / self.kernel_size)
        self.register_buffer("window_", window)

        n = (self.kernel_size - 1) / 2.0
        n_ = 2 * np.pi * torch.arange(-n, 0).view(1, -1) / self.sample_rate
        self.register_buffer("n_", n_)

    @staticmethod
    def _to_mel(hz):
        return 2595 * np.log10(1 + hz / 700)

    @staticmethod
    def _to_hz(mel):
        return 700 * (10 ** (mel / 2595) - 1)

    def forward(self, waveforms: torch.Tensor) -> torch.Tensor:
        low = self.min_low_hz + torch.abs(self.low_hz_)
        high = torch.clamp(low + self.min_band_hz + torch.abs(self.band_hz_),
                            self.min_low_hz, self.sample_rate / 2)
        band = (high - low)[:, 0]

        f_times_t_low = torch.matmul(low, self.n_)
        f_times_t_high = torch.matmul(high, self.n_)

        band_pass_left = ((torch.sin(f_times_t_high) - torch.sin(f_times_t_low))
                           / (self.n_ / 2)) * self.window_
        band_pass_center = 2 * band.view(-1, 1)
        band_pass_right = torch.flip(band_pass_left, dims=[1])

        band_pass = torch.cat([band_pass_left, band_pass_center, band_pass_right], dim=1)
        band_pass = band_pass / (2 * band[:, None])

        filters = band_pass.view(self.out_channels, 1, self.kernel_size)
        return F.conv1d(waveforms, filters, stride=1, padding=self.kernel_size // 2)


class FMS(nn.Module):
    """Filter-wise Feature Map Scaling -- channel attention applied after
    each residual block, letting the network re-weight filters by how
    useful they currently are for the spoof/genuine decision."""

    def __init__(self, channels: int):
        super().__init__()
        self.fc = nn.Linear(channels, channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        pooled = F.adaptive_avg_pool1d(x, 1).squeeze(-1)
        scale = torch.sigmoid(self.fc(pooled)).unsqueeze(-1)
        return x * scale + scale


class ResBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, first: bool = False):
        super().__init__()
        self.first = first
        if not first:
            self.bn1 = nn.BatchNorm1d(in_channels)
        self.conv1 = nn.Conv1d(in_channels, out_channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(out_channels)
        self.conv2 = nn.Conv1d(out_channels, out_channels, kernel_size=3, padding=1)

        self.downsample = (
            nn.Conv1d(in_channels, out_channels, kernel_size=1)
            if in_channels != out_channels else None
        )
        self.fms = FMS(out_channels)
        self.pool = nn.MaxPool1d(3)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x
        out = x if self.first else F.leaky_relu(self.bn1(x), 0.3)
        out = self.conv1(out)
        out = F.leaky_relu(self.bn2(out), 0.3)
        out = self.conv2(out)

        if self.downsample is not None:
            identity = self.downsample(identity)
        out = out + identity
        out = self.fms(out)
        return self.pool(out)


class RawNet2(nn.Module):
    """
    Input:  raw waveform, shape (batch, 1, samples) -- 64600 samples
            (~4.04s at 16kHz) is the standard fixed length used in the
            ASVspoof literature for this architecture family.
    Output: single logit -- sigmoid gives spoof_score in [0,1].
    """

    def __init__(self, sample_rate: int = 16000):
        super().__init__()
        self.sinc = SincConv(out_channels=70, kernel_size=129, sample_rate=sample_rate)
        self.bn0 = nn.BatchNorm1d(70)

        self.block1 = ResBlock(70, 20, first=True)
        self.block2 = ResBlock(20, 20)
        self.block3 = ResBlock(20, 128)
        self.block4 = ResBlock(128, 128)
        self.block5 = ResBlock(128, 128)
        self.block6 = ResBlock(128, 128)

        self.gru = nn.GRU(input_size=128, hidden_size=1024, num_layers=3, batch_first=True)
        self.fc1 = nn.Linear(1024, 1024)
        self.dropout = nn.Dropout(0.3)
        self.fc2 = nn.Linear(1024, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.sinc(x)
        out = F.max_pool1d(torch.abs(out), 3)
        out = F.leaky_relu(self.bn0(out), 0.3)

        out = self.block1(out)
        out = self.block2(out)
        out = self.block3(out)
        out = self.block4(out)
        out = self.block5(out)
        out = self.block6(out)

        out = out.transpose(1, 2)  # (batch, time, channels) for the GRU
        out, _ = self.gru(out)
        out = out[:, -1, :]  # final time step's hidden state

        out = F.leaky_relu(self.fc1(out), 0.3)
        out = self.dropout(out)
        return self.fc2(out).squeeze(-1)
