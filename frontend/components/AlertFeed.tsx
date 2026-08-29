"use client";

type Alert = {
  risk_score: number;
  rationale: string;
  recommended_action: string;
};

export default function AlertFeed({ alerts }: { alerts: Alert[] }) {
  return (
    <div className="panel">
      <h2>Alerts</h2>
      {alerts.length === 0 && <div className="empty-state">No alerts this session.</div>}
      {alerts.map((a, i) => (
        <div className="alert-item" key={i}>
          <div>{a.rationale}</div>
          <span className="action">{a.recommended_action.replace(/_/g, " ")}</span>
        </div>
      ))}
    </div>
  );
}
