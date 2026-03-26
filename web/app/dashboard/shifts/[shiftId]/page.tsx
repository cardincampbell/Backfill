import Link from "next/link";
import { notFound } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { getShiftStatus, getWorkers } from "@/lib/api";

export const dynamic = "force-dynamic";

type ShiftDetailPageProps = {
  params: Promise<{ shiftId: string }>;
};

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

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Shift Detail</span>
        <h1>{status.shift.role} on {status.shift.date}</h1>
        <p>
          {status.location?.name ?? "Unknown location"} · {status.shift.start_time} to {status.shift.end_time}
        </p>
      </div>

      <section className="section">
        <div className="two-up">
          <div className="callout">
            <h3>Coverage state</h3>
            <p>Status: <strong>{status.shift.status}</strong></p>
            <p>Mode: <strong>{status.cascade?.outreach_mode ?? "n/a"}</strong></p>
            <p>Tier: <strong>{status.cascade?.current_tier ?? "n/a"}</strong></p>
          </div>
          <div className="callout">
            <h3>Confirmed worker</h3>
            <p>
              {status.filled_worker
                ? `${status.filled_worker.name} (${status.shift.fill_tier ?? "unclassified"})`
                : "Nobody confirmed yet"}
            </p>
            <p>
              <Link className="text-link" href="/dashboard">Back to dashboard</Link>
            </p>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Standby queue</h2>
            <p className="muted">Ordered backups for this shift if the confirmed worker drops out.</p>
          </div>
        </div>
        {standbyNames.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Position</th>
                  <th>Worker</th>
                </tr>
              </thead>
              <tbody>
                {standbyNames.map((name, index) => (
                  <tr key={`${name}-${index}`}>
                    <td>#{index + 1}</td>
                    <td>{name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No standby workers" body="This shift does not currently have ranked backup workers." />
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Outreach attempts</h2>
            <p className="muted">All outreach rows currently attached to this shift.</p>
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
                  <th>Responded</th>
                </tr>
              </thead>
              <tbody>
                {status.outreach_attempts.map((attempt) => (
                  <tr key={attempt.id}>
                    <td>{workerNames.get(attempt.worker_id) ?? `Worker #${attempt.worker_id}`}</td>
                    <td>{attempt.channel}</td>
                    <td>{attempt.status}</td>
                    <td>{attempt.outcome ?? "pending"}</td>
                    <td>{attempt.standby_position ? `#${attempt.standby_position}` : "-"}</td>
                    <td>{attempt.sent_at ?? "-"}</td>
                    <td>{attempt.responded_at ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No outreach yet" body="This shift does not have any recorded outreach attempts." />
        )}
      </section>
    </main>
  );
}
