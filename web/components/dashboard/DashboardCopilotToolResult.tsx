"use client";

import {
  Activity,
  CalendarClock,
  Clock3,
  MapPin,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import type {
  CopilotActionRun,
  CopilotCampaignResultItem,
  CopilotCampaignsResult,
  CopilotHelpResult,
  CopilotManagerActionResultItem,
  CopilotManagerActionsResult,
  CopilotOpenShiftResultItem,
  CopilotOpenShiftsResult,
} from "@/lib/types/copilot";

function formatDateTime(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatDateRange(
  startsAt: string | null | undefined,
  endsAt: string | null | undefined,
): string | null {
  const start = formatDateTime(startsAt);
  const end = formatDateTime(endsAt);
  if (start && end) {
    return `${start} – ${end}`;
  }
  return start ?? end;
}

function normalizeStatusLabel(status: string | null | undefined): string {
  return (status ?? "unknown").replace(/_/g, " ");
}

function getResultKind(
  payload: CopilotActionRun["result_payload"],
): string | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }
  const kind = (payload as { kind?: unknown }).kind;
  return typeof kind === "string" ? kind : null;
}

function StatusPill({
  dark,
  label,
}: {
  dark: boolean;
  label: string;
}) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${
        dark ? "bg-white/[0.08] text-[#C1CED8]" : "bg-[#F0F0F5] text-[#5E6D7A]"
      }`}
      style={{ fontWeight: 520 }}
    >
      {label}
    </span>
  );
}

function ResultRow({
  dark,
  title,
  subtitle,
  status,
}: {
  dark: boolean;
  title: string;
  subtitle?: string | null;
  status?: string | null;
}) {
  return (
    <div
      className={`flex items-start justify-between gap-3 rounded-xl border px-3 py-2.5 ${
        dark
          ? "border-white/[0.06] bg-white/[0.03]"
          : "border-[#E5E7EB] bg-[#FAFBFC]"
      }`}
    >
      <div className="min-w-0">
        <p
          className={`truncate text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`}
          style={{ fontWeight: 560 }}
        >
          {title}
        </p>
        {subtitle ? (
          <p
            className={`mt-1 text-[11px] ${
              dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"
            }`}
            style={{ fontWeight: 420 }}
          >
            {subtitle}
          </p>
        ) : null}
      </div>
      {status ? <StatusPill dark={dark} label={normalizeStatusLabel(status)} /> : null}
    </div>
  );
}

function OpenShiftsCard({
  dark,
  payload,
}: {
  dark: boolean;
  payload: CopilotOpenShiftsResult;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <CalendarClock size={14} className="text-[#635BFF]" />
          <span
            className={`text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`}
            style={{ fontWeight: 560 }}
          >
            Open shifts
          </span>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill dark={dark} label={`${payload.total_open_shifts} open`} />
          {typeof payload.location_count === "number" ? (
            <StatusPill dark={dark} label={`${payload.location_count} locations`} />
          ) : null}
        </div>
      </div>
      <div className="space-y-2">
        {payload.items.map((item: CopilotOpenShiftResultItem) => (
          <ResultRow
            key={item.shift_id}
            dark={dark}
            title={`${item.role_name ?? "Open role"} · ${item.location_name ?? "Unknown location"}`}
            subtitle={formatDateRange(item.starts_at, item.ends_at)}
            status={item.status}
          />
        ))}
      </div>
    </div>
  );
}

function CampaignsCard({
  dark,
  payload,
}: {
  dark: boolean;
  payload: CopilotCampaignsResult;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-[#635BFF]" />
          <span
            className={`text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`}
            style={{ fontWeight: 560 }}
          >
            Active campaigns
          </span>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill dark={dark} label={`${payload.total_active_campaigns} active`} />
          {typeof payload.running_count === "number" ? (
            <StatusPill dark={dark} label={`${payload.running_count} running`} />
          ) : null}
          {typeof payload.queued_count === "number" ? (
            <StatusPill dark={dark} label={`${payload.queued_count} queued`} />
          ) : null}
        </div>
      </div>
      <div className="space-y-2">
        {payload.items.map((item: CopilotCampaignResultItem) => (
          <ResultRow
            key={item.campaign_id}
            dark={dark}
            title={`${item.role_name ?? "Coverage campaign"} · ${item.location_name ?? "Unknown location"}`}
            subtitle={
              item.phase_target
                ? `${formatDateTime(item.opened_at) ?? "Opened"} · ${normalizeStatusLabel(item.phase_target)} target`
                : formatDateTime(item.opened_at)
            }
            status={item.status}
          />
        ))}
      </div>
    </div>
  );
}

function ManagerActionsCard({
  dark,
  payload,
}: {
  dark: boolean;
  payload: CopilotManagerActionsResult;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldAlert size={14} className="text-[#E5484D]" />
          <span
            className={`text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`}
            style={{ fontWeight: 560 }}
          >
            Manager actions
          </span>
        </div>
        <StatusPill dark={dark} label={`${payload.total_actions} pending`} />
      </div>
      <div className="space-y-2">
        {payload.items.map((item: CopilotManagerActionResultItem) => (
          <ResultRow
            key={item.campaign_id}
            dark={dark}
            title={`${item.role_name ?? "Manager review"} · ${item.location_name ?? "Unknown location"}`}
            subtitle={formatDateTime(item.starts_at)}
            status={item.status}
          />
        ))}
      </div>
    </div>
  );
}

function HelpCard({
  dark,
  payload,
}: {
  dark: boolean;
  payload: CopilotHelpResult;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles size={14} className="text-[#635BFF]" />
        <span
          className={`text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`}
          style={{ fontWeight: 560 }}
        >
          Available tools
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {payload.tools.map((tool) => (
          <span
            key={tool.name}
            className={`rounded-full px-2.5 py-1 text-[11px] ${
              dark
                ? "bg-white/[0.06] text-[#C1CED8]"
                : "bg-[#F0F0F5] text-[#5E6D7A]"
            }`}
            style={{ fontWeight: 500 }}
          >
            {tool.title}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function DashboardCopilotToolResult({
  actionRun,
  dark,
}: {
  actionRun: CopilotActionRun;
  dark: boolean;
}) {
  const resultKind = getResultKind(actionRun.result_payload);

  if (!resultKind) {
    return null;
  }

  return (
    <div
      className={`mt-2 rounded-2xl border px-3.5 py-3 ${
        dark
          ? "border-white/[0.06] bg-white/[0.03]"
          : "border-[#E5E7EB] bg-white"
      }`}
    >
      {resultKind === "open_shifts" ? (
        <OpenShiftsCard
          dark={dark}
          payload={actionRun.result_payload as CopilotOpenShiftsResult}
        />
      ) : null}
      {resultKind === "campaigns" ? (
        <CampaignsCard
          dark={dark}
          payload={actionRun.result_payload as CopilotCampaignsResult}
        />
      ) : null}
      {resultKind === "manager_actions" ? (
        <ManagerActionsCard
          dark={dark}
          payload={actionRun.result_payload as CopilotManagerActionsResult}
        />
      ) : null}
      {resultKind === "help" ? (
        <HelpCard
          dark={dark}
          payload={actionRun.result_payload as CopilotHelpResult}
        />
      ) : null}
      <div
        className={`mt-3 flex items-center gap-2 text-[10px] ${
          dark ? "text-[#8898AA]" : "text-[#8898AA]"
        }`}
        style={{ fontWeight: 500 }}
      >
        <Clock3 size={11} />
        <span>{formatDateTime(actionRun.finished_at ?? actionRun.started_at) ?? "Just now"}</span>
        <MapPin size={11} />
        <span>{normalizeStatusLabel(actionRun.tool_name.replace(/\./g, " "))}</span>
      </div>
    </div>
  );
}
