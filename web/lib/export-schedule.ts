/**
 * Client-side schedule export — CSV, Excel (.xlsx), PDF.
 *
 * Columns: Name | Role | Monday … Sunday  (9 total)
 * Day cells: "9 AM – 5 PM" pipe-joined for multiple shifts, blank if none.
 */

import type {
  ComplianceWeekShift,
  LocationCompliancePayrollExport,
  LocationComplianceWeek,
} from "./api/finance";
import type { ComplianceRuleSourceReference } from "./api/workspace";

export interface ExportEmployee {
  id: string;
  name: string;
  role: string;
  /** hex accent color for the role (used in PDF/Excel styling) */
  roleColor: string;
}

export interface ExportShift {
  id?: string | null;
  employeeId: string | null;
  day: number; // 0=Mon … 6=Sun
  startHour: number;
  endHour: number;
  roleName?: string;
  complianceStatus?: string | null;
  complianceProfileCode?: string | null;
  complianceBlockingRuleCodes?: string[];
  complianceWarningRuleCodes?: string[];
  compliancePremiumRuleCodes?: string[];
  compliancePremiumTotalCents?: number;
  complianceUnresolvedPremiumRuleCodes?: string[];
  complianceOverrideApplied?: boolean;
  complianceOverrideArtifactId?: string | null;
}

export interface ExportOptions {
  businessName: string;
  locationName: string;
  weekLabel: string;
  /** The Monday of the displayed week */
  weekStart: Date;
  employees: ExportEmployee[];
  shifts: ExportShift[];
  complianceWeek?: LocationComplianceWeek | null;
  compliancePayrollExport?: LocationCompliancePayrollExport | null;
}

// ─── helpers ────────────────────────────────────────────────────────────────

const FULL_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export function fmtHour(h: number): string {
  const normalized = ((h % 24) + 24) % 24;
  const whole = Math.floor(normalized);
  const mins = Math.round((normalized - whole) * 60);
  const h12 = whole === 0 ? 12 : whole > 12 ? whole - 12 : whole;
  const sfx = whole < 12 ? 'AM' : 'PM';
  return mins === 0 ? `${h12} ${sfx}` : `${h12}:${String(mins).padStart(2, '0')} ${sfx}`;
}

export function dayCell(shifts: ExportShift[]): string {
  return shifts.map((s) => `${fmtHour(s.startHour)} – ${fmtHour(s.endHour)}`).join(' | ');
}

export function safeFilename(locationName: string, weekLabel: string, ext: string): string {
  const safe = (s: string) => s.replace(/[^a-zA-Z0-9_\- ]/g, '').replace(/\s+/g, '_');
  return `${safe(locationName)}_Schedule_${safe(weekLabel)}.${ext}`;
}

/** "Acme Corp · Downtown" */
export function exportTitle(opts: Pick<ExportOptions, 'businessName' | 'locationName'>): string {
  return `${opts.businessName} · ${opts.locationName}`;
}

export function buildRows(opts: ExportOptions): { header: string[]; rows: string[][] } {
  const header = ['Name', 'Role', ...FULL_DAYS];
  const rows = opts.employees.map((emp) => {
    const days = FULL_DAYS.map((_, i) => {
      const dayShifts = opts.shifts.filter(
        (s) => s.employeeId === emp.id && s.day === i,
      );
      return dayCell(dayShifts);
    });
    return [emp.name, emp.role, ...days];
  });
  return { header, rows };
}

function weekdayLabel(day: number): string {
  return FULL_DAYS[((day % 7) + 7) % 7] ?? 'Day';
}

function currencyFromCents(cents: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(cents / 100);
}

function formatRuleSourceReferences(
  references: ComplianceRuleSourceReference[] | null | undefined,
): string {
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
  return labels.join(" | ");
}

export function buildComplianceRows(opts: ExportOptions): { header: string[]; rows: string[][] } {
  const complianceWeekByShiftId = new Map(
    (opts.complianceWeek?.shifts ?? []).map((shift) => [shift.shift_id, shift]),
  );
  const employeeNameById = new Map(opts.employees.map((employee) => [employee.id, employee.name]));
  const header = [
    'Employee',
    'Role',
    'Shift',
    'Status',
    'Premium',
    'Unresolved Premium',
    'Artifact Applied',
    'Warning Rules',
    'Blocking Rules',
    'Rule Sources',
  ];
  const rows = opts.shifts
    .filter(
      (shift) =>
        Boolean(shift.employeeId)
        && (
          Boolean(shift.complianceStatus)
          || (shift.compliancePremiumTotalCents ?? 0) > 0
          || Boolean(shift.complianceOverrideApplied)
          || (shift.complianceWarningRuleCodes?.length ?? 0) > 0
          || (shift.complianceBlockingRuleCodes?.length ?? 0) > 0
          || (shift.complianceUnresolvedPremiumRuleCodes?.length ?? 0) > 0
        ),
    )
    .map((shift) => {
      const premiumCents = Math.max(0, shift.compliancePremiumTotalCents ?? 0);
      const complianceWeekShift = complianceWeekByShiftId.get(shift.id ?? "");
      return [
        employeeNameById.get(shift.employeeId!) ?? 'Assigned employee',
        shift.roleName ?? '',
        `${weekdayLabel(shift.day)} ${fmtHour(shift.startHour)} – ${fmtHour(shift.endHour)}`,
        shift.complianceStatus ?? '',
        premiumCents > 0 ? currencyFromCents(premiumCents) : '',
        (shift.complianceUnresolvedPremiumRuleCodes ?? []).join(' | '),
        shift.complianceOverrideApplied ? 'Yes' : '',
        (shift.complianceWarningRuleCodes ?? []).join(' | '),
        (shift.complianceBlockingRuleCodes ?? []).join(' | '),
        formatRuleSourceReferences(complianceWeekShift?.rule_source_references),
      ];
    });
  return { header, rows };
}

export function buildCompliancePayrollRows(opts: ExportOptions): { header: string[]; rows: string[][] } {
  const report = opts.compliancePayrollExport;
  const header = [
    'Row Kind',
    'Export Status',
    'Employee',
    'Employee Identifier Type',
    'Employee Identifier',
    'Role',
    'Shift',
    'Status',
    'Earning Code',
    'Earning Label',
    'Source Rule',
    'Premium',
    'Premium Rules',
    'Unresolved Premium',
    'Payment Required',
    'Manual Review',
    'Artifact Type',
    'Artifact Note',
    'Source Reasons',
    'Rule Sources',
  ];
  if (!report || report.rows.length === 0) {
    return { header, rows: [] };
  }
  const rows = report.rows.map((row) => [
    row.payroll_row_kind ?? '',
    row.payroll_status ?? '',
    row.employee_name ?? '',
    row.employee_identifier_type ?? '',
    row.employee_identifier ?? '',
    row.role_name ?? '',
    `${row.starts_at} → ${row.ends_at}`,
    row.compliance_status,
    row.earning_code ?? '',
    row.earning_label ?? '',
    row.source_rule_code ?? '',
    row.premium_cents > 0 ? currencyFromCents(row.premium_cents) : '',
    row.premium_rule_codes.join(' | '),
    row.unresolved_premium_rule_codes.join(' | '),
    row.premium_payment_required ? 'Yes' : 'No',
    row.manual_review_required ? 'Yes' : 'No',
    row.override_artifact_type ?? '',
    row.override_artifact_note ?? '',
    (row.source_reason_codes ?? []).join(' | '),
    formatRuleSourceReferences(row.rule_source_references),
  ]);
  return { header, rows };
}

// ─── CSV ────────────────────────────────────────────────────────────────────

export function exportCSV(opts: ExportOptions): void {
  const { header, rows } = buildRows(opts);
  const { header: complianceHeader, rows: complianceRows } = buildComplianceRows(opts);
  const { header: payrollHeader, rows: payrollRows } = buildCompliancePayrollRows(opts);
  const escape = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const titleLines = [
    escape(exportTitle(opts)),
    escape(`Schedule: ${opts.weekLabel}`),
    '',
  ];
  const dataLines = [header, ...rows].map((row) => row.map(escape).join(','));
  const complianceLines =
    complianceRows.length > 0
      ? [
          '',
          escape('Compliance Summary'),
          [complianceHeader, ...complianceRows].map((row) => row.map(escape).join(',')),
        ].flat()
      : [];
  const payrollLines =
    payrollRows.length > 0
      ? [
          '',
          escape('Compliance Payroll Consequences'),
          [payrollHeader, ...payrollRows].map((row) => row.map(escape).join(',')),
        ].flat()
      : [];
  const csv = [...titleLines, ...dataLines, ...complianceLines, ...payrollLines].join('\r\n');
  triggerDownload(
    new Blob([csv], { type: 'text/csv;charset=utf-8;' }),
    safeFilename(opts.locationName, opts.weekLabel, 'csv'),
  );
}

// ─── Excel ──────────────────────────────────────────────────────────────────

export async function exportExcel(opts: ExportOptions): Promise<void> {
  const ExcelJS = (await import('exceljs')).default;
  const { header, rows } = buildRows(opts);
  const { header: complianceHeader, rows: complianceRows } = buildComplianceRows(opts);
  const { header: payrollHeader, rows: payrollRows } = buildCompliancePayrollRows(opts);

  const wb = new ExcelJS.Workbook();
  wb.creator = 'Backfill';
  // Freeze row 3: row 1 = business · location title, row 2 = week label, row 3 = column headers
  const ws = wb.addWorksheet('Schedule', { views: [{ state: 'frozen', ySplit: 3 }] });

  // Column widths — no header property here; we write row 3 manually below
  ws.columns = header.map((_, i) => ({
    key: String(i),
    width: i === 0 ? 22 : i === 1 ? 18 : 20,
  }));

  // Row 1 — business · location title
  const titleRow = ws.getRow(1);
  titleRow.height = 28;
  titleRow.getCell(1).value = exportTitle(opts);
  titleRow.getCell(1).font = { bold: true, color: { argb: 'FF0A2540' }, size: 12 };
  titleRow.getCell(1).alignment = { vertical: 'middle' };
  ws.mergeCells(1, 1, 1, header.length);

  // Row 2 — week label
  const weekRow = ws.getRow(2);
  weekRow.height = 18;
  weekRow.getCell(1).value = `Schedule: ${opts.weekLabel}`;
  weekRow.getCell(1).font = { color: { argb: 'FF5E6D7A' }, size: 9 };
  weekRow.getCell(1).alignment = { vertical: 'middle' };
  ws.mergeCells(2, 1, 2, header.length);

  // Row 3 — column headers
  const headerRow = ws.getRow(3);
  headerRow.height = 26;
  header.forEach((_, ci) => {
    const cell = headerRow.getCell(ci + 1);
    cell.value = header[ci];
    cell.font = { bold: true, color: { argb: 'FFFFFFFF' }, size: 10 };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF0A2540' } };
    cell.alignment = { vertical: 'middle', horizontal: ci < 2 ? 'left' : 'center' };
    cell.border = {
      bottom: { style: 'thin', color: { argb: 'FF635BFF' } },
    };
  });

  // Group employees by role for alternating role bands
  let prevRole = '';
  let roleToggle = false;

  rows.forEach((row) => {
    const empRole = row[1];
    if (empRole !== prevRole) {
      prevRole = empRole;
      roleToggle = !roleToggle;
    }

    const dataRow = ws.addRow(row);
    dataRow.height = 22;

    row.forEach((val, ci) => {
      const cell = dataRow.getCell(ci + 1);
      cell.value = val;
      cell.font = { size: 9, color: { argb: 'FF0A2540' } };
      cell.alignment = {
        vertical: 'middle',
        horizontal: ci < 2 ? 'left' : 'center',
        wrapText: false,
      };
      // Alternating fill per role group
      cell.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: roleToggle ? 'FFF8F9FF' : 'FFFFFFFF' },
      };
      cell.border = {
        bottom: { style: 'hair', color: { argb: 'FFE5E7EB' } },
      };
    });
  });

  if (complianceRows.length > 0) {
    const complianceSheet = wb.addWorksheet('Compliance', { views: [{ state: 'frozen', ySplit: 3 }] });
    complianceSheet.columns = complianceHeader.map((column) => ({
      key: column,
      width:
        column === 'Employee'
          ? 22
          : column === 'Role'
            ? 18
            : column === 'Shift'
              ? 26
              : column === 'Warning Rules' || column === 'Blocking Rules'
                ? 28
                : 18,
    }));

    const titleRow = complianceSheet.getRow(1);
    titleRow.height = 28;
    titleRow.getCell(1).value = `${exportTitle(opts)} · Compliance`;
    titleRow.getCell(1).font = { bold: true, color: { argb: 'FF0A2540' }, size: 12 };
    titleRow.getCell(1).alignment = { vertical: 'middle' };
    complianceSheet.mergeCells(1, 1, 1, complianceHeader.length);

    const weekRow = complianceSheet.getRow(2);
    weekRow.height = 18;
    weekRow.getCell(1).value = `Schedule: ${opts.weekLabel}`;
    weekRow.getCell(1).font = { color: { argb: 'FF5E6D7A' }, size: 9 };
    weekRow.getCell(1).alignment = { vertical: 'middle' };
    complianceSheet.mergeCells(2, 1, 2, complianceHeader.length);

    const complianceHeaderRow = complianceSheet.getRow(3);
    complianceHeaderRow.height = 26;
    complianceHeader.forEach((column, index) => {
      const cell = complianceHeaderRow.getCell(index + 1);
      cell.value = column;
      cell.font = { bold: true, color: { argb: 'FFFFFFFF' }, size: 10 };
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF0A2540' } };
      cell.alignment = { vertical: 'middle', horizontal: index < 3 ? 'left' : 'center', wrapText: true };
      cell.border = {
        bottom: { style: 'thin', color: { argb: 'FF635BFF' } },
      };
    });

    complianceRows.forEach((row) => {
      const dataRow = complianceSheet.addRow(row);
      dataRow.height = 22;
      row.forEach((value, index) => {
        const cell = dataRow.getCell(index + 1);
        cell.value = value;
        cell.font = { size: 9, color: { argb: 'FF0A2540' } };
        cell.alignment = {
          vertical: 'middle',
          horizontal: index < 3 ? 'left' : 'center',
          wrapText: true,
        };
        cell.fill = {
          type: 'pattern',
          pattern: 'solid',
          fgColor: { argb: 'FFFFFFFF' },
        };
        cell.border = {
          bottom: { style: 'hair', color: { argb: 'FFE5E7EB' } },
        };
      });
    });
  }

  if (payrollRows.length > 0) {
    const payrollSheet = wb.addWorksheet('Compliance Payroll', { views: [{ state: 'frozen', ySplit: 3 }] });
    payrollSheet.columns = payrollHeader.map((column) => ({
      key: column,
      width:
        column === 'Employee'
          ? 22
          : column === 'Role'
            ? 18
            : column === 'Shift'
              ? 38
              : column === 'Premium Rules' || column === 'Unresolved Premium' || column === 'Artifact Note'
                ? 28
                : 18,
    }));

    const titleRow = payrollSheet.getRow(1);
    titleRow.height = 28;
    titleRow.getCell(1).value = `${exportTitle(opts)} · Compliance Payroll`;
    titleRow.getCell(1).font = { bold: true, color: { argb: 'FF0A2540' }, size: 12 };
    titleRow.getCell(1).alignment = { vertical: 'middle' };
    payrollSheet.mergeCells(1, 1, 1, payrollHeader.length);

    const weekRow = payrollSheet.getRow(2);
    weekRow.height = 18;
    weekRow.getCell(1).value = `Schedule: ${opts.weekLabel}`;
    weekRow.getCell(1).font = { color: { argb: 'FF5E6D7A' }, size: 9 };
    weekRow.getCell(1).alignment = { vertical: 'middle' };
    payrollSheet.mergeCells(2, 1, 2, payrollHeader.length);

    const payrollHeaderRow = payrollSheet.getRow(3);
    payrollHeaderRow.height = 26;
    payrollHeader.forEach((column, index) => {
      const cell = payrollHeaderRow.getCell(index + 1);
      cell.value = column;
      cell.font = { bold: true, color: { argb: 'FFFFFFFF' }, size: 10 };
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF635BFF' } };
      cell.alignment = { vertical: 'middle', horizontal: index < 3 ? 'left' : 'center', wrapText: true };
      cell.border = {
        bottom: { style: 'thin', color: { argb: 'FF0A2540' } },
      };
    });

    payrollRows.forEach((row) => {
      const dataRow = payrollSheet.addRow(row);
      dataRow.height = 22;
      row.forEach((value, index) => {
        const cell = dataRow.getCell(index + 1);
        cell.value = value;
        cell.font = { size: 9, color: { argb: 'FF0A2540' } };
        cell.alignment = {
          vertical: 'middle',
          horizontal: index < 3 ? 'left' : 'center',
          wrapText: true,
        };
        cell.fill = {
          type: 'pattern',
          pattern: 'solid',
          fgColor: { argb: 'FFFFFFFF' },
        };
        cell.border = {
          bottom: { style: 'hair', color: { argb: 'FFE5E7EB' } },
        };
      });
    });
  }

  const buf = await wb.xlsx.writeBuffer();
  triggerDownload(
    new Blob([buf], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }),
    safeFilename(opts.locationName, opts.weekLabel, 'xlsx'),
  );
}

// ─── PDF ────────────────────────────────────────────────────────────────────

export async function exportPDF(opts: ExportOptions): Promise<void> {
  const { default: jsPDF } = await import('jspdf');
  const { default: autoTable } = await import('jspdf-autotable');
  const { header, rows } = buildRows(opts);
  const { header: complianceHeader, rows: complianceRows } = buildComplianceRows(opts);
  const { header: payrollHeader, rows: payrollRows } = buildCompliancePayrollRows(opts);

  const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'letter' });

  // Title
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.setTextColor(10, 37, 64); // #0A2540
  doc.text(exportTitle(opts), 40, 38);

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(94, 109, 122); // #5E6D7A
  doc.text(`Schedule: ${opts.weekLabel}`, 40, 52);

  autoTable(doc, {
    head: [header],
    body: rows,
    startY: 64,
    margin: { left: 40, right: 40 },
    tableWidth: 'auto',
    styles: {
      fontSize: 8,
      cellPadding: { top: 5, bottom: 5, left: 6, right: 6 },
      valign: 'middle',
      textColor: [10, 37, 64],
      lineColor: [229, 231, 235],
      lineWidth: 0.5,
      overflow: 'linebreak',
    },
    headStyles: {
      fillColor: [10, 37, 64],   // #0A2540
      textColor: [255, 255, 255],
      fontStyle: 'bold',
      fontSize: 8,
      halign: 'center',
    },
    columnStyles: {
      0: { halign: 'left', cellWidth: 80 },  // Name
      1: { halign: 'left', cellWidth: 64 },  // Role
      2: { halign: 'center' },
      3: { halign: 'center' },
      4: { halign: 'center' },
      5: { halign: 'center' },
      6: { halign: 'center' },
      7: { halign: 'center' },
      8: { halign: 'center' },
    },
    alternateRowStyles: {
      fillColor: [248, 249, 255], // very light indigo tint
    },
    didParseCell(data) {
      // Highlight today's day column header
      if (data.section === 'head' && data.column.index >= 2) {
        const dayIdx = data.column.index - 2; // 0=Mon
        const colDate = new Date(opts.weekStart);
        colDate.setDate(colDate.getDate() + dayIdx);
        const today = new Date();
        if (
          colDate.getDate() === today.getDate() &&
          colDate.getMonth() === today.getMonth() &&
          colDate.getFullYear() === today.getFullYear()
        ) {
          data.cell.styles.fillColor = [99, 91, 255]; // #635BFF
        }
      }
    },
  });

  if (complianceRows.length > 0) {
    autoTable(doc, {
      head: [complianceHeader],
      body: complianceRows,
      startY: (doc as unknown as { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY
        ? ((doc as unknown as { lastAutoTable?: { finalY?: number } }).lastAutoTable!.finalY ?? 64) + 18
        : 320,
      margin: { left: 40, right: 40 },
      tableWidth: 'auto',
      styles: {
        fontSize: 7,
        cellPadding: { top: 4, bottom: 4, left: 5, right: 5 },
        valign: 'middle',
        textColor: [10, 37, 64],
        lineColor: [229, 231, 235],
        lineWidth: 0.5,
        overflow: 'linebreak',
      },
      headStyles: {
        fillColor: [99, 91, 255],
        textColor: [255, 255, 255],
        fontStyle: 'bold',
        fontSize: 7,
        halign: 'center',
      },
      columnStyles: {
        0: { halign: 'left', cellWidth: 68 },
        1: { halign: 'left', cellWidth: 54 },
        2: { halign: 'left', cellWidth: 86 },
      },
    });
  }

  if (payrollRows.length > 0) {
    autoTable(doc, {
      head: [payrollHeader],
      body: payrollRows,
      startY: (doc as unknown as { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY
        ? ((doc as unknown as { lastAutoTable?: { finalY?: number } }).lastAutoTable!.finalY ?? 64) + 18
        : 420,
      margin: { left: 40, right: 40 },
      tableWidth: 'auto',
      styles: {
        fontSize: 7,
        cellPadding: { top: 4, bottom: 4, left: 5, right: 5 },
        valign: 'middle',
        textColor: [10, 37, 64],
        lineColor: [229, 231, 235],
        lineWidth: 0.5,
        overflow: 'linebreak',
      },
      headStyles: {
        fillColor: [245, 158, 11],
        textColor: [255, 255, 255],
        fontStyle: 'bold',
        fontSize: 7,
        halign: 'center',
      },
      columnStyles: {
        0: { halign: 'left', cellWidth: 62 },
        1: { halign: 'left', cellWidth: 48 },
        2: { halign: 'left', cellWidth: 120 },
      },
    });
  }

  doc.save(safeFilename(opts.locationName, opts.weekLabel, 'pdf'));
}

// ─── shared ─────────────────────────────────────────────────────────────────

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
