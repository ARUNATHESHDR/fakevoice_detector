"use client";

type AlertItem = {
  risk_score: number;
  rationale: string;
  recommended_action: string;
  severity?: {
    level: string;
    description: string;
    auto_block: boolean;
  };
  verification_required?: string[];
  block_transaction?: boolean;
};

type Props = {
  alertData: AlertItem | null;
  onDismiss: () => void;
};

export default function AlertModal({ alertData, onDismiss }: Props) {
  if (!alertData || (!alertData.block_transaction && alertData.risk_score < 65)) return null;

  const severityLevel = alertData.severity?.level || "CRITICAL";

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              background: "rgba(244, 63, 94, 0.2)",
              color: "#f43f5e",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 22,
              border: "1px solid rgba(244, 63, 94, 0.4)",
            }}
          >
            🚨
          </div>
          <div>
            <div style={{ fontSize: 11, fontFamily: "var(--mono)", color: "#f43f5e", fontWeight: 700 }}>
              {severityLevel} VOICE IMPERSONATION THREAT
            </div>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Pre-Transaction Action Blocked</h3>
          </div>
        </div>

        <div
          style={{
            background: "rgba(244, 63, 94, 0.08)",
            borderLeft: "4px solid #f43f5e",
            padding: 14,
            borderRadius: "0 8px 8px 0",
            fontSize: 13,
            lineHeight: 1.5,
            marginBottom: 20,
          }}
        >
          <b>AI Verdict:</b> {alertData.rationale}
        </div>

        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-muted)", marginBottom: 8 }}>
            RECOMMENDED PROTOCOL
          </div>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: "#38bdf8",
              background: "rgba(56, 189, 248, 0.1)",
              padding: "8px 12px",
              borderRadius: 6,
              border: "1px solid rgba(56, 189, 248, 0.2)",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <span>🛡️</span> {alertData.recommended_action.replace(/_/g, " ").toUpperCase()}
          </div>
        </div>

        {/* Verification Options */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
          <button
            onClick={() => {
              window.alert("Initiating Out-of-Band Callback on Registered Mobile Number...");
              onDismiss();
            }}
            className="btn-primary"
            style={{ width: "100%", justifyContent: "center" }}
          >
            📞 Initiate Out-of-Band Callback Verification
          </button>
          <button
            onClick={() => {
              window.alert("Escalating Session & Recording to Fraud Supervisor Team...");
              onDismiss();
            }}
            className="btn-secondary"
            style={{ width: "100%", justifyContent: "center" }}
          >
            👨‍💼 Escalate Session to Fraud Supervisor
          </button>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={onDismiss}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              fontSize: 12,
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            Acknowledge & Close Warning
          </button>
        </div>
      </div>
    </div>
  );
}
