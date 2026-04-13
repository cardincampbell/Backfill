/**
 * Client-side schedule export — CSV, Excel (.xlsx), PDF.
 *
 * Columns: Name | Role | Monday … Sunday  (9 total)
 * Day cells: "9 AM – 5 PM" pipe-joined for multiple shifts, blank if none.
 */

export interface ExportEmployee {
  id: string;
  name: string;
  role: string;
  /** hex accent color for the role (used in PDF/Excel styling) */
  roleColor: string;
}

export interface ExportShift {
  employeeId: string | null;
  day: number; // 0=Mon … 6=Sun
  startHour: number;
  endHour: number;
}

export interface ExportOptions {
  businessName: string;
  locationName: string;
  weekLabel: string;
  /** The Monday of the displayed week */
  weekStart: Date;
  employees: ExportEmployee[];
  shifts: ExportShift[];
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

// ─── CSV ────────────────────────────────────────────────────────────────────

export function exportCSV(opts: ExportOptions): void {
  const { header, rows } = buildRows(opts);
  const escape = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const titleLines = [
    escape(exportTitle(opts)),
    escape(`Schedule: ${opts.weekLabel}`),
    '',
  ];
  const dataLines = [header, ...rows].map((row) => row.map(escape).join(','));
  const csv = [...titleLines, ...dataLines].join('\r\n');
  triggerDownload(
    new Blob([csv], { type: 'text/csv;charset=utf-8;' }),
    safeFilename(opts.locationName, opts.weekLabel, 'csv'),
  );
}

// ─── Excel ──────────────────────────────────────────────────────────────────

export async function exportExcel(opts: ExportOptions): Promise<void> {
  const ExcelJS = (await import('exceljs')).default;
  const { header, rows } = buildRows(opts);

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
