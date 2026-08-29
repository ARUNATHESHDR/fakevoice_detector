"use client";

import { useState } from "react";

type PhaseAnalysis = {
  group_delay_deviation?: number;
  instantaneous_freq_deviation?: number;
  phase_randomness_index?: number;
  gdd_score?: number;
  ifd_score?: number;
  pri_score?: number;
  phase_score?: number;
};

type Scores = {
  spoof_score: number;
  prosody_score: number;
  consistency_score: number;
  phase_analysis?: PhaseAnalysis;
};

export default function ScoreBreakdownPlus({ scores }: { scores: Scores | null }) {
  const [showPhase, setShowPhase] = useState(false);

  const layers = [
    {
      name: "Spectral Artifacts (RawNet2)",
      value: scores?.spoof_score ?? 0,
      desc: "SincConv front-end learned filterbank",
      color: "#06b6d4",
    },
    {
      name: "Prosody Irregularity (LightGBM)",
      value: scores?.prosody_score ?? 0,
      desc: "40-feature Praat pitch/shimmer/HNR physics",
      color: "#8b5cf6",
    },
    {
      name: "Speaker Identity Drift (ECAPA-TDNN)",
      value: scores?.consistency_score ?? 0,
      desc: "VoxCeleb deep embeddings cosine similarity",
      color: "#f59e0b",
    },
  ];

  const phase = scores?.phase_analysis;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Multi-Layer Authenticity Breakdown</h2>
        <button
          onClick={() => setShowPhase(!showPhase)}
          style={{
            background: "rgba(6, 182, 212, 0.1)",
            border: "1px solid rgba(6, 182, 212, 0.3)",
            color: "#38bdf8",
            fontSize: 11,
            fontFamily: "var(--mono)",
            padding: "4px 8px",
            borderRadius: 6,
            cursor: "pointer",
          }}
        >
          {showPhase ? "Hide Phase Data ▲" : "Phase Spectrum Data ▼"}
        </button>
      </div>

      {!scores && (
        <div style={{ color: "var(--text-muted)", fontSize: 13, fontStyle: "italic", padding: "12px 0" }}>
          Waiting for live audio stream...
        </div>
      )}

      {scores && (
        <div>
          {layers.map((layer, i) => {
            const pct = Math.round(layer.value * 100);
            return (
              <div key={i} style={{ marginBottom: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                  <span style={{ fontWeight: 600 }}>{layer.name}</span>
                  <span style={{ fontFamily: "var(--mono)", color: pct > 60 ? "#f43f5e" : "var(--text)" }}>
                    {pct}%
                  </span>
                </div>

                <div
                  style={{
                    height: 6,
                    background: "rgba(255, 255, 255, 0.08)",
                    borderRadius: 3,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${pct}%`,
                      background: layer.color,
                      borderRadius: 3,
                      transition: "width 0.4s ease",
                      boxShadow: `0 0 10px ${layer.color}66`,
                    }}
                  />
                </div>

                <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>{layer.desc}</div>
              </div>
            );
          })}

          {/* Phase Spectrum Analysis Expander */}
          {showPhase && phase && (
            <div
              style={{
                marginTop: 16,
                padding: 12,
                borderRadius: 8,
                background: "rgba(6, 182, 212, 0.05)",
                border: "1px solid rgba(6, 182, 212, 0.2)",
                fontSize: 11,
                fontFamily: "var(--mono)",
              }}
            >
              <div style={{ fontWeight: 700, color: "#38bdf8", marginBottom: 8 }}>
                🔬 PHASE SPECTRUM ANOMALY ANALYSIS (PS 26104)
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, color: "var(--text-dim)" }}>
                <div>
                  Group Delay Deviation: <b style={{ color: "#fff" }}>{phase.group_delay_deviation ?? "N/A"}</b>
                </div>
                <div>
                  IFD Consistency: <b style={{ color: "#fff" }}>{phase.instantaneous_freq_deviation ?? "N/A"}</b>
                </div>
                <div>
                  Phase Randomness (PRI): <b style={{ color: "#fff" }}>{phase.phase_randomness_index ?? "N/A"}</b>
                </div>
                <div>
                  Combined Phase Score: <b style={{ color: phase.phase_score && phase.phase_score > 0.5 ? "#f43f5e" : "#10b981" }}>
                    {phase.phase_score ? `${(phase.phase_score * 100).toFixed(0)}%` : "N/A"}
                  </b>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
