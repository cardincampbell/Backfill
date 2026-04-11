"use client";

import type { ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
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
import { Link } from "./router-shim";

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
    return `${start} - ${end}`;
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

function buildShiftHref(shiftId: string): string {
  return `/dashboard/shifts/${shiftId}`;
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

function ResultMetric({
  dark,
  label,
  value,
}: {
  dark: boolean;
  label: string;
  value: string;
}) {
  return (
    <div
      className={`rounded-xl border px-3 py-2 ${
        dark
          ? "border-white/[0.06] bg-white/[0.03]"
          : "border-[#E5E7EB] bg-[#FAFBFC]"
      }`}
    >
      <p
        className={`text-[14px] ${dark ? "text-white" : "text-[#0A2540]"}`}
        style={{ fontWeight: 620 }}
      >
        {value}
      </p>
      <p
        className={`mt-1 text-[10px] uppercase tracking-[0.08em] ${
          dark ? "text-[#8898AA]" : "text-[#8898AA]"
        }`}
        style={{ fontWeight: 560 }}
      >
        {label}
      </p>
    </div>
  );
}

function ResultHeader({
  dark,
  title,
  subtitle,
  icon,
  badges,
  metrics,
}: {
  dark: boolean;
  title: string;
  subtitle: string;
  icon: ReactNode;
  badges?: string[];
  metrics?: Array<{ label: string; value: string }>;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {icon}
            <span
              className={`text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`}
              style={{ fontWeight: 560 }}
            >
              {title}
            </span>
          </div>
          <p
            className={`mt-1 text-[11px] ${
              dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"
            }`}
            style={{ fontWeight: 420 }}
          >
            {subtitle}
          </p>
        </div>
        {badges?.length ? (
          <div className="flex flex-wrap justify-end gap-2">
            {badges.map((badge) => (
              <StatusPill key={badge} dark={dark} label={badge} />
            ))}
          </div>
        ) : null}
      </div>
      {metrics?.length ? (
        <div className={`grid gap-2 ${metrics.length > 2 ? "grid-cols-3" : "grid-cols-2"}`}>
          {metrics.map((metric) => (
            <ResultMetric
              key={metric.label}
              dark={dark}
              label={metric.label}
              value={metric.value}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function EmptyState({
  dark,
  message,
}: {
  dark: boolean;
  message: string;
}) {
  return (
    <div
      className={`rounded-xl border border-dashed px-3 py-3 text-[11px] ${
        dark
          ? "border-white/[0.08] bg-white/[0.02] text-[#C1CED8]"
          : "border-[#D7DBE0] bg-[#FAFBFC] text-[#5E6D7A]"
      }`}
      style={{ fontWeight: 420 }}
    >
      {message}
    </div>
  );
}

function ActionLink({
  dark,
  href,
  label,
}: {
  dark: boolean;
  href: string;
  label: string;
}) {
  return (
    <Link
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] transition-colors ${
        dark
          ? "bg-white/[0.06] text-white hover:bg-white/[0.1]"
          : "bg-[#EEF2FF] text-[#4F46E5] hover:bg-[#E0E7FF]"
      }`}
      style={{ fontWeight: 560 }}
      to={href}
    >
      {label}
      <ArrowUpRight size={11} />
    </Link>
  );
}

function DetailChip({
  dark,
  value,
}: {
  dark: boolean;
  value: string;
}) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] ${
        dark ? "bg-white/[0.06] text-[#C1CED8]" : "bg-[#F0F0F5] text-[#5E6D7A]"
      }`}
      style={{ fontWeight: 500 }}
    >
      {value}
    </span>
  );
}

function ResultRow({
  dark,
  eyebrow,
  title,
  details,
  status,
  action,
}: {
  dark: boolean;
  eyebrow: string;
  title: string;
  details: string[];
  status?: string | null;
  action?: { href: string; label: string } | null;
}) {
  return (
    <div
      className={`rounded-xl border px-3 py-3 ${
        dark
          ? "border-white/[0.06] bg-white/[0.03]"
          : "border-[#E5E7EB] bg-[#FAFBFC]"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p
            className={`text-[10px] uppercase tracking-[0.08em] ${
              dark ? "text-[#8898AA]" : "text-[#8898AA]"
            }`}
            style={{ fontWeight: 560 }}
          >
            {eyebrow}
          </p>
          <p
            className={`mt-1 text-[12px] ${dark ? "text-white" : "text-[#0A2540]"}`}
            style={{ fontWeight: 560 }}
          >
            {title}
          </p>
        </div>
        {status ? <StatusPill dark={dark} label={normalizeStatusLabel(status)} /> : null}
      </div>
      {details.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {details.map((detail) => (
            <DetailChip key={detail} dark={dark} value={detail} />
          ))}
        </div>
      ) : null}
      {action ? (
        <div className="mt-3">
          <ActionLink dark={dark} href={action.href} label={action.label} />
        </div>
      ) : null}
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
      <ResultHeader
        badges={[
          `${payload.total_open_shifts} open`,
          ...(typeof payload.location_count === "number"
            ? [`${payload.location_count} locations`]
            : []),
        ]}
        dark={dark}
        icon={<CalendarClock size={14} className="text-[#635BFF]" />}
        metrics={[
          { label: "open shifts", value: String(payload.total_open_shifts) },
          { label: "locations", value: String(payload.location_count ?? payload.items.length) },
        ]}
        subtitle="Open shifts that still need coverage right now."
        title="Open shifts"
      />
      {payload.items.length === 0 ? (
        <EmptyState
          dark={dark}
          message="No open shifts need coverage right now."
        />
      ) : (
        <div className="space-y-2">
          {payload.items.map((item: CopilotOpenShiftResultItem) => (
            <ResultRow
              key={item.shift_id}
              action={{
                href: buildShiftHref(item.shift_id),
                label: "Open shift",
              }}
              dark={dark}
              details={[
                item.location_name ?? "Unknown location",
                formatDateRange(item.starts_at, item.ends_at) ?? "Time unavailable",
              ]}
              eyebrow={item.role_name ?? "Open role"}
              status={item.status}
              title={item.location_name ?? "Coverage needed"}
            />
          ))}
        </div>
      )}
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
      <ResultHeader
        badges={[
          `${payload.total_active_campaigns} active`,
          ...(typeof payload.running_count === "number"
            ? [`${payload.running_count} running`]
            : []),
          ...(typeof payload.queued_count === "number"
            ? [`${payload.queued_count} queued`]
            : []),
        ]}
        dark={dark}
        icon={<Activity size={14} className="text-[#635BFF]" />}
        metrics={[
          { label: "active", value: String(payload.total_active_campaigns) },
          { label: "running", value: String(payload.running_count ?? 0) },
          { label: "queued", value: String(payload.queued_count ?? 0) },
        ]}
        subtitle="Coverage campaigns currently in motion."
        title="Active campaigns"
      />
      {payload.items.length === 0 ? (
        <EmptyState
          dark={dark}
          message="There are no active campaigns right now."
        />
      ) : (
        <div className="space-y-2">
          {payload.items.map((item: CopilotCampaignResultItem) => (
            <ResultRow
              key={item.campaign_id}
              action={{
                href: buildShiftHref(item.shift_id),
                label: "Open shift",
              }}
              dark={dark}
              details={[
                item.location_name ?? "Unknown location",
                item.phase_target
                  ? `${normalizeStatusLabel(item.phase_target)} target`
                  : "Phase target unavailable",
                formatDateTime(item.opened_at) ?? "Opened recently",
              ]}
              eyebrow={item.role_name ?? "Coverage campaign"}
              status={item.status}
              title={item.location_name ?? "Campaign in progress"}
            />
          ))}
        </div>
      )}
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
      <ResultHeader
        badges={[`${payload.total_actions} pending`]}
        dark={dark}
        icon={<ShieldAlert size={14} className="text-[#E5484D]" />}
        metrics={[
          { label: "pending", value: String(payload.total_actions) },
          {
            label: "next up",
            value: payload.items[0]?.starts_at
              ? formatDateTime(payload.items[0].starts_at)?.split(",")[0] ?? "Now"
              : "Now",
          },
        ]}
        subtitle="Shifts that still need manager review or intervention."
        title="Manager actions"
      />
      {payload.items.length === 0 ? (
        <EmptyState
          dark={dark}
          message="No manager actions need attention right now."
        />
      ) : (
        <div className="space-y-2">
          {payload.items.map((item: CopilotManagerActionResultItem) => (
            <ResultRow
              key={item.campaign_id}
              action={{
                href: buildShiftHref(item.shift_id),
                label: "Review shift",
              }}
              dark={dark}
              details={[
                item.location_name ?? "Unknown location",
                formatDateTime(item.starts_at) ?? "Time unavailable",
              ]}
              eyebrow={item.role_name ?? "Manager review"}
              status={item.status}
              title={item.location_name ?? "Review needed"}
            />
          ))}
        </div>
      )}
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
      <ResultHeader
        dark={dark}
        icon={<Sparkles size={14} className="text-[#635BFF]" />}
        metrics={[{ label: "tools", value: String(payload.tools.length) }]}
        subtitle="These are the dashboard tools Copilot can currently use."
        title="Available tools"
      />
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

function ResultFooter({
  dark,
  actionRun,
}: {
  dark: boolean;
  actionRun: CopilotActionRun;
}) {
  return (
    <div
      className={`mt-3 flex flex-wrap items-center gap-2 text-[10px] ${
        dark ? "text-[#8898AA]" : "text-[#8898AA]"
      }`}
      style={{ fontWeight: 500 }}
    >
      <span className="inline-flex items-center gap-1">
        <Clock3 size={11} />
        {formatDateTime(actionRun.finished_at ?? actionRun.started_at) ?? "Just now"}
      </span>
      <span className="inline-flex items-center gap-1">
        <MapPin size={11} />
        {normalizeStatusLabel(actionRun.tool_name.replace(/\./g, " "))}
      </span>
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
      <ResultFooter actionRun={actionRun} dark={dark} />
    </div>
  );
}
