"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Loader2,
  Send,
  Sparkles,
  Waves,
} from "lucide-react";

import {
  createCopilotMessage,
  createCopilotSession,
} from "@/lib/api/copilot";
import type {
  CopilotActionRun,
  CopilotMessage as CopilotMessageRecord,
  CopilotSessionDetail,
  CopilotTurn,
} from "@/lib/types/copilot";
import DashboardActivityFeedPanel from "./DashboardActivityFeedPanel";
import DashboardCopilotToolResult from "./DashboardCopilotToolResult";
import SegmentedControl from "./SegmentedControl";

const copilotSuggestions = [
  "Show me open shifts this week",
  "What needs my attention right now?",
  "Show active coverage campaigns",
];

function sortCopilotMessages(messages: CopilotMessageRecord[]) {
  return [...messages].sort(
    (left, right) =>
      new Date(left.created_at).getTime() - new Date(right.created_at).getTime(),
  );
}

function mergeTurnIntoSession(
  current: CopilotSessionDetail | null,
  turn: CopilotTurn,
): CopilotSessionDetail {
  const messages = sortCopilotMessages([
    ...(current?.messages ?? []),
    turn.inbound_message,
    turn.outbound_message,
  ]);
  return {
    session: turn.session,
    tools: turn.tools,
    messages,
    action_runs: [...(current?.action_runs ?? []), turn.action_run],
  };
}

function messageToolName(
  message: CopilotMessageRecord,
): string | null {
  const value = message.message_metadata?.tool_name;
  return typeof value === "string" ? value : null;
}

function buildToolResultMap(
  messages: CopilotMessageRecord[],
  actionRuns: CopilotActionRun[],
): Map<string, CopilotActionRun> {
  const queues = new Map<string, CopilotActionRun[]>();
  for (const actionRun of [...actionRuns].sort(
    (left, right) =>
      new Date(left.started_at).getTime() - new Date(right.started_at).getTime(),
  )) {
    if (actionRun.status !== "executed") {
      continue;
    }
    const queue = queues.get(actionRun.tool_name) ?? [];
    queue.push(actionRun);
    queues.set(actionRun.tool_name, queue);
  }

  const result = new Map<string, CopilotActionRun>();
  for (const message of sortCopilotMessages(messages)) {
    if (message.direction !== "outbound") {
      continue;
    }
    if (message.message_metadata?.message_kind !== "tool_result") {
      continue;
    }
    const toolName = messageToolName(message);
    if (!toolName) {
      continue;
    }
    const queue = queues.get(toolName);
    if (!queue || queue.length === 0) {
      continue;
    }
    const matched = queue.shift();
    if (matched) {
      result.set(message.id, matched);
    }
  }
  return result;
}

function messageSurfaceClass({
  dark,
  direction,
}: {
  dark: boolean;
  direction: CopilotMessageRecord["direction"];
}) {
  if (direction === "inbound") {
    return "bg-[#635BFF] text-white rounded-br-md";
  }
  return dark
    ? "bg-white/[0.06] text-[#C1CED8] rounded-bl-md"
    : "bg-[#F0F0F5] text-[#3E4C59] rounded-bl-md";
}

function typingBubbleClass(dark: boolean) {
  return dark
    ? "bg-white/[0.06] backfill-ui-radius rounded-bl-md px-4 py-3 flex items-center gap-1.5"
    : "bg-[#F0F0F5] rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1.5";
}

function suggestionButtonClass(dark: boolean) {
  return dark
    ? "w-full text-left px-3 py-2 backfill-ui-radius bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] transition-colors text-[11px] text-[#C1CED8]"
    : "w-full text-left px-3 py-2 rounded-lg bg-[#F7F8FA] border border-[#E5E7EB] hover:bg-[#F0F0F5] transition-colors text-[11px] text-[#5E6D7A]";
}

function inputWrapClass(dark: boolean) {
  return dark
    ? "flex items-center gap-2 bg-white/[0.04] border border-white/[0.06] backfill-ui-radius px-3 py-2 focus-within:border-[#635BFF]/40 transition-colors"
    : "flex items-center gap-2 bg-[#F7F8FA] border border-[#E5E7EB] rounded-xl px-3 py-2 focus-within:border-[#635BFF]/40 focus-within:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all";
}

function inputClass(dark: boolean) {
  return dark
    ? "flex-1 bg-transparent text-[12px] text-white placeholder-[#8898AA]/50 focus:outline-none"
    : "flex-1 bg-transparent text-[12px] text-[#0A2540] placeholder-[#8898AA]/60 focus:outline-none";
}

function sendButtonClass(dark: boolean) {
  return dark
    ? "p-1.5 backfill-ui-radius hover:bg-white/[0.06] transition-colors disabled:opacity-30"
    : "p-1.5 rounded-lg hover:bg-[#E5E7EB] transition-colors disabled:opacity-30";
}

export default function DashboardCopilotSidebar({
  dark,
  businessId,
  locationId,
  locationName,
}: {
  dark: boolean;
  businessId?: string | null;
  locationId?: string | null;
  locationName?: string | null;
}) {
  const [panelTab, setPanelTab] = useState<"chat" | "feed">("chat");
  const [sessionDetail, setSessionDetail] = useState<CopilotSessionDetail | null>(
    null,
  );
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sessionDetailRef = useRef<CopilotSessionDetail | null>(null);
  const sessionContextKeyRef = useRef("");
  const sessionRequestRef = useRef<Promise<CopilotSessionDetail | null> | null>(
    null,
  );

  const activeSessionId = sessionDetail?.session.id ?? null;
  const messages = sessionDetail?.messages ?? [];
  const actionRuns = sessionDetail?.action_runs ?? [];
  const sessionContextKey = `${businessId ?? "none"}:${locationId ?? "none"}`;
  const toolResultsByMessageId = useMemo(
    () => buildToolResultMap(messages, actionRuns),
    [actionRuns, messages],
  );
  const footerBorderClass = dark ? "border-white/[0.06]" : "border-[#F0F0F5]";

  useEffect(() => {
    sessionDetailRef.current = sessionDetail;
  }, [sessionDetail]);

  useEffect(() => {
    sessionContextKeyRef.current = sessionContextKey;
  }, [sessionContextKey]);

  useEffect(() => {
    if (panelTab !== "chat") {
      return;
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping, panelTab]);

  useEffect(() => {
    sessionRequestRef.current = null;
    if (!businessId) {
      setSessionDetail(null);
      setError("Copilot needs a business context before it can answer.");
    } else {
      setSessionDetail(null);
      setError(null);
    }
    setInput("");
    setIsTyping(false);
    setIsLoadingSession(false);
  }, [businessId, locationId]);

  const ensureSession = useCallback(async (): Promise<CopilotSessionDetail | null> => {
    if (!businessId) {
      setError("Copilot needs a business context before it can answer.");
      return null;
    }
    if (sessionDetailRef.current) {
      return sessionDetailRef.current;
    }
    if (sessionRequestRef.current) {
      return sessionRequestRef.current;
    }
    setIsLoadingSession(true);
    setError(null);

    const requestContextKey = sessionContextKey;
    let request: Promise<CopilotSessionDetail | null>;
    request = createCopilotSession(businessId, {
      location_id: locationId ?? null,
      normalized_channel: "dashboard",
      reuse_active: true,
    })
      .then((detail) => {
        const normalizedDetail = {
          ...detail,
          messages: sortCopilotMessages(detail.messages),
        };
        if (requestContextKey === sessionContextKeyRef.current) {
          sessionDetailRef.current = normalizedDetail;
          setSessionDetail(normalizedDetail);
        }
        return normalizedDetail;
      })
      .catch((nextError) => {
        if (requestContextKey === sessionContextKeyRef.current) {
          setError(
            nextError instanceof Error
              ? nextError.message
              : "Failed to start Copilot.",
          );
        }
        return null;
      })
      .finally(() => {
        if (sessionRequestRef.current === request) {
          sessionRequestRef.current = null;
        }
        if (requestContextKey === sessionContextKeyRef.current) {
          setIsLoadingSession(false);
        }
      });

    sessionRequestRef.current = request;
    return request;
  }, [businessId, locationId, sessionContextKey]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !businessId) {
        return;
      }
      setInput("");
      setIsTyping(true);
      setError(null);
      try {
        const detail = activeSessionId
          ? sessionDetailRef.current
          : await ensureSession();
        const sessionId =
          detail?.session.id ?? sessionDetailRef.current?.session.id ?? activeSessionId;
        if (!sessionId) {
          setInput(trimmed);
          return;
        }
        const turn = await createCopilotMessage(businessId, sessionId, {
          text: trimmed,
          location_id: locationId ?? null,
          normalized_channel: "dashboard",
        });
        setSessionDetail((current) => mergeTurnIntoSession(current, turn));
      } catch (nextError) {
        setInput(trimmed);
        setError(
          nextError instanceof Error
            ? nextError.message
            : "Failed to send Copilot message.",
        );
      } finally {
        setIsTyping(false);
      }
    },
    [activeSessionId, businessId, ensureSession, locationId],
  );

  return (
    <div className="flex h-full flex-col">
      <div
        className={`border-b px-3 pb-2 pt-3 ${
          dark ? "border-white/[0.06]" : "border-[#F0F0F5]"
        }`}
      >
        <SegmentedControl
          activeItemClassName={
            dark
              ? "backfill-ui-radius bg-white/[0.08] text-white shadow-[0_1px_3px_rgba(0,0,0,0.25)]"
              : "bg-white text-[#0A2540] shadow-[0_1px_3px_rgba(0,0,0,0.08)]"
          }
          className={dark ? "flex w-full bg-white/[0.04]" : "flex w-full bg-[#F0F0F5]"}
          iconSize={13}
          inactiveItemClassName={
            dark
              ? "text-[#8898AA] hover:text-[#C1CED8]"
              : "text-[#8898AA] hover:text-[#5E6D7A]"
          }
          itemClassName="flex-1 py-2 text-[12px]"
          items={[
            { value: "chat", label: "Chat", icon: Sparkles },
            { value: "feed", label: "Feed", icon: Waves },
          ]}
          onChange={(value) => setPanelTab(value as "chat" | "feed")}
          value={panelTab}
        />
      </div>

      <AnimatePresence mode="wait">
        {panelTab === "chat" ? (
          <motion.div
            key="chat"
            animate={{ opacity: 1, x: 0 }}
            className="flex h-full flex-col"
            initial={{ opacity: 0, x: -8 }}
            transition={{ duration: 0.18 }}
          >
            <div className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
              {error ? (
                <div
                  className={`rounded-xl border px-3 py-2 text-[11px] ${
                    dark
                      ? "border-[#E5484D]/30 bg-[#E5484D]/10 text-[#F8B4B4]"
                      : "border-[#E5484D]/20 bg-[#FFF2F2] text-[#A33A3A]"
                  }`}
                  style={{ fontWeight: 500 }}
                >
                  {error}
                </div>
              ) : null}

              {isLoadingSession && messages.length === 0 ? (
                <div
                  className={`flex items-center gap-2 rounded-2xl px-3.5 py-3 text-[12px] ${
                    dark
                      ? "bg-white/[0.05] text-[#C1CED8]"
                      : "bg-[#F0F0F5] text-[#5E6D7A]"
                  }`}
                  style={{ fontWeight: 420 }}
                >
                  <Loader2 size={14} className="animate-spin" />
                  Loading Copilot…
                </div>
              ) : null}

              {!error && !isLoadingSession && !sessionDetail ? (
                <div
                  className={`rounded-2xl border px-4 py-4 ${
                    dark
                      ? "border-white/[0.06] bg-white/[0.03]"
                      : "border-[#E5E7EB] bg-white"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6]">
                      <Sparkles size={14} className="text-white" />
                    </div>
                    <div className="min-w-0">
                      <p
                        className={`text-[13px] ${
                          dark ? "text-white" : "text-[#0A2540]"
                        }`}
                        style={{ fontWeight: 560 }}
                      >
                        Copilot is ready when you are
                      </p>
                      <p
                        className={`mt-1 text-[12px] ${
                          dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"
                        }`}
                        style={{ fontWeight: 420 }}
                      >
                        Start a session only when you want to ask about open shifts,
                        active campaigns, or manager actions.
                      </p>
                      <button
                        className="mt-3 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] px-3.5 py-2 text-[12px] text-white transition-all hover:shadow-[0_0_20px_rgba(99,91,255,0.22)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:shadow-none"
                        disabled={isLoadingSession}
                        onClick={() => {
                          void ensureSession();
                        }}
                        style={{ fontWeight: 540 }}
                        type="button"
                      >
                        Start Copilot
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}

              {messages.map((message) => {
                const toolResult = toolResultsByMessageId.get(message.id);
                return (
                  <motion.div
                    key={message.id}
                    animate={{ opacity: 1, y: 0 }}
                    className={`flex ${
                      message.direction === "inbound"
                        ? "justify-end"
                        : "justify-start"
                    }`}
                    initial={{ opacity: 0, y: 6 }}
                    transition={{ duration: 0.25 }}
                  >
                    {message.direction === "outbound" ? (
                      <div className="mr-2 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6]">
                        <Sparkles size={11} className="text-white" />
                      </div>
                    ) : null}
                    <div className="max-w-[85%]">
                      <div
                        className={`rounded-2xl px-3.5 py-2.5 text-[12px] leading-relaxed ${messageSurfaceClass(
                          {
                            dark,
                            direction: message.direction,
                          },
                        )}`}
                        style={{ fontWeight: 420, whiteSpace: "pre-line" }}
                      >
                        {message.raw_text}
                      </div>
                      {toolResult ? (
                        <DashboardCopilotToolResult
                          actionRun={toolResult}
                          dark={dark}
                        />
                      ) : null}
                    </div>
                  </motion.div>
                );
              })}

              {isTyping ? (
                <div className="flex items-center gap-2">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6]">
                    <Sparkles size={11} className="text-white" />
                  </div>
                  <div className={typingBubbleClass(dark)}>
                    <div
                      className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#8898AA]"
                      style={{ animationDelay: "0ms" }}
                    />
                    <div
                      className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#8898AA]"
                      style={{ animationDelay: "150ms" }}
                    />
                    <div
                      className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#8898AA]"
                      style={{ animationDelay: "300ms" }}
                    />
                  </div>
                </div>
              ) : null}
              <div ref={bottomRef} />
            </div>

            {messages.length <= 2 ? (
              <div className="space-y-1.5 px-3 pb-2">
                {copilotSuggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    className={suggestionButtonClass(dark)}
                    disabled={!businessId || isLoadingSession || isTyping}
                    onClick={() => {
                      void sendMessage(suggestion);
                    }}
                    style={{ fontWeight: 440 }}
                    type="button"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            ) : null}

            <div className={`border-t p-3 ${footerBorderClass}`}>
              <div className={inputWrapClass(dark)}>
                <input
                  className={inputClass(dark)}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      void sendMessage(input);
                    }
                  }}
                  placeholder={
                    locationName
                      ? `Ask Copilot about ${locationName}...`
                      : "Ask Copilot..."
                  }
                  style={{ fontWeight: 420 }}
                  type="text"
                  value={input}
                />
                <button
                  className={sendButtonClass(dark)}
                  disabled={
                    !input.trim() || !businessId || isLoadingSession || isTyping
                  }
                  onClick={() => {
                    void sendMessage(input);
                  }}
                  type="button"
                >
                  <Send size={14} className="text-[#635BFF]" />
                </button>
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="feed"
            animate={{ opacity: 1, x: 0 }}
            className="flex h-full flex-col overflow-hidden"
            initial={{ opacity: 0, x: 8 }}
            transition={{ duration: 0.18 }}
          >
            <DashboardActivityFeedPanel
              businessId={businessId}
              dark={dark}
              locationId={locationId}
              locationName={locationName}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
