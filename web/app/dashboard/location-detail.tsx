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
import { ExceptionsFeed } from "@/components/exceptions-feed";
import { AddEmployeeForm } from "@/components/add-employee-form";
import { ScheduleActions } from "@/components/schedule-actions";
import { ScheduleReviewPanel } from "@/components/schedule-review-panel";
import { DraftLauncher } from "@/components/draft-launcher";
import { TemplatePanel } from "@/components/template-panel";
import { WeekNav } from "@/components/week-nav";
import { getLocationStatus, getLocations } from "@/lib/api";
import { sendOnboardingLink, updateLocation } from "@/lib/server-api";
import { getWeeklySchedule, getImportJob, getImportRows, getCoverage, getLocationWorkers, getLocationRoster, getEligibleWorkers, getManagerActions, getLocationSettings, getScheduleExceptions, getScheduleTemplates } from "@/lib/shifts-api";

export const dynamic = "force-dynamic";

type LocationDetailPageProps = {
  params: Promise<{ locationId: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function currentMonday(): string {
  const today = new Date();
  const day = today.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const monday = new Date(today);
  monday.setDate(today.getDate() + diff);
  return monday.toISOString().slice(0, 10);
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

function detailPath(locationId: number, query?: string): string {
  return query
    ? `/dashboard/locations/${locationId}?${query}`
    : `/dashboard/locations/${locationId}`;
}

const LOCATION_TABS = [
  { key: "overview", label: "Overview" },
  { key: "schedule", label: "Schedule" },
  { key: "roster", label: "Roster" },
  { key: "imports", label: "Imports" },
  { key: "coverage", label: "Coverage" },
  { key: "actions", label: "Actions" },
  { key: "exceptions", label: "Exceptions" },
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
        redirect(detailPath(locationId, "action=error&detail=Missing+primary+contact+phone+number"));
      }

      const result = await sendOnboardingLink({ phone, kind, platform, location_id: locationId });
      revalidatePath(destination);
      redirect(
        detailPath(
          locationId,
          `action=link_ok&detail=${encodeURIComponent(`Sent ${result.path} to ${phone}.`)}`
        )
      );
    }

    if (action === "toggle_writeback") {
      const enabled = String(formData.get("enabled") ?? "").trim() === "true";
      await updateLocation(locationId, {
        writeback_enabled: enabled,
        writeback_subscription_tier: enabled ? "premium" : "core"
      });
      revalidatePath(destination);
      redirect(
        detailPath(
          locationId,
          `action=writeback_ok&detail=${encodeURIComponent(
            enabled
              ? "Paid write-back enabled for this location."
              : "Write-back disabled. Native remains the execution ledger."
          )}`
        )
      );
    }

    redirect(detailPath(locationId, "action=error&detail=Unsupported+location+action"));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Action failed";
    redirect(detailPath(locationId, `action=error&detail=${encodeURIComponent(message)}`));
  }
}

export default async function LocationDetailPage({
  params,
  searchParams
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

  const activeTab = typeof query.tab === "string" ? query.tab : "overview";
  const action = typeof query.action === "string" ? query.action : "";
  const detail = typeof query.detail === "string" ? decodeURIComponent(query.detail) : "";
  const weekStart = typeof query.week_start === "string" ? query.week_start : undefined;
  const jobIdParam = typeof query.job_id === "string" ? Number(query.job_id) : undefined;
  const rowParam = typeof query.row === "string" ? Number(query.row) : undefined;
  const shiftIdParam = typeof query.shift_id === "string" ? Number(query.shift_id) : undefined;
  const setupKind = setupKindForPlatform(status.location.scheduling_platform);
  const setupPath = setupPathForPlatform(numericLocationId, status.location.scheduling_platform);
  const modeLabel = describeMode(status.integration.mode);
  const writebackEnabled = Boolean(status.integration.writeback_enabled);
  const writebackSupported = Boolean(status.integration.writeback_supported);

  const basePath = `/dashboard/locations/${numericLocationId}`;

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Location Detail</span>
        <h1>{status.location.name}</h1>
        <p>
          {status.location.address ?? "No address on file"} · {status.location.vertical ?? "unspecified"} · {modeLabel} · {status.integration.platform}
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
          preserveParams={["week_start", "job_id", "shift_id"]}
        />
      </Suspense>

      {/* ── Overview tab ──────────────────────────────────────────────── */}
      {activeTab === "overview" && (
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
      )}

      {/* ── Schedule tab ──────────────────────────────────────────────── */}
      {activeTab === "schedule" && (
        <ScheduleTabContent locationId={numericLocationId} weekStart={weekStart} />
      )}

      {/* ── Roster tab ────────────────────────────────────────────────── */}
      {activeTab === "roster" && (
        <RosterTabContent locationId={numericLocationId} />
      )}

      {/* ── Imports tab ───────────────────────────────────────────────── */}
      {activeTab === "imports" && (
        <ImportsTabContent locationId={numericLocationId} jobId={jobIdParam} highlightRow={rowParam} />
      )}

      {/* ── Coverage tab ──────────────────────────────────────────────── */}
      {activeTab === "coverage" && (
        <CoverageTabContent locationId={numericLocationId} weekStart={weekStart} highlightShiftId={shiftIdParam} />
      )}

      {/* ── Actions tab ──────────────────────────────────────────────── */}
      {activeTab === "actions" && (
        <ManagerActionsTabContent locationId={numericLocationId} weekStart={weekStart} />
      )}

      {/* ── Exceptions tab ────────────────────────────────────────────── */}
      {activeTab === "exceptions" && (
        <ExceptionsTabContent locationId={numericLocationId} />
      )}

      {/* ── Settings tab ──────────────────────────────────────────────── */}
      {activeTab === "settings" && (
        <SettingsTabContent locationId={numericLocationId} />
      )}

      <section className="section">
        <Link className="text-link" href="/dashboard">
          Back to dashboard
        </Link>
      </section>
    </main>
  );
}

// ── Tab content loaders ────────────────────────────────────────────────────

async function ScheduleTabContent({ locationId, weekStart }: { locationId: number; weekStart?: string }) {
  const [schedule, eligibleResponse, templates] = await Promise.all([
    getWeeklySchedule(locationId, weekStart),
    getEligibleWorkers(locationId),
    getScheduleTemplates(locationId),
  ]);
  const workers = eligibleResponse?.workers ?? [];

  if (!schedule || !schedule.schedule) {
    return (
      <section className="section">
        <div className="section-head">
          <div>
            <h2>Weekly schedule</h2>
            <p className="muted">Draft, review, publish, and amend weekly schedules.</p>
          </div>
          <div className="cta-row">
            <WeekNav locationId={locationId} weekStartDate={weekStart ?? currentMonday()} />
            <Link className="button-secondary button-small" href={`/dashboard/locations/${locationId}?tab=imports`}>
              Import CSV
            </Link>
          </div>
        </div>
        <EmptyState
          title="No schedule found for this week"
          body="Import a roster and shifts CSV, copy last week, or create a draft from a template."
        />
        <div style={{ marginTop: 24 }}>
          <DraftLauncher locationId={locationId} weekStart={weekStart ?? currentMonday()} />
        </div>
        {(templates ?? []).length > 0 && (
          <div style={{ marginTop: 24 }}>
            <TemplatePanel
              locationId={locationId}
              templates={templates ?? []}
            />
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>
            Week of {schedule.schedule.week_start_date}
          </h2>
          <WeekNav locationId={locationId} weekStartDate={schedule.schedule.week_start_date} />
        </div>
        <div className="cta-row">
          <ScheduleActions
            scheduleId={schedule.schedule.id}
            locationId={locationId}
            lifecycleState={schedule.schedule.lifecycle_state}
            weekStartDate={schedule.schedule.week_start_date}
          />
          <Link className="button-secondary button-small" href={`/dashboard/locations/${locationId}?tab=imports`}>
            Import
          </Link>
        </div>
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
      <ScheduleReviewPanel scheduleId={schedule.schedule.id} />
      <div style={{ marginTop: 24 }}>
        <TemplatePanel
          locationId={locationId}
          scheduleId={schedule.schedule.id}
          currentWeekStart={schedule.schedule.week_start_date}
          templates={templates ?? []}
        />
      </div>
    </section>
  );
}

async function RosterTabContent({ locationId }: { locationId: number }) {
  const [roster, allLocations] = await Promise.all([
    getLocationRoster(locationId),
    getLocations(),
  ]);
  const locationOptions = allLocations.map((l) => ({ id: l.id, name: l.name }));
  const emptyRoster = { location_id: locationId, summary: { total_workers: 0, active_workers: 0, inactive_workers: 0, enrolled_workers: 0 }, workers: [] as never[] };
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
          <Link className="button-secondary button-small" href={`/dashboard/locations/${locationId}?tab=imports`}>
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

async function ImportsTabContent({ locationId, jobId, highlightRow }: { locationId: number; jobId?: number; highlightRow?: number }) {
  if (!jobId) {
    return (
      <section className="section">
        <div className="section-head">
          <div>
            <h2>Import pipeline</h2>
            <p className="muted">Upload, map, validate, and commit roster and shift data.</p>
          </div>
        </div>
        <ImportFlow locationId={locationId} />
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
            href={`/dashboard/locations/${locationId}?tab=imports`}
          >
            New import
          </Link>
        </div>
      </div>
      <ImportStatus job={job} rows={rowsResponse?.rows ?? []} highlightRow={highlightRow} />
    </section>
  );
}

async function CoverageTabContent({ locationId, weekStart, highlightShiftId }: { locationId: number; weekStart?: string; highlightShiftId?: number }) {
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
    </section>
  );
}

async function ManagerActionsTabContent({ locationId, weekStart }: { locationId: number; weekStart?: string }) {
  const actions = await getManagerActions(locationId, weekStart);
  const emptyActions: import("@/lib/types").ManagerActionsResponse = {
    location_id: locationId,
    summary: { total: 0, approve_fill: 0, approve_agency: 0 },
    actions: [],
  };

  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>Manager actions</h2>
          <p className="muted">Pending approvals for coverage fills and agency escalations.</p>
        </div>
      </div>
      <ManagerActionsPanel data={actions ?? emptyActions} />
    </section>
  );
}

async function ExceptionsTabContent({ locationId }: { locationId: number }) {
  const data = await getScheduleExceptions(locationId);
  const empty: import("@/lib/types").ScheduleExceptionQueueResponse = {
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
