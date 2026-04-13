import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fmtHour,
  dayCell,
  safeFilename,
  buildRows,
  exportCSV,
  type ExportEmployee,
  type ExportShift,
  type ExportOptions,
} from './export-schedule';

// ─── fixtures ───────────────────────────────────────────────────────────────

const employees: ExportEmployee[] = [
  { id: 'e1', name: 'Alice Smith', role: 'Barista', roleColor: '#635BFF' },
  { id: 'e2', name: 'Bob Jones', role: 'Barista', roleColor: '#635BFF' },
  { id: 'e3', name: 'Carol Lin', role: 'Shift Lead', roleColor: '#00B893' },
];

const shifts: ExportShift[] = [
  { employeeId: 'e1', day: 0, startHour: 9, endHour: 17 },   // Mon 9–5
  { employeeId: 'e1', day: 0, startHour: 19, endHour: 22 },  // Mon 7–10 PM (double shift)
  { employeeId: 'e2', day: 2, startHour: 8.5, endHour: 14 }, // Wed 8:30–2
  { employeeId: 'e3', day: 6, startHour: 10, endHour: 18 },  // Sun 10–6
];

const baseOpts: ExportOptions = {
  businessName: "The Original Coley's LLC",
  locationName: 'Downtown',
  weekLabel: 'Apr 14 – 20',
  weekStart: new Date(2025, 3, 14), // Mon Apr 14 2025
  employees,
  shifts,
};

// ─── fmtHour ────────────────────────────────────────────────────────────────

describe('fmtHour', () => {
  it('formats whole AM hours', () => {
    expect(fmtHour(9)).toBe('9 AM');
    expect(fmtHour(11)).toBe('11 AM');
  });

  it('formats noon as 12 PM', () => {
    expect(fmtHour(12)).toBe('12 PM');
  });

  it('formats whole PM hours', () => {
    expect(fmtHour(13)).toBe('1 PM');
    expect(fmtHour(17)).toBe('5 PM');
    expect(fmtHour(22)).toBe('10 PM');
  });

  it('formats midnight (0) as 12 AM', () => {
    expect(fmtHour(0)).toBe('12 AM');
    expect(fmtHour(24)).toBe('12 AM');
  });

  it('formats fractional half-hours', () => {
    expect(fmtHour(8.5)).toBe('8:30 AM');
    expect(fmtHour(13.5)).toBe('1:30 PM');
  });

  it('pads minutes with leading zero', () => {
    // 8 hours + 5/60 ≈ 8.083
    expect(fmtHour(8 + 5 / 60)).toBe('8:05 AM');
  });
});

// ─── dayCell ────────────────────────────────────────────────────────────────

describe('dayCell', () => {
  it('returns empty string for no shifts', () => {
    expect(dayCell([])).toBe('');
  });

  it('formats a single shift', () => {
    expect(dayCell([{ employeeId: 'e1', day: 0, startHour: 9, endHour: 17 }])).toBe('9 AM – 5 PM');
  });

  it('pipe-joins multiple shifts', () => {
    const result = dayCell([
      { employeeId: 'e1', day: 0, startHour: 9, endHour: 13 },
      { employeeId: 'e1', day: 0, startHour: 16, endHour: 20 },
    ]);
    expect(result).toBe('9 AM – 1 PM | 4 PM – 8 PM');
  });
});

// ─── safeFilename ────────────────────────────────────────────────────────────

describe('safeFilename', () => {
  it('replaces spaces with underscores', () => {
    const name = safeFilename('Coley Shop', 'Apr 14', 'csv');
    expect(name).toBe('Coley_Shop_Schedule_Apr_14.csv');
  });

  it('strips special characters (apostrophes, slashes)', () => {
    const name = safeFilename("The Original Coley's LLC", 'Apr 14 – 20', 'csv');
    // apostrophe, em-dash, and spaces stripped/replaced
    expect(name).not.toMatch(/['"–]/);
    expect(name).toMatch(/\.csv$/);
  });

  it('respects the extension parameter', () => {
    expect(safeFilename('Loc', 'Week', 'xlsx')).toMatch(/\.xlsx$/);
    expect(safeFilename('Loc', 'Week', 'pdf')).toMatch(/\.pdf$/);
  });

  it('includes Schedule_ in the filename', () => {
    expect(safeFilename('Coffee Bar', 'Week 1', 'csv')).toContain('Schedule_');
  });
});

// ─── buildRows ───────────────────────────────────────────────────────────────

describe('buildRows', () => {
  it('produces the correct header', () => {
    const { header } = buildRows(baseOpts);
    expect(header).toEqual([
      'Name', 'Role', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
    ]);
  });

  it('produces one row per employee', () => {
    const { rows } = buildRows(baseOpts);
    expect(rows).toHaveLength(3);
  });

  it('puts name and role in the first two columns', () => {
    const { rows } = buildRows(baseOpts);
    expect(rows[0][0]).toBe('Alice Smith');
    expect(rows[0][1]).toBe('Barista');
    expect(rows[2][0]).toBe('Carol Lin');
    expect(rows[2][1]).toBe('Shift Lead');
  });

  it('leaves days blank when there are no shifts', () => {
    const { rows } = buildRows(baseOpts);
    // Alice has no Tuesday shift (day 1)
    expect(rows[0][3]).toBe(''); // Tuesday column (index 2 = Mon, 3 = Tue)
    // Bob has no Monday shift
    expect(rows[1][2]).toBe(''); // Monday column
  });

  it('fills the correct day columns for single shifts', () => {
    const { rows } = buildRows(baseOpts);
    // Alice: Mon (day 0) = col 2
    expect(rows[0][2]).toContain('9 AM');
    expect(rows[0][2]).toContain('5 PM');
    // Bob: Wed (day 2) = col 4
    expect(rows[1][4]).toContain('8:30 AM');
    // Carol: Sun (day 6) = col 8
    expect(rows[2][8]).toContain('10 AM');
    expect(rows[2][8]).toContain('6 PM');
  });

  it('pipe-joins double shifts in the same day', () => {
    const { rows } = buildRows(baseOpts);
    // Alice has two Mon shifts: 9–5 and 7–10 PM
    expect(rows[0][2]).toContain(' | ');
    expect(rows[0][2]).toContain('9 AM – 5 PM');
    expect(rows[0][2]).toContain('7 PM – 10 PM');
  });

  it('ignores shifts with null employeeId', () => {
    const optsWithNull: ExportOptions = {
      ...baseOpts,
      shifts: [
        ...shifts,
        { employeeId: null, day: 0, startHour: 9, endHour: 17 }, // open shift
      ],
    };
    // should not throw and should not alter any employee row
    const { rows } = buildRows(optsWithNull);
    expect(rows).toHaveLength(3);
  });
});

// ─── exportCSV ───────────────────────────────────────────────────────────────

describe('exportCSV', () => {
  let createObjectURLSpy: ReturnType<typeof vi.spyOn>;
  let revokeObjectURLSpy: ReturnType<typeof vi.spyOn>;
  let createElementSpy: ReturnType<typeof vi.spyOn>;
  let capturedBlob: Blob | null = null;
  let capturedFilename: string | null = null;

  beforeEach(() => {
    capturedBlob = null;
    capturedFilename = null;

    createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      capturedBlob = blob as Blob;
      return 'blob:fake-url';
    });
    revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);

    createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag) => {
      if (tag === 'a') {
        const anchor = { href: '', download: '', click: vi.fn() } as unknown as HTMLAnchorElement;
        Object.defineProperty(anchor, 'download', {
          get() { return capturedFilename ?? ''; },
          set(v: string) { capturedFilename = v; },
        });
        return anchor;
      }
      return document.createElement(tag); // fallback for other tags
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('triggers a download with a .csv filename', () => {
    exportCSV(baseOpts);
    expect(capturedFilename).toMatch(/\.csv$/);
  });

  it('calls URL.createObjectURL with a Blob', () => {
    exportCSV(baseOpts);
    expect(createObjectURLSpy).toHaveBeenCalledOnce();
    expect(capturedBlob).toBeInstanceOf(Blob);
  });

  it('produces a CSV Blob with the correct MIME type', () => {
    exportCSV(baseOpts);
    expect((capturedBlob as Blob).type).toContain('text/csv');
  });

  it('CSV content starts with the business · location title', async () => {
    exportCSV(baseOpts);
    const text = await (capturedBlob as Blob).text();
    expect(text.trimStart()).toMatch(/^"The Original Coley's LLC · Downtown"/);
  });

  it('CSV content contains the column header row', async () => {
    exportCSV(baseOpts);
    const text = await (capturedBlob as Blob).text();
    expect(text).toContain('"Name","Role","Monday"');
    expect(text).toContain('"Sunday"');
  });

  it('CSV content contains employee names', async () => {
    exportCSV(baseOpts);
    const text = await (capturedBlob as Blob).text();
    expect(text).toContain('Alice Smith');
    expect(text).toContain('Bob Jones');
    expect(text).toContain('Carol Lin');
  });

  it('CSV content has pipe-joined double shifts', async () => {
    exportCSV(baseOpts);
    const text = await (capturedBlob as Blob).text();
    expect(text).toContain('9 AM – 5 PM | 7 PM – 10 PM');
  });

  it('CSV content escapes internal double-quotes', async () => {
    const optsWithQuotes: ExportOptions = {
      ...baseOpts,
      employees: [{ id: 'q1', name: 'O"Brien', role: 'Server', roleColor: '#000' }],
      shifts: [],
    };
    exportCSV(optsWithQuotes);
    const text = await (capturedBlob as Blob).text();
    // RFC 4180: internal " becomes ""
    expect(text).toContain('O""Brien');
  });

  it('uses CRLF line endings', async () => {
    exportCSV(baseOpts);
    const text = await (capturedBlob as Blob).text();
    expect(text).toContain('\r\n');
  });
});
