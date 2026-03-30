"use client";

import { useState, useRef } from "react";
import type {
  WebAiActionResponse,
  AiClarificationCandidate,
  AiWebActionRequest,
} from "@/lib/types";
import {
  submitAiAction,
  confirmAiAction,
  clarifyAiAction,
  cancelAiAction,
} from "@/lib/api/ai-actions";
import AiResultCard from "./ai-result-card";
import AiClarificationChooser from "./ai-clarification-chooser";
import AiConfirmationCard from "./ai-confirmation-card";
import AiActionHistoryFeed from "./ai-action-history-feed";

type AiPromptPanelProps = {
  locationId: number;
  scheduleId?: number;
  weekStartDate?: string;
  activeTab?: string;
};

type ConversationEntry = {
  role: "user" | "assistant";
  text: string;
  response?: WebAiActionResponse;
};

export default function AiPromptPanel({
  locationId,
  scheduleId,
  weekStartDate,
  activeTab,
}: AiPromptPanelProps) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversation, setConversation] = useState<ConversationEntry[]>([]);
  const [activeResponse, setActiveResponse] = useState<WebAiActionResponse | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  function addEntry(entry: ConversationEntry) {
    setConversation((prev) => [...prev, entry]);
  }

  function handleResponse(response: WebAiActionResponse) {
    setActiveResponse(response);
    addEntry({ role: "assistant", text: response.summary, response });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    addEntry({ role: "user", text });
    setInput("");
    setActiveResponse(null);
    setLoading(true);

    try {
      const request: AiWebActionRequest = {
        location_id: locationId,
        text,
        context: {
          tab: activeTab,
          schedule_id: scheduleId,
          week_start_date: weekStartDate,
        },
      };
      const response = await submitAiAction(request);
      handleResponse(response);
    } catch (err) {
      addEntry({
        role: "assistant",
        text: err instanceof Error ? err.message : "Something went wrong",
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm() {
    if (!activeResponse || loading) return;
    setLoading(true);
    try {
      const response = await confirmAiAction(activeResponse.action_request_id);
      handleResponse(response);
      setHistoryKey((k) => k + 1);
    } catch (err) {
      addEntry({
        role: "assistant",
        text: err instanceof Error ? err.message : "Confirmation failed",
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleClarify(candidate: AiClarificationCandidate) {
    if (!activeResponse || loading) return;
    setLoading(true);
    try {
      const response = await clarifyAiAction(activeResponse.action_request_id, {
        selection: {
          entity_type: candidate.entity_type,
          entity_id: candidate.entity_id ?? 0,
        },
      });
      handleResponse(response);
    } catch (err) {
      addEntry({
        role: "assistant",
        text: err instanceof Error ? err.message : "Clarification failed",
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel() {
    if (!activeResponse || loading) return;
    setLoading(true);
    try {
      const response = await cancelAiAction(activeResponse.action_request_id);
      setActiveResponse(null);
      addEntry({ role: "assistant", text: response.summary, response });
    } catch (err) {
      addEntry({
        role: "assistant",
        text: err instanceof Error ? err.message : "Cancellation failed",
      });
    } finally {
      setLoading(false);
    }
  }

  function handleRedirect() {
    if (!activeResponse?.redirect?.url) return;
    window.location.href = activeResponse.redirect.url;
  }

  return (
    <div className="settings-card">
      <div className="settings-card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Assistant</span>
        <button
          onClick={() => setShowHistory(!showHistory)}
          style={{
            fontSize: "0.65rem",
            color: "var(--muted)",
            background: "none",
            border: "none",
            cursor: "pointer",
            fontWeight: 500,
          }}
        >
          {showHistory ? "Prompt" : "History"}
        </button>
      </div>

      <div className="settings-card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {showHistory ? (
          <AiActionHistoryFeed key={historyKey} locationId={locationId} />
        ) : (
          <>
            {/* Conversation thread */}
            {conversation.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 320, overflowY: "auto" }}>
                {conversation.map((entry, i) => (
                  <div key={i} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <div
                      style={{
                        fontSize: "0.6rem",
                        fontWeight: 600,
                        textTransform: "uppercase",
                        letterSpacing: "0.04em",
                        color: entry.role === "user" ? "var(--foreground)" : "var(--muted)",
                      }}
                    >
                      {entry.role === "user" ? "You" : "Backfill"}
                    </div>
                    {entry.response ? (
                      <AiResultCard response={entry.response} />
                    ) : (
                      <div style={{ fontSize: "0.78rem", lineHeight: 1.5 }}>{entry.text}</div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Active interaction: clarification or confirmation */}
            {activeResponse?.mode === "clarification" && activeResponse.clarification && (
              <AiClarificationChooser
                clarification={activeResponse.clarification}
                onSelect={handleClarify}
                onCancel={handleCancel}
                loading={loading}
              />
            )}

            {activeResponse?.mode === "confirmation" && activeResponse.confirmation && (
              <AiConfirmationCard
                confirmation={activeResponse.confirmation}
                summary={activeResponse.summary}
                riskClass={activeResponse.risk_class}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
                loading={loading}
              />
            )}

            {activeResponse?.mode === "redirect" && activeResponse.redirect && (
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
                <div style={{ fontSize: "0.8rem", lineHeight: 1.5 }}>
                  {activeResponse.summary}
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
                  {activeResponse.redirect.reason}
                </div>
                <button className="button" onClick={handleRedirect}>
                  {activeResponse.redirect.label ?? "Open in dashboard"}
                </button>
              </div>
            )}

            {/* Input */}
            <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
              <input
                ref={inputRef}
                type="text"
                placeholder="Ask Backfill anything..."
                className="settings-select"
                style={{ flex: 1 }}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
              />
              <button
                type="submit"
                className="button"
                disabled={!input.trim() || loading}
                style={{ flexShrink: 0 }}
              >
                {loading ? "..." : "Send"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
