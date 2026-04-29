import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ExportScheduleModal } from './ExportScheduleModal';

// ─── mock the heavy export library ──────────────────────────────────────────

const mockExportCSV = vi.fn();
const mockExportExcel = vi.fn().mockResolvedValue(undefined);
const mockExportPDF = vi.fn().mockResolvedValue(undefined);

vi.mock('@/lib/export-schedule', () => ({
  exportCSV: (...args: unknown[]) => mockExportCSV(...args),
  exportExcel: (...args: unknown[]) => mockExportExcel(...args),
  exportPDF: (...args: unknown[]) => mockExportPDF(...args),
}));

const mockGetLocationComplianceWeek = vi.fn();
const mockGetLocationCompliancePayrollExport = vi.fn();

vi.mock('@/lib/api/finance', () => ({
  getLocationComplianceWeek: (...args: unknown[]) => mockGetLocationComplianceWeek(...args),
  getLocationCompliancePayrollExport: (...args: unknown[]) =>
    mockGetLocationCompliancePayrollExport(...args),
}));

// ─── fixtures ───────────────────────────────────────────────────────────────

const defaultProps = {
  businessId: 'biz_1',
  locationId: 'loc_1',
  businessName: "Coley's Coffee",
  weekLabel: 'Apr 14 – 20',
  weekStartDateKey: '2025-04-14',
  locationName: 'Downtown',
  weekStart: new Date(2025, 3, 14),
  employees: [
    { id: 'e1', name: 'Alice', role: 'Barista', roleColor: '#635BFF' },
  ],
  shifts: [
    { employeeId: 'e1', day: 0, startHour: 9, endHour: 17 },
  ],
  onClose: vi.fn(),
  onExport: vi.fn(),
};

// ─── helpers ────────────────────────────────────────────────────────────────

function renderModal(overrides = {}) {
  return render(<ExportScheduleModal {...defaultProps} {...overrides} />);
}

// ─── format selection ────────────────────────────────────────────────────────

describe('ExportScheduleModal — format selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetLocationComplianceWeek.mockResolvedValue(null);
    mockGetLocationCompliancePayrollExport.mockResolvedValue(null);
  });

  it('renders all three format labels', () => {
    renderModal();
    expect(screen.getByText('CSV')).toBeInTheDocument();
    expect(screen.getByText('Excel')).toBeInTheDocument();
    expect(screen.getByText('PDF')).toBeInTheDocument();
  });

  it('renders the CSV format description copy', () => {
    renderModal();
    expect(
      screen.getByText('Comma-separated values — opens in Excel or Google Sheets'),
    ).toBeInTheDocument();
  });

  it('renders the Excel format description copy', () => {
    renderModal();
    expect(
      screen.getByText('Formatted Microsoft Excel workbook (.xlsx)'),
    ).toBeInTheDocument();
  });

  it('renders the PDF format description copy', () => {
    renderModal();
    expect(screen.getByText('Print-ready landscape document')).toBeInTheDocument();
  });

  it('renders the week label as the modal subtitle', () => {
    renderModal();
    expect(screen.getByText('Apr 14 – 20')).toBeInTheDocument();
  });

  it('defaults to CSV and shows "Export CSV" on the button', () => {
    renderModal();
    expect(screen.getByRole('button', { name: /export csv/i })).toBeInTheDocument();
  });

  it('clicking Excel changes the export button label to "Export EXCEL"', () => {
    renderModal();
    fireEvent.click(screen.getByText('Excel'));
    expect(screen.getByRole('button', { name: /export excel/i })).toBeInTheDocument();
  });

  it('clicking PDF changes the export button label to "Export PDF"', () => {
    renderModal();
    fireEvent.click(screen.getByText('PDF'));
    expect(screen.getByRole('button', { name: /export pdf/i })).toBeInTheDocument();
  });

  it('switching format updates the button label back when re-selecting CSV', () => {
    renderModal();
    fireEvent.click(screen.getByText('PDF'));
    fireEvent.click(screen.getByText('CSV'));
    expect(screen.getByRole('button', { name: /export csv/i })).toBeInTheDocument();
  });
});

// ─── export trigger ──────────────────────────────────────────────────────────

describe('ExportScheduleModal — export trigger', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetLocationComplianceWeek.mockResolvedValue(null);
    mockGetLocationCompliancePayrollExport.mockResolvedValue(null);
  });

  it('calls exportCSV when CSV is selected and Export is clicked', async () => {
    renderModal();
    fireEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await waitFor(() => expect(mockExportCSV).toHaveBeenCalledOnce());
    expect(mockExportExcel).not.toHaveBeenCalled();
    expect(mockExportPDF).not.toHaveBeenCalled();
  });

  it('calls exportExcel when Excel is selected and Export is clicked', async () => {
    renderModal();
    fireEvent.click(screen.getByText('Excel'));
    fireEvent.click(screen.getByRole('button', { name: /export excel/i }));
    await waitFor(() => expect(mockExportExcel).toHaveBeenCalledOnce());
    expect(mockExportCSV).not.toHaveBeenCalled();
  });

  it('calls exportPDF when PDF is selected and Export is clicked', async () => {
    renderModal();
    fireEvent.click(screen.getByText('PDF'));
    fireEvent.click(screen.getByRole('button', { name: /export pdf/i }));
    await waitFor(() => expect(mockExportPDF).toHaveBeenCalledOnce());
    expect(mockExportCSV).not.toHaveBeenCalled();
  });

  it('calls onExport after a successful CSV export', async () => {
    const onExport = vi.fn();
    renderModal({ onExport });
    fireEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await waitFor(() => expect(onExport).toHaveBeenCalledOnce());
  });

  it('passes the correct opts to exportCSV', async () => {
    mockGetLocationComplianceWeek.mockResolvedValue({
      location_id: 'loc_1',
      week_start_date: '2025-04-14',
      week_end_date: '2025-04-20',
      shift_count: 1,
      assigned_shift_count: 1,
      employee_count: 1,
      warning_assignment_count: 0,
      blocked_assignment_count: 0,
      unresolved_premium_assignment_count: 1,
      premium_total_cents: 1800,
      override_applied_count: 0,
      warning_rule_codes: [],
      premium_rule_codes: ['meal_break_first_window'],
      unresolved_premium_rule_codes: ['split_shift_premium'],
      artifact_type_counts: [],
      shifts: [],
      employees: [],
      override_artifacts: [],
    });
    mockGetLocationCompliancePayrollExport.mockResolvedValue({
      location_id: 'loc_1',
      week_start_date: '2025-04-14',
      week_end_date: '2025-04-20',
      row_count: 1,
      premium_payment_row_count: 1,
      ready_adjustment_row_count: 1,
      manual_review_row_count: 1,
      missing_employee_identifier_row_count: 1,
      artifact_record_row_count: 1,
      total_premium_cents: 1800,
      rows: [],
    });
    renderModal();
    await waitFor(() =>
      expect(mockGetLocationCompliancePayrollExport).toHaveBeenCalledWith(
        'biz_1',
        'loc_1',
        '2025-04-14',
      ),
    );
    await waitFor(() => expect(screen.getByText('Ready Rows')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await waitFor(() => expect(mockExportCSV).toHaveBeenCalledOnce());
    const [opts] = mockExportCSV.mock.calls[0] as [Record<string, unknown>];
    expect(opts.businessName).toBe("Coley's Coffee");
    expect(opts.locationName).toBe('Downtown');
    expect(opts.weekLabel).toBe('Apr 14 – 20');
    expect(opts.employees).toHaveLength(1);
    expect(opts.shifts).toHaveLength(1);
    expect(opts.compliancePayrollExport).toMatchObject({
      location_id: 'loc_1',
      premium_payment_row_count: 1,
      ready_adjustment_row_count: 1,
      manual_review_row_count: 1,
    });
    expect(screen.getByText('Missing IDs')).toBeInTheDocument();
    expect(
      screen.getByText(/some payroll consequence rows still require manual handling/i),
    ).toBeInTheDocument();
  });
});

// ─── cancel / close ──────────────────────────────────────────────────────────

describe('ExportScheduleModal — cancel / close', () => {
  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when the X button is clicked', () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    // The X button is the close icon button in the header
    const closeButtons = screen.getAllByRole('button');
    // X button has no accessible name — find by aria-label absence; it's the first button
    const xButton = closeButtons.find((btn) => btn.querySelector('svg'));
    if (xButton) fireEvent.click(xButton);
    expect(onClose).toHaveBeenCalled();
  });
});

// ─── dark mode ───────────────────────────────────────────────────────────────

describe('ExportScheduleModal — dark prop', () => {
  it('renders without errors in dark mode', () => {
    expect(() => renderModal({ dark: true })).not.toThrow();
  });
});
