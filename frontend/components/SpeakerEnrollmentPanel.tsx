"use client";

import { useEffect, useState } from "react";

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";

type EnrolledSpeaker = {
  speaker_id: string;
  name: string;
  enrolled_at: number;
  num_samples: number;
};

export default function SpeakerEnrollmentPanel() {
  const [speakers, setSpeakers] = useState<EnrolledSpeaker[]>([]);
  const [speakerName, setSpeakerName] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  async function fetchEnrolled() {
    try {
      const res = await fetch(`${GATEWAY_URL}/api/v1/enrolled-speakers`);
      const data = await res.json();
      setSpeakers(data.enrolled_speakers || []);
    } catch {
      // Gateway unreachable
    }
  }

  useEffect(() => {
    fetchEnrolled();
  }, []);

  async function handleEnrollSample(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !speakerName.trim()) {
      setStatusMsg("Please enter a Speaker Name before uploading an audio sample!");
      return;
    }

    setLoading(true);
    setStatusMsg(`Extracting ECAPA-TDNN voiceprint for ${speakerName}...`);

    try {
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = "";
      for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
      }
      const b64 = btoa(binary);

      const payload = {
        speaker_name: speakerName.trim(),
        audio_samples: [{ pcm_base64: b64, sample_rate: 16000 }],
      };

      const res = await fetch(`${GATEWAY_URL}/api/v1/enroll-speaker`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (data.status === "enrolled") {
        setStatusMsg(`Successfully enrolled ${speakerName}! Voiceprint stored.`);
        setSpeakerName("");
        fetchEnrolled();
      } else {
        setStatusMsg(`Enrollment failed: ${data.error || "Unknown error"}`);
      }
    } catch (err: any) {
      setStatusMsg(`Error during enrollment: ${err.message}`);
    } finally {
      setLoading(false);
      e.target.value = "";
    }
  }

  async function handleDelete(id: string) {
    try {
      await fetch(`${GATEWAY_URL}/api/v1/enrolled-speaker/${id}`, { method: "DELETE" });
      fetchEnrolled();
    } catch {
      // Error
    }
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Executive Speaker Enrollment & Voiceprints</h2>
        <span style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--accent-cyan)" }}>
          ECAPA-TDNN DEEP BIOMETRICS
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        {/* Enroll Form */}
        <div style={{ background: "rgba(15, 23, 42, 0.6)", padding: 16, borderRadius: 10, border: "1px solid var(--panel-border)" }}>
          <h3 style={{ margin: "0 0 12px", fontSize: 13, color: "#38bdf8" }}>+ Enroll New Executive Voice</h3>

          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              SPEAKER NAME / TITLE
            </label>
            <input
              type="text"
              className="form-input"
              placeholder="e.g. CFO Rajesh Sharma"
              value={speakerName}
              onChange={(e) => setSpeakerName(e.target.value)}
            />
          </div>

          <div style={{ position: "relative" }}>
            <button className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={loading}>
              {loading ? "Extracting Embeddings..." : "🎙️ Upload Reference Audio Sample (.wav)"}
            </button>
            <input
              type="file"
              accept="audio/*"
              onChange={handleEnrollSample}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: "100%",
                opacity: 0,
                cursor: "pointer",
              }}
            />
          </div>

          {statusMsg && (
            <div style={{ marginTop: 10, fontSize: 11, fontFamily: "var(--mono)", color: "#38bdf8" }}>
              {statusMsg}
            </div>
          )}
        </div>

        {/* Enrolled Profiles List */}
        <div>
          <h3 style={{ margin: "0 0 12px", fontSize: 13, color: "#94a3b8" }}>
            Active Voiceprints ({speakers.length})
          </h3>

          {speakers.length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: 12, fontStyle: "italic" }}>
              No speakers enrolled yet. Enroll an executive's voice to verify future calls against genuine samples.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 180, overflowY: "auto" }}>
              {speakers.map((s) => (
                <div
                  key={s.speaker_id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    background: "rgba(30, 41, 59, 0.5)",
                    padding: "8px 12px",
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600, color: "#fff" }}>{s.name}</div>
                    <div style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
                      ID: {s.speaker_id.slice(0, 8)} • {s.num_samples} audio samples
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(s.speaker_id)}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "#f43f5e",
                      cursor: "pointer",
                      fontSize: 14,
                    }}
                    title="Delete Voiceprint"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
