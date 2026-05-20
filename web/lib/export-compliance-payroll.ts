import type { LocationCompliancePayrollExport } from "./api/finance";

export function describeCompliancePayrollProviderProfile(
  profile: LocationCompliancePayrollExport["provider_profile"] | undefined,
) {
  switch (profile) {
    case "gusto_csv_v1":
      return "Gusto-aligned CSV";
    case "quickbooks_csv_v1":
      return "QuickBooks-aligned CSV";
    case "adp_csv_v1":
      return "ADP-aligned CSV";
    default:
      return "Backfill generic CSV";
  }
}

function providerLabel(profile: LocationCompliancePayrollExport["provider_profile"] | undefined) {
  switch (profile) {
    case "gusto_csv_v1":
      return "gusto";
    case "quickbooks_csv_v1":
      return "quickbooks";
    case "adp_csv_v1":
      return "adp";
    default:
      return "compliance-payroll";
  }
}

function escapeCsv(value: string) {
  const escaped = value.replaceAll('"', '""');
  return `"${escaped}"`;
}

function formatMoney(cents: number) {
  return (cents / 100).toFixed(2);
}

function safeFilename(
  locationName: string,
  weekLabel: string,
  providerProfile: LocationCompliancePayrollExport["provider_profile"] | undefined,
) {
  return `${locationName}-${weekLabel}-${providerLabel(providerProfile)}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function formatRuleSourceReferences(
  references: LocationCompliancePayrollExport["rows"][number]["rule_source_references"] | null | undefined,
) {
  const items = references ?? [];
  if (!items.length) {
    return "";
  }
  const seen = new Set<string>();
  const labels: string[] = [];
  for (const reference of items) {
    const key = [
      reference.rule_code,
      reference.source_kind,
      reference.source_code ?? "",
      reference.source_hash ?? "",
      reference.version_id ?? "",
    ].join(":");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    const kind = reference.source_kind
      .split("_")
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
    const primary = reference.source_label ?? reference.source_document_title ?? reference.source_code ?? kind;
    labels.push(primary === kind ? primary : `${kind} · ${primary}`);
  }
  return labels.join("; ");
}

function resolvedEmployeeNumber(
  row: LocationCompliancePayrollExport["rows"][number],
) {
  if (row.employee_number) {
    return row.employee_number;
  }
  if (row.employee_identifier_type === "employee_number") {
    return row.employee_identifier ?? "";
  }
  return "";
}

function resolvedExternalRef(
  row: LocationCompliancePayrollExport["rows"][number],
) {
  if (row.external_ref) {
    return row.external_ref;
  }
  if (row.employee_identifier_type === "external_ref") {
    return row.employee_identifier ?? "";
  }
  return "";
}

function buildRowNotes(
  row: LocationCompliancePayrollExport["rows"][number],
) {
  const parts: string[] = [];
  if (row.override_artifact_note) {
    parts.push(row.override_artifact_note);
  }
  if (row.manual_review_required) {
    parts.push("Manual review required");
  }
  if (row.source_reason_codes?.length) {
    parts.push(`Reasons: ${row.source_reason_codes.join("; ")}`);
  }
  return parts.join(" | ");
}

function payrollCsvHeaderForProfile(
  profile: LocationCompliancePayrollExport["provider_profile"] | undefined,
) {
  switch (profile) {
    case "gusto_csv_v1":
      return [
        "Location",
        "Week",
        "Employee Number",
        "Employee",
        "Earning Code",
        "Earning Label",
        "Amount USD",
        "Shift Start",
        "Shift End",
        "Compliance Status",
        "Source Rule",
        "Rule Sources",
        "Notes",
      ];
    case "quickbooks_csv_v1":
      return [
        "Location",
        "Week",
        "Employee Number",
        "External Reference",
        "Employee",
        "Payroll Item Code",
        "Payroll Item Label",
        "Amount USD",
        "Shift Start",
        "Shift End",
        "Compliance Status",
        "Source Rule",
        "Rule Sources",
        "Notes",
      ];
    case "adp_csv_v1":
      return [
        "Location",
        "Week",
        "Associate ID",
        "Alternate ID",
        "Employee",
        "Pay Code",
        "Pay Code Label",
        "Amount USD",
        "Shift Start",
        "Shift End",
        "Compliance Status",
        "Manual Review Required",
        "Source Rule",
        "Rule Sources",
        "Notes",
      ];
    default:
      return [
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
        "Rule Sources",
      ];
  }
}

function payrollCsvRowForProfile(
  row: LocationCompliancePayrollExport["rows"][number],
  opts: { locationName: string; weekLabel: string; providerProfile: LocationCompliancePayrollExport["provider_profile"] | undefined },
) {
  const ruleSources = formatRuleSourceReferences(row.rule_source_references);
  const notes = buildRowNotes(row);
  switch (opts.providerProfile) {
    case "gusto_csv_v1":
      return [
        opts.locationName,
        opts.weekLabel,
        resolvedEmployeeNumber(row),
        row.employee_name ?? "",
        row.earning_code ?? "",
        row.earning_label ?? "",
        formatMoney(row.premium_cents),
        row.starts_at,
        row.ends_at,
        row.compliance_status,
        row.source_rule_code ?? "",
        ruleSources,
        notes,
      ];
    case "quickbooks_csv_v1":
      return [
        opts.locationName,
        opts.weekLabel,
        resolvedEmployeeNumber(row),
        resolvedExternalRef(row),
        row.employee_name ?? "",
        row.earning_code ?? "",
        row.earning_label ?? "",
        formatMoney(row.premium_cents),
        row.starts_at,
        row.ends_at,
        row.compliance_status,
        row.source_rule_code ?? "",
        ruleSources,
        notes,
      ];
    case "adp_csv_v1":
      return [
        opts.locationName,
        opts.weekLabel,
        resolvedEmployeeNumber(row),
        resolvedExternalRef(row),
        row.employee_name ?? "",
        row.earning_code ?? "",
        row.earning_label ?? "",
        formatMoney(row.premium_cents),
        row.starts_at,
        row.ends_at,
        row.compliance_status,
        row.manual_review_required ? "yes" : "no",
        row.source_rule_code ?? "",
        ruleSources,
        notes,
      ];
    default:
      return [
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
        ruleSources,
      ];
  }
}

export function buildCompliancePayrollCsv(
  report: LocationCompliancePayrollExport,
  opts: { locationName: string; weekLabel: string },
): string {
  const header = payrollCsvHeaderForProfile(report.provider_profile);
  const lines: string[] = [
    header.map(escapeCsv).join(","),
  ];

  report.rows.forEach((row) => {
    lines.push(
      payrollCsvRowForProfile(row, {
        locationName: opts.locationName,
        weekLabel: opts.weekLabel,
        providerProfile: report.provider_profile,
      })
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
  anchor.download = `${safeFilename(
    opts.locationName,
    opts.weekLabel,
    report.provider_profile,
  )}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}
