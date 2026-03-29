import Link from "next/link";
import type { CoverageShift, CoverageStatus } from "@/lib/types";
import { EmptyState } from "./empty-state";
import { ImportRowScroller } from "./import-row-scroller";

type CoveragePanelProps = {
  shifts: CoverageShift[];
  locationId: number;
  highlightShiftId?: number;
};

/* ── Status display config ─────────────────────────────────────────────── */

type StatusConfig = {
  label: string;
  className: string;
  icon: string;
};

function statusConfig(status: CoverageStatus): StatusConfig {
  const map: Record<CoverageStatus, StatusConfig> = {
    offering: {
      label: "Offering",
      className: "cov-status cov-status-offering",
      icon: "cov-pulse",
    },
    awaiting_manager_approval: {
      label: "Awaiting approval",
      className: "cov-status cov-status-approval",
      icon: "cov-pulse",
    },
    awaiting_agency_approval: {
      label: "Awaiting agency",
      className: "cov-status cov-status-agency",
      icon: "cov-pulse",
    },
    agency_routing: {
      label: "Agency routing",
      className: "cov-status cov-status-agency",
      icon: "cov-pulse",
    },
    unassigned: {
      label: "Unassigned",
      className: "cov-status cov-status-unassigned",
      icon: "",
    },
    unfilled: {
      label: "Unfilled",
      className: "cov-status cov-status-unfilled",
      icon: "",
    },
  };
  return map[status] ?? { label: status, className: "cov-status", icon: "" };
}

function tierLabel(tier: string | null | undefined): string | null {
  if (!tier) return null;
  const map: Record<string, string> = {
    tier_1: "Internal",
    tier_2: "Alumni",
    tier_3: "Agency",
    internal: "Internal",
    alumni: "Alumni",
    agency: "Agency",
  };
  return map[tier] ?? tier;
}

function formatTime(time: string): string {
  const [h, m] = time.split(":");
  const hour = parseInt(h, 10);
  const suffix = hour >= 12 ? "pm" : "am";
  const display = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
  return m === "00" ? `${display}${suffix}` : `${display}:${m}${suffix}`;
}

function formatDate(date: string): string {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function timeAgo(isoString: string | null | undefined): string | null {
  if (!isoString) return null;
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/* ── Progress ring ─────────────────────────────────────────────────────── */

function OutreachProgress({
  offered,
  responded,
}: {
  offered: number | null | undefined;
  responded: number | null | undefined;
}) {
  const total = offered ?? 0;
  const done = responded ?? 0;
  if (total === 0) return null;

  const pct = Math.round((done / total) * 100);

  return (
    <div className="cov-progress">
      <div className="cov-progress-bar">
        <div className="cov-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="cov-progress-label">
        {done}/{total} responded
      </span>
    </div>
  );
}

/* ── Card ───────────────────────────────────────────────────────────────── */

function CoverageCard({ shift, highlight }: { shift: CoverageShift; highlight: boolean }) {
  const config = statusConfig(shift.coverage_status);
  const tier = tierLabel(shift.current_tier);
  const lastActivity = timeAgo(shift.last_response_at ?? shift.last_outreach_at);

  return (
    <div
      id={`coverage-shift-${shift.shift_id}`}
      className={`cov-card${highlight ? " cov-card-highlight" : ""}${shift.manager_action_required ? " cov-card-action" : ""}`}
    >
      {/* Header: status + action badge */}
      <div className="cov-card-header">
        <div className="cov-card-header-left">
          <span className={config.className}>
            {config.icon && <span className={config.icon} />}
            {config.label}
          </span>
          {tier && <span className="cov-tier">{tier}</span>}
        </div>
        {shift.manager_action_required && (
          <span className="cov-action-badge">Action needed</span>
        )}
      </div>

      {/* Body: shift info */}
      <div className="cov-card-body">
        <div className="cov-card-title">
          {shift.role}
        </div>
        <div className="cov-card-meta">
          {formatDate(shift.date)} at {formatTime(shift.start_time)}
        </div>
      </div>

      {/* Claimed worker (pending approval) */}
      {shift.claimed_by_worker_name && (
        <div className="cov-card-claimed">
          <span className="cov-card-claimed-label">Claimed by</span>
          <span className="cov-card-claimed-name">{shift.claimed_by_worker_name}</span>
          {shift.claimed_at && (
            <span className="cov-metric">{timeAgo(shift.claimed_at)}</span>
          )}
        </div>
      )}

      {/* Metrics row */}
      <div className="cov-card-metrics">
        <OutreachProgress offered={shift.offered_worker_count} responded={shift.responded_worker_count} />
        {shift.standby_depth != null && shift.standby_depth > 0 && (
          <span className="cov-metric">
            {shift.standby_depth} standby
          </span>
        )}
        {lastActivity && (
          <span className="cov-metric">
            {lastActivity}
          </span>
        )}
        {shift.cascade_id != null && (
          <span className="cov-metric">
            Cascade #{shift.cascade_id}
          </span>
        )}
      </div>

      {/* Footer */}
      <div className="cov-card-footer">
        <Link
          className="cov-view-link"
          href={`/dashboard/shifts/${shift.shift_id}`}
        >
          View details
        </Link>
      </div>
    </div>
  );
}

/* ── Panel ──────────────────────────────────────────────────────────────── */

export function CoveragePanel({ shifts, locationId, highlightShiftId }: CoveragePanelProps) {
  if (shifts.length === 0) {
    return (
      <EmptyState
        title="No at-risk shifts"
        body="When a callout is reported or a shift goes unfilled, coverage workflows will appear here."
      />
    );
  }

  // Sort: action-required first, then by coverage_status priority, then by date
  const statusOrder: Record<string, number> = {
    awaiting_manager_approval: 0,
    offering: 1,
    awaiting_agency_approval: 2,
    agency_routing: 3,
    unassigned: 4,
    unfilled: 5,
  };

  const sorted = [...shifts].sort((a, b) => {
    // Action required first
    if (a.manager_action_required && !b.manager_action_required) return -1;
    if (!a.manager_action_required && b.manager_action_required) return 1;
    // Then by status
    const sa = statusOrder[a.coverage_status] ?? 9;
    const sb = statusOrder[b.coverage_status] ?? 9;
    if (sa !== sb) return sa - sb;
    // Then by date
    return a.date.localeCompare(b.date) || a.start_time.localeCompare(b.start_time);
  });

  // Summary counts
  const activeCount = shifts.filter(
    (s) => s.coverage_status === "offering" || s.coverage_status === "agency_routing" || s.coverage_status === "awaiting_agency_approval"
  ).length;
  const actionCount = shifts.filter((s) => s.manager_action_required).length;

  return (
    <div className="cov-panel">
      {highlightShiftId && <ImportRowScroller targetId={`coverage-shift-${highlightShiftId}`} />}

      {/* Summary strip */}
      <div className="cov-summary">
        <div className="cov-summary-stat">
          <span className="cov-summary-number">{shifts.length}</span>
          <span className="cov-summary-label">At risk</span>
        </div>
        <div className="cov-summary-divider" />
        <div className="cov-summary-stat">
          <span className="cov-summary-number">{activeCount}</span>
          <span className="cov-summary-label">Active outreach</span>
        </div>
        {actionCount > 0 && (
          <>
            <div className="cov-summary-divider" />
            <div className="cov-summary-stat">
              <span className="cov-summary-number cov-summary-number-alert">{actionCount}</span>
              <span className="cov-summary-label">Need attention</span>
            </div>
          </>
        )}
      </div>

      {/* Cards */}
      <div className="cov-card-list">
        {sorted.map((shift) => (
          <CoverageCard
            key={shift.shift_id}
            shift={shift}
            highlight={shift.shift_id === highlightShiftId}
          />
        ))}
      </div>
    </div>
  );
}
