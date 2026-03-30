import Link from "next/link";
import { Suspense } from "react";
import { revalidatePath } from "next/cache";
import { notFound, redirect } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { StatCard } from "@/components/stat-card";
import { TabBar } from "@/components/tab-bar";
import { ScheduleGrid } from "@/components/schedule-grid";
import { ImportStatus } from "@/components/import-status";
import { ImportFlow } from "@/components/import-flow";
import { CoveragePanel } from "@/components/coverage-panel";
import { RosterPanel } from "@/components/roster-panel";
import { ManagerActionsPanel } from "@/components/manager-actions-panel";
import { LocationSettingsPanel } from "@/components/location-settings-panel";
import { PilotMetricsPanel } from "@/components/pilot-metrics-panel";
import AiPromptPanel from "@/components/ai-prompt-panel";
import { ExceptionsFeed } from "@/components/exceptions-feed";
import { AddEmployeeForm } from "@/components/add-employee-form";
import { ScheduleActions } from "@/components/schedule-actions";
import { ScheduleReviewPanel } from "@/components/schedule-review-panel";
import { DraftLauncher } from "@/components/draft-launcher";
import { TemplatePanel } from "@/components/template-panel";
import { WeekNav } from "@/components/week-nav";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";
import { getLocationStatus, getLocations } from "@/lib/api";
import { sendOnboardingLink, updateLocation } from "@/lib/server-api";
import {
  getWeeklySchedule,
  getImportJob,
  getImportRows,
  getCoverage,
  getLocationRoster,
  getEligibleWorkers,
  getManagerActions,
  getLocationSettings,
  getScheduleExceptions,
  getScheduleTemplates,
} from "@/lib/shifts-api";
import type {
  LocationStatusResponse,
  ManagerActionsResponse,
  ScheduleExceptionQueueResponse,
  ScheduleShift,
  WeeklyScheduleResponse,
} from "@/lib/types";

export const dynamic = "force-dynamic";

export type LocationDetailQuery = Record<string, string | string[] | undefined>;

type LocationDetailPageProps = {
  params: Promise<{ locationId: string }>;
  searchParams?: Promise<LocationDetailQuery>;
};

type RenderLocationDetailPageArgs = {
  locationId: number;
  query?: LocationDetailQuery;
  basePath: string;
};

type ManagerMetric = {
  label: string;
  value: string;
  hint: string;
  tone?: "default" | "accent" | "success";
};

function currentMonday(): string {
  const today = new Date();
  const day = today.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const monday = new Date(today);
  monday.setDate(today.getDate() + diff);
  return monday.toISOString().slice(0, 10);
}

function queryValue(value: string | string[] | undefined): string | undefined {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return typeof value[0] === "string" ? value[0] : undefined;
  }
  return undefined;
}

function normalizeQuery(query: LocationDetailQuery): Record<string, string> {
  return Object.fromEntries(
    Object.entries(query)
      .map(([key, value]) => [key, queryValue(value)] as const)
      .filter((entry): entry is [string, string] => Boolean(entry[1])),
  );
}

function buildLocationHref(
  basePath: string,
  params?: Record<string, string | number | undefined | null>,
): string {
  if (!params) {
    return basePath;
  }
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value == null || value === "") {
      continue;
    }
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

function formatSyncStamp(timestamp?: string | null, status?: string | null): string {
  if (!timestamp && !status) {
    return "Never";
  }
  const stamp = timestamp ? new Date(timestamp).toLocaleString() : "No timestamp";
  return `${status ?? "unknown"} · ${stamp}`;
}

function describeMode(mode?: string | null): string {
  if (mode === "companion_writeback") {
    return "Companion + write-back";
  }
  if (mode === "companion") {
    return "Companion";
  }
  return "Native Lite";
}

function setupKindForPlatform(platform?: string | null): "integration" | "csv_upload" {
  return platform && platform !== "backfill_native" ? "integration" : "csv_upload";
}

function setupPathForPlatform(locationId: number, platform?: string | null): string {
  if (platform && platform !== "backfill_native") {
    return `/setup/connect?location_id=${locationId}&platform=${encodeURIComponent(platform)}`;
  }
  return `/setup/upload?location_id=${locationId}`;
}

function legacyDetailPath(locationId: number, query?: string): string {
  return query
    ? `/dashboard/locations/${locationId}?${query}`
    : `/dashboard/locations/${locationId}`;
}

function countBackfillWins(shifts: ScheduleShift[]): number {
  return shifts.filter(
    (shift) =>
      Boolean(shift.assignment?.filled_via_backfill) ||
      shift.coverage?.status === "backfilled",
  ).length;
}

function estimateManagerHoursSaved(shifts: ScheduleShift[]): number {
  const backfillWins = countBackfillWins(shifts);
  const pendingAiAssist = shifts.filter(
    (shift) =>
      shift.coverage?.status === "awaiting_manager_approval" ||
      shift.coverage?.status === "active",
  ).length;
  return backfillWins * 0.8 + pendingAiAssist * 0.15;
}

function formatEstimatedHours(value: number): string {
  if (value <= 0) {
    return "0.0h";
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)}h`;
}

function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
}

function scheduleLifecyclePillClass(lifecycleState?: string | null): string {
  if (lifecycleState === "published") return "pill pill-published";
  if (lifecycleState === "amended") return "pill pill-amended";
  if (lifecycleState === "recalled") return "pill pill-recalled";
  if (lifecycleState === "draft") return "pill pill-draft";
  return "pill";
}

function buildExceptionFeed(
  locationId: number,
  exceptions: WeeklyScheduleResponse["exceptions"],
): ScheduleExceptionQueueResponse {
  return {
    location_id: locationId,
    summary: {
      total: exceptions.length,
      action_required: exceptions.filter((exception) => exception.action_required).length,
      critical: exceptions.filter((exception) => exception.severity === "critical").length,
    },
    exceptions,
  };
}

function emptyManagerActions(locationId: number): ManagerActionsResponse {
  return {
    location_id: locationId,
    summary: { total: 0, approve_fill: 0, approve_agency: 0, attendance_reviews: 0 },
    actions: [],
  };
}

function buildManagerMetrics(
  schedule: WeeklyScheduleResponse | null,
  managerActions: ManagerActionsResponse,
): ManagerMetric[] {
  if (!schedule?.schedule) {
    return [
      {
        label: "Manager hours saved",
        value: "0.0h",
        hint: "Starts accruing once Backfill handles live fill work.",
      },
      {
        label: "Open shifts",
        value: "0",
        hint: "No shifts drafted yet for this week.",
      },
      {
        label: "At-risk shifts",
        value: "0",
        hint: "Coverage issues surface here once the week is active.",
      },
      {
        label: "Fill rate",
        value: "0%",
        hint: "Calculated after the first weekly draft exists.",
      },
      {
        label: "Needs attention",
        value: String(managerActions.summary.total),
        hint: "Outstanding approvals and reviews waiting on the manager.",
        tone: managerActions.summary.total > 0 ? "accent" : "default",
      },
    ];
  }

  const totalShifts = schedule.shifts.length;
  const fillRate = totalShifts > 0 ? (schedule.summary.filled_shifts / totalShifts) * 100 : 0;
  const needsAttention = Math.max(
    schedule.summary.action_required_count ?? 0,
    managerActions.summary.total,
  );

  return [
    {
      label: "Manager hours saved",
      value: formatEstimatedHours(estimateManagerHoursSaved(schedule.shifts)),
      hint: "Estimated from automated fill coverage and Backfill-led interventions this week.",
      tone: countBackfillWins(schedule.shifts) > 0 ? "success" : "default",
    },
    {
      label: "Open shifts",
      value: String(schedule.summary.open_shifts),
      hint: "Unassigned or still open on the live weekly schedule.",
      tone: schedule.summary.open_shifts > 0 ? "accent" : "default",
    },
    {
      label: "At-risk shifts",
      value: String(schedule.summary.at_risk_shifts),
      hint: "Coverage pressure across callouts, pending claims, and active escalation.",
      tone: schedule.summary.at_risk_shifts > 0 ? "accent" : "default",
    },
    {
      label: "Fill rate",
      value: formatPercent(fillRate),
      hint: totalShifts > 0 ? `${schedule.summary.filled_shifts} of ${totalShifts} shifts currently covered.` : "No shifts in this week yet.",
      tone: fillRate >= 90 ? "success" : fillRate < 70 ? "accent" : "default",
    },
    {
      label: "Needs attention",
      value: String(needsAttention),
      hint: "Approvals, attendance reviews, and exception items requiring a manager decision.",
      tone: needsAttention > 0 ? "accent" : "default",
    },
  ];
}

function ManagerMetricStrip({ metrics }: { metrics: ManagerMetric[] }) {
  return (
    <div className="workspace-kpis">
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className={`workspace-kpi${metric.tone ? ` workspace-kpi-${metric.tone}` : ""}`}
        >
          <div className="workspace-kpi-label">{metric.label}</div>
          <div className="workspace-kpi-value">{metric.value}</div>
          <div className="workspace-kpi-hint">{metric.hint}</div>
        </div>
      ))}
    </div>
  );
}

const LOCATION_TABS = [
  { key: "schedule", label: "Schedule" },
  { key: "coverage", label: "Coverage" },
  { key: "actions", label: "Actions" },
  { key: "exceptions", label: "Exceptions" },
  { key: "roster", label: "Roster" },
  { key: "imports", label: "Imports" },
  { key: "overview", label: "Overview" },
  { key: "settings", label: "Settings" },
];

async function runLocationAction(formData: FormData) {
  "use server";

  const locationId = Number(formData.get("location_id"));
  const action = String(formData.get("action") ?? "");

  if (!Number.isInteger(locationId) || locationId <= 0) {
    redirect("/dashboard?sync=error&message=Invalid+location+id");
  }

  const destination = `/dashboard/locations/${locationId}`;

  try {
    if (action === "send_onboarding") {
      const phone = String(formData.get("phone") ?? "").trim();
      const kind = String(formData.get("kind") ?? "").trim();
      const platform = String(formData.get("platform") ?? "").trim() || undefined;

      if (!phone) {
        redirect(legacyDetailPath(locationId, "action=error&detail=Missing+primary+contact+phone+number"));
      }

      const result = await sendOnboardingLink({ phone, kind, platform, location_id: locationId });
      revalidatePath(destination);
      redirect(
        legacyDetailPath(
          locationId,
          `action=link_ok&detail=${encodeURIComponent(`Sent ${result.path} to ${phone}.`)}`,
        ),
      );
    }

    if (action === "toggle_writeback") {
      const enabled = String(formData.get("enabled") ?? "").trim() === "true";
      await updateLocation(locationId, {
        writeback_enabled: enabled,
        writeback_subscription_tier: enabled ? "premium" : "core",
      });
      revalidatePath(destination);
      redirect(
        legacyDetailPath(
          locationId,
          `action=writeback_ok&detail=${encodeURIComponent(
            enabled
              ? "Paid write-back enabled for this location."
              : "Write-back disabled. Native remains the execution ledger.",
          )}`,
        ),
      );
    }

    redirect(legacyDetailPath(locationId, "action=error&detail=Unsupported+location+action"));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Action failed";
    redirect(legacyDetailPath(locationId, `action=error&detail=${encodeURIComponent(message)}`));
  }
}

export default async function LocationDetailPage({
  params,
  searchParams,
}: LocationDetailPageProps) {
  const { locationId } = await params;
  const numericLocationId = Number(locationId);
  const query = searchParams ? await searchParams : {};

  if (!Number.isInteger(numericLocationId) || numericLocationId <= 0) {
    notFound();
  }

  const status = await getLocationStatus(numericLocationId);

  if (!status) {
    notFound();
  }

  redirect(buildDashboardLocationPath(status.location, normalizeQuery(query)));
}

export async function renderLocationDetailPage({
  locationId,
  query = {},
  basePath,
}: RenderLocationDetailPageArgs) {
  const status = await getLocationStatus(locationId);

  if (!status) {
    notFound();
  }

  const activeTab = queryValue(query.tab) ?? "schedule";
  const action = queryValue(query.action) ?? "";
  const detail = queryValue(query.detail) ? decodeURIComponent(queryValue(query.detail) ?? "") : "";
  const weekStart = queryValue(query.week_start);
  const jobIdParam = queryValue(query.job_id) ? Number(queryValue(query.job_id)) : undefined;
  const rowParam = queryValue(query.row) ? Number(queryValue(query.row)) : undefined;
  const shiftIdParam = queryValue(query.shift_id) ? Number(queryValue(query.shift_id)) : undefined;
  const setupKind = setupKindForPlatform(status.location.scheduling_platform);
  const setupPath = setupPathForPlatform(locationId, status.location.scheduling_platform);
  const modeLabel = describeMode(status.integration.mode);
  const writebackEnabled = Boolean(status.integration.writeback_enabled);
  const writebackSupported = Boolean(status.integration.writeback_supported);

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Manager workspace</span>
        <h1>{status.location.organization_name ?? status.location.name}</h1>
        <p>
          {status.location.name}
          {status.location.address ? ` · ${status.location.address}` : ""}
          {status.location.vertical ? ` · ${status.location.vertical}` : ""}
        </p>
      </div>

      {action.endsWith("_ok") ? (
        <section style={{ marginBottom: 16 }}>
          <div className="callout success-callout">
            <h3>Action completed</h3>
            <p>{detail || "The location action completed successfully."}</p>
          </div>
        </section>
      ) : null}

      {action === "error" ? (
        <section style={{ marginBottom: 16 }}>
          <div className="callout error-callout">
            <h3>Action failed</h3>
            <p>{detail || "The location action did not complete."}</p>
          </div>
        </section>
      ) : null}

      <Suspense>
        <TabBar
          tabs={LOCATION_TABS}
          basePath={basePath}
          preserveParams={["week_start", "job_id", "row", "shift_id"]}
        />
      </Suspense>

      {activeTab === "schedule" && (
        <ScheduleTabContent
          locationId={locationId}
          location={status}
          weekStart={weekStart}
          basePath={basePath}
        />
      )}

      {activeTab === "roster" && (
        <RosterTabContent locationId={locationId} basePath={basePath} />
      )}

      {activeTab === "imports" && (
        <ImportsTabContent
          locationId={locationId}
          basePath={basePath}
          jobId={jobIdParam}
          highlightRow={rowParam}
        />
      )}

      {activeTab === "coverage" && (
        <CoverageTabContent locationId={locationId} weekStart={weekStart} highlightShiftId={shiftIdParam} />
      )}

      {activeTab === "actions" && (
        <ManagerActionsTabContent locationId={locationId} weekStart={weekStart} />
      )}

      {activeTab === "exceptions" && (
        <ExceptionsTabContent locationId={locationId} />
      )}

      {activeTab === "settings" && (
        <SettingsTabContent locationId={locationId} />
      )}

      {activeTab === "overview" && (
        <OverviewTabContent
          locationId={locationId}
          status={status}
          setupPath={setupPath}
          setupKind={setupKind}
          modeLabel={modeLabel}
          writebackEnabled={writebackEnabled}
          writebackSupported={writebackSupported}
        />
      )}

      <section className="section">
        <Link className="text-link" href="/dashboard">
          Back to dashboard
        </Link>
      </section>
    </main>
  );
}

async function OverviewTabContent({
  locationId,
  status,
  setupPath,
  setupKind,
  modeLabel,
  writebackEnabled,
  writebackSupported,
}: {
  locationId: number;
  status: LocationStatusResponse;
  setupPath: string;
  setupKind: "integration" | "csv_upload";
  modeLabel: string;
  writebackEnabled: boolean;
  writebackSupported: boolean;
}) {
  return (
    <>
      <div className="stat-grid">
        <StatCard label="Workers" value={status.metrics.workers_total} />
        <StatCard label="SMS Ready" value={status.metrics.workers_sms_ready} />
        <StatCard label="Voice Ready" value={status.metrics.workers_voice_ready} />
        <StatCard label="Upcoming Shifts" value={status.metrics.upcoming_shifts} />
        <StatCard label="Vacancies" value={status.metrics.shifts_vacant} />
        <StatCard label="Filled Shifts" value={status.metrics.shifts_filled} />
        <StatCard label="Active Cascades" value={status.metrics.active_cascades} />
        <StatCard label="Standby Workers" value={status.metrics.workers_on_standby} />
      </div>

      <section className="section">
        <div className="two-up">
          <div className="callout">
            <h3>Platform settings</h3>
            <p>Platform: <strong>{status.integration.platform}</strong></p>
            <p>Mode: <strong>{modeLabel}</strong></p>
            <p>Write-back support: <strong>{writebackSupported ? "Supported by platform" : "Not supported"}</strong></p>
            <p>Write-back status: <strong>{writebackEnabled ? "Enabled" : "Disabled"}</strong></p>
            <p>Plan: <strong>{status.integration.writeback_subscription_tier ?? "core"}</strong></p>
            <p>External ID: <strong>{status.location.scheduling_platform_id ?? "Not set"}</strong></p>
            <p>Integration status: <strong>{status.integration.status}</strong></p>
            <p>Operational state: <strong>{status.integration.integration_state ?? "healthy"}</strong></p>
            <div className="table-meta">
              <div>Roster sync: {formatSyncStamp(status.integration.last_roster_sync_at, status.integration.last_roster_sync_status)}</div>
              <div>Schedule sync: {formatSyncStamp(status.integration.last_schedule_sync_at, status.integration.last_schedule_sync_status)}</div>
              <div>Event reconcile: {status.integration.last_event_sync_at ?? "Never"}</div>
              <div>Rolling sweep: {status.integration.last_rolling_sync_at ?? "Never"}</div>
              <div>Daily reconcile: {status.integration.last_daily_sync_at ?? "Never"}</div>
              <div>Last write-back: {status.integration.last_writeback_at ?? "Never"}</div>
              {status.integration.reason ? <div>Credential check: {status.integration.reason}</div> : null}
              {status.integration.last_sync_error ? <div>Last error: {status.integration.last_sync_error}</div> : null}
            </div>
            <div className="cta-row">
              <Link className="button-secondary button-small" href={setupPath}>
                Open setup flow
              </Link>
              {writebackSupported ? (
                <form action={runLocationAction}>
                  <input type="hidden" name="location_id" value={status.location.id} />
                  <input type="hidden" name="action" value="toggle_writeback" />
                  <input type="hidden" name="enabled" value={writebackEnabled ? "false" : "true"} />
                  <button className="button-secondary button-small" type="submit">
                    {writebackEnabled ? "Disable write-back" : "Enable paid write-back"}
                  </button>
                </form>
              ) : null}
            </div>
          </div>

          <div className="callout">
            <h3>Primary contact handoff</h3>
            <p>Primary contact: <strong>{status.location.manager_name ?? "Unassigned"}</strong></p>
            <p>Phone: <strong>{status.location.manager_phone ?? "Missing"}</strong></p>
            <p>Email: <strong>{status.location.manager_email ?? "Missing"}</strong></p>
            <p>Agency escalation: <strong>{status.location.agency_supply_approved ? "Approved" : "Not approved"}</strong></p>
            <div className="table-meta">
              <div>Onboarding notes: {status.location.onboarding_info ?? "No notes yet."}</div>
            </div>
            <div className="cta-row">
              <Link className="button-secondary button-small" href={setupPath}>
                Continue setup
              </Link>
              <Link className="button-secondary button-small" href="/setup/add">
                Manual add
              </Link>
              {status.location.manager_phone ? (
                <form action={runLocationAction}>
                  <input type="hidden" name="location_id" value={status.location.id} />
                  <input type="hidden" name="action" value="send_onboarding" />
                  <input type="hidden" name="phone" value={status.location.manager_phone} />
                  <input type="hidden" name="kind" value={setupKind} />
                  <input
                    type="hidden"
                    name="platform"
                    value={status.location.scheduling_platform ?? ""}
                  />
                  <button className="button-secondary button-small" type="submit">Text setup link</button>
                </form>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Coverage runs</h2>
            <p className="muted">Location-scoped coverage state.</p>
          </div>
        </div>
        {status.active_cascades.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Shift</th>
                  <th>Mode</th>
                  <th>Tier</th>
                  <th>Status</th>
                  <th>Confirmed</th>
                  <th>Standby</th>
                </tr>
              </thead>
              <tbody>
                {status.active_cascades.map((cascade) => (
                  <tr key={cascade.id}>
                    <td>
                      <Link className="text-link" href={`/dashboard/shifts/${cascade.shift_id}`}>
                        {cascade.shift_role} · {cascade.shift_date} · {cascade.shift_start_time}
                      </Link>
                    </td>
                    <td>{cascade.outreach_mode ?? "n/a"}</td>
                    <td>{cascade.current_tier ? `Tier ${cascade.current_tier}` : "n/a"}</td>
                    <td><span className="pill">{cascade.status}</span></td>
                    <td>{cascade.confirmed_worker_name ?? "None yet"}</td>
                    <td>{cascade.standby_depth}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No active coverage" body="This location does not currently have live broadcast or cascade runs." />
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Recent shifts</h2>
            <p className="muted">Latest scheduled, vacant, and filled shifts.</p>
          </div>
        </div>
        {status.recent_shifts.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Role</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Fill tier</th>
                </tr>
              </thead>
              <tbody>
                {status.recent_shifts.map((shift) => (
                  <tr key={shift.id}>
                    <td>
                      <Link className="text-link" href={`/dashboard/shifts/${shift.id}`}>
                        {shift.id}
                      </Link>
                    </td>
                    <td>{shift.role}</td>
                    <td>{shift.date} · {shift.start_time}</td>
                    <td><span className="pill">{shift.status}</span></td>
                    <td>{shift.fill_tier ?? "Not filled yet"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No shifts yet" body="Shifts will appear here once created or synced." />
        )}
      </section>

      <section className="section">
        <div className="two-up">
          <div className="panel">
            <h3>Recent audit</h3>
            {status.recent_audit.length ? (
              <table>
                <thead>
                  <tr><th>Timestamp</th><th>Action</th><th>Actor</th></tr>
                </thead>
                <tbody>
                  {status.recent_audit.map((audit) => (
                    <tr key={audit.id}>
                      <td>{audit.timestamp}</td>
                      <td>{audit.action}</td>
                      <td>{audit.actor}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="No audit yet" body="Events appear as actions happen." />
            )}
          </div>

          <div className="panel">
            <h3>Recent sync queue</h3>
            {status.recent_sync_jobs.length ? (
              <table>
                <thead>
                  <tr><th>Job</th><th>Status</th><th>Attempts</th><th>Next run</th></tr>
                </thead>
                <tbody>
                  {status.recent_sync_jobs.map((job) => (
                    <tr key={job.id}>
                      <td>{job.job_type}<div className="table-meta"><div>{job.platform}</div></div></td>
                      <td><span className="pill">{job.status}</span></td>
                      <td>{job.attempt_count} / {job.max_attempts}</td>
                      <td>{job.status === "completed" ? (job.completed_at ?? "-") : job.next_run_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="No sync jobs yet" body="Webhook-triggered and scheduled reconcile jobs appear automatically." />
            )}
          </div>
        </div>
      </section>
    </>
  );
}

async function ScheduleTabContent({
  locationId,
  location,
  weekStart,
  basePath,
}: {
  locationId: number;
  location: LocationStatusResponse;
  weekStart?: string;
  basePath: string;
}) {
  const targetWeek = weekStart ?? currentMonday();
  const [schedule, eligibleResponse, templates, managerActions] = await Promise.all([
    getWeeklySchedule(locationId, weekStart),
    getEligibleWorkers(locationId),
    getScheduleTemplates(locationId),
    getManagerActions(locationId, targetWeek),
  ]);

  const workers = eligibleResponse?.workers ?? [];
  const actionQueue = managerActions ?? emptyManagerActions(locationId);
  const metrics = buildManagerMetrics(schedule, actionQueue);
  const organizationLabel = location.location.organization_name ?? "Independent business";
  const locationLabel = location.location.name;

  if (!schedule || !schedule.schedule) {
    return (
      <section className="section workspace-shell workspace-shell-manager">
      <div className="workspace-top workspace-top-manager">
        <div className="workspace-context">
          <span className="workspace-kicker">{organizationLabel} / {locationLabel}</span>
          <h2>{locationLabel} schedule</h2>
          <p>Start from a template, import the roster, or ask Backfill to draft the first workable week for this location.</p>
        </div>
        <div className="workspace-top-actions">
            <WeekNav locationId={locationId} weekStartDate={targetWeek} basePath={basePath} />
            <Link className="button-secondary button-small" href={buildLocationHref(basePath, { tab: "imports" })}>
              Import CSV
            </Link>
          </div>
        </div>

        <ManagerMetricStrip metrics={metrics} />

        <div className="workspace-layout workspace-layout-manager">
          <div className="workspace-main workspace-main-manager">
            <div className="workspace-section">
              <div className="workspace-section-headline">
                <div>
                  <h3>Schedule canvas</h3>
                  <p>No weekly draft exists yet. Use one of the launch paths below to get to a first-pass schedule fast.</p>
                </div>
                <span className="workspace-pill">Week of {targetWeek}</span>
              </div>
              <EmptyState
                title="No schedule found for this week"
                body="Import a roster and shifts CSV, apply a template, or let Backfill generate the first draft."
              />
            </div>

            <div className="workspace-secondary workspace-secondary-manager">
              <div className="workspace-section">
                <div className="workspace-section-headline">
                  <div>
                    <h3>Create the first draft</h3>
                    <p>Build from existing patterns or let Backfill propose a starting point.</p>
                  </div>
                </div>
                <DraftLauncher locationId={locationId} weekStart={targetWeek} basePath={basePath} />
              </div>

              <div className="workspace-section">
                <div className="workspace-section-headline">
                  <div>
                    <h3>Import roster and shifts</h3>
                    <p>Fastest path if you already have a CSV export from another system.</p>
                  </div>
                </div>
                <ImportFlow locationId={locationId} basePath={basePath} />
              </div>

              {(templates ?? []).length > 0 && (
                <div className="workspace-section">
                  <div className="workspace-section-headline">
                    <div>
                      <h3>Reusable weekly patterns</h3>
                      <p>Apply a saved template or spin a draft schedule from a proven staffing pattern.</p>
                    </div>
                  </div>
                  <TemplatePanel
                    locationId={locationId}
                    templates={templates ?? []}
                    basePath={basePath}
                  />
                </div>
              )}
            </div>
          </div>

          <aside className="workspace-rail workspace-rail-manager">
            <div className="workspace-section workspace-section-sticky">
              <div className="workspace-section-headline">
                <div>
                  <h3>Backfill Copilot</h3>
                  <p>Ask for a draft, pull import issues forward, or inspect what this location still needs to go live.</p>
                </div>
              </div>
              <AiPromptPanel
                locationId={locationId}
                weekStartDate={targetWeek}
                activeTab="schedule"
              />
            </div>

            <div className="workspace-section">
              <div className="workspace-section-headline">
                <div>
                  <h3>Needs attention</h3>
                  <p>Approvals and attendance reviews waiting on a manager.</p>
                </div>
                <span className="workspace-pill">{actionQueue.summary.total}</span>
              </div>
              <ManagerActionsPanel data={actionQueue} />
            </div>
          </aside>
        </div>
      </section>
    );
  }

  const exceptionFeed = buildExceptionFeed(locationId, schedule.exceptions);

  return (
    <section className="section workspace-shell workspace-shell-manager">
      <div className="workspace-top workspace-top-manager">
        <div className="workspace-context">
          <span className="workspace-kicker">{organizationLabel} / {locationLabel}</span>
          <h2>{locationLabel} week board</h2>
          <p>The schedule is the main operating surface: who works when, what is open, and what still needs a manager decision.</p>
        </div>
        <div className="workspace-top-actions">
          <span className={`${scheduleLifecyclePillClass(schedule.schedule.lifecycle_state)} workspace-state-pill`}>
            {schedule.schedule.lifecycle_state}
          </span>
          <WeekNav
            locationId={locationId}
            weekStartDate={schedule.schedule.week_start_date}
            basePath={basePath}
          />
          <Link className="button-secondary button-small" href={buildLocationHref(basePath, { tab: "imports" })}>
            Import
          </Link>
        </div>
      </div>

      <ManagerMetricStrip metrics={metrics} />

      <div className="workspace-layout workspace-layout-manager">
        <div className="workspace-main workspace-main-manager">
          <div className="workspace-section workspace-section-schedule">
            <div className="workspace-section-headline workspace-section-headline-wide">
              <div>
                <h3>Week of {schedule.schedule.week_start_date}</h3>
                <p>The schedule is the main canvas. Use the actions here to publish, amend, and keep the week moving.</p>
              </div>
              <ScheduleActions
                scheduleId={schedule.schedule.id}
                locationId={locationId}
                lifecycleState={schedule.schedule.lifecycle_state}
                weekStartDate={schedule.schedule.week_start_date}
                basePath={basePath}
              />
            </div>
            <ScheduleGrid
              shifts={schedule.shifts}
              exceptions={schedule.exceptions}
              summary={schedule.summary}
              lifecycleState={schedule.schedule.lifecycle_state}
              weekStartDate={schedule.schedule.week_start_date}
              scheduleId={schedule.schedule.id}
              workers={workers}
            />
          </div>

          <div className="workspace-secondary workspace-secondary-manager">
            <div className="workspace-section workspace-section-support">
              <div className="workspace-section-headline">
                <div>
                  <h3>Review before publish</h3>
                  <p>Draft quality, publish blockers, and worker-impact summaries for this specific week.</p>
                </div>
              </div>
              <ScheduleReviewPanel scheduleId={schedule.schedule.id} />
            </div>

            <div className="workspace-section workspace-section-support">
              <div className="workspace-section-headline">
                <div>
                  <h3>Templates and next week</h3>
                  <p>Save this week as a repeatable pattern, apply an existing template, or generate the next draft faster.</p>
                </div>
              </div>
              <TemplatePanel
                locationId={locationId}
                scheduleId={schedule.schedule.id}
                currentWeekStart={schedule.schedule.week_start_date}
                templates={templates ?? []}
                basePath={basePath}
              />
            </div>
          </div>
        </div>

        <aside className="workspace-rail workspace-rail-manager">
          <div className="workspace-section workspace-section-sticky workspace-section-rail workspace-section-rail-ai">
            <div className="workspace-section-headline">
              <div>
                <h3>Backfill Copilot</h3>
                <p>Ask for changes in plain language, review the plan, and confirm only when the action is safe.</p>
              </div>
            </div>
            <AiPromptPanel
              locationId={locationId}
              scheduleId={schedule.schedule.id}
              weekStartDate={schedule.schedule.week_start_date}
              activeTab="schedule"
            />
          </div>

          <div className="workspace-section workspace-section-rail">
            <div className="workspace-section-headline">
              <div>
                <h3>Needs attention</h3>
                <p>Coverage approvals and attendance decisions waiting for a manager.</p>
              </div>
              <span className="workspace-pill">{actionQueue.summary.total}</span>
            </div>
            <ManagerActionsPanel data={actionQueue} />
          </div>

          <div className="workspace-section workspace-section-rail">
            <div className="workspace-section-headline">
              <div>
                <h3>Shift exceptions</h3>
                <p>Open shifts, active escalations, and any week-specific exception Backfill has already detected.</p>
              </div>
              <span className="workspace-pill">{exceptionFeed.summary.total}</span>
            </div>
            <ExceptionsFeed data={exceptionFeed} />
          </div>
        </aside>
      </div>
    </section>
  );
}

async function RosterTabContent({
  locationId,
  basePath,
}: {
  locationId: number;
  basePath: string;
}) {
  const [roster, allLocations] = await Promise.all([
    getLocationRoster(locationId),
    getLocations(),
  ]);
  const locationOptions = allLocations.map((l) => ({ id: l.id, name: l.name }));
  const emptyRoster = {
    location_id: locationId,
    summary: { total_workers: 0, active_workers: 0, inactive_workers: 0, enrolled_workers: 0 },
    workers: [] as never[],
  };
  const rosterRoles = [...new Set((roster ?? emptyRoster).workers.flatMap((w: { roles?: string[]; active_assignment?: { roles?: string[] } }) => w.active_assignment?.roles ?? w.roles ?? []))].sort();

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>Employee roster</h2>
          <p className="muted">Manage employees, roles, and enrollment status.</p>
        </div>
        <div className="cta-row">
          <AddEmployeeForm locationId={locationId} existingRoles={rosterRoles} />
          <Link className="button-secondary button-small" href={buildLocationHref(basePath, { tab: "imports" })}>
            Import CSV
          </Link>
        </div>
      </div>
      <RosterPanel
        roster={roster ?? emptyRoster}
        locationId={locationId}
        locations={locationOptions}
      />
    </section>
  );
}

async function ImportsTabContent({
  locationId,
  basePath,
  jobId,
  highlightRow,
}: {
  locationId: number;
  basePath: string;
  jobId?: number;
  highlightRow?: number;
}) {
  if (!jobId) {
    return (
      <section className="section">
        <div className="section-head">
          <div>
            <h2>Import pipeline</h2>
            <p className="muted">Upload, map, validate, and commit roster and shift data.</p>
          </div>
        </div>
        <ImportFlow locationId={locationId} basePath={basePath} />
      </section>
    );
  }

  const [job, rowsResponse] = await Promise.all([
    getImportJob(jobId),
    getImportRows(jobId),
  ]);

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>Import pipeline</h2>
          <p className="muted">Upload, map, validate, and commit roster and shift data.</p>
        </div>
        <div className="cta-row">
          <Link
            className="button button-small"
            href={buildLocationHref(basePath, { tab: "imports" })}
          >
            New import
          </Link>
        </div>
      </div>
      <ImportStatus job={job} rows={rowsResponse?.rows ?? []} highlightRow={highlightRow} />
    </section>
  );
}

async function CoverageTabContent({
  locationId,
  weekStart,
  highlightShiftId,
}: {
  locationId: number;
  weekStart?: string;
  highlightShiftId?: number;
}) {
  const coverage = await getCoverage(locationId, weekStart);

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>Coverage</h2>
          <p className="muted">At-risk shifts and active coverage workflows.</p>
        </div>
      </div>
      <CoveragePanel
        shifts={coverage?.at_risk_shifts ?? []}
        locationId={locationId}
        highlightShiftId={highlightShiftId}
      />
      <div style={{ marginTop: 24 }}>
        <AiPromptPanel locationId={locationId} activeTab="coverage" />
      </div>
    </section>
  );
}

async function ManagerActionsTabContent({ locationId, weekStart }: { locationId: number; weekStart?: string }) {
  const actions = await getManagerActions(locationId, weekStart);

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>Manager actions</h2>
          <p className="muted">Pending approvals for coverage fills and agency escalations.</p>
        </div>
      </div>
      <ManagerActionsPanel data={actions ?? emptyManagerActions(locationId)} />
    </section>
  );
}

async function ExceptionsTabContent({ locationId }: { locationId: number }) {
  const data = await getScheduleExceptions(locationId);
  const empty: ScheduleExceptionQueueResponse = {
    location_id: locationId,
    summary: { total: 0, action_required: 0, critical: 0 },
    exceptions: [],
  };

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>Schedule exceptions</h2>
          <p className="muted">Open shifts, coverage alerts, attendance issues, and other exceptions across all schedules.</p>
        </div>
      </div>
      <ExceptionsFeed data={data ?? empty} />
    </section>
  );
}

async function SettingsTabContent({ locationId }: { locationId: number }) {
  const settings = await getLocationSettings(locationId);

  if (!settings) {
    return (
      <section className="section">
        <div className="section-head">
          <div>
            <h2>Location settings</h2>
            <p className="muted">Coverage and attendance policies for this location.</p>
          </div>
        </div>
        <div className="empty">
          <strong>Settings unavailable</strong>
          <div>Could not load location settings. Try refreshing.</div>
        </div>
      </section>
    );
  }

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>Location settings</h2>
          <p className="muted">Coverage and attendance policies for this location.</p>
        </div>
      </div>
      <LocationSettingsPanel settings={settings} />
      {settings.backfill_shifts_enabled && (
        <div style={{ marginTop: 24 }}>
          <PilotMetricsPanel locationId={locationId} />
        </div>
      )}
    </section>
  );
}
