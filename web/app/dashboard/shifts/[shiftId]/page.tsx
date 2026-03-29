import Link from "next/link";
import { notFound } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { getShiftStatus, getWorkers } from "@/lib/api";

export const dynamic = "force-dynamic";

type ShiftDetailPageProps = {
  params: Promise<{ shiftId: string }>;
};

function formatTime(time: string): string {
  const [h, m] = time.split(":");
  const hour = parseInt(h, 10);
  const suffix = hour >= 12 ? "pm" : "am";
  const display = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
  return m === "00" ? `${display}${suffix}` : `${display}:${m}${suffix}`;
}

function formatDate(date: string): string {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

function statusColor(status: string): string {
  if (status === "filled" || status === "confirmed") return "pill pill-success";
  if (status === "vacant" || status === "open") return "pill pill-open";
  if (status === "active") return "pill pill-published";
  return "pill";
}

function outcomePill(outcome?: string | null): { label: string; className: string } {
  if (!outcome) return { label: "Pending", className: "pill" };
  if (outcome === "accepted" || outcome === "confirmed") return { label: outcome, className: "pill pill-success" };
  if (outcome === "declined" || outcome === "no_response") return { label: outcome.replace("_", " "), className: "pill pill-failed" };
  if (outcome === "standby") return { label: "Standby", className: "pill pill-warning" };
  return { label: outcome, className: "pill" };
}

function timeAgo(iso?: string | null): string {
  if (!iso) return "\u2014";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default async function ShiftDetailPage({ params }: ShiftDetailPageProps) {
  const { shiftId } = await params;
  const numericShiftId = Number(shiftId);

  if (!Number.isInteger(numericShiftId) || numericShiftId <= 0) {
    notFound();
  }

  const [status, workers] = await Promise.all([
    getShiftStatus(numericShiftId),
    getWorkers()
  ]);

  if (!status) {
    notFound();
  }

  const workerNames = new Map(workers.map((worker) => [worker.id, worker.name]));
  const standbyNames = (status.cascade?.standby_queue ?? []).map((workerId) => {
    return workerNames.get(workerId) ?? `Worker #${workerId}`;
  });

  const locationName = status.location?.name ?? "Unknown location";

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Shift Detail</span>
        <h1>{status.shift.role}</h1>
        <p>
          {formatDate(status.shift.date)} · {formatTime(status.shift.start_time)}\u2013{formatTime(status.shift.end_time)} · {locationName}
        </p>
      </div>

      {/* Key info cards */}
      <div className="shift-detail-grid">
        <div className="shift-detail-card">
          <div className="shift-detail-card-label">Status</div>
          <div className="shift-detail-card-value">
            <span className={statusColor(status.shift.status)}>{status.shift.status}</span>
          </div>
        </div>
        <div className="shift-detail-card">
          <div className="shift-detail-card-label">Confirmed worker</div>
          <div className="shift-detail-card-value">
            {status.filled_worker ? (
              <span style={{ fontWeight: 600 }}>{status.filled_worker.name}</span>
            ) : (
              <span style={{ color: "var(--muted)" }}>Nobody confirmed</span>
            )}
          </div>
          {status.shift.fill_tier && (
            <div className="shift-detail-card-hint">Fill tier: {status.shift.fill_tier}</div>
          )}
        </div>
        <div className="shift-detail-card">
          <div className="shift-detail-card-label">Outreach mode</div>
          <div className="shift-detail-card-value">{status.cascade?.outreach_mode ?? "\u2014"}</div>
        </div>
        <div className="shift-detail-card">
          <div className="shift-detail-card-label">Coverage tier</div>
          <div className="shift-detail-card-value">
            {status.cascade?.current_tier != null ? `Tier ${status.cascade.current_tier}` : "\u2014"}
          </div>
        </div>
      </div>

      {/* Standby queue */}
      <section className="section">
        <div className="section-head">
          <div>
            <h2>Standby queue</h2>
            <p className="muted">Ranked backup workers for this shift.</p>
          </div>
        </div>
        {standbyNames.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 80 }}>Position</th>
                  <th>Worker</th>
                </tr>
              </thead>
              <tbody>
                {standbyNames.map((name, index) => (
                  <tr key={`${name}-${index}`}>
                    <td>
                      <span className="pill" style={{ fontVariantNumeric: "tabular-nums" }}>#{index + 1}</span>
                    </td>
                    <td style={{ fontWeight: 500 }}>{name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No standby workers" body="This shift does not currently have ranked backup workers." />
        )}
      </section>

      {/* Outreach attempts */}
      <section className="section">
        <div className="section-head">
          <div>
            <h2>Outreach</h2>
            <p className="muted">All contact attempts for this shift.</p>
          </div>
        </div>
        {status.outreach_attempts.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Worker</th>
                  <th>Channel</th>
                  <th>Status</th>
                  <th>Outcome</th>
                  <th>Standby</th>
                  <th>Sent</th>
                  <th>Response</th>
                </tr>
              </thead>
              <tbody>
                {status.outreach_attempts.map((attempt) => {
                  const outcome = outcomePill(attempt.outcome);
                  return (
                    <tr key={attempt.id}>
                      <td style={{ fontWeight: 500 }}>
                        {workerNames.get(attempt.worker_id) ?? `Worker #${attempt.worker_id}`}
                      </td>
                      <td>
                        <span className="pill">{attempt.channel}</span>
                      </td>
                      <td>
                        <span className="pill">{attempt.status}</span>
                      </td>
                      <td>
                        <span className={outcome.className}>{outcome.label}</span>
                      </td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>
                        {attempt.standby_position ? `#${attempt.standby_position}` : "\u2014"}
                      </td>
                      <td style={{ color: "var(--muted)", fontSize: "0.82rem" }}>
                        {timeAgo(attempt.sent_at)}
                      </td>
                      <td style={{ color: "var(--muted)", fontSize: "0.82rem" }}>
                        {timeAgo(attempt.responded_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No outreach yet" body="Outreach attempts will appear here once coverage starts." />
        )}
      </section>

      <section style={{ padding: "12px 0 36px" }}>
        <Link className="text-link" href="/dashboard">
          Back to dashboard
        </Link>
      </section>
    </main>
  );
}
