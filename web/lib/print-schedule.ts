/**
 * Client-side schedule print.
 *
 * Generates a styled HTML page, opens it in a new window, and triggers
 * window.print(). The page is designed for landscape letter (11×8.5 in)
 * and matches the web scheduler's visual language.
 */

const DAYS_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const DAYS_FULL  = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export interface PrintEmployee {
  id: string;
  name: string;
  role: string;
  roleColor: string;
  email?: string | null;
  phone?: string | null;
}

export interface PrintShift {
  employeeId: string | null;
  day: number;   // 0 = Mon … 6 = Sun
  startHour: number;
  endHour: number;
}

export interface PrintOptions {
  businessName: string;
  locationName: string;
  weekLabel: string;
  weekDates: Date[];        // exactly 7 dates, Mon first
  employees: PrintEmployee[];
  shifts: PrintShift[];
  includeContactInfo: boolean;
  includeHours: boolean;
  includeRoles: boolean;
}

// ─── helpers ────────────────────────────────────────────────────────────────

export function printFmtHour(h: number): string {
  const normalized = ((h % 24) + 24) % 24;
  const whole = Math.floor(normalized);
  const mins  = Math.round((normalized - whole) * 60);
  const h12   = whole === 0 ? 12 : whole > 12 ? whole - 12 : whole;
  const sfx   = whole < 12 ? 'AM' : 'PM';
  return mins === 0
    ? `${h12} ${sfx}`
    : `${h12}:${String(mins).padStart(2, '0')} ${sfx}`;
}

export function printShiftDuration(s: PrintShift): number {
  return ((s.endHour - s.startHour) + 24) % 24 || 24;
}

export function formatPhone(e164: string): string {
  // Basic US formatting: +12125551234 → (212) 555-1234
  const digits = e164.replace(/\D/g, '');
  if (digits.length === 11 && digits[0] === '1') {
    return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  return e164;
}

function fmtShortDate(date: Date): string {
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function isToday(date: Date): boolean {
  const t = new Date();
  return (
    date.getDate()     === t.getDate() &&
    date.getMonth()    === t.getMonth() &&
    date.getFullYear() === t.getFullYear()
  );
}

function escape(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── HTML builder ────────────────────────────────────────────────────────────

export function buildPrintHTML(opts: PrintOptions): string {
  const {
    businessName,
    locationName,
    weekLabel,
    weekDates,
    employees,
    shifts,
    includeContactInfo,
    includeHours,
    includeRoles,
  } = opts;

  const todayIndices = weekDates
    .map((d, i) => (isToday(d) ? i : -1))
    .filter((i) => i >= 0);

  // ── column headers ──
  const dayHeaders = DAYS_SHORT.map((d, i) => {
    const cls = todayIndices.includes(i) ? ' class="today"' : '';
    return `<th${cls}>${escape(d)}<br><span class="date-sub">${escape(fmtShortDate(weekDates[i]))}</span></th>`;
  }).join('');

  const roleHeader   = includeRoles ? '<th class="col-role">Role</th>' : '';
  const hoursHeader  = includeHours ? '<th class="col-hours">Hrs</th>' : '';

  // ── data rows ──
  let prevRole = '';
  let rowBand  = false;

  const rows = employees.map((emp) => {
    if (emp.role !== prevRole) {
      prevRole = emp.role;
      rowBand  = !rowBand;
    }

    const empShifts = shifts.filter((s) => s.employeeId === emp.id);
    const totalHours = empShifts.reduce((sum, s) => sum + printShiftDuration(s), 0);

    const dayCells = DAYS_FULL.map((_, di) => {
      const dayShifts = empShifts.filter((s) => s.day === di);
      const cls = todayIndices.includes(di) ? ' class="today"' : '';
      const content = dayShifts
        .map((s) => `<span class="shift">${escape(printFmtHour(s.startHour))} – ${escape(printFmtHour(s.endHour))}</span>`)
        .join('');
      return `<td${cls}>${content}</td>`;
    }).join('');

    const contactHtml = includeContactInfo
      ? [
          emp.email ? `<span class="contact">${escape(emp.email)}</span>` : '',
          emp.phone ? `<span class="contact">${escape(formatPhone(emp.phone))}</span>` : '',
        ].filter(Boolean).join('')
      : '';

    const nameCell = `<td class="col-name">${escape(emp.name)}${contactHtml}</td>`;
    const roleCell = includeRoles  ? `<td class="col-role">${escape(emp.role)}</td>` : '';
    const hoursCell = includeHours
      ? `<td class="col-hours">${totalHours > 0 ? `${totalHours}h` : ''}</td>`
      : '';

    const bandClass = rowBand ? ' class="band"' : '';
    return `<tr${bandClass}>${nameCell}${roleCell}${dayCells}${hoursCell}</tr>`;
  }).join('');

  const title = `${businessName} · ${locationName}`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${escape(title)} — ${escape(weekLabel)}</title>
<style>
  @page { size: letter landscape; margin: 0.45in 0.5in; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    color: #0A2540;
    font-size: 8pt;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  /* ── header ── */
  .page-header { margin-bottom: 10pt; }
  .page-title  { font-size: 13pt; font-weight: 700; color: #0A2540; }
  .page-sub    { font-size: 8pt; color: #5E6D7A; margin-top: 2pt; }

  /* ── table ── */
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }

  th {
    background: #0A2540;
    color: #fff;
    font-size: 7.5pt;
    font-weight: 600;
    padding: 5pt 5pt;
    text-align: center;
    vertical-align: middle;
    line-height: 1.3;
    border-right: 1px solid #1a3a57;
  }
  th:last-child { border-right: none; }
  th.today { background: #635BFF; }

  th.col-name  { text-align: left; width: 90pt; }
  th.col-role  { text-align: left; width: 60pt; }
  th.col-hours { width: 28pt; }

  td {
    padding: 4pt 5pt;
    border-bottom: 0.5pt solid #E5E7EB;
    border-right:  0.5pt solid #F0F0F5;
    vertical-align: top;
    font-size: 7.5pt;
    color: #0A2540;
  }
  td:last-child { border-right: none; }
  td.today { background: rgba(99,91,255,0.06); }

  td.col-name  { font-weight: 500; }
  td.col-role  { color: #5E6D7A; }
  td.col-hours { text-align: center; font-weight: 600; color: #635BFF; }

  tr.band td { background: #F8F9FF; }
  tr.band td.today { background: rgba(99,91,255,0.09); }

  .date-sub { font-weight: 400; font-size: 6.5pt; opacity: 0.75; }
  .shift    { display: block; white-space: nowrap; }
  .contact  { display: block; font-size: 6.5pt; color: #5E6D7A; margin-top: 1pt; }
</style>
</head>
<body>
<div class="page-header">
  <div class="page-title">${escape(title)}</div>
  <div class="page-sub">Schedule: ${escape(weekLabel)}</div>
</div>

<table>
  <thead>
    <tr>
      <th class="col-name">Name</th>
      ${roleHeader}
      ${dayHeaders}
      ${hoursHeader}
    </tr>
  </thead>
  <tbody>
    ${rows}
  </tbody>
</table>
</body>
</html>`;
}

// ─── trigger ─────────────────────────────────────────────────────────────────

/**
 * Injects the print HTML into the current document as a full-screen overlay,
 * triggers window.print(), then removes the overlay on afterprint.
 * Used when window.open() is blocked by the browser.
 */
function printViaOverlay(html: string): void {
  // Extract just the <body> content and <style> from the generated HTML so we
  // can inject it into the current document without nesting <html>/<body>.
  const bodyMatch  = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  const styleMatch = /<style[^>]*>([\s\S]*?)<\/style>/i.exec(html);
  if (!bodyMatch) return;

  const overlay = document.createElement('div');
  overlay.id = '__print_overlay__';
  overlay.style.cssText =
    'position:fixed;inset:0;z-index:99999;background:#fff;overflow:auto;';
  overlay.innerHTML = bodyMatch[1];

  const style = document.createElement('style');
  style.id = '__print_overlay_style__';
  style.textContent = [
    styleMatch ? styleMatch[1] : '',
    // During print, hide everything except the overlay.
    '@media print { body > *:not(#__print_overlay__) { display:none !important; } }',
  ].join('\n');

  document.head.appendChild(style);
  document.body.appendChild(overlay);

  const cleanup = () => {
    overlay.remove();
    style.remove();
    window.removeEventListener('afterprint', cleanup);
  };
  window.addEventListener('afterprint', cleanup);
  window.print();
}

export function printSchedule(opts: PrintOptions): void {
  const html = buildPrintHTML(opts);
  const win  = window.open('', '_blank', 'width=1100,height=750');

  if (!win) {
    // Popup blocked — inject into current page instead of printing the live UI.
    printViaOverlay(html);
    return;
  }

  win.document.open();
  win.document.write(html);
  win.document.close();

  // Guard so only one of (load event | timeout) fires win.print().
  let printed = false;
  const doPrint = () => {
    if (printed) return;
    printed = true;
    win.focus();
    win.print();
    win.addEventListener('afterprint', () => win.close());
  };

  win.addEventListener('load', doPrint);
  // Timeout handles browsers where document.write() causes load to fire
  // synchronously before the listener is registered.
  setTimeout(doPrint, 500);
}
