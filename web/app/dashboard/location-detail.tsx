import Link from "next/link";
import { revalidatePath } from "next/cache";
import { notFound, redirect } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { ScheduleGrid } from "@/components/schedule-grid";
import { ImportStatus } from "@/components/import-status";
import { ImportFlow } from "@/components/import-flow";
import { CoveragePanel } from "@/components/coverage-panel";
import { RosterPanel } from "@/components/roster-panel";
import { ManagerActionsPanel } from "@/components/manager-actions-panel";
import { LocationSettingsPanel } from "@/components/location-settings-panel";
import { PilotMetricsPanel } from "@/components/pilot-metrics-panel";
import AiPromptPanel from "@/components/ai-prompt-panel";
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
  getScheduleTemplates,
} from "@/lib/shifts-api";
import type {
  LocationStatusResponse,
  ManagerActionsResponse,
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

function legacyDetailPath(locationId: number, query?: string): string {
  return query
    ? `/dashboard/locations/${locationId}?${query}`
    : `/dashboard/locations/${locationId}`;
}

function scheduleLifecyclePillClass(lifecycleState?: string | null): string {
  if (lifecycleState === "published") return "pill pill-published";
  if (lifecycleState === "amended") return "pill pill-amended";
  if (lifecycleState === "recalled") return "pill pill-recalled";
  if (lifecycleState === "draft") return "pill pill-draft";
  return "pill";
}

function emptyManagerActions(locationId: number): ManagerActionsResponse {
  return {
    location_id: locationId,
    summary: { total: 0, approve_fill: 0, approve_agency: 0, attendance_reviews: 0 },
    actions: [],
  };
}

function formatWeekRange(weekStartDate: string): string {
  const start = new Date(`${weekStartDate}T00:00:00`);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);

  const sameMonth = start.getMonth() === end.getMonth();
  const sameYear = start.getFullYear() === end.getFullYear();
  const startLabel = start.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  const endLabel = end.toLocaleDateString("en-US", {
    month: sameMonth ? undefined : "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
  });
  return `${startLabel} - ${endLabel}`;
}

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

  const requestedTab = queryValue(query.tab) ?? "schedule";
  const activeTab =
    requestedTab === "exceptions" || requestedTab === "overview"
      ? "schedule"
      : requestedTab === "imports"
        ? "roster"
        : requestedTab;
  const action = queryValue(query.action) ?? "";
  const detail = queryValue(query.detail) ? decodeURIComponent(queryValue(query.detail) ?? "") : "";
  const weekStart = queryValue(query.week_start);
  const jobIdParam = queryValue(query.job_id) ? Number(queryValue(query.job_id)) : undefined;
  const rowParam = queryValue(query.row) ? Number(queryValue(query.row)) : undefined;
  const shiftIdParam = queryValue(query.shift_id) ? Number(queryValue(query.shift_id)) : undefined;
  const organizationName = status.location.organization_name?.trim();
  const brandName = status.location.place_brand_name?.trim() ?? organizationName;
  const locationName = status.location.name.trim();
  const placeLocationLabel = status.location.place_location_label?.trim();
  const locationTitle =
    placeLocationLabel &&
    (!brandName || placeLocationLabel.toLowerCase() !== brandName.toLowerCase())
      ? placeLocationLabel
      : locationName;
  const showOrganizationName =
    Boolean(brandName) &&
    brandName!.toLowerCase() !== locationTitle.toLowerCase();
  const locationMeta = [status.location.place_formatted_address ?? status.location.address]
    .filter((value): value is string => Boolean(value))
    .join(" · ");

  return (
    <main className="section">
      <div className="workspace-shell-head">
        <div className="workspace-shell-head-copy">
          {showOrganizationName ? (
            <span className="workspace-shell-brand">{brandName}</span>
          ) : null}
          <h1>{locationTitle}</h1>
          {locationMeta ? <p>{locationMeta}</p> : null}
        </div>
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

      {activeTab === "schedule" && (
        <ScheduleTabContent
          locationId={locationId}
          weekStart={weekStart}
          basePath={basePath}
        />
      )}

      {activeTab === "roster" && (
        <RosterTabContent
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

      {activeTab === "settings" && (
        <SettingsTabContent locationId={locationId} />
      )}
    </main>
  );
}

async function ScheduleTabContent({
  locationId,
  weekStart,
  basePath,
}: {
  locationId: number;
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

  if (!schedule || !schedule.schedule) {
    return (
      <section className="section workspace-shell workspace-shell-manager">
        <div className="workspace-layout workspace-layout-manager">
          <div className="workspace-main workspace-main-manager">
            <div className="workspace-section">
              <div className="workspace-section-headline workspace-section-headline-board">
                <div>
                  <h3>{formatWeekRange(targetWeek)}</h3>
                  <p>No schedule yet for this week.</p>
                </div>
                <div className="workspace-top-actions">
                  <WeekNav locationId={locationId} weekStartDate={targetWeek} basePath={basePath} />
                  <Link className="button-secondary button-small" href={buildLocationHref(basePath, { tab: "roster" })}>
                    Import CSV
                  </Link>
                </div>
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
            <div className="workspace-section workspace-section-sticky workspace-section-rail workspace-section-rail-ai">
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
  return (
    <section className="section workspace-shell workspace-shell-manager">
      <div className="workspace-layout workspace-layout-manager">
        <div className="workspace-main workspace-main-manager">
          <div className="workspace-section workspace-section-schedule">
            <div className="workspace-section-headline workspace-section-headline-wide workspace-section-headline-board">
              <div>
                <h3>{formatWeekRange(schedule.schedule.week_start_date)}</h3>
                <p>{workers.length} scheduled team members across the visible role lanes.</p>
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
                <ScheduleActions
                  scheduleId={schedule.schedule.id}
                  locationId={locationId}
                  lifecycleState={schedule.schedule.lifecycle_state}
                  weekStartDate={schedule.schedule.week_start_date}
                  basePath={basePath}
                />
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

          <div className="workspace-section workspace-section-rail workspace-section-rail-compact">
            <div className="workspace-section-headline">
              <div>
                <h3>Action needed</h3>
                <p>Coverage approvals and attendance decisions waiting for a manager.</p>
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

async function RosterTabContent({
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
  const [roster, allLocations, job, rowsResponse] = await Promise.all([
    getLocationRoster(locationId),
    getLocations(),
    jobId ? getImportJob(jobId) : Promise.resolve(null),
    jobId ? getImportRows(jobId) : Promise.resolve(null),
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
          <Link className="button-secondary button-small" href={buildLocationHref(basePath, { tab: "roster" })}>
            Import CSV
          </Link>
        </div>
      </div>
      <RosterPanel
        roster={roster ?? emptyRoster}
        locationId={locationId}
        locations={locationOptions}
      />
      <div style={{ marginTop: 24 }} className="workspace-section">
        <div className="workspace-section-headline">
          <div>
            <h3>Imports</h3>
            <p>Upload, map, validate, and commit roster or shift data for this location.</p>
          </div>
          {jobId ? (
            <div className="cta-row">
              <Link
                className="button button-small"
                href={buildLocationHref(basePath, { tab: "roster" })}
              >
                New import
              </Link>
            </div>
          ) : null}
        </div>
        {jobId && job ? (
          <ImportStatus job={job} rows={rowsResponse?.rows ?? []} highlightRow={highlightRow} />
        ) : (
          <ImportFlow locationId={locationId} basePath={basePath} />
        )}
      </div>
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
