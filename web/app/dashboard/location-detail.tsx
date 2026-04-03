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

  return (
    <main className="section">
      <div className="workspace-shell-head">
        <div className="workspace-shell-head-copy">
          <span className="workspace-shell-brand">{location.business_name}</span>
          <h1>{location.location_name}</h1>
          {locationMeta(location) ? <p>{locationMeta(location)}</p> : null}
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
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
      </div>

      {activeTab === "schedule" ? <ScheduleBoard board={board} /> : null}
      {activeTab === "schedule" ? (
        <ShiftManagerPanel
          businessId={location.business_id}
          locationId={location.location_id}
          timezone={board.timezone}
          weekStartDate={board.week_start_date}
          roles={board.roles}
          shifts={board.shifts}
        />
      ) : null}

      {activeTab === "coverage" ? (
        <CoverageControlPanel
          businessId={location.business_id}
          description="Launch or advance coverage directly from the live queue."
          emptyBody="There are no open or actively filling shifts for this location right now."
          emptyTitle="No active coverage"
          shifts={coverageItems}
          title="Coverage queue"
        />
      ) : null}

      {activeTab === "actions" ? (
        <CoverageControlPanel
          businessId={location.business_id}
          description="Use this queue for the shifts that still need a manager decision or coverage push."
          emptyBody="Manager approvals and action-required shifts will appear here."
          emptyTitle="Nothing needs your attention"
          shifts={actionItems}
          title="Manager actions"
        />
      ) : null}

      {activeTab === "roster" ? (
        <RosterManagerPanel
          businessId={location.business_id}
          canManageTeam={canManageTeam}
          locationId={location.location_id}
          roles={board.roles}
          workers={board.workers}
        />
      ) : null}

      {activeTab === "settings" ? (
        settings ? (
          <LocationSettingsPanel
            businessId={location.business_id}
            locationId={location.location_id}
            settings={settings}
          />
        ) : (
          <section className="settings-card">
            <div className="settings-card-body">
              <EmptyState
                title="Settings unavailable"
                body="Location settings could not be loaded for this workspace."
              />
            </div>
          </section>
        )
      ) : null}

    </main>
  );
}
