"use client";

import { useState } from "react";
import type { ImportUploadResponse } from "@/lib/types";

const TARGET_FIELDS = [
  { value: "", label: "Skip" },
  { value: "worker_name", label: "Employee name" },
  { value: "first_name", label: "First name" },
  { value: "last_name", label: "Last name" },
  { value: "phone", label: "Phone" },
  { value: "email", label: "Email" },
  { value: "employee_id", label: "Employee ID" },
  { value: "role", label: "Role" },
  { value: "date", label: "Shift date" },
  { value: "start_time", label: "Start time" },
  { value: "end_time", label: "End time" },
  { value: "pay_rate", label: "Pay rate" },
  { value: "notes", label: "Notes" },
  { value: "shift_label", label: "Shift label" },
  { value: "employment_status", label: "Employment status" },
  { value: "max_hours_per_week", label: "Max hours/week" },
];

function guessTargetField(column: string): string {
  const col = column.toLowerCase().replace(/[_\- ]/g, "");
  const guesses: Record<string, string> = {
    name: "worker_name",
    employeename: "worker_name",
    employee: "worker_name",
    firstname: "first_name",
    lastname: "last_name",
    phone: "phone",
    mobile: "phone",
    cell: "phone",
    phonenumber: "phone",
    mobilenumber: "phone",
    email: "email",
    emailaddress: "email",
    employeeid: "employee_id",
    role: "role",
    position: "role",
    jobtitle: "role",
    date: "date",
    shiftdate: "date",
    start: "start_time",
    starttime: "start_time",
    end: "end_time",
    endtime: "end_time",
    payrate: "pay_rate",
    rate: "pay_rate",
    hourlyrate: "pay_rate",
    notes: "notes",
    shiftnotes: "notes",
    label: "shift_label",
    shiftlabel: "shift_label",
  };
  return guesses[col] ?? "";
}

type ImportMappingGridProps = {
  uploadResult: ImportUploadResponse;
  onSubmit: (mapping: Record<string, string>) => void;
  submitting: boolean;
};

export function ImportMappingGrid({ uploadResult, onSubmit, submitting }: ImportMappingGridProps) {
  const [mapping, setMapping] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const col of uploadResult.columns) {
      initial[col] = guessTargetField(col);
    }
    return initial;
  });

  const mappedCount = Object.values(mapping).filter((v) => v !== "").length;

  function handleChange(column: string, target: string) {
    setMapping((prev) => ({ ...prev, [column]: target }));
  }

  function handleSubmit() {
    const filtered: Record<string, string> = {};
    for (const [col, target] of Object.entries(mapping)) {
      if (target) filtered[col] = target;
    }
    onSubmit(filtered);
  }

  return (
    <div style={{
      padding: 24,
      borderRadius: "var(--radius-lg)",
      background: "var(--panel)",
      border: "1px solid var(--line)",
      boxShadow: "var(--shadow)",
    }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 20 }}>
        <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>Map columns</div>
        <div style={{ fontSize: "0.82rem", color: "var(--muted)" }}>
          {mappedCount} of {uploadResult.columns.length} mapped
        </div>
      </div>

      <div className="mapping-grid">
        <div style={{ fontWeight: 600, fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
          CSV Column
        </div>
        <div />
        <div style={{ fontWeight: 600, fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
          Maps to
        </div>

        {uploadResult.columns.map((col) => (
          <MappingRow
            key={col}
            column={col}
            value={mapping[col] ?? ""}
            onChange={(target) => handleChange(col, target)}
          />
        ))}
      </div>

      {/* Preview table */}
      {uploadResult.preview_rows.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--muted)", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Preview ({uploadResult.preview_rows.length} rows)
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  {uploadResult.columns.map((col) => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {uploadResult.preview_rows.map((row) => (
                  <tr key={row.row_number}>
                    <td style={{ color: "var(--muted)", fontVariantNumeric: "tabular-nums" }}>{row.row_number}</td>
                    {uploadResult.columns.map((col) => (
                      <td key={col}>{row.values[col] ?? ""}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div style={{ marginTop: 20 }}>
        <button
          className="button"
          disabled={mappedCount === 0 || submitting}
          onClick={handleSubmit}
        >
          {submitting ? "Validating\u2026" : "Validate mapping"}
        </button>
      </div>
    </div>
  );
}

function MappingRow({
  column,
  value,
  onChange,
}: {
  column: string;
  value: string;
  onChange: (target: string) => void;
}) {
  return (
    <>
      <div className="mapping-source">{column}</div>
      <div className="mapping-arrow">\u2192</div>
      <select
        className="mapping-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ fontSize: "0.85rem", color: value ? "var(--text)" : "var(--muted)" }}
      >
        {TARGET_FIELDS.map((f) => (
          <option key={f.value} value={f.value}>
            {f.label}
          </option>
        ))}
      </select>
    </>
  );
}
