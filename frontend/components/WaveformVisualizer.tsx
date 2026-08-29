"use client";

import { useEffect, useRef } from "react";

type Props = {
  isListening: boolean;
  riskScore: number;
};

export default function WaveformVisualizer({ isListening, riskScore }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationId: number;
    let phase = 0;

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const width = canvas.width;
      const height = canvas.height;
      const centerY = height / 2;

      // Color scheme based on risk score
      let strokeColor = "#06b6d4"; // Safe cyan
      let glowColor = "rgba(6, 182, 212, 0.4)";
      if (riskScore >= 65) {
        strokeColor = "#f43f5e"; // Rose
        glowColor = "rgba(244, 63, 94, 0.5)";
      } else if (riskScore >= 45) {
        strokeColor = "#f59e0b"; // Amber
        glowColor = "rgba(245, 158, 11, 0.4)";
      }

      ctx.save();
      ctx.shadowBlur = 12;
      ctx.shadowColor = glowColor;

      // Draw 3 wave layers
      for (let layer = 1; layer <= 3; layer++) {
        ctx.beginPath();
        ctx.lineWidth = layer === 1 ? 2.5 : 1;
        ctx.strokeStyle = layer === 1 ? strokeColor : `${strokeColor}55`;

        const freq = 0.02 * layer;
        const amp = isListening ? (14 / layer) * (1 + riskScore / 100) : 3;

        for (let x = 0; x < width; x += 2) {
          const y = centerY + Math.sin(x * freq + phase * layer) * Math.cos(x * 0.008) * amp;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      ctx.restore();

      if (isListening) {
        phase += 0.08;
      } else {
        phase += 0.02;
      }
      animationId = requestAnimationFrame(render);
    };

    render();

    return () => cancelAnimationFrame(animationId);
  }, [isListening, riskScore]);

  return (
    <div style={{ position: "relative", width: "100%", height: 60, overflow: "hidden" }}>
      <canvas
        ref={canvasRef}
        width={600}
        height={60}
        style={{ width: "100%", height: "100%", display: "block" }}
      />
      <div
        style={{
          position: "absolute",
          top: 6,
          right: 10,
          fontSize: 10,
          fontFamily: "var(--mono)",
          color: isListening ? strokeColor(riskScore) : "#64748b",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span className={`pulse-dot ${riskScore >= 65 ? "danger" : ""}`} />
        {isListening ? "LIVE WAVEFORM STREAM" : "IDLE"}
      </div>
    </div>
  );
}

function strokeColor(score: number) {
  if (score >= 65) return "#f43f5e";
  if (score >= 45) return "#f59e0b";
  return "#06b6d4";
}
