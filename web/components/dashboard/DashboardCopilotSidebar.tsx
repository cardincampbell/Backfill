"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { motion } from "motion/react";
import {
  Loader2,
  Send,
  Sparkles,
  Square,
} from "lucide-react";

import {
  cancelCopilotSocketTurn,
  connectCopilotSessionSocket,
  createCopilotMessage,
  createCopilotSession,
  sendCopilotSocketMessage,
} from "@/lib/api/copilot";
import type {
  CopilotActionRun,
  CopilotLiveEvent,
  CopilotMessage as CopilotMessageRecord,
  CopilotSessionDetail,
  CopilotTurn,
} from "@/lib/types/copilot";
import DashboardCopilotToolResult from "./DashboardCopilotToolResult";

const copilotSuggestions = [
  "Show me open shifts this week",
  "What needs my attention right now?",
  "Show active coverage campaigns",
  "Update my availability to weekdays from 9 AM to 5 PM",
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
  const messagesById = new Map<string, CopilotMessageRecord>();
  for (const message of current?.messages ?? []) {
    messagesById.set(message.id, message);
  }
  messagesById.set(turn.inbound_message.id, turn.inbound_message);
  messagesById.set(turn.outbound_message.id, turn.outbound_message);

  const actionRunsById = new Map<string, CopilotActionRun>();
  for (const actionRun of current?.action_runs ?? []) {
    actionRunsById.set(actionRun.id, actionRun);
  }
  actionRunsById.set(turn.action_run.id, turn.action_run);

  return {
    session: turn.session,
    tools: turn.tools,
    messages: sortCopilotMessages([...messagesById.values()]),
    action_runs: [...actionRunsById.values()],
  };
}

function mergeAcceptedMessageIntoSession(
  current: CopilotSessionDetail | null,
  message: CopilotMessageRecord,
  session: CopilotSessionDetail["session"],
): CopilotSessionDetail | null {
  if (!current) {
    return current;
  }
  const messagesById = new Map<string, CopilotMessageRecord>();
  for (const currentMessage of current.messages) {
    messagesById.set(currentMessage.id, currentMessage);
  }
  messagesById.set(message.id, message);
  return {
    ...current,
    session,
    messages: sortCopilotMessages([...messagesById.values()]),
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
    ? "flex-1 bg-transparent text-[16px] text-white placeholder-[#8898AA]/50 focus:outline-none sm:text-[12px]"
    : "flex-1 bg-transparent text-[16px] text-[#0A2540] placeholder-[#8898AA]/60 focus:outline-none sm:text-[12px]";
}

function sendButtonClass(dark: boolean) {
  return dark
    ? "p-1.5 backfill-ui-radius hover:bg-white/[0.06] transition-colors disabled:opacity-30"
    : "p-1.5 rounded-lg hover:bg-[#E5E7EB] transition-colors disabled:opacity-30";
}

type LiveStatus = {
  traceId: string | null;
  state: "thinking" | "planning" | "running_tool" | "completed" | "failed";
  label: string;
};

export default function DashboardCopilotSidebar({
  autoStartSignal = 0,
  dark,
  businessId,
  locationId,
  locationHref: _locationHref,
  locationName,
}: {
  autoStartSignal?: number;
  dark: boolean;
  businessId?: string | null;
  locationId?: string | null;
  locationHref?: string | null;
  locationName?: string | null;
}) {
  const [sessionDetail, setSessionDetail] = useState<CopilotSessionDetail | null>(
    null,
  );
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liveStatus, setLiveStatus] = useState<LiveStatus | null>(null);
  const [socketState, setSocketState] = useState<
    "idle" | "connecting" | "connected" | "failed"
  >("idle");
  const bottomRef = useRef<HTMLDivElement>(null);
  const sessionDetailRef = useRef<CopilotSessionDetail | null>(null);
  const sessionContextKeyRef = useRef("");
  const sessionRequestRef = useRef<Promise<CopilotSessionDetail | null> | null>(
    null,
  );
  const socketRef = useRef<WebSocket | null>(null);
  const activeTraceIdRef = useRef<string | null>(null);
  const clearLiveStatusTimeoutRef = useRef<number | null>(null);

  const activeSessionId = sessionDetail?.session.id ?? null;
  const messages = sessionDetail?.messages ?? [];
  const actionRuns = sessionDetail?.action_runs ?? [];
  const sessionContextKey = `${businessId ?? "none"}:${locationId ?? "none"}`;
  const toolResultsByMessageId = useMemo(
    () => buildToolResultMap(messages, actionRuns),
    [actionRuns, messages],
  );
  const footerBorderClass = dark ? "border-white/[0.06]" : "border-[#F0F0F5]";
  const isRealtimeReady =
    socketState === "connected" &&
    socketRef.current?.readyState === 1;
  const canCancelLiveTurn = Boolean(
    liveStatus && activeTraceIdRef.current && isRealtimeReady,
  );

  useEffect(() => {
    sessionDetailRef.current = sessionDetail;
  }, [sessionDetail]);

  useEffect(() => {
    sessionContextKeyRef.current = sessionContextKey;
  }, [sessionContextKey]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [liveStatus, messages]);

  useEffect(() => {
    sessionRequestRef.current = null;
    socketRef.current?.close();
    socketRef.current = null;
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
    setLiveStatus(null);
    setSocketState("idle");
    activeTraceIdRef.current = null;
    if (clearLiveStatusTimeoutRef.current) {
      window.clearTimeout(clearLiveStatusTimeoutRef.current);
      clearLiveStatusTimeoutRef.current = null;
    }
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

  useEffect(() => {
    if (!autoStartSignal || !businessId) {
      return;
    }
    if (sessionDetailRef.current || sessionRequestRef.current) {
      return;
    }
    void ensureSession();
  }, [autoStartSignal, businessId, ensureSession]);

  const scheduleLiveStatusClear = useCallback(() => {
    if (clearLiveStatusTimeoutRef.current) {
      window.clearTimeout(clearLiveStatusTimeoutRef.current);
    }
    clearLiveStatusTimeoutRef.current = window.setTimeout(() => {
      setLiveStatus(null);
      clearLiveStatusTimeoutRef.current = null;
    }, 1200);
  }, []);

  const handleSocketEvent = useCallback(
    (event: CopilotLiveEvent) => {
      switch (event.event_type) {
        case "session.ready":
          sessionDetailRef.current = {
            ...event.payload.detail,
            messages: sortCopilotMessages(event.payload.detail.messages),
          };
          setSessionDetail(sessionDetailRef.current);
          return;
        case "user.message.accepted":
          activeTraceIdRef.current = event.trace_id;
          setSessionDetail((current) => {
            const next = mergeAcceptedMessageIntoSession(
              current,
              event.payload.message,
              event.payload.session,
            );
            if (next) {
              sessionDetailRef.current = next;
            }
            return next;
          });
          setLiveStatus({
            traceId: event.trace_id,
            state: "thinking",
            label: "Thinking…",
          });
          return;
        case "assistant.turn.started":
          activeTraceIdRef.current = event.trace_id;
          setLiveStatus({
            traceId: event.trace_id,
            state: "thinking",
            label: "Thinking…",
          });
          return;
        case "assistant.progress":
          setLiveStatus({
            traceId: event.trace_id,
            state: event.payload.state,
            label: event.payload.label,
          });
          return;
        case "tool.started":
          setLiveStatus({
            traceId: event.trace_id,
            state: "running_tool",
            label: `Running ${event.payload.tool_name}…`,
          });
          return;
        case "tool.finished":
          setLiveStatus({
            traceId: event.trace_id,
            state: "running_tool",
            label: `${event.payload.action_run.tool_name} completed.`,
          });
          return;
        case "assistant.message.completed": {
          activeTraceIdRef.current = null;
          setSessionDetail((current) => {
            const next = mergeTurnIntoSession(current, event.payload.turn);
            sessionDetailRef.current = next;
            return next;
          });
          setIsTyping(false);
          setLiveStatus({
            traceId: event.trace_id,
            state: "completed",
            label: "Completed.",
          });
          scheduleLiveStatusClear();
          return;
        }
        case "assistant.turn.failed": {
          activeTraceIdRef.current = null;
          if (event.payload.turn) {
            setSessionDetail((current) => {
              const next = mergeTurnIntoSession(current, event.payload.turn as CopilotTurn);
              sessionDetailRef.current = next;
              return next;
            });
          }
          setIsTyping(false);
          setError(event.payload.error.message);
          setLiveStatus({
            traceId: event.trace_id,
            state: "failed",
            label: event.payload.error.message,
          });
          return;
        }
        case "session.error":
          setError(event.payload.message);
          return;
      }
    },
    [scheduleLiveStatusClear],
  );

  useEffect(() => {
    if (!businessId || !activeSessionId) {
      return;
    }
    if (socketRef.current?.readyState === 1) {
      return;
    }

    setSocketState("connecting");
    const socket = connectCopilotSessionSocket({
      businessId,
      sessionId: activeSessionId,
      onEvent: handleSocketEvent,
      onError: (message) => {
        setSocketState("failed");
        setError(message);
      },
      onClose: () => {
        if (socketRef.current === socket) {
          socketRef.current = null;
        }
        setSocketState((current) =>
          current === "connected" ? "failed" : current,
        );
      },
    });
    socket.addEventListener("open", () => {
      if (socketRef.current === socket) {
        setSocketState("connected");
      }
    });
    socketRef.current = socket;

    return () => {
      if (socketRef.current === socket) {
        socketRef.current = null;
      }
      socket.close();
    };
  }, [activeSessionId, businessId, handleSocketEvent]);

  const cancelActiveTurn = useCallback(() => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== 1) {
      return;
    }
    cancelCopilotSocketTurn(socket, activeTraceIdRef.current);
  }, []);

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
        const socket = socketRef.current;
        if (socket && socket.readyState === 1) {
          const traceId =
            typeof crypto !== "undefined" && "randomUUID" in crypto
              ? crypto.randomUUID()
              : `${Date.now()}`;
          activeTraceIdRef.current = traceId;
          sendCopilotSocketMessage(socket, {
            text: trimmed,
            location_id: locationId ?? null,
            normalized_channel: "dashboard",
            trace_id: traceId,
          });
          setLiveStatus({
            traceId,
            state: "thinking",
            label: "Thinking…",
          });
          return;
        }
        const turn = await createCopilotMessage(businessId, sessionId, {
          text: trimmed,
          location_id: locationId ?? null,
          normalized_channel: "dashboard",
        });
        setSessionDetail((current) => mergeTurnIntoSession(current, turn));
        setLiveStatus({
          traceId: null,
          state: "completed",
          label: "Completed.",
        });
        scheduleLiveStatusClear();
      } catch (nextError) {
        setInput(trimmed);
        setError(
          nextError instanceof Error
            ? nextError.message
            : "Failed to send Copilot message.",
        );
        setLiveStatus({
          traceId: null,
          state: "failed",
          label:
            nextError instanceof Error
              ? nextError.message
              : "Failed to send Copilot message.",
        });
      } finally {
        setIsTyping(false);
      }
    },
    [
      activeSessionId,
      businessId,
      ensureSession,
      locationId,
      scheduleLiveStatusClear,
    ],
  );

  return (
    <div className="flex h-full flex-col">
      <motion.div
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

          {liveStatus ? (
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6]">
                <Sparkles size={11} className="text-white" />
              </div>
              <div className={typingBubbleClass(dark)}>
                {liveStatus.state === "completed" ? (
                  <Sparkles size={12} className="text-[#635BFF]" />
                ) : liveStatus.state === "failed" ? (
                  <span className="h-2 w-2 rounded-full bg-[#E5484D]" />
                ) : (
                  <Loader2 size={12} className="animate-spin text-[#8898AA]" />
                )}
                <span
                  className={dark ? "text-[11px] text-[#C1CED8]" : "text-[11px] text-[#5E6D7A]"}
                  style={{ fontWeight: 500 }}
                >
                  {liveStatus.label}
                </span>
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
                  if (liveStatus) {
                    return;
                  }
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
                (!canCancelLiveTurn && (!input.trim() || !businessId || isTyping)) ||
                !businessId ||
                isLoadingSession
              }
              onClick={() => {
                if (canCancelLiveTurn) {
                  cancelActiveTurn();
                  return;
                }
                void sendMessage(input);
              }}
              type="button"
            >
              {canCancelLiveTurn ? (
                <Square size={14} className="text-[#635BFF]" />
              ) : (
                <Send size={14} className="text-[#635BFF]" />
              )}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
