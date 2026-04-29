import type { LocationCompliancePayrollExport } from "./api/finance";

function escapeCsv(value: string) {
  const escaped = value.replaceAll('"', '""');
  return `"${escaped}"`;
}

function formatMoney(cents: number) {
  return (cents / 100).toFixed(2);
}

function safeFilename(locationName: string, weekLabel: string) {
  return `${locationName}-${weekLabel}-compliance-payroll`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function buildCompliancePayrollCsv(
  report: LocationCompliancePayrollExport,
  opts: { locationName: string; weekLabel: string },
): string {
  const lines: string[] = [
    [
      "Location",
      "Week",
      "Row Kind",
      "Export Status",
      "Employee",
      "Employee Identifier Type",
      "Employee Identifier",
      "Role",
      "Shift Start",
      "Shift End",
      "Compliance Status",
      "Profile",
      "Earning Code",
      "Earning Label",
      "Source Rule",
      "Premium Cents",
      "Premium USD",
      "Premium Rules",
      "Unresolved Premium Rules",
      "Premium Payment Required",
      "Manual Review Required",
      "Override Applied",
      "Override Artifact Type",
      "Override Artifact Note",
      "Source Reasons",
    ]
      .map(escapeCsv)
      .join(","),
  ];

  report.rows.forEach((row) => {
    lines.push(
      [
        opts.locationName,
        opts.weekLabel,
        row.payroll_row_kind ?? "",
        row.payroll_status ?? "",
        row.employee_name ?? "",
        row.employee_identifier_type ?? "",
        row.employee_identifier ?? "",
        row.role_name ?? "",
        row.starts_at,
        row.ends_at,
        row.compliance_status,
        row.profile_code ?? "",
        row.earning_code ?? "",
        row.earning_label ?? "",
        row.source_rule_code ?? "",
        String(row.premium_cents),
        formatMoney(row.premium_cents),
        row.premium_rule_codes.join("; "),
        row.unresolved_premium_rule_codes.join("; "),
        row.premium_payment_required ? "yes" : "no",
        row.manual_review_required ? "yes" : "no",
        row.override_applied ? "yes" : "no",
        row.override_artifact_type ?? "",
        row.override_artifact_note ?? "",
        (row.source_reason_codes ?? []).join("; "),
      ]
        .map((value) => escapeCsv(String(value)))
        .join(","),
    );
  });

  return lines.join("\n");
}

export function exportCompliancePayrollCsv(
  report: LocationCompliancePayrollExport,
  opts: { locationName: string; weekLabel: string },
) {
  const csv = buildCompliancePayrollCsv(report, opts);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${safeFilename(opts.locationName, opts.weekLabel)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}
