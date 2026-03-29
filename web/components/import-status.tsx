import type { ImportJob, ImportRowResult } from "@/lib/types";
import { EmptyState } from "./empty-state";
import { ImportRowActions, ExportErrorsCsvButton } from "./import-row-actions";
import { ImportRowScroller } from "./import-row-scroller";

type ImportStatusProps = {
  job: ImportJob | null;
  rows: ImportRowResult[];
  highlightRow?: number;
};

function outcomePillClass(outcome: string): string {
  const map: Record<string, string> = {
    success: "pill pill-success",
    warning: "pill pill-warning",
    failed: "pill pill-failed",
    skipped: "pill",
  };
  return map[outcome] ?? "pill";
}

function badgeClass(outcome: string): string {
  const map: Record<string, string> = {
    warning: "row-issue-badge row-issue-badge-warning",
    failed: "row-issue-badge row-issue-badge-failed",
  };
  return map[outcome] ?? "row-issue-badge";
}

export function ImportStatus({ job, rows, highlightRow }: ImportStatusProps) {
  if (!job) {
    return (
      <EmptyState
        title="No import in progress"
        body="Upload a CSV to import roster and shift data for this location."
      />
    );
  }

  const actionRows = rows.filter(
    (r) => r.outcome === "warning" || r.outcome === "failed"
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Summary bar */}
      <div className="summary-bar">
        <div className="summary-bar-item">
          <strong>{job.summary.total_rows}</strong>
          <span>Total rows</span>
        </div>
        <div className="summary-bar-item">
          <strong>{job.summary.success_rows}</strong>
          <span>Success</span>
        </div>
        <div className="summary-bar-item">
          <strong>{job.summary.warning_rows}</strong>
          <span>Warnings</span>
        </div>
        <div className="summary-bar-item">
          <strong>{job.summary.failed_rows}</strong>
          <span>Failed</span>
        </div>
        <div className="summary-bar-item">
          <span className={outcomePillClass(job.status)}>{job.status}</span>
        </div>
        {(job.summary.warning_rows > 0 || job.summary.failed_rows > 0) && (
          <div className="summary-bar-item" style={{ borderRight: "none" }}>
            <ExportErrorsCsvButton jobId={job.id} />
          </div>
        )}
      </div>

      {/* Action needed rows */}
      {actionRows.length > 0 ? (
        <div className="table-wrap">
          <div style={{ padding: "14px 16px 10px", fontSize: "0.82rem", fontWeight: 600, color: "var(--muted)" }}>
            Action needed ({actionRows.length})
          </div>
          {highlightRow && <ImportRowScroller targetId={`import-row-${highlightRow}`} />}
          {actionRows.map((row) => (
            <div
              key={row.id}
              id={`import-row-${row.row_number}`}
              className="row-issue"
              style={row.row_number === highlightRow ? {
                background: "rgba(22, 66, 60, 0.02)",
                boxShadow: "inset 3px 0 0 var(--brand)",
              } : undefined}
            >
              <div className={badgeClass(row.outcome)}>R{row.row_number}</div>
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>
                  {row.error_message ?? "Unknown issue"}
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--muted)", marginTop: 3 }}>
                  {row.entity_type} row
                  {row.error_code && (
                    <> &middot; <code style={{ fontSize: "0.72rem", padding: "1px 4px", background: "rgba(0,0,0,0.03)", borderRadius: 4 }}>{row.error_code}</code></>
                  )}
                  {row.raw_payload?.employee_name && (
                    <> &middot; {row.raw_payload.employee_name}</>
                  )}
                </div>
              </div>
              <ImportRowActions rowId={row.id} />
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          title="All rows passed"
          body="No warnings or errors found in this import."
        />
      )}
    </div>
  );
}
