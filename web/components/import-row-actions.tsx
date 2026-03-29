"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { resolveImportRow, exportImportErrorsCsv } from "@/lib/shifts-api";

type ImportRowActionsProps = {
  rowId: number;
};

export function ImportRowActions({ rowId }: ImportRowActionsProps) {
  const router = useRouter();
  const [loading, setLoading] = useState<"fix" | "ignore" | null>(null);

  async function handleAction(action: "fix" | "ignore") {
    setLoading(action);
    try {
      const result = await resolveImportRow(rowId, action === "fix" ? "retry" : "ignore");
      if (result) {
        router.refresh();
      }
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="row-issue-actions">
      <button
        className="button-secondary button-small"
        disabled={loading !== null}
        onClick={() => handleAction("fix")}
      >
        {loading === "fix" ? "Retrying\u2026" : "Retry"}
      </button>
      <button
        className="button-secondary button-small"
        disabled={loading !== null}
        onClick={() => handleAction("ignore")}
      >
        {loading === "ignore" ? "Ignoring\u2026" : "Ignore"}
      </button>
    </div>
  );
}

type ExportErrorsCsvButtonProps = {
  jobId: number;
};

export function ExportErrorsCsvButton({ jobId }: ExportErrorsCsvButtonProps) {
  const [loading, setLoading] = useState(false);

  async function handleExport() {
    setLoading(true);
    try {
      const result = await exportImportErrorsCsv(jobId);
      if (result && result.csv) {
        const blob = new Blob([result.csv], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `import-${jobId}-errors.csv`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      className="button-secondary button-small"
      disabled={loading}
      onClick={handleExport}
    >
      {loading ? "Exporting\u2026" : "Export errors CSV"}
    </button>
  );
}
