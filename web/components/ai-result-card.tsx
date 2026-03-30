"use client";

import type { WebAiActionResponse, AiUiPayload } from "@/lib/types";

type AiResultCardProps = {
  response: WebAiActionResponse;
};

function SimpleResult({ data }: { data: Extract<AiUiPayload, { kind: "simple_result" }>["data"] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {data.title && (
        <div style={{ fontSize: "0.8rem", fontWeight: 600 }}>{data.title}</div>
      )}
      {data.body && (
        <div style={{ fontSize: "0.78rem", color: "var(--foreground)", lineHeight: 1.6 }}>
          {data.body}
        </div>
      )}
      {data.metrics && Object.keys(data.metrics).length > 0 && (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 4 }}>
          {Object.entries(data.metrics).map(([key, value]) => (
            <div key={key} style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1.1rem", fontWeight: 600 }}>{value}</div>
              <div style={{ fontSize: "0.65rem", color: "var(--muted)", textTransform: "capitalize" }}>
                {key.replace(/_/g, " ")}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PayloadRenderer({ payload }: { payload: AiUiPayload }) {
  switch (payload.kind) {
    case "simple_result":
      return <SimpleResult data={payload.data} />;
    case "schedule_review":
    case "publish_preview":
    case "publish_diff":
    case "schedule_exceptions":
    case "manager_actions":
    case "coverage_summary":
      return (
        <div style={{ fontSize: "0.75rem", color: "var(--muted)", fontStyle: "italic" }}>
          {payload.kind.replace(/_/g, " ")} preview available
        </div>
      );
    default:
      return null;
  }
}

function riskPill(risk?: "green" | "yellow" | "red") {
  if (!risk) return null;
  const colors: Record<string, { bg: string; fg: string }> = {
    green: { bg: "#e6f4ea", fg: "#1a7a42" },
    yellow: { bg: "#fef7e0", fg: "#8a6d00" },
    red: { bg: "#fce8e6", fg: "#c5221f" },
  };
  const c = colors[risk] ?? colors.green;
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: "0.6rem",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.04em",
        padding: "2px 8px",
        borderRadius: 999,
        background: c.bg,
        color: c.fg,
      }}
    >
      {risk}
    </span>
  );
}

export default function AiResultCard({ response }: AiResultCardProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        padding: "14px 16px",
        background: "var(--panel)",
        borderRadius: "var(--radius)",
        border: "1px solid var(--line)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {riskPill(response.risk_class)}
        <span style={{ fontSize: "0.68rem", color: "var(--muted)", textTransform: "capitalize" }}>
          {response.status.replace(/_/g, " ")}
        </span>
      </div>
      <div style={{ fontSize: "0.8rem", lineHeight: 1.6 }}>{response.summary}</div>
      {response.ui_payload && <PayloadRenderer payload={response.ui_payload} />}
    </div>
  );
}
