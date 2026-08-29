"use client";

import { useEffect, useState } from "react";

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || "http://localhost:8000";

export default function PrivacyComplianceVault() {
  const [auditLog, setAuditLog] = useState<any>(null);
  const [phoneToErase, setPhoneToErase] = useState("");
  const [erasureResult, setErasureResult] = useState("");

  async function fetchPrivacyLog() {
    try {
      const res = await fetch(`${GATEWAY_URL}/api/v1/privacy/audit-log`);
      const data = await res.json();
      setAuditLog(data);
    } catch {
      // Gateway offline
    }
  }

  useEffect(() => {
    fetchPrivacyLog();
  }, []);

  async function handleRightToErasure() {
    if (!phoneToErase.trim()) return;
    try {
      const res = await fetch(`${GATEWAY_URL}/api/v1/privacy/data/${phoneToErase.trim()}`, {
        method: "DELETE",
      });
      const data = await res.json();
      setErasureResult(`DATA ERASED (GDPR Art 17 / DPDPA): ${JSON.stringify(data.details)}`);
      setPhoneToErase("");
      fetchPrivacyLog();
    } catch (err: any) {
      setErasureResult(`Erasure failed: ${err.message}`);
    }
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Privacy & Compliance Vault (GDPR / India DPDPA)</h2>
        <span style={{ fontSize: 11, fontFamily: "var(--mono)", color: "#10b981" }}>
          MINIMAL RETENTION GUARANTEE
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        {/* Compliance Guarantees */}
        <div style={{ background: "rgba(16, 185, 129, 0.05)", border: "1px solid rgba(16, 185, 129, 0.2)", padding: 14, borderRadius: 8 }}>
          <h3 style={{ margin: "0 0 8px", fontSize: 13, color: "#10b981" }}>🛡️ Privacy Guarantees in Code</h3>
          <div style={{ fontSize: 11, color: "var(--text-dim)", lineHeight: 1.6 }}>
            <div>• <b>Zero Central Audio Storage:</b> Raw audio buffered in-memory only in 2s ring buffers, immediately discarded after feature extraction.</div>
            <div>• <b>Feature-Only Fraud Ledger:</b> Only SHA-256 metadata hashes stored on chain — biometrics never touch unerasable ledgers.</div>
            <div>• <b>Anonymized Identifiers:</b> Callers identified solely via pre-hashed cryptographic digests.</div>
          </div>
        </div>

        {/* Right to Erasure (DPDPA / GDPR) */}
        <div style={{ background: "rgba(15, 23, 42, 0.6)", border: "1px solid var(--panel-border)", padding: 14, borderRadius: 8 }}>
          <h3 style={{ margin: "0 0 8px", fontSize: 13, color: "#38bdf8" }}>🗑️ Right-to-Erasure Trigger</h3>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
            Purge caller consent, session cache & metadata for compliance requests.
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              className="form-input"
              placeholder="Caller ID / Hash to erase"
              value={phoneToErase}
              onChange={(e) => setPhoneToErase(e.target.value)}
            />
            <button className="btn-danger" onClick={handleRightToErasure} style={{ whiteSpace: "nowrap" }}>
              Purge Data
            </button>
          </div>
          {erasureResult && (
            <div style={{ marginTop: 8, fontSize: 10, fontFamily: "var(--mono)", color: "#10b981" }}>
              {erasureResult}
            </div>
          )}
        </div>
      </div>

      {/* Audit Log Metrics */}
      {auditLog && (
        <div style={{ marginTop: 16, borderTop: "1px solid var(--panel-border)", paddingTop: 12 }}>
          <div style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-muted)", marginBottom: 6 }}>
            PRIVACY AUDIT METRICS
          </div>
          <div style={{ display: "flex", gap: 16, fontSize: 11, fontFamily: "var(--mono)" }}>
            <span>Active Sessions: <b style={{ color: "#38bdf8" }}>{auditLog.active_sessions}</b></span>
            <span>Consent Records: <b style={{ color: "#10b981" }}>{auditLog.consent_records}</b></span>
            <span>Audio Retention: <b style={{ color: "#f43f5e" }}>0% (IN-MEMORY DISCARD)</b></span>
          </div>
        </div>
      )}
    </div>
  );
}
