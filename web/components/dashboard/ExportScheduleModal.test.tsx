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

// ─── fixtures ───────────────────────────────────────────────────────────────

const defaultProps = {
  weekLabel: 'Apr 14 – 20',
  locationName: "Coley's Coffee",
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
    renderModal();
    fireEvent.click(screen.getByRole('button', { name: /export csv/i }));
    await waitFor(() => expect(mockExportCSV).toHaveBeenCalledOnce());
    const [opts] = mockExportCSV.mock.calls[0] as [Record<string, unknown>];
    expect(opts.locationName).toBe("Coley's Coffee");
    expect(opts.weekLabel).toBe('Apr 14 – 20');
    expect(opts.employees).toHaveLength(1);
    expect(opts.shifts).toHaveLength(1);
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
