"use client";

import { useState, useEffect } from "react";
import type { AiActionHistoryItem, AiActionHistoryResponse } from "@/lib/types";
import { getAiActionHistory } from "@/lib/api/ai-actions";

type AiActionHistoryFeedProps = {
  locationId: number;
};

function statusColor(status: string): string {
  switch (status) {
    case "completed": return "#1a7a42";
    case "failed": return "#c5221f";
    case "cancelled": return "var(--muted)";
    case "redirected": return "#8a6d00";
    default: return "var(--foreground)";
  }
}

function channelLabel(channel: string): string {
  switch (channel) {
    case "web": return "Web";
    case "sms": return "SMS";
    case "voice": return "Voice";
    default: return channel;
  }
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export default function AiActionHistoryFeed({ locationId }: AiActionHistoryFeedProps) {
  const [items, setItems] = useState<AiActionHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      const result = await getAiActionHistory(locationId);
      if (!cancelled && result) {
        setItems(result.items);
      }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [locationId]);

  if (loading) {
    return (
      <div style={{ fontSize: "0.75rem", color: "var(--muted)", padding: "12px 0" }}>
        Loading history...
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div style={{ fontSize: "0.75rem", color: "var(--muted)", padding: "12px 0" }}>
        No AI actions yet. Try typing a request above.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {items.map((item) => (
        <div
          key={item.action_request_id}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 3,
            padding: "10px 0",
            borderBottom: "1px solid var(--line)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                style={{
                  fontSize: "0.6rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: statusColor(item.status),
                }}
              >
                {item.status}
              </span>
              <span style={{ fontSize: "0.6rem", color: "var(--muted)" }}>
                {channelLabel(item.channel)}
              </span>
            </div>
            <span style={{ fontSize: "0.65rem", color: "var(--muted)" }}>
              {formatTime(item.created_at)}
            </span>
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>{item.text}</div>
          <div style={{ fontSize: "0.75rem", lineHeight: 1.5 }}>{item.summary}</div>
        </div>
      ))}
    </div>
  );
}
