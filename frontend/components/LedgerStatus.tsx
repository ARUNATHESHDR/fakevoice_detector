"use client";

import { useEffect, useState } from "react";

const LEDGER_URL = process.env.NEXT_PUBLIC_LEDGER_URL || "http://localhost:8007";
const NODES = ["bank_a", "bank_b", "telecom_x"];

type NodeStatus = {
  chainLength: number;
  verified: boolean | null; // null = not yet checked
  tamperedAt: number | null;
};

export default function LedgerStatus() {
  const [nodeStatus, setNodeStatus] = useState<Record<string, NodeStatus>>({});
  const [verifying, setVerifying] = useState(false);
  const [lastChecked, setLastChecked] = useState<string | null>(null);

  async function refreshChainLengths() {
    try {
      const res = await fetch(`${LEDGER_URL}/ledger/nodes`);
      const data = await res.json();
      setNodeStatus((prev) => {
        const next = { ...prev };
        for (const node of NODES) {
          next[node] = {
            chainLength: data.chain_lengths?.[node] ?? 0,
            verified: prev[node]?.verified ?? null,
            tamperedAt: prev[node]?.tamperedAt ?? null,
          };
        }
        return next;
      });
    } catch {
      // ledger service not reachable yet
    }
  }

  async function verifyAllNodes() {
    setVerifying(true);
    for (const node of NODES) {
      try {
        const res = await fetch(`${LEDGER_URL}/ledger/verify/${node}`);
        const data = await res.json();
        setNodeStatus((prev) => ({
          ...prev,
          [node]: {
            chainLength: prev[node]?.chainLength ?? 0,
            verified: data.valid,
            tamperedAt: data.first_tampered_block,
          },
        }));
      } catch {
        // skip unreachable node
      }
    }
    setLastChecked(new Date().toLocaleTimeString());
    setVerifying(false);
  }

  useEffect(() => {
    refreshChainLengths();
    const interval = setInterval(refreshChainLengths, 8000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Fraud Intelligence Ledger (Blockchain)</h2>
        <span style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--accent-purple)", background: "rgba(139, 92, 246, 0.15)", padding: "2px 6px", borderRadius: 4 }}>
          PERMISSIONED HASH-CHAIN
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
        {NODES.map((node) => {
          const status = nodeStatus[node];
          const isVerified = status?.verified === true;
          const isTampered = status?.verified === false;

          const verifiedColor = isVerified ? "#10b981" : isTampered ? "#f43f5e" : "#94a3b8";
          const verifiedLabel = isVerified
            ? "INTACT ✓"
            : isTampered
            ? `TAMPERED @ BLK ${status.tamperedAt} ✕`
            : "UNCHECKED";

          return (
            <div
              key={node}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                background: "rgba(15, 23, 42, 0.6)",
                padding: "8px 12px",
                borderRadius: 8,
                border: "1px solid var(--panel-border)",
                fontSize: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 14 }}>
                  {node.includes("bank") ? "🏦" : "📡"}
                </span>
                <div>
                  <div style={{ fontWeight: 600, color: "#fff", textTransform: "capitalize" }}>
                    {node.replace("_", " ")} Node
                  </div>
                  <div style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
                    {status ? `${status.chainLength} SHA-256 blocks chained` : "Connecting to consortium..."}
                  </div>
                </div>
              </div>

              <span
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  color: verifiedColor,
                  fontWeight: 700,
                  background: `${verifiedColor}15`,
                  padding: "4px 8px",
                  borderRadius: 6,
                  border: `1px solid ${verifiedColor}33`,
                }}
              >
                {verifiedLabel}
              </span>
            </div>
          );
        })}
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <button className="btn-secondary" onClick={verifyAllNodes} disabled={verifying} style={{ fontSize: 12, padding: "6px 12px" }}>
          {verifying ? "Recomputing SHA-256 Hashes..." : "🔐 Verify Hash-Chain Integrity"}
        </button>
        {lastChecked && (
          <span style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
            verified {lastChecked}
          </span>
        )}
      </div>
    </div>
  );
}
