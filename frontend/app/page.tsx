"use client";

import { useEffect, useRef, useState } from "react";
import AnimatedRiskGauge from "../components/AnimatedRiskGauge";
import ScoreBreakdownPlus from "../components/ScoreBreakdownPlus";
import AlertFeed from "../components/AlertFeed";
import LedgerStatus from "../components/LedgerStatus";
import WaveformVisualizer from "../components/WaveformVisualizer";
import RiskTimelineChart from "../components/RiskTimelineChart";
import AlertModal from "../components/AlertModal";
import SpeakerEnrollmentPanel from "../components/SpeakerEnrollmentPanel";
import PrivacyComplianceVault from "../components/PrivacyComplianceVault";

const EDGE_WS_URL = process.env.NEXT_PUBLIC_EDGE_WS_URL || "ws://localhost:8001/ws/audio";
const ALERTING_WS_BASE = process.env.NEXT_PUBLIC_ALERTING_WS_URL || "ws://localhost:8006/ws/alerts";
const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";

type Scores = {
  spoof_score: number;
  prosody_score: number;
  consistency_score: number;
  phase_analysis?: any;
};

type Alert = {
  risk_score: number;
  rationale: string;
  recommended_action: string;
  severity?: any;
  block_transaction?: boolean;
};

type StatusLog = {
  time: string;
  message: string;
  level: "info" | "success" | "error" | "warn";
};

type TimelineEntry = {
  window: number;
  risk: number;
  spectral: number;
  prosody: number;
  consistency: number;
};

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<"inspection" | "enrollment" | "privacy">("inspection");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [riskScore, setRiskScore] = useState(0);
  const [scores, setScores] = useState<Scores | null>(null);
  const [trend, setTrend] = useState<any>(null);
  const [enrollmentMatch, setEnrollmentMatch] = useState<any>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [modalAlert, setModalAlert] = useState<Alert | null>(null);
  const [listening, setListening] = useState(false);
  const [statusLogs, setStatusLogs] = useState<StatusLog[]>([]);
  const [windowsSent, setWindowsSent] = useState(0);
  const [serviceHealth, setServiceHealth] = useState<Record<string, boolean>>({});
  const [timelineData, setTimelineData] = useState<TimelineEntry[]>([]);

  const audioSocketRef = useRef<WebSocket | null>(null);
  const alertSocketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  function addLog(message: string, level: StatusLog["level"] = "info") {
    const time = new Date().toLocaleTimeString();
    setStatusLogs((prev) => [{ time, message, level }, ...prev].slice(0, 30));
  }

  // Check service health on mount
  useEffect(() => {
    async function checkHealth() {
      const services: Record<string, string> = {
        "Gateway REST (:8000)": "http://localhost:8000/health",
        "Edge Ingestion (:8001)": "http://localhost:8001/health",
        "RawNet2 Spectral (:8002)": "http://localhost:8002/health",
        "Prosody LightGBM (:8003)": "http://localhost:8003/health",
        "ECAPA Consistency (:8004)": "http://localhost:8004/health",
        "Risk Fusion Engine (:8005)": "http://localhost:8005/health",
        "Alerting & Workflow (:8006)": "http://localhost:8006/health",
        "Blockchain Ledger (:8007)": "http://localhost:8007/health",
      };
      const results: Record<string, boolean> = {};
      for (const [name, url] of Object.entries(services)) {
        try {
          const resp = await fetch(url, { signal: AbortSignal.timeout(2000) });
          results[name] = resp.ok;
        } catch {
          results[name] = false;
        }
      }
      setServiceHealth(results);
      const down = Object.entries(results).filter(([, ok]) => !ok).map(([n]) => n);
      if (down.length === 0) {
        addLog("All 8 backend microservices & gRPC server online ✓", "success");
      } else {
        addLog(`Backend services offline: ${down.join(", ")}`, "error");
      }
    }
    checkHealth();
  }, []);

  // Connect to Alerting WebSocket when sessionId is assigned
  useEffect(() => {
    if (!sessionId) return;

    addLog(`Subscribing to real-time alerts for session ${sessionId.slice(0, 8)}...`, "info");
    const alertSocket = new WebSocket(`${ALERTING_WS_BASE}/${sessionId}`);

    alertSocket.onopen = () => {
      addLog("Alerting WebSocket channel connected ✓", "success");
    };
    alertSocket.onerror = () => {
      addLog("Alert WebSocket connection failed", "error");
    };
    alertSocket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "score_update") {
        setRiskScore(msg.risk_score);
        setScores({
          spoof_score: msg.spoof_score,
          prosody_score: msg.prosody_score,
          consistency_score: msg.consistency_score,
          phase_analysis: msg.phase_analysis,
        });
        setTrend(msg.trend_analysis);
        setEnrollmentMatch(msg.enrollment_match);

        // Update timeline chart
        setTimelineData((prev) => [
          ...prev,
          {
            window: msg.window_index,
            risk: Math.round(msg.risk_score),
            spectral: msg.spoof_score,
            prosody: msg.prosody_score,
            consistency: msg.consistency_score,
          },
        ].slice(-30));

        addLog(
          `Window #${msg.window_index}: Risk=${msg.risk_score.toFixed(1)}/100 | Spectral=${msg.spoof_score.toFixed(2)} | Prosody=${msg.prosody_score.toFixed(2)} | Consistency=${msg.consistency_score.toFixed(2)}`,
          msg.risk_score >= 65 ? "error" : "success"
        );
      } else if (msg.type === "alert") {
        setAlerts((prev) => [msg as Alert, ...prev]);
        setModalAlert(msg as Alert);
        addLog(`🚨 THREAT ALERT: ${msg.rationale}`, "error");
      }
    };
    alertSocketRef.current = alertSocket;

    return () => alertSocket.close();
  }, [sessionId]);

  async function startListening() {
    addLog("Requesting microphone stream access...", "info");

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        }
      });
      addLog("Microphone granted ✓", "success");
    } catch (err: any) {
      addLog(`Microphone access DENIED: ${err.message}`, "error");
      return;
    }
    streamRef.current = stream;

    addLog(`Connecting to Edge Ingestion WebSocket at ${EDGE_WS_URL}...`, "info");

    const socket = new WebSocket(EDGE_WS_URL);
    socket.binaryType = "arraybuffer";

    socket.onerror = () => {
      addLog("Edge WebSocket connection failed — check backend services", "error");
    };

    socket.onopen = () => {
      addLog("Streaming live audio chunks to Edge Ingestion pipeline...", "success");

      const audioContext = new AudioContext({ sampleRate: 16000 });
      audioCtxRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);

      let chunkCount = 0;
      processor.onaudioprocess = (e) => {
        if (socket.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        const pcm16 = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          pcm16[i] = Math.max(-32768, Math.min(32767, input[i] * 32768));
        }
        socket.send(pcm16.buffer);
        chunkCount++;
        if (chunkCount % 8 === 0) {
          setWindowsSent((prev) => prev + 1);
        }
      };

      // Mute the output to prevent feedback/echo cancellation muting the mic
      const gainNode = audioContext.createGain();
      gainNode.gain.value = 0;
      
      source.connect(processor);
      processor.connect(gainNode);
      gainNode.connect(audioContext.destination);
    };

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.session_id) {
        setSessionId(msg.session_id);
        addLog(`Call Session initialized: ${msg.session_id.slice(0, 8)}`, "success");
      }
    };

    audioSocketRef.current = socket;
    setListening(true);
    setWindowsSent(0);
    setTimelineData([]);
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    addLog(`Loading audio file: ${file.name}...`, "info");
    const arrayBuffer = await file.arrayBuffer();

    const audioContext = new AudioContext({ sampleRate: 16000 });
    audioCtxRef.current = audioContext;

    try {
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
      addLog("File decoded ✓ — streaming audio window frames...", "success");

      const socket = new WebSocket(EDGE_WS_URL);
      socket.binaryType = "arraybuffer";

      socket.onopen = () => {
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        const processor = audioContext.createScriptProcessor(4096, 1, 1);

        let chunkCount = 0;
        processor.onaudioprocess = (evt) => {
          if (socket.readyState !== WebSocket.OPEN) return;
          const input = evt.inputBuffer.getChannelData(0);
          const pcm16 = new Int16Array(input.length);
          for (let i = 0; i < input.length; i++) {
            pcm16[i] = Math.max(-32768, Math.min(32767, input[i] * 32768));
          }
          socket.send(pcm16.buffer);
          chunkCount++;
          if (chunkCount % 8 === 0) {
            setWindowsSent((prev) => prev + 1);
          }
        };

        source.connect(processor);
        processor.connect(audioContext.destination);
        source.start(0);

        source.onended = () => {
          addLog("File playback completed.", "success");
          stopListening();
        };
      };

      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.session_id) {
          setSessionId(msg.session_id);
          addLog(`Session started: ${msg.session_id.slice(0, 8)}`, "success");
        }
      };

      audioSocketRef.current = socket;
      setListening(true);
      setWindowsSent(0);
      setTimelineData([]);
    } catch (err: any) {
      addLog(`Failed to decode file: ${err.message}`, "error");
    }
    e.target.value = "";
  }

  function stopListening() {
    audioSocketRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioCtxRef.current?.close();
    setListening(false);
    addLog("Call simulation terminated.", "warn");
  }

  const logColors: Record<string, string> = {
    info: "#38bdf8",
    success: "#4ade80",
    error: "#f87171",
    warn: "#facc15",
  };

  return (
    <div className="app-shell">
      {/* Alert Warning Modal */}
      <AlertModal alertData={modalAlert} onDismiss={() => setModalAlert(null)} />

      {/* Header */}
      <div className="app-header">
        <div className="brand-title">
          <div className="brand-icon">🛡️</div>
          <div>
            <h1>Voice Integrity Verification Platform</h1>
            <div style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
              SIH 2026 Problem Statement 26104 • AI Real-Time Impersonation Detection
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="header-badge">gRPC :50051 & REST :8000</span>
          <span className="header-badge" style={{ borderColor: "rgba(139, 92, 246, 0.3)", color: "#c084fc", background: "rgba(139, 92, 246, 0.1)" }}>
            Blockchain Ledger
          </span>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="tab-bar">
        <button
          className={`tab-btn ${activeTab === "inspection" ? "active" : ""}`}
          onClick={() => setActiveTab("inspection")}
        >
          📊 Live Inspection Console
        </button>
        <button
          className={`tab-btn ${activeTab === "enrollment" ? "active" : ""}`}
          onClick={() => setActiveTab("enrollment")}
        >
          👤 Executive Voiceprints & Enrollment
        </button>
        <button
          className={`tab-btn ${activeTab === "privacy" ? "active" : ""}`}
          onClick={() => setActiveTab("privacy")}
        >
          🛡️ Privacy & Compliance Vault
        </button>
      </div>

      {/* Service Health Grid */}
      <div className="panel" style={{ marginBottom: 20, padding: "10px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11, fontFamily: "var(--mono)" }}>
          <span style={{ color: "var(--text-muted)", fontWeight: 700 }}>MICROSERVICES INFRASTRUCTURE STATUS:</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px" }}>
            {Object.entries(serviceHealth).map(([name, ok]) => (
              <span key={name} style={{ color: ok ? "#10b981" : "#f43f5e" }}>
                {ok ? "●" : "✕"} {name}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Controls Bar */}
      <div className="panel" style={{ marginBottom: 20, padding: "14px 20px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button className={listening ? "btn-danger" : "btn-primary"} onClick={listening ? stopListening : startListening}>
              {listening ? "⏹️ Stop Call Simulation" : "🎙️ Start Live Call Simulation"}
            </button>

            <div style={{ position: "relative" }}>
              <button className="btn-secondary">
                📁 Upload Pre-Recorded Audio (.wav)
              </button>
              <input
                type="file"
                accept="audio/*"
                onChange={handleFileUpload}
                style={{ position: "absolute", left: 0, top: 0, opacity: 0, cursor: "pointer", height: "100%", width: "100%" }}
              />
            </div>

            {listening && (
              <span style={{ color: "#10b981", fontSize: 12, fontFamily: "var(--mono)", display: "flex", alignItems: "center", gap: 6 }}>
                <span className="pulse-dot" />
                Processing Window #{windowsSent}
              </span>
            )}
          </div>

          <div style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-dim)" }}>
            Session ID: <span style={{ color: "#38bdf8" }}>{sessionId ? sessionId.slice(0, 12) : "UNINITIALIZED"}</span>
          </div>
        </div>

        {/* Real-time Waveform Canvas */}
        <div style={{ marginTop: 12 }}>
          <WaveformVisualizer isListening={listening} riskScore={riskScore} />
        </div>
      </div>

      {/* TAB 1: Live Inspection Console */}
      {activeTab === "inspection" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="grid-2col">
            <div>
              <AnimatedRiskGauge riskScore={riskScore} trend={trend} enrollmentMatch={enrollmentMatch} />
              <div style={{ height: 16 }} />
              <ScoreBreakdownPlus scores={scores} />
            </div>

            <div>
              <AlertFeed alerts={alerts} />
              <div style={{ height: 16 }} />
              <LedgerStatus />
            </div>
          </div>

          {/* Risk Timeline Chart */}
          <RiskTimelineChart data={timelineData} />
        </div>
      )}

      {/* TAB 2: Executive Voiceprints & Enrollment */}
      {activeTab === "enrollment" && <SpeakerEnrollmentPanel />}

      {/* TAB 3: Privacy & Compliance Vault */}
      {activeTab === "privacy" && <PrivacyComplianceVault />}

      {/* Live Pipeline Terminal Log */}
      <div className="panel" style={{ marginTop: 20 }}>
        <div className="panel-header">
          <h2>Real-Time Pipeline Execution Log</h2>
          <span style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
            WEBSOCKET EVENTS STREAM
          </span>
        </div>
        <div
          style={{
            maxHeight: 160,
            overflowY: "auto",
            fontFamily: "var(--mono)",
            fontSize: 11,
            lineHeight: 1.6,
            background: "rgba(3, 7, 18, 0.6)",
            padding: 12,
            borderRadius: 8,
            border: "1px solid var(--panel-border)",
          }}
        >
          {statusLogs.length === 0 ? (
            <div style={{ color: "var(--text-muted)" }}>Click &quot;Start Live Call Simulation&quot; to begin pipeline streaming...</div>
          ) : (
            statusLogs.map((log, i) => (
              <div key={i} style={{ color: logColors[log.level] }}>
                <span style={{ color: "var(--text-muted)" }}>[{log.time}]</span> {log.message}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
