import Link from "next/link";
import { notFound } from "next/navigation";

import { CoverageControlPanel } from "@/components/coverage-control-panel";
import { EmptyState } from "@/components/empty-state";
import { LocationSettingsPanel } from "@/components/location-settings-panel";
import { RosterManagerPanel } from "@/components/roster-manager-panel";
import { ShiftManagerPanel } from "@/components/shift-manager-panel";
import {
  getLocationBoard,
  getLocationSettings,
  type Workspace,
  type WorkspaceBoard,
  type WorkspaceLocation,
} from "@/lib/api/workspace";

type LocationDetailQuery = Record<string, string | string[] | undefined>;

type RenderLocationDetailPageArgs = {
  workspace: Workspace;
  location: WorkspaceLocation;
  query?: LocationDetailQuery;
  basePath: string;
};

type BoardDay = {
  key: string;
  label: string;
  number: string;
};

type ShiftCardEntry = WorkspaceBoard["shifts"][number];

function queryValue(value: string | string[] | undefined): string | undefined {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value[0] ?? undefined;
  return undefined;
}

function buildLocationHref(
  basePath: string,
  params?: Record<string, string | number | undefined | null>,
): string {
  if (!params) return basePath;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value == null || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${basePath}?${query}` : basePath;
}

function weekShift(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function locationMeta(location: WorkspaceLocation): string {
  return [
    location.address_line_1,
    location.locality,
    location.region,
    location.postal_code,
  ]
    .filter((value): value is string => Boolean(value))
    .join(", ");
}

function formatTimeRange(start: string, end: string): string {
  const startDate = new Date(start);
  const endDate = new Date(end);
  return `${startDate.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  })} - ${endDate.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  })}`;
}

function dayKey(value: string): string {
  return new Date(value).toISOString().slice(0, 10);
}

function buildBoardDays(weekStartDate: string): BoardDay[] {
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(`${weekStartDate}T00:00:00`);
    date.setDate(date.getDate() + index);
    return {
      key: date.toISOString().slice(0, 10),
      label: date.toLocaleDateString("en-US", { weekday: "short" }),
      number: date.toLocaleDateString("en-US", { day: "numeric" }),
    };
  });
}

function shiftTone(shift: ShiftCardEntry): string {
  if (shift.manager_action_required) return "warning";
  if (
    shift.pending_offer_count > 0 ||
    shift.delivered_offer_count > 0 ||
    shift.standby_depth > 0
  ) {
    return "coverage";
  }
  if (shift.current_assignment) return "assigned";
  return "open";
}

function renderShiftCard(
  shift: ShiftCardEntry,
  mode: "open" | "assignment" = "open",
) {
  return (
    <div
      key={`${shift.shift_id}-${mode}`}
      className="board-shift-card"
      data-tone={shiftTone(shift)}
    >
      <strong>{formatTimeRange(shift.starts_at, shift.ends_at)}</strong>
      <span>{shift.role_name}</span>
      {mode === "assignment" && shift.current_assignment?.employee_name ? (
        <span>{shift.current_assignment.employee_name}</span>
      ) : null}
      <small>
        {shift.manager_action_required
          ? "Needs manager review"
          : shift.pending_offer_count > 0
            ? `${shift.pending_offer_count} pending`
            : shift.delivered_offer_count > 0
              ? `${shift.delivered_offer_count} delivered`
              : shift.standby_depth > 0
                ? `${shift.standby_depth} standby`
              : shift.status}
      </small>
    </div>
  );
}

function buildRoleSections(board: WorkspaceBoard) {
  return board.roles.map((role) => {
    const roleShifts = board.shifts.filter((shift) => shift.role_id === role.role_id);
    const workers = board.workers.filter((worker) => worker.role_ids.includes(role.role_id));

    const openByDay = new Map<string, ShiftCardEntry[]>();
    const assignmentsByWorker = new Map<string, Map<string, ShiftCardEntry[]>>();

    for (const shift of roleShifts) {
      const key = dayKey(shift.starts_at);
      const isOpen = !shift.current_assignment || shift.seats_filled < shift.seats_requested;
      if (isOpen) {
        const existing = openByDay.get(key) ?? [];
        existing.push(shift);
        openByDay.set(key, existing);
      }
      if (shift.current_assignment?.employee_id) {
        const workerMap =
          assignmentsByWorker.get(shift.current_assignment.employee_id) ?? new Map<string, ShiftCardEntry[]>();
        const existing = workerMap.get(key) ?? [];
        existing.push(shift);
        workerMap.set(key, existing);
        assignmentsByWorker.set(shift.current_assignment.employee_id, workerMap);
      }
    }

    return { role, workers, openByDay, assignmentsByWorker };
  });
}

function ScheduleBoard({ board }: { board: WorkspaceBoard }) {
  const days = buildBoardDays(board.week_start_date);
  const sections = buildRoleSections(board);

  return (
    <section className="board-shell">
      <div className="board-summary">
        <div className="board-summary-item">
          <span>Action needed</span>
          <strong>{board.action_summary.total}</strong>
        </div>
        <div className="board-summary-item">
          <span>Approval</span>
          <strong>{board.action_summary.approval_required}</strong>
        </div>
        <div className="board-summary-item">
          <span>Active coverage</span>
          <strong>{board.action_summary.active_coverage}</strong>
        </div>
        <div className="board-summary-item">
          <span>Open shifts</span>
          <strong>{board.action_summary.open_shifts}</strong>
        </div>
      </div>

      <div className="board-toolbar">
        <div>
          <strong>Week of {board.week_start_date}</strong>
          <div className="muted">{board.timezone}</div>
        </div>
      </div>

      <div className="board-scroll">
        <div className="board-grid">
          <div className="board-head board-sticky">Team / role</div>
          {days.map((day) => (
            <div key={day.key} className="board-head">
              <strong>{day.label}</strong>
              <span>{day.number}</span>
            </div>
          ))}

          {sections.map((section) => (
            <div key={section.role.role_id} className="board-role-section">
              <div className="board-role-row">
                <div className="board-role-cell board-sticky">
                  <strong>{section.role.role_name}</strong>
                  <span>
                    {section.role.min_headcount ?? 0}
                    {section.role.max_headcount ? ` - ${section.role.max_headcount}` : "+"} target
                  </span>
                </div>
                <div className="board-role-fill" />
              </div>

              <div className="board-row">
                <div className="board-label board-sticky">
                  <strong>Open shifts</strong>
                  <span>{section.role.role_name}</span>
                </div>
                {days.map((day) => {
                  const shifts = section.openByDay.get(day.key) ?? [];
                  return (
                    <div key={`${section.role.role_id}-open-${day.key}`} className="board-cell">
                      {shifts.length ? shifts.map((shift) => renderShiftCard(shift)) : null}
                    </div>
                  );
                })}
              </div>

              {section.workers.map((worker) => {
                const assignments =
                  section.assignmentsByWorker.get(worker.employee_id) ?? new Map<string, ShiftCardEntry[]>();
                return (
                  <div key={`${section.role.role_id}-${worker.employee_id}`} className="board-row">
                    <div className="board-label board-sticky">
                      <strong>{worker.preferred_name || worker.full_name}</strong>
                      <span>
                        {worker.reliability_score.toFixed(1)} reliability
                        {worker.can_blast_here ? " · blast-ready" : ""}
                      </span>
                    </div>
                    {days.map((day) => {
                      const shifts = assignments.get(day.key) ?? [];
                      return (
                        <div key={`${worker.employee_id}-${day.key}`} className="board-cell">
                          {shifts.length ? shifts.map((shift) => renderShiftCard(shift, "assignment")) : null}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export async function renderLocationDetailPage({
  workspace,
  location,
  query = {},
  basePath,
}: RenderLocationDetailPageArgs) {
  const requestedTab = queryValue(query.tab) ?? "schedule";
  const activeTab = ["schedule", "coverage", "actions", "roster", "settings"].includes(requestedTab)
    ? requestedTab
    : "schedule";
  const weekStart = queryValue(query.week_start);
  const board = await getLocationBoard(
    location.business_id,
    location.location_id,
    weekStart ?? undefined,
  );

  if (!board) {
    notFound();
  }

  const settings =
    activeTab === "settings"
      ? await getLocationSettings(location.business_id, location.location_id)
      : null;

  const actionItems = board.shifts.filter(
    (shift) => shift.manager_action_required || shift.status !== "covered",
  );
  const coverageItems = board.shifts.filter(
    (shift) =>
      shift.status !== "covered" ||
      shift.pending_offer_count > 0 ||
      shift.delivered_offer_count > 0,
  );
  const canManageTeam = ["owner", "admin"].includes(location.membership_role);
  const totalShifts = board.shifts.length;
  const coveredShifts = board.shifts.filter(
    (shift) =>
      Boolean(shift.current_assignment) ||
      shift.seats_filled >= shift.seats_requested,
  ).length;
  const fillRate = totalShifts
    ? Math.round((coveredShifts / totalShifts) * 100)
    : 100;
  const standbyDepth = board.shifts.reduce(
    (sum, shift) => sum + shift.standby_depth,
    0,
  );
  const roleCoverage = board.roles
    .map((role) => {
      const shifts = board.shifts.filter((shift) => shift.role_id === role.role_id);
      if (!shifts.length) {
        return null;
      }
      const covered = shifts.filter(
        (shift) =>
          Boolean(shift.current_assignment) ||
          shift.seats_filled >= shift.seats_requested,
      ).length;
      const filling = shifts.some(
        (shift) =>
          shift.manager_action_required ||
          shift.pending_offer_count > 0 ||
          shift.delivered_offer_count > 0 ||
          shift.status !== "covered",
      );
      return {
        label: role.role_name,
        covered,
        total: shifts.length,
        status: covered === shifts.length ? "covered" : filling ? "filling" : "open",
      };
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
    .slice(0, 4);
  const upcomingShifts = [...board.shifts]
    .sort(
      (left, right) =>
        new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime(),
    )
    .slice(0, 5);
  const topWorkers = [...board.workers]
    .sort((left, right) => right.reliability_score - left.reliability_score)
    .slice(0, 4);
  const hotspotShifts = [...board.shifts]
    .filter(
      (shift) =>
        shift.manager_action_required ||
        shift.pending_offer_count > 0 ||
        shift.delivered_offer_count > 0 ||
        shift.standby_depth > 0 ||
        shift.status !== "covered",
    )
    .sort((left, right) => {
      const leftWeight =
        Number(left.manager_action_required) * 100 +
        left.pending_offer_count * 10 +
        left.standby_depth;
      const rightWeight =
        Number(right.manager_action_required) * 100 +
        right.pending_offer_count * 10 +
        right.standby_depth;
      return rightWeight - leftWeight;
    })
    .slice(0, 4);
  const tabHref = (tab: string) =>
    buildLocationHref(basePath, {
      tab,
      week_start: weekStart ?? board.week_start_date,
    });
  const quickLinks = [
    { label: "Open coverage", href: tabHref("coverage") },
    { label: "Manage team", href: tabHref("roster") },
    { label: "Location settings", href: tabHref("settings") },
  ];
  const metricCards = [
    {
      label: "Fill rate",
      value: `${fillRate}%`,
      detail: `${coveredShifts} of ${totalShifts} shifts staffed`,
    },
    {
      label: "Open shifts",
      value: String(board.action_summary.open_shifts),
      detail: `${actionItems.length} need attention now`,
    },
    {
      label: "Active coverage",
      value: String(board.action_summary.active_coverage),
      detail: `${coverageItems.length} cases in motion`,
    },
    {
      label: "Standby depth",
      value: String(standbyDepth),
      detail: `${board.workers.length} workers on this board`,
    },
  ];
  const todayLabel = new Date().toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  return (
    <main className="section">
      <div className="dashboard-page-shell">
        <header className="dashboard-page-hero">
          <div className="dashboard-page-hero-main">
            <div className="dashboard-page-mark" aria-hidden="true">
              {location.location_name.slice(0, 1).toUpperCase()}
            </div>
            <div className="dashboard-page-copy">
              <span className="dashboard-page-kicker">{location.business_name}</span>
              <h1>{location.location_name}</h1>
              <p>
                {locationMeta(location) || "Live operating view for this location."}
              </p>
            </div>
          </div>

          <div className="dashboard-page-actions">
            <Link
              className="button-secondary button-small"
              href={buildLocationHref(basePath, {
                tab: activeTab,
                week_start: weekShift(board.week_start_date, -7),
              })}
            >
              Previous week
            </Link>
            <Link
              className="button-secondary button-small"
              href={buildLocationHref(basePath, {
                tab: activeTab,
                week_start: weekShift(board.week_start_date, 7),
              })}
            >
              Next week
            </Link>
          </div>
        </header>

        <section className="dashboard-scenario-grid">
          <article className="dashboard-scenario-card dashboard-scenario-card-coverage">
            <div className="dashboard-scenario-card-head">
              <div>
                <span className="dashboard-surface-kicker">Today</span>
                <h3>Coverage snapshot</h3>
              </div>
              <span className="dashboard-surface-meta">{todayLabel}</span>
            </div>

            {roleCoverage.length ? (
              <div className="dashboard-scenario-list">
                {roleCoverage.map((item) => (
                  <div className="dashboard-scenario-list-row" key={item.label}>
                    <div className="dashboard-scenario-list-copy">
                      <strong>{item.label}</strong>
                      <span>
                        {item.covered}/{item.total} shifts covered
                      </span>
                    </div>
                    <span
                      className="dashboard-scenario-status"
                      data-tone={item.status}
                    >
                      {item.status === "covered"
                        ? "Covered"
                        : item.status === "filling"
                          ? "Filling"
                          : "Open"}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="dashboard-empty-note">
                Role coverage will appear once shifts are on the board.
              </div>
            )}

            <div className="dashboard-scenario-foot">
              <div className="dashboard-scenario-progress">
                <strong>{fillRate}%</strong>
                <span>{coveredShifts} of {totalShifts} shifts covered</span>
              </div>
              <div className="dashboard-scenario-progress-bar">
                <div style={{ width: `${fillRate}%` }} />
              </div>
            </div>
          </article>

          <div className="dashboard-scenario-stat-grid">
            {metricCards.map((metric) => (
              <article className="dashboard-mini-stat" key={metric.label}>
                <span className="dashboard-mini-stat-label">{metric.label}</span>
                <strong>{metric.value}</strong>
                <span className="dashboard-mini-stat-detail">{metric.detail}</span>
              </article>
            ))}
          </div>

          <article className="dashboard-scenario-card dashboard-scenario-card-staff">
            <div className="dashboard-scenario-card-head">
              <div>
                <span className="dashboard-surface-kicker">Reliability</span>
                <h3>Top staff</h3>
              </div>
            </div>

            {topWorkers.length ? (
              <div className="dashboard-scenario-list">
                {topWorkers.map((worker) => (
                  <div className="dashboard-scenario-list-row" key={worker.employee_id}>
                    <div className="dashboard-scenario-list-copy">
                      <strong>{worker.preferred_name || worker.full_name}</strong>
                      <span>{worker.role_names.join(" · ")}</span>
                    </div>
                    <span className="dashboard-scenario-score">
                      {worker.reliability_score.toFixed(1)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="dashboard-empty-note">
                Team reliability will show up once workers are enrolled.
              </div>
            )}
          </article>
        </section>

        <nav className="dashboard-tabbar" aria-label="Location dashboard views">
          {[
            ["schedule", "Schedule"],
            ["coverage", "Coverage"],
            ["actions", "Actions"],
            ["roster", "Team"],
            ["settings", "Settings"],
          ].map(([key, label]) => (
            <Link
              key={key}
              className="dashboard-tablink"
              data-active={activeTab === key}
              href={tabHref(key)}
            >
              {label}
            </Link>
          ))}
        </nav>

        <div className="dashboard-layout-grid">
          <div className="dashboard-primary-stack">
            {activeTab === "schedule" ? (
              <>
                <section className="dashboard-surface">
                  <div className="dashboard-surface-head">
                    <div>
                      <span className="dashboard-surface-kicker">Board</span>
                      <h3>Live schedule</h3>
                    </div>
                    <span className="dashboard-surface-meta">
                      Week of {board.week_start_date}
                    </span>
                  </div>
                  <ScheduleBoard board={board} />
                </section>

                <section className="dashboard-surface dashboard-surface-panel">
                  <div className="dashboard-surface-head">
                    <div>
                      <span className="dashboard-surface-kicker">Execution</span>
                      <h3>Shift manager</h3>
                    </div>
                    <span className="dashboard-surface-meta">
                      Create, edit, and review live shifts
                    </span>
                  </div>
                  <ShiftManagerPanel
                    businessId={location.business_id}
                    locationId={location.location_id}
                    timezone={board.timezone}
                    weekStartDate={board.week_start_date}
                    roles={board.roles}
                    shifts={board.shifts}
                  />
                </section>
              </>
            ) : null}

            {activeTab === "coverage" ? (
              <section className="dashboard-surface dashboard-surface-panel">
                <div className="dashboard-surface-head">
                  <div>
                    <span className="dashboard-surface-kicker">Queue</span>
                    <h3>Coverage queue</h3>
                  </div>
                  <span className="dashboard-surface-meta">
                    Launch or advance coverage directly from the live queue.
                  </span>
                </div>
                <CoverageControlPanel
                  businessId={location.business_id}
                  description="Launch or advance coverage directly from the live queue."
                  emptyBody="There are no open or actively filling shifts for this location right now."
                  emptyTitle="No active coverage"
                  shifts={coverageItems}
                  title="Coverage queue"
                />
              </section>
            ) : null}

            {activeTab === "actions" ? (
              <section className="dashboard-surface dashboard-surface-panel">
                <div className="dashboard-surface-head">
                  <div>
                    <span className="dashboard-surface-kicker">Attention</span>
                    <h3>Manager actions</h3>
                  </div>
                  <span className="dashboard-surface-meta">
                    Resolve approvals and push the next action from one place.
                  </span>
                </div>
                <CoverageControlPanel
                  businessId={location.business_id}
                  description="Use this queue for the shifts that still need a manager decision or coverage push."
                  emptyBody="Manager approvals and action-required shifts will appear here."
                  emptyTitle="Nothing needs your attention"
                  shifts={actionItems}
                  title="Manager actions"
                />
              </section>
            ) : null}

            {activeTab === "roster" ? (
              <section className="dashboard-surface dashboard-surface-panel">
                <div className="dashboard-surface-head">
                  <div>
                    <span className="dashboard-surface-kicker">Team</span>
                    <h3>Roster manager</h3>
                  </div>
                  <span className="dashboard-surface-meta">
                    Staff, enrollments, roles, and reliability by location.
                  </span>
                </div>
                <RosterManagerPanel
                  businessId={location.business_id}
                  canManageTeam={canManageTeam}
                  locationId={location.location_id}
                  roles={board.roles}
                  workers={board.workers}
                />
              </section>
            ) : null}

            {activeTab === "settings" ? (
              settings ? (
                <section className="dashboard-surface dashboard-surface-panel">
                  <div className="dashboard-surface-head">
                    <div>
                      <span className="dashboard-surface-kicker">Configuration</span>
                      <h3>Location settings</h3>
                    </div>
                    <span className="dashboard-surface-meta">
                      Coverage policies, integrations, and Backfill Shifts.
                    </span>
                  </div>
                  <LocationSettingsPanel
                    businessId={location.business_id}
                    locationId={location.location_id}
                    settings={settings}
                  />
                </section>
              ) : (
                <section className="dashboard-surface dashboard-surface-panel">
                  <div className="settings-card">
                    <div className="settings-card-body">
                      <EmptyState
                        title="Settings unavailable"
                        body="Location settings could not be loaded for this workspace."
                      />
                    </div>
                  </div>
                </section>
              )
            ) : null}
          </div>

          <aside className="dashboard-side-stack">
            <section className="dashboard-surface">
              <div className="dashboard-surface-head">
                <div>
                  <span className="dashboard-surface-kicker">Hotspots</span>
                  <h3>Shifts to watch</h3>
                </div>
              </div>
              {hotspotShifts.length ? (
                <div className="dashboard-list">
                  {hotspotShifts.map((shift) => (
                    <div className="dashboard-list-item" key={shift.shift_id}>
                      <div>
                        <strong>{shift.role_name}</strong>
                        <span>
                          {formatTimeRange(shift.starts_at, shift.ends_at)}
                        </span>
                      </div>
                      <span className="dashboard-list-pill">
                        {shift.manager_action_required
                          ? "Needs review"
                          : shift.pending_offer_count > 0
                            ? `${shift.pending_offer_count} pending`
                            : shift.standby_depth > 0
                              ? `${shift.standby_depth} standby`
                              : shift.status}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="dashboard-empty-note">
                  No active hotspots right now.
                </div>
              )}
            </section>

            <section className="dashboard-surface">
              <div className="dashboard-surface-head">
                <div>
                  <span className="dashboard-surface-kicker">Upcoming</span>
                  <h3>Next shifts</h3>
                </div>
              </div>
              {upcomingShifts.length ? (
                <div className="dashboard-upcoming-list">
                  {upcomingShifts.map((shift) => (
                    <div className="dashboard-upcoming-item" key={shift.shift_id}>
                      <div>
                        <strong>{shift.role_name}</strong>
                        <span>{formatTimeRange(shift.starts_at, shift.ends_at)}</span>
                      </div>
                      {shift.current_assignment?.employee_name ? (
                        <span className="dashboard-upcoming-assignee">
                          {shift.current_assignment.employee_name}
                        </span>
                      ) : (
                        <span
                          className="dashboard-scenario-status"
                          data-tone={
                            shift.pending_offer_count > 0 || shift.delivered_offer_count > 0
                              ? "filling"
                              : "open"
                          }
                        >
                          {shift.pending_offer_count > 0 || shift.delivered_offer_count > 0
                            ? "Filling"
                            : "Open"}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="dashboard-empty-note">
                  Upcoming shifts will appear here once the board is populated.
                </div>
              )}
            </section>

            <section className="dashboard-surface">
              <div className="dashboard-surface-head">
                <div>
                  <span className="dashboard-surface-kicker">Quick links</span>
                  <h3>Jump to</h3>
                </div>
              </div>
              <div className="dashboard-action-grid">
                {quickLinks.map((link) => (
                  <Link
                    className="dashboard-action-card"
                    href={link.href}
                    key={link.label}
                  >
                    <strong>{link.label}</strong>
                    <span>Open this view</span>
                  </Link>
                ))}
              </div>
            </section>
          </aside>
        </div>
      </div>
    </main>
  );
}
