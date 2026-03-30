"use client";

import type { AiClarification, AiClarificationCandidate } from "@/lib/types";

type AiClarificationChooserProps = {
  clarification: AiClarification;
  onSelect: (candidate: AiClarificationCandidate) => void;
  onCancel: () => void;
  loading?: boolean;
};

export default function AiClarificationChooser({
  clarification,
  onSelect,
  onCancel,
  loading,
}: AiClarificationChooserProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: "14px 16px",
        background: "var(--panel)",
        borderRadius: "var(--radius)",
        border: "1px solid var(--line)",
      }}
    >
      <div style={{ fontSize: "0.8rem", fontWeight: 500, lineHeight: 1.5 }}>
        {clarification.prompt}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {clarification.candidates.map((candidate, i) => (
          <button
            key={candidate.entity_id ?? i}
            onClick={() => onSelect(candidate)}
            disabled={loading}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 14px",
              background: "var(--background)",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius)",
              cursor: loading ? "default" : "pointer",
              opacity: loading ? 0.6 : 1,
              textAlign: "left",
              fontSize: "0.78rem",
              transition: "border-color 0.15s",
            }}
          >
            <div>
              <div style={{ fontWeight: 500 }}>{candidate.label}</div>
              {candidate.description && (
                <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginTop: 2 }}>
                  {candidate.description}
                </div>
              )}
            </div>
            {candidate.confidence_score != null && (
              <span style={{ fontSize: "0.65rem", color: "var(--muted)", flexShrink: 0, marginLeft: 12 }}>
                {Math.round(candidate.confidence_score * 100)}%
              </span>
            )}
          </button>
        ))}
      </div>
      <button
        onClick={onCancel}
        disabled={loading}
        style={{
          fontSize: "0.72rem",
          color: "var(--muted)",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "4px 0",
          textAlign: "center",
        }}
      >
        Cancel
      </button>
    </div>
  );
}
