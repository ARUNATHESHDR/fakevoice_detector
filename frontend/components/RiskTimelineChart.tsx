"use client";

import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine } from "recharts";

type TimelineData = {
  window: number;
  risk: number;
  spectral: number;
  prosody: number;
  consistency: number;
};

type Props = {
  data: TimelineData[];
};

export default function RiskTimelineChart({ data }: Props) {
  if (!data || data.length === 0) {
    return (
      <div className="panel" style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "var(--text-muted)", fontSize: 13, fontStyle: "italic" }}>
          Risk score timeline will plot live as audio windows arrive...
        </div>
      </div>
    );
  }

  // Format data for chart
  const chartData = data.map((d) => ({
    time: `W${d.window}`,
    risk: d.risk,
    spectral: Math.round(d.spectral * 100),
    prosody: Math.round(d.prosody * 100),
    consistency: Math.round(d.consistency * 100),
  }));

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Live Risk Evolution Timeline</h2>
        <span style={{ fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
          {chartData.length} WINDOWS ANALYZED
        </span>
      </div>

      <div style={{ width: "100%", height: 160 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} />
            <YAxis domain={[0, 100]} stroke="#64748b" fontSize={10} tickLine={false} />
            <Tooltip
              contentStyle={{
                background: "#0f172a",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                borderRadius: 8,
                fontSize: 12,
                fontFamily: "var(--mono)",
              }}
            />
            <ReferenceLine y={65} stroke="#f43f5e" strokeDasharray="3 3" label={{ value: "ALERT (65)", fill: "#f43f5e", fontSize: 10 }} />
            <Line type="monotone" dataKey="risk" stroke="#f43f5e" strokeWidth={2.5} dot={{ r: 3, fill: "#f43f5e" }} activeDot={{ r: 6 }} />
            <Line type="monotone" dataKey="spectral" stroke="#06b6d4" strokeWidth={1} dot={false} opacity={0.6} />
            <Line type="monotone" dataKey="prosody" stroke="#8b5cf6" strokeWidth={1} dot={false} opacity={0.6} />
            <Line type="monotone" dataKey="consistency" stroke="#f59e0b" strokeWidth={1} dot={false} opacity={0.6} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
