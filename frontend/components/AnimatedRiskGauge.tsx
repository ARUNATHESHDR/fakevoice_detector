"use client";

type Props = {
  riskScore: number; // 0-100
  trend?: {
    trend?: string;
    risk_velocity?: number;
    spike_detected?: boolean;
  };
  enrollmentMatch?: {
    matched?: boolean;
    best_match_name?: string;
    similarity?: number;
    verdict?: string;
  };
};

export default function AnimatedRiskGauge({ riskScore, trend, enrollmentMatch }: Props) {
  const rounded = Math.round(riskScore);
  let color = "#10b981"; // Safe Green
  let label = "GENUINE VOICE";
  let badgeBg = "rgba(16, 185, 129, 0.15)";
  let badgeBorder = "rgba(16, 185, 129, 0.3)";

  if (riskScore >= 65 || trend?.spike_detected) {
    color = "#f43f5e"; // Critical Rose
    label = "IMPERSONATION ATTACK";
    badgeBg = "rgba(244, 63, 94, 0.15)";
    badgeBorder = "rgba(244, 63, 94, 0.3)";
  } else if (riskScore >= 45) {
    color = "#f59e0b"; // Warning Amber
    label = "ELEVATED ANOMALY";
    badgeBg = "rgba(245, 158, 11, 0.15)";
    badgeBorder = "rgba(245, 158, 11, 0.3)";
  }

  // SVG Gauge calculations
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  // Semi-circle gauge (180 deg sweep)
  const strokeDashoffset = circumference - (rounded / 100) * (circumference / 2);

  return (
    <div className="panel" style={{ textAlign: "center", position: "relative" }}>
      <div className="panel-header" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h2>Live Risk Verdict</h2>
        <span
          style={{
            fontSize: 10,
            fontFamily: "var(--mono)",
            padding: "3px 8px",
            borderRadius: 12,
            background: badgeBg,
            color: color,
            border: `1px solid ${badgeBorder}`,
            fontWeight: 700,
          }}
        >
          {label}
        </span>
      </div>

      <div style={{ position: "relative", width: 180, height: 110, margin: "0 auto" }}>
        <svg width="180" height="110" viewBox="0 0 180 110">
          {/* Background arc */}
          <path
            d="M 20 95 A 70 70 0 0 1 160 95"
            fill="none"
            stroke="rgba(255, 255, 255, 0.08)"
            strokeWidth="12"
            strokeLinecap="round"
          />
          {/* Active gauge arc */}
          <path
            d="M 20 95 A 70 70 0 0 1 160 95"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={circumference / 2}
            strokeDashoffset={strokeDashoffset}
            style={{
              transition: "stroke-dashoffset 0.6s ease, stroke 0.4s ease",
              filter: `drop-shadow(0 0 8px ${color})`,
            }}
          />
        </svg>

        {/* Center Score Readout */}
        <div
          style={{
            position: "absolute",
            bottom: 4,
            left: 0,
            right: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
          }}
        >
          <span
            style={{
              fontSize: 42,
              fontFamily: "var(--mono)",
              fontWeight: 800,
              lineHeight: 1,
              color: color,
              textShadow: `0 0 16px ${color}44`,
            }}
          >
            {rounded}
          </span>
          <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--mono)", marginTop: 2 }}>
            RISK INDEX / 100
          </span>
        </div>
      </div>

      {/* Footer Indicators */}
      <div
        style={{
          marginTop: 14,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-around",
          fontSize: 11,
          fontFamily: "var(--mono)",
          borderTop: "1px solid var(--panel-border)",
          paddingTop: 10,
        }}
      >
        <div>
          <span style={{ color: "var(--text-muted)", display: "block" }}>VELOCITY</span>
          <span style={{ color: trend?.risk_velocity && trend.risk_velocity > 5 ? "#f43f5e" : "#94a3b8" }}>
            {trend?.risk_velocity ? `${trend.risk_velocity > 0 ? "+" : ""}${trend.risk_velocity.toFixed(1)}/w` : "0.0/w"}
          </span>
        </div>
        <div style={{ borderLeft: "1px solid var(--panel-border)", paddingLeft: 16 }}>
          <span style={{ color: "var(--text-muted)", display: "block" }}>VOICEPRINT</span>
          <span
            style={{
              color: enrollmentMatch?.matched
                ? "#10b981"
                : enrollmentMatch?.best_match_name
                ? "#f59e0b"
                : "#64748b",
            }}
          >
            {enrollmentMatch?.matched
              ? `✓ ${enrollmentMatch.best_match_name}`
              : enrollmentMatch?.best_match_name
              ? `UNVERIFIED`
              : "NO VOICEPRINT"}
          </span>
        </div>
      </div>
    </div>
  );
}
