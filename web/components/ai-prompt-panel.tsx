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

const DEFAULT_PROMPTS = [
  "Show me open shifts this week",
  "What needs my attention right now?",
  "Can you publish this schedule?",
];

const SCHEDULE_PROMPTS = [
  "Open a dishwasher shift on Friday from 4pm to 10pm",
  "Show me what changed before publish",
  "Assign this week's open shifts if there are safe options",
];

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

  async function runPrompt(rawText: string) {
    const text = rawText.trim();
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await runPrompt(input);
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

  const promptSuggestions = activeTab === "schedule"
    ? [...DEFAULT_PROMPTS.slice(0, 2), ...SCHEDULE_PROMPTS]
    : DEFAULT_PROMPTS;

  return (
    <div className="settings-card">
      <div className="settings-card-header ai-panel-header">
        <span>Assistant</span>
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="ai-panel-toggle"
        >
          {showHistory ? "Prompt" : "History"}
        </button>
      </div>

      <div className="settings-card-body ai-panel-body">
        {showHistory ? (
          <AiActionHistoryFeed key={historyKey} locationId={locationId} />
        ) : (
          <>
            <div className="ai-panel-prompt-suggestions">
              {promptSuggestions.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="ai-panel-suggestion"
                  disabled={loading}
                  onClick={() => void runPrompt(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>

            {/* Conversation thread */}
            {conversation.length > 0 && (
              <div className="ai-thread">
                {conversation.map((entry, i) => (
                  <div key={i} className={`ai-thread-entry ai-thread-entry-${entry.role}`}>
                    <div className="ai-thread-speaker">
                      {entry.role === "user" ? "You" : "Backfill"}
                    </div>
                    {entry.response ? (
                      <AiResultCard response={entry.response} />
                    ) : (
                      <div className="ai-thread-text">{entry.text}</div>
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
              <div className="ai-redirect-card">
                <div className="ai-redirect-summary">
                  {activeResponse.summary}
                </div>
                <div className="ai-redirect-reason">
                  {activeResponse.redirect.reason}
                </div>
                <button className="button" onClick={handleRedirect}>
                  {activeResponse.redirect.label ?? "Open in dashboard"}
                </button>
              </div>
            )}

            {/* Input */}
            <form onSubmit={handleSubmit} className="ai-input-row">
              <input
                ref={inputRef}
                type="text"
                placeholder="Ask Backfill to publish, explain, create, assign, or fix"
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
