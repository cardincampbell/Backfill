"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import {
  createImportJob,
  uploadImportFile,
  saveImportMapping,
  commitImport,
} from "@/lib/shifts-api";
import type {
  ImportJob,
  ImportUploadResponse,
  ImportMappingResponse,
  ImportCommitResponse,
} from "@/lib/types";
import { ImportMappingGrid } from "./import-mapping-grid";

type ImportFlowStep = "pick" | "uploading" | "mapping" | "validating" | "review" | "committing" | "done" | "error";

type ImportFlowProps = {
  locationId: number;
  basePath?: string;
};

function StepIndicator({ label }: { label: string }) {
  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "24px 0",
      color: "var(--muted)",
      fontSize: "0.88rem",
    }}>
      <span className="import-spinner" />
      {label}
    </div>
  );
}

export function ImportFlow({ locationId, basePath }: ImportFlowProps) {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<ImportFlowStep>("pick");
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [uploadResult, setUploadResult] = useState<ImportUploadResponse | null>(null);
  const [mappingResult, setMappingResult] = useState<ImportMappingResponse | null>(null);
  const [commitResult, setCommitResult] = useState<ImportCommitResponse | null>(null);
  const [importType, setImportType] = useState<string>("combined");
  const locationBasePath = basePath ?? `/dashboard/locations/${locationId}`;

  function reset() {
    setStep("pick");
    setError(null);
    setJob(null);
    setUploadResult(null);
    setMappingResult(null);
    setCommitResult(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function handleFileSelect() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    setStep("uploading");
    setError(null);

    try {
      const newJob = await createImportJob(locationId, importType, file.name);
      if (!newJob) {
        setError("Failed to create import job");
        setStep("error");
        return;
      }
      setJob(newJob);

      const upload = await uploadImportFile(newJob.id, file);
      if (!upload) {
        setError("Failed to upload CSV file");
        setStep("error");
        return;
      }
      setUploadResult(upload);
      setStep("mapping");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setStep("error");
    }
  }

  async function handleMapping(mapping: Record<string, string>) {
    if (!job) return;
    setStep("validating");
    setError(null);

    try {
      const result = await saveImportMapping(job.id, mapping);
      if (!result) {
        setError("Failed to validate mapping");
        setStep("error");
        return;
      }
      setMappingResult(result);
      setStep("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mapping validation failed");
      setStep("error");
    }
  }

  async function handleCommit() {
    if (!job) return;
    setStep("committing");
    setError(null);

    try {
      const result = await commitImport(job.id);
      if (!result) {
        setError("Failed to commit import");
        setStep("error");
        return;
      }
      setCommitResult(result);
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Commit failed");
      setStep("error");
    }
  }

  function handleViewResults() {
    if (job) {
      router.push(`${locationBasePath}?tab=roster&job_id=${job.id}`);
      router.refresh();
    }
  }

  return (
    <div>
      {/* Step: File picker */}
      {step === "pick" && (
        <div style={{
          padding: 24,
          borderRadius: "var(--radius-lg)",
          background: "var(--panel)",
          border: "1px solid var(--line)",
          boxShadow: "var(--shadow)",
        }}>
          <div style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: 20 }}>
            Upload a CSV
          </div>
          <div className="form-grid" style={{ maxWidth: 480 }}>
            <label className="field">
              <span>Import type</span>
              <select
                value={importType}
                onChange={(e) => setImportType(e.target.value)}
              >
                <option value="combined">Combined (roster + shifts)</option>
                <option value="roster_only">Roster only</option>
                <option value="shifts_only">Shifts only</option>
              </select>
            </label>
            <label className="field">
              <span>CSV file</span>
              <input ref={fileRef} type="file" accept=".csv" />
            </label>
          </div>
          <div style={{ marginTop: 20 }}>
            <button className="button" onClick={handleFileSelect}>
              Upload &amp; continue
            </button>
          </div>
        </div>
      )}

      {/* Step: Uploading */}
      {step === "uploading" && <StepIndicator label="Uploading and parsing CSV\u2026" />}

      {/* Step: Mapping */}
      {step === "mapping" && uploadResult && (
        <ImportMappingGrid
          uploadResult={uploadResult}
          onSubmit={handleMapping}
          submitting={false}
        />
      )}

      {/* Step: Validating */}
      {step === "validating" && <StepIndicator label="Validating rows against mapping\u2026" />}

      {/* Step: Review mapping result */}
      {step === "review" && mappingResult && (
        <div>
          <div className="summary-bar">
            <div className="summary-bar-item">
              <strong>{mappingResult.summary.total_rows}</strong>
              <span>Total</span>
            </div>
            <div className="summary-bar-item">
              <strong>{mappingResult.summary.success_rows}</strong>
              <span>Ready</span>
            </div>
            <div className="summary-bar-item">
              <strong>{mappingResult.summary.warning_rows}</strong>
              <span>Warnings</span>
            </div>
            <div className="summary-bar-item">
              <strong>{mappingResult.summary.failed_rows}</strong>
              <span>Failed</span>
            </div>
          </div>

          {mappingResult.action_needed_count > 0 && (
            <div style={{
              padding: "14px 18px",
              borderRadius: "var(--radius)",
              background: "rgba(243, 156, 18, 0.04)",
              border: "1px solid rgba(243, 156, 18, 0.1)",
              fontSize: "0.88rem",
              color: "var(--text)",
              marginBottom: 16,
            }}>
              <strong>{mappingResult.action_needed_count}</strong> row(s) need attention.
              You can commit now and resolve issues later, or view the full results first.
            </div>
          )}

          <div className="cta-row">
            <button className="button" onClick={handleCommit}>
              Commit import
            </button>
            <button className="button-secondary" onClick={handleViewResults}>
              View rows first
            </button>
            <button className="button-secondary" onClick={reset}>
              Start over
            </button>
          </div>
        </div>
      )}

      {/* Step: Committing */}
      {step === "committing" && <StepIndicator label="Committing valid rows\u2026" />}

      {/* Step: Done */}
      {step === "done" && commitResult && (
        <div>
          <div style={{
            padding: "20px 22px",
            borderRadius: "var(--radius-lg)",
            background: "rgba(39, 174, 96, 0.04)",
            border: "1px solid rgba(39, 174, 96, 0.12)",
            marginBottom: 16,
          }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Import committed</div>
            <div style={{ fontSize: "0.88rem", color: "var(--muted)" }}>
              Created <strong style={{ color: "var(--text)" }}>{commitResult.created_workers}</strong> worker(s),
              updated <strong style={{ color: "var(--text)" }}>{commitResult.updated_workers}</strong>,
              and created <strong style={{ color: "var(--text)" }}>{commitResult.created_shifts}</strong> shift(s).
              {commitResult.schedule_id && (
                <> Schedule <strong style={{ color: "var(--text)" }}>#{commitResult.schedule_id}</strong> for week of {commitResult.week_start_date}.</>
              )}
            </div>
          </div>
          <div className="cta-row">
            <button className="button" onClick={handleViewResults}>
              View import details
            </button>
            <button className="button-secondary" onClick={reset}>
              Import another file
            </button>
          </div>
        </div>
      )}

      {/* Step: Error */}
      {step === "error" && (
        <div>
          <div style={{
            padding: "20px 22px",
            borderRadius: "var(--radius-lg)",
            background: "rgba(191, 91, 57, 0.04)",
            border: "1px solid rgba(191, 91, 57, 0.12)",
            marginBottom: 16,
          }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Something went wrong</div>
            <div style={{ fontSize: "0.88rem", color: "var(--muted)" }}>
              {error ?? "An unexpected error occurred."}
            </div>
          </div>
          <button className="button-secondary" onClick={reset}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
