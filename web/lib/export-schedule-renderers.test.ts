/**
 * Contract tests for the PDF and Excel renderers in export-schedule.ts.
 *
 * These tests verify the rendering configuration (orientation, column widths,
 * frozen panes, etc.) so that layout regressions surface immediately.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ExportOptions } from './export-schedule';

// ─── shared fixtures ─────────────────────────────────────────────────────────

const opts: ExportOptions = {
  businessName: "Coley's Coffee",
  locationName: 'Downtown',
  weekLabel: 'Apr 14 – 20',
  weekStart: new Date(2025, 3, 14),
  employees: [
    { id: 'e1', name: 'Alice', role: 'Barista', roleColor: '#635BFF' },
    { id: 'e2', name: 'Bob', role: 'Shift Lead', roleColor: '#00B893' },
  ],
  shifts: [
    { employeeId: 'e1', day: 0, startHour: 9, endHour: 17 },
    { employeeId: 'e2', day: 4, startHour: 12, endHour: 20 },
  ],
};

const complianceOpts: ExportOptions = {
  ...opts,
  shifts: [
    {
      employeeId: 'e1',
      day: 0,
      startHour: 9,
      endHour: 17,
      roleName: 'Barista',
      complianceStatus: 'warning',
      compliancePremiumTotalCents: 2100,
      complianceWarningRuleCodes: ['paid_rest_break_quota'],
      complianceBlockingRuleCodes: [],
      complianceUnresolvedPremiumRuleCodes: [],
      complianceOverrideApplied: true,
      complianceOverrideArtifactId: 'artifact_123',
    },
  ],
};

// ─── PDF renderer mocks ───────────────────────────────────────────────────────

const {
  MockJsPDF,
  jsPDFInstance,
  mockAutoTable,
} = vi.hoisted(() => {
  const instance = {
    setFont: vi.fn(),
    setFontSize: vi.fn(),
    setTextColor: vi.fn(),
    text: vi.fn(),
    save: vi.fn(),
  };
  // Must use a regular function (not arrow) so it can be called with `new`.
  // eslint-disable-next-line prefer-arrow-callback
  const MockJsPDF = vi.fn(function MockJsPDFCtor() { return instance; });
  const mockAutoTable = vi.fn();
  return { MockJsPDF, jsPDFInstance: instance, mockAutoTable };
});

vi.mock('jspdf', () => ({ default: MockJsPDF }));
vi.mock('jspdf-autotable', () => ({ default: mockAutoTable }));

// ─── Excel renderer mocks ─────────────────────────────────────────────────────

const {
  MockWorkbook,
  mockWorkbookInstance,
  mockWorksheet,
  mockWriteBuffer,
} = vi.hoisted(() => {
  const mockCell = () => ({
    value: undefined as unknown,
    font: undefined as unknown,
    fill: undefined as unknown,
    alignment: undefined as unknown,
    border: undefined as unknown,
  });

  const mockWorksheet = {
    columns: [] as unknown[],
    getRow: vi.fn(() => ({ height: 0, getCell: vi.fn(mockCell) })),
    addRow: vi.fn(() => ({ height: 0, getCell: vi.fn(mockCell) })),
    mergeCells: vi.fn(),
  };

  const mockWriteBuffer = vi.fn().mockResolvedValue(new Uint8Array([0, 1, 2]));

  const mockWorkbookInstance = {
    creator: '' as string,
    addWorksheet: vi.fn(() => mockWorksheet),
    xlsx: { writeBuffer: mockWriteBuffer },
  };

  // Must use a regular function (not arrow) so it can be called with `new`.
  // eslint-disable-next-line prefer-arrow-callback
  const MockWorkbook = vi.fn(function MockWorkbookCtor() { return mockWorkbookInstance; });

  return { MockWorkbook, mockWorkbookInstance, mockWorksheet, mockWriteBuffer };
});

vi.mock('exceljs', () => ({
  default: { Workbook: MockWorkbook },
}));

// ─── DOM helpers shared by both suites ───────────────────────────────────────

function stubDomDownload() {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  vi.spyOn(document, 'createElement').mockReturnValue(
    { href: '', download: '', click: vi.fn() } as unknown as HTMLElement,
  );
}

// ─── PDF tests ───────────────────────────────────────────────────────────────

describe('exportPDF — rendering contract', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWriteBuffer.mockResolvedValue(new Uint8Array([0, 1, 2]));
    stubDomDownload();
  });

  it('initializes jsPDF in landscape letter orientation', async () => {
    const { exportPDF } = await import('./export-schedule');
    await exportPDF(opts);
    expect(MockJsPDF).toHaveBeenCalledWith({
      orientation: 'landscape',
      unit: 'pt',
      format: 'letter',
    });
  });

  it('passes the full 9-column header (Name + Role + 7 days) to autoTable', async () => {
    const { exportPDF } = await import('./export-schedule');
    await exportPDF(opts);

    expect(mockAutoTable).toHaveBeenCalledOnce();
    const [, tableOpts] = mockAutoTable.mock.calls[0] as [unknown, { head: string[][] }];
    expect(tableOpts.head[0]).toEqual([
      'Name', 'Role', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
    ]);
  });

  it('sets Name and Role columns to left-align', async () => {
    const { exportPDF } = await import('./export-schedule');
    await exportPDF(opts);

    const [, tableOpts] = mockAutoTable.mock.calls[0] as [
      unknown,
      { columnStyles: Record<number, { halign: string }> },
    ];
    expect(tableOpts.columnStyles[0].halign).toBe('left');
    expect(tableOpts.columnStyles[1].halign).toBe('left');
  });

  it('sets day columns (2–8) to center-align', async () => {
    const { exportPDF } = await import('./export-schedule');
    await exportPDF(opts);

    const [, tableOpts] = mockAutoTable.mock.calls[0] as [
      unknown,
      { columnStyles: Record<number, { halign: string }> },
    ];
    for (let i = 2; i <= 8; i++) {
      expect(tableOpts.columnStyles[i].halign).toBe('center');
    }
  });

  it('uses the dark navy header fill color (#0A2540 = [10,37,64])', async () => {
    const { exportPDF } = await import('./export-schedule');
    await exportPDF(opts);

    const [, tableOpts] = mockAutoTable.mock.calls[0] as [
      unknown,
      { headStyles: { fillColor: number[] } },
    ];
    expect(tableOpts.headStyles.fillColor).toEqual([10, 37, 64]);
  });

  it('applies alternating row fill (very light indigo tint [248,249,255])', async () => {
    const { exportPDF } = await import('./export-schedule');
    await exportPDF(opts);

    const [, tableOpts] = mockAutoTable.mock.calls[0] as [
      unknown,
      { alternateRowStyles: { fillColor: number[] } },
    ];
    expect(tableOpts.alternateRowStyles.fillColor).toEqual([248, 249, 255]);
  });

  it('renders the business · location title as the first text line', async () => {
    const { exportPDF } = await import('./export-schedule');
    await exportPDF(opts);
    const firstTextCall = jsPDFInstance.text.mock.calls[0] as [string, number, number];
    expect(firstTextCall[0]).toBe("Coley's Coffee · Downtown");
  });

  it('saves with a .pdf filename', async () => {
    const { exportPDF } = await import('./export-schedule');
    await exportPDF(opts);
    expect(jsPDFInstance.save).toHaveBeenCalledOnce();
    const [filename] = jsPDFInstance.save.mock.calls[0] as [string];
    expect(filename).toMatch(/\.pdf$/);
  });

  it('adds a second PDF table for compliance rows when present', async () => {
    const { exportPDF } = await import('./export-schedule');
    await exportPDF(complianceOpts);

    expect(mockAutoTable).toHaveBeenCalledTimes(2);
    const [, complianceTableOpts] = mockAutoTable.mock.calls[1] as [unknown, { head: string[][] }];
    expect(complianceTableOpts.head[0]).toEqual([
      'Employee',
      'Role',
      'Shift',
      'Status',
      'Premium',
      'Unresolved Premium',
      'Artifact Applied',
      'Warning Rules',
      'Blocking Rules',
    ]);
  });
});

// ─── Excel tests ──────────────────────────────────────────────────────────────

describe('exportExcel — rendering contract', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWriteBuffer.mockResolvedValue(new Uint8Array([0, 1, 2]));
    mockWorkbookInstance.addWorksheet.mockReturnValue(mockWorksheet);
    mockWorksheet.columns = [];
    stubDomDownload();
  });

  it('creates a worksheet named "Schedule" with the first 3 rows frozen', async () => {
    const { exportExcel } = await import('./export-schedule');
    await exportExcel(opts);

    // ySplit: 3 — title row, week label row, and column header row all frozen
    expect(mockWorkbookInstance.addWorksheet).toHaveBeenCalledWith('Schedule', {
      views: [{ state: 'frozen', ySplit: 3 }],
    });
  });

  it('sets Name column width to 22, Role to 18, and day columns to 20', async () => {
    const { exportExcel } = await import('./export-schedule');
    await exportExcel(opts);

    const cols = mockWorksheet.columns as { width: number }[];
    expect(cols[0].width).toBe(22); // Name
    expect(cols[1].width).toBe(18); // Role
    for (let i = 2; i < 9; i++) {
      expect(cols[i].width).toBe(20); // Mon–Sun
    }
  });

  it('calls xlsx.writeBuffer to produce the file', async () => {
    const { exportExcel } = await import('./export-schedule');
    await exportExcel(opts);
    expect(mockWriteBuffer).toHaveBeenCalledOnce();
  });

  it('triggers a download with a .xlsx filename', async () => {
    let capturedFilename: string | null = null;
    vi.spyOn(document, 'createElement').mockReturnValue(
      Object.defineProperty(
        { href: '', click: vi.fn() } as unknown as HTMLAnchorElement,
        'download',
        {
          set(v: string) { capturedFilename = v; },
          get() { return capturedFilename ?? ''; },
        },
      ),
    );

    const { exportExcel } = await import('./export-schedule');
    await exportExcel(opts);

    expect(capturedFilename).toMatch(/\.xlsx$/);
  });

  it('sets workbook creator to "Backfill"', async () => {
    const { exportExcel } = await import('./export-schedule');
    await exportExcel(opts);
    expect(mockWorkbookInstance.creator).toBe('Backfill');
  });

  it('writes the business · location title into the first frozen row', async () => {
    const titleCell = { value: undefined as unknown, font: undefined as unknown, alignment: undefined as unknown };
    mockWorksheet.getRow.mockImplementation((n: number) => ({
      height: 0,
      getCell: (ci: number) => (n === 1 && ci === 1 ? titleCell : { value: undefined, font: undefined, alignment: undefined }),
    }));

    const { exportExcel } = await import('./export-schedule');
    await exportExcel(opts);

    expect(titleCell.value).toBe("Coley's Coffee · Downtown");
  });

  it('adds a Compliance worksheet when compliance rows are present', async () => {
    const { exportExcel } = await import('./export-schedule');
    await exportExcel(complianceOpts);

    expect(mockWorkbookInstance.addWorksheet).toHaveBeenCalledWith('Compliance', {
      views: [{ state: 'frozen', ySplit: 3 }],
    });
  });
});
