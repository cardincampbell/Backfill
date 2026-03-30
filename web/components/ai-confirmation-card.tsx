"use client";

import type { AiConfirmation } from "@/lib/types";

type AiConfirmationCardProps = {
  confirmation: AiConfirmation;
  summary: string;
  riskClass?: "green" | "yellow" | "red";
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
};

const REASON_LABELS: Record<string, string> = {
  destructive_change: "This change removes or reassigns work",
  multi_step_action: "Multiple steps will execute",
  channel_policy: "Channel policy requires confirmation",
  publish_blast_radius: "Published changes will notify workers",
  coverage_side_effect: "Coverage will be started",
};

export default function AiConfirmationCard({
  confirmation,
  summary,
  riskClass,
  onConfirm,
  onCancel,
  loading,
}: AiConfirmationCardProps) {
  const borderColor = riskClass === "red"
    ? "#c5221f"
    : riskClass === "yellow"
      ? "#e8a600"
      : "var(--line)";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 14,
        padding: "14px 16px",
        background: "var(--panel)",
        borderRadius: "var(--radius)",
        border: `1px solid ${borderColor}`,
      }}
    >
      <div style={{ fontSize: "0.8rem", fontWeight: 500, lineHeight: 1.5 }}>
        {confirmation.prompt}
      </div>

      {summary && (
        <div style={{ fontSize: "0.75rem", color: "var(--muted)", lineHeight: 1.5 }}>
          {summary}
        </div>
      )}

      {confirmation.affected_entities.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Affected
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {confirmation.affected_entities.map((entity, i) => (
              <span
                key={i}
                style={{
                  fontSize: "0.7rem",
                  padding: "3px 10px",
                  borderRadius: 999,
                  background: "var(--background)",
                  border: "1px solid var(--line)",
                }}
              >
                {entity.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {confirmation.reason_codes && confirmation.reason_codes.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          {confirmation.reason_codes.map((code) => (
            <div key={code} style={{ fontSize: "0.7rem", color: "var(--muted)" }}>
              {REASON_LABELS[code] ?? code.replace(/_/g, " ")}
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        <button
          className="button"
          onClick={onConfirm}
          disabled={loading}
          style={{ flex: 1 }}
        >
          {loading ? "Executing..." : "Confirm"}
        </button>
        <button
          onClick={onCancel}
          disabled={loading}
          style={{
            flex: 1,
            padding: "8px 16px",
            fontSize: "0.72rem",
            fontWeight: 500,
            borderRadius: "var(--radius)",
            border: "1px solid var(--line)",
            background: "var(--panel)",
            cursor: "pointer",
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
