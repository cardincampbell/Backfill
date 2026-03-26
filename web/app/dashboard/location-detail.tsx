import Link from "next/link";
import { revalidatePath } from "next/cache";
import { notFound, redirect } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { StatCard } from "@/components/stat-card";
import { getLocationStatus } from "@/lib/api";
import { sendOnboardingLink, updateLocation } from "@/lib/server-api";

export const dynamic = "force-dynamic";

type LocationDetailPageProps = {
  params: Promise<{ locationId: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

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

function setupPathForPlatform(platform?: string | null): string {
  if (platform && platform !== "backfill_native") {
    return `/setup/connect?platform=${encodeURIComponent(platform)}`;
  }
  return "/setup/upload";
}

function detailPath(locationId: number, query?: string): string {
  return query
    ? `/dashboard/locations/${locationId}?${query}`
    : `/dashboard/locations/${locationId}`;
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
        redirect(detailPath(locationId, "action=error&detail=Missing+primary+contact+phone+number"));
      }

      const result = await sendOnboardingLink({ phone, kind, platform });
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

  const action = typeof query.action === "string" ? query.action : "";
  const detail = typeof query.detail === "string" ? decodeURIComponent(query.detail) : "";
  const setupKind = setupKindForPlatform(status.location.scheduling_platform);
  const setupPath = setupPathForPlatform(status.location.scheduling_platform);
  const modeLabel = describeMode(status.integration.mode);
  const writebackEnabled = Boolean(status.integration.writeback_enabled);
  const writebackSupported = Boolean(status.integration.writeback_supported);

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
        <section className="section">
          <div className="callout success-callout">
            <h3>Action completed</h3>
            <p>{detail || "The location action completed successfully."}</p>
          </div>
        </section>
      ) : null}

      {action === "error" ? (
        <section className="section">
          <div className="callout error-callout">
            <h3>Action failed</h3>
            <p>{detail || "The location action did not complete."}</p>
          </div>
        </section>
      ) : null}

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
              <span className="muted">Customer-facing sync is automatic. Native stays authoritative for fills.</span>
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
            <p className="muted">Location-scoped coverage state instead of dashboard-wide row hunting.</p>
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
        <div className="two-up">
          <div className="panel">
            <h3>Roster preview</h3>
            {status.worker_preview.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Roles</th>
                    <th>Source</th>
                    <th>Consent</th>
                  </tr>
                </thead>
                <tbody>
                  {status.worker_preview.map((worker) => (
                    <tr key={worker.id}>
                      <td>{worker.name}</td>
                      <td>{worker.roles.join(", ") || "Unspecified"}</td>
                      <td>{worker.source ?? "manual"}</td>
                      <td>
                        <div className="table-meta">
                          <div>SMS: {worker.sms_consent_status}</div>
                          <div>Voice: {worker.voice_consent_status}</div>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="No workers yet" body="Use setup or sync actions to add the first roster entries." />
            )}
          </div>

          <div className="panel">
            <h3>Recent sync queue</h3>
            {status.recent_sync_jobs.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Status</th>
                    <th>Attempts</th>
                    <th>Next run</th>
                  </tr>
                </thead>
                <tbody>
                  {status.recent_sync_jobs.map((job) => (
                    <tr key={job.id}>
                      <td>
                        {job.job_type}
                        <div className="table-meta">
                          <div>{job.platform}</div>
                          {job.last_error ? <div>Error: {job.last_error}</div> : null}
                        </div>
                      </td>
                      <td><span className="pill">{job.status}</span></td>
                      <td>{job.attempt_count} / {job.max_attempts}</td>
                      <td>{job.status === "completed" ? (job.completed_at ?? "-") : job.next_run_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="No sync jobs yet" body="Webhook-triggered and scheduled reconcile jobs will appear here automatically." />
            )}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Recent audit</h2>
            <p className="muted">Location-level audit and outcome events.</p>
          </div>
        </div>
        {status.recent_audit.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Action</th>
                  <th>Actor</th>
                </tr>
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
          </div>
        ) : (
          <EmptyState title="No location audit yet" body="Location-level audit events will appear here as setup and coverage actions happen." />
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Recent shifts</h2>
            <p className="muted">Latest scheduled, vacant, and filled shifts for this location.</p>
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
          <EmptyState title="No shifts yet" body="Shifts for this location will appear here once they are created or synced." />
        )}
      </section>

      <section className="section">
        <Link className="text-link" href="/dashboard">
          Back to dashboard
        </Link>
      </section>
    </main>
  );
}
