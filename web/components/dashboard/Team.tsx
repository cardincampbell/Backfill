"use client";

import { useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Plus,
  Upload,
  Search,
  Filter,
  Mail,
  Phone,
  ChevronDown,
  X,
  CheckCircle2,
  AlertCircle,
  FileSpreadsheet,
  UserPlus,
  ArrowUpDown,
  Download,
  Eye,
  Trash2,
  MapPin,
  Activity,
  Tag,
  Shield as ShieldCheck,
  Info,
} from 'lucide-react';
import { useResolvedAppAppearance } from '@/components/app-session-gate';
import DashboardShell from './DashboardShell';

/* ─── Types ─── */
interface EmployeeLocation {
  name: string;
  emoji: string;
  primary: boolean;
}

interface Employee {
  id: number;
  name: string;
  email: string;
  phone: string;
  roles: string[];
  locations: EmployeeLocation[];
  status: 'available-now' | 'available-later' | 'on-shift' | 'off-today' | 'on-leave';
  reliability: number;
  avatar: string;
}

/* ─── Curated roles from onboarding ─── */
const curatedRoles = [
  'RN', 'LPN', 'CNA', 'NP', 'PA', 'Medical Assistant', 'Phlebotomist',
  'Respiratory Therapist', 'Radiology Tech', 'Surgical Tech', 'EMT',
  'Caregiver', 'Server Lead', 'Host', 'Bartender', 'Line Cook',
];

/* ─── All business locations ─── */
const allBusinessLocations = [
  { name: 'Downtown Medical Center', emoji: '\u{1F3E5}' },
  { name: 'Sunrise Senior Living', emoji: '\u{1F305}' },
  { name: 'Bay Area Staffing Co.', emoji: '\u{1F3E2}' },
  { name: 'Coastal Hospitality Group', emoji: '\u{1F3E8}' },
];

/* ─── Mock Data ─── */
const employees: Employee[] = [
  { id: 1, name: 'Sarah Martinez', email: 'sarah.m@backfill.io', phone: '(415) 555-0142', roles: ['RN'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }, { name: 'Bay Area Staffing Co.', emoji: '\u{1F3E2}', primary: false }], status: 'available-now', reliability: 98, avatar: 'SM' },
  { id: 2, name: 'James Chen', email: 'james.c@backfill.io', phone: '(415) 555-0198', roles: ['LPN'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }], status: 'on-shift', reliability: 96, avatar: 'JC' },
  { id: 3, name: 'Aisha Patel', email: 'aisha.p@backfill.io', phone: '(415) 555-0176', roles: ['CNA'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }], status: 'available-now', reliability: 94, avatar: 'AP' },
  { id: 4, name: 'Emily Ross', email: 'emily.r@backfill.io', phone: '(510) 555-0234', roles: ['Caregiver'], locations: [{ name: 'Sunrise Senior Living', emoji: '\u{1F305}', primary: true }], status: 'available-later', reliability: 99, avatar: 'ER' },
  { id: 5, name: 'David Kim', email: 'david.k@backfill.io', phone: '(510) 555-0187', roles: ['CNA'], locations: [{ name: 'Sunrise Senior Living', emoji: '\u{1F305}', primary: true }], status: 'on-leave', reliability: 91, avatar: 'DK' },
  { id: 6, name: 'Carlos Rivera', email: 'carlos.r@backfill.io', phone: '(408) 555-0165', roles: ['RN', 'EMT'], locations: [{ name: 'Bay Area Staffing Co.', emoji: '\u{1F3E2}', primary: true }, { name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: false }], status: 'on-shift', reliability: 97, avatar: 'CR' },
  { id: 7, name: 'Mia Johnson', email: 'mia.j@backfill.io', phone: '(831) 555-0119', roles: ['Server Lead'], locations: [{ name: 'Coastal Hospitality Group', emoji: '\u{1F3E8}', primary: true }], status: 'available-now', reliability: 99, avatar: 'MJ' },
  { id: 8, name: 'Marcus Thompson', email: 'marcus.t@backfill.io', phone: '(415) 555-0203', roles: ['RN'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }], status: 'off-today', reliability: 85, avatar: 'MT' },
  { id: 9, name: 'Priya Sharma', email: 'priya.s@backfill.io', phone: '(408) 555-0291', roles: ['LPN', 'Phlebotomist'], locations: [{ name: 'Bay Area Staffing Co.', emoji: '\u{1F3E2}', primary: true }], status: 'available-now', reliability: 95, avatar: 'PS' },
  { id: 10, name: 'Alex Morgan', email: 'alex.m@backfill.io', phone: '(510) 555-0148', roles: ['Caregiver'], locations: [{ name: 'Sunrise Senior Living', emoji: '\u{1F305}', primary: true }], status: 'off-today', reliability: 96, avatar: 'AM' },
  { id: 11, name: 'Jordan Lee', email: 'jordan.l@backfill.io', phone: '(415) 555-0177', roles: ['CNA'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }], status: 'available-later', reliability: 92, avatar: 'JL' },
  { id: 12, name: 'Nina Patel', email: 'nina.p@backfill.io', phone: '(831) 555-0205', roles: ['Bartender', 'Host'], locations: [{ name: 'Coastal Hospitality Group', emoji: '\u{1F3E8}', primary: true }], status: 'available-now', reliability: 94, avatar: 'NP' },
];

const roleColors: Record<string, string> = {
  'RN': '#635BFF', 'LPN': '#3B82F6', 'CNA': '#00B893', 'Caregiver': '#8B5CF6',
  'Temp RN': '#F59E0B', 'Temp LPN': '#F59E0B', 'Server Lead': '#FF6B35', 'Bartender': '#E5484D',
};

const statusConfig = {
  'available-now': { label: 'Available now', color: '#00B893', bg: '#00B893', description: 'Can be scheduled for a shift today' },
  'available-later': { label: 'Available later', color: '#3B82F6', bg: '#3B82F6', description: 'Available after 5PM today' },
  'on-shift': { label: 'On shift', color: '#635BFF', bg: '#635BFF', description: 'Currently working' },
  'off-today': { label: 'Off today', color: '#F59E0B', bg: '#F59E0B', description: 'Not available today' },
  'on-leave': { label: 'On leave', color: '#8898AA', bg: '#8898AA', description: 'Extended unavailability' },
};

/* ─── Status Info Tooltip ─── */
function StatusWithInfo({
  status,
  dark = false,
}: {
  status: keyof typeof statusConfig;
  dark?: boolean;
}) {
  const [showTooltip, setShowTooltip] = useState(false);
  const cfg = statusConfig[status];
  return (
    <div className="flex items-center gap-1.5 relative">
      <div className="w-1.5 h-1.5 rounded-full" style={{ background: cfg.color }} />
      <span className="text-[12px]" style={{ fontWeight: 460, color: cfg.color }}>{cfg.label}</span>
      <div className="relative"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}>
        <Info size={12} className={`cursor-help transition-colors ${dark ? 'text-[#5E6D7A] hover:text-[#C1CED8]' : 'text-[#C1CED8] hover:text-[#8898AA]'}`} />
        <AnimatePresence>
          {showTooltip && (
            <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
              className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 w-48 px-3 py-2 rounded-lg bg-[#0A2540] shadow-xl pointer-events-none">
              <p className="text-[11px] text-white text-center" style={{ fontWeight: 440 }}>{cfg.description}</p>
              <div className="absolute top-full left-1/2 -translate-x-1/2 w-2 h-2 bg-[#0A2540] rotate-45 -mt-1" />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

const locationOptions = ['All Locations', 'Downtown Medical Center', 'Sunrise Senior Living', 'Bay Area Staffing Co.', 'Coastal Hospitality Group'];
const statusOptions = ['All Status', 'Available now', 'Available later', 'On shift', 'Off today', 'On leave'];

function getPrimaryLocation(emp: Employee) {
  return emp.locations.find((l) => l.primary) || emp.locations[0];
}

function getReliabilityColor(r: number) {
  if (r >= 95) return '#00B893';
  if (r >= 85) return '#F59E0B';
  return '#E5484D';
}

function getTeamTheme(dark: boolean) {
  return {
    textPrimary: dark ? 'text-white' : 'text-[#0A2540]',
    textSecondary: dark ? 'text-[#C1CED8]' : 'text-[#8898AA]',
    textTertiary: dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]',
    rowText: dark ? 'text-[#C1CED8]' : 'text-[#3E4C59]',
    panelClass: dark
      ? 'bg-[#0F2E4C] border-white/[0.06] shadow-[0_18px_48px_rgba(0,0,0,0.28)]'
      : 'bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]',
    overlayPanelClass: dark ? 'bg-[#0F2E4C] border-white/[0.08]' : 'bg-white border-[#E5E7EB]',
    borderClass: dark ? 'border-white/[0.06]' : 'border-[#F0F0F5]',
    subtleBorderClass: dark ? 'border-white/[0.08]' : 'border-[#E5E7EB]',
    subtleSurfaceClass: dark ? 'bg-white/[0.04]' : 'bg-[#F7F8FA]',
    softSurfaceClass: dark ? 'bg-white/[0.03]' : 'bg-[#FAFBFC]',
    rowHoverClass: dark ? 'hover:bg-white/[0.03]' : 'hover:bg-[#FAFBFC]',
    rowBorderClass: dark ? 'border-white/[0.06]' : 'border-[#F7F8FA]',
    dropdownClass: dark
      ? 'bg-[#0F2E4C] border-white/[0.08] shadow-[0_24px_60px_rgba(0,0,0,0.35)]'
      : 'bg-white border-[#E5E7EB] shadow-xl',
    inputClass: dark
      ? 'border-white/[0.08] bg-white/[0.04] text-white placeholder-[#8898AA]/60'
      : 'border-[#E5E7EB] bg-white text-[#0A2540] placeholder-[#8898AA]/50',
    filterButtonClass: dark
      ? 'bg-white/[0.04] border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]'
      : 'bg-white border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]',
    secondaryButtonClass: dark
      ? 'border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]'
      : 'border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]',
    closeButtonClass: dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]',
    pillClass: dark ? 'bg-white/[0.06] text-[#C1CED8]' : 'bg-[#F7F8FA] text-[#8898AA]',
    emptyIconClass: dark ? 'text-white/[0.16]' : 'text-[#E5E7EB]',
  };
}

/* ─── Add Employee Modal ─── */
function AddEmployeeModal({
  dark,
  onClose,
}: {
  dark: boolean;
  onClose: () => void;
}) {
  const theme = getTeamTheme(dark);
  const [formData, setFormData] = useState({
    firstName: '', lastName: '', email: '', phone: '', role: '', location: '',
  });

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}>
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
        className={`w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden mx-4 sm:mx-0 border ${theme.overlayPanelClass}`}
        onClick={(e) => e.stopPropagation()}>
        <div className={`flex items-center justify-between px-4 sm:px-6 py-5 border-b ${theme.borderClass}`}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#635BFF]/10 flex items-center justify-center">
              <UserPlus size={18} className="text-[#635BFF]" />
            </div>
            <div>
              <h2 className={`text-[16px] ${theme.textPrimary}`} style={{ fontWeight: 600 }}>Add Employee</h2>
              <p className={`text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Add a new team member to your roster</p>
            </div>
          </div>
          <button onClick={onClose} className={`p-2 rounded-lg transition-colors ${theme.closeButtonClass}`}>
            <X size={18} className="text-[#8898AA]" />
          </button>
        </div>

        <div className="px-4 sm:px-6 py-5 space-y-4 max-h-[60vh] overflow-y-auto">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>First Name</label>
              <input type="text" value={formData.firstName} onChange={(e) => setFormData({ ...formData, firstName: e.target.value })}
                className={`w-full px-3.5 py-2.5 rounded-lg border text-[13px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${theme.inputClass}`}
                style={{ fontWeight: 440 }} placeholder="Sarah" />
            </div>
            <div>
              <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Last Name</label>
              <input type="text" value={formData.lastName} onChange={(e) => setFormData({ ...formData, lastName: e.target.value })}
                className={`w-full px-3.5 py-2.5 rounded-lg border text-[13px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${theme.inputClass}`}
                style={{ fontWeight: 440 }} placeholder="Martinez" />
            </div>
          </div>

          <div>
            <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Email</label>
            <input type="email" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className={`w-full px-3.5 py-2.5 rounded-lg border text-[13px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${theme.inputClass}`}
              style={{ fontWeight: 440 }} placeholder="sarah.m@company.com" />
          </div>

          <div>
            <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Phone</label>
            <input type="tel" value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              className={`w-full px-3.5 py-2.5 rounded-lg border text-[13px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${theme.inputClass}`}
              style={{ fontWeight: 440 }} placeholder="(415) 555-0142" />
          </div>

          <div>
            <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Role</label>
            <select value={formData.role} onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              className={`w-full px-3.5 py-2.5 rounded-lg border text-[13px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all appearance-none ${theme.inputClass}`}
              style={{ fontWeight: 440 }}>
              <option value="">Select role</option>
              {curatedRoles.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Location</label>
            <select value={formData.location} onChange={(e) => setFormData({ ...formData, location: e.target.value })}
              className={`w-full px-3.5 py-2.5 rounded-lg border text-[13px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all appearance-none ${theme.inputClass}`}
              style={{ fontWeight: 440 }}>
              <option value="">Select location</option>
              {locationOptions.slice(1).map((l) => <option key={l}>{l}</option>)}
            </select>
          </div>
        </div>

        <div className={`flex items-center justify-end gap-3 px-4 sm:px-6 py-4 border-t ${theme.borderClass} ${theme.softSurfaceClass}`}>
          <button onClick={onClose}
            className={`px-4 py-2.5 rounded-lg text-[13px] border transition-all ${theme.secondaryButtonClass}`}
            style={{ fontWeight: 480 }}>
            Cancel
          </button>
          <button
            className="px-5 py-2.5 rounded-lg text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_20px_rgba(99,91,255,0.25)]"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
            Add Employee
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Bulk Upload Modal ─── */
function BulkUploadModal({
  dark,
  onClose,
}: {
  dark: boolean;
  onClose: () => void;
}) {
  const theme = getTeamTheme(dark);
  const fileRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) simulateUpload(file.name);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) simulateUpload(file.name);
  };

  const simulateUpload = (name: string) => {
    setUploadedFile(name);
    setUploadProgress(0);
    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 100) { clearInterval(interval); return 100; }
        return prev + 15;
      });
    }, 200);
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
        className={`w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden border ${theme.overlayPanelClass}`}
        onClick={(e) => e.stopPropagation()}>
        <div className={`flex items-center justify-between px-6 py-5 border-b ${theme.borderClass}`}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#00B893]/10 flex items-center justify-center">
              <Upload size={18} className="text-[#00B893]" />
            </div>
            <div>
              <h2 className={`text-[16px] ${theme.textPrimary}`} style={{ fontWeight: 600 }}>Bulk Upload</h2>
              <p className={`text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Import employees from a CSV or Excel file</p>
            </div>
          </div>
          <button onClick={onClose} className={`p-2 rounded-lg transition-colors ${theme.closeButtonClass}`}>
            <X size={18} className="text-[#8898AA]" />
          </button>
        </div>

        <div className="px-6 py-6">
          <div className={`mb-5 flex items-center gap-3 p-3.5 rounded-xl border ${
            dark
              ? 'bg-[#635BFF]/[0.08] border-[#635BFF]/20'
              : 'bg-[#635BFF]/[0.04] border-[#635BFF]/10'
          }`}>
            <FileSpreadsheet size={18} className="text-[#635BFF] shrink-0" />
            <div className="flex-1">
              <p className={`text-[12px] ${theme.textPrimary}`} style={{ fontWeight: 500 }}>Need a template?</p>
              <p className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Download our CSV template with the required columns.</p>
            </div>
            <button className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[11px] text-[#635BFF] transition-all ${dark ? 'bg-white/[0.04] border-white/[0.08] hover:bg-white/[0.06]' : 'bg-white border-[#E5E7EB] hover:bg-[#F7F8FA]'}`}
              style={{ fontWeight: 500 }}>
              <Download size={12} /> Template
            </button>
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            className={`relative cursor-pointer rounded-xl border-2 border-dashed transition-all duration-300 p-8 text-center ${
              isDragging ? 'border-[#635BFF] bg-[#635BFF]/[0.08]' :
              uploadedFile ? 'border-[#00B893]/40 bg-[#00B893]/[0.06]' :
              dark ? 'border-white/[0.08] hover:border-[#635BFF]/30 hover:bg-white/[0.04]' :
              'border-[#E5E7EB] hover:border-[#635BFF]/30 hover:bg-[#F7F8FA]'
            }`}>
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleFileSelect} className="hidden" />
            
            {uploadedFile ? (
              <div>
                <div className="w-12 h-12 rounded-full bg-[#00B893]/10 flex items-center justify-center mx-auto mb-3">
                  {uploadProgress >= 100 ? (
                    <CheckCircle2 size={24} className="text-[#00B893]" />
                  ) : (
                    <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
                      <Activity size={20} className="text-[#00B893]" />
                    </motion.div>
                  )}
                </div>
                <p className={`mb-1 text-[13px] ${theme.textPrimary}`} style={{ fontWeight: 520 }}>{uploadedFile}</p>
                {uploadProgress < 100 ? (
                  <div className="w-48 mx-auto">
                    <div className={`mt-2 h-1.5 rounded-full overflow-hidden ${dark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]'}`}>
                      <motion.div className="h-full rounded-full bg-gradient-to-r from-[#00B893] to-[#00D4AA]"
                        initial={{ width: 0 }} animate={{ width: `${Math.min(uploadProgress, 100)}%` }} />
                    </div>
                    <p className={`mt-1.5 text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Processing...</p>
                  </div>
                ) : (
                  <p className="text-[12px] text-[#00B893]" style={{ fontWeight: 480 }}>Ready to import {'\u2022'} 24 employees found</p>
                )}
              </div>
            ) : (
              <div>
                <div className={`w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3 ${theme.subtleSurfaceClass}`}>
                  <Upload size={20} className="text-[#8898AA]" />
                </div>
                <p className={`mb-1 text-[13px] ${theme.textPrimary}`} style={{ fontWeight: 520 }}>Drop your file here, or click to browse</p>
                <p className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Supports CSV, XLS, XLSX {'\u2022'} Max 5MB</p>
              </div>
            )}
          </div>

          {uploadedFile && uploadProgress >= 100 && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.1 }}
              className={`mt-4 p-4 rounded-xl border ${theme.subtleBorderClass} ${theme.subtleSurfaceClass}`}>
              <p className={`mb-3 text-[11px] uppercase tracking-[0.04em] ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Column Mapping Preview</p>
              <div className="space-y-2">
                {[
                  { csv: 'full_name', mapped: 'Employee Name', icon: '\u2713' },
                  { csv: 'email_address', mapped: 'Email', icon: '\u2713' },
                  { csv: 'phone', mapped: 'Phone Number', icon: '\u2713' },
                  { csv: 'job_title', mapped: 'Role', icon: '\u2713' },
                  { csv: 'work_location', mapped: 'Location', icon: '\u2713' },
                ].map((col) => (
                  <div key={col.csv} className="flex items-center gap-3 text-[12px]">
                    <span className="text-[#00B893]">{col.icon}</span>
                    <span className={`w-28 truncate ${theme.textSecondary}`} style={{ fontWeight: 420 }}>{col.csv}</span>
                    <span className={theme.textSecondary}>{'\u2192'}</span>
                    <span className={theme.textPrimary} style={{ fontWeight: 480 }}>{col.mapped}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </div>

        <div className={`flex items-center justify-end gap-3 px-6 py-4 border-t ${theme.borderClass} ${theme.softSurfaceClass}`}>
          <button onClick={onClose}
            className={`px-4 py-2.5 rounded-lg text-[13px] border transition-all ${theme.secondaryButtonClass}`}
            style={{ fontWeight: 480 }}>
            Cancel
          </button>
          <button
            className={`px-5 py-2.5 rounded-lg text-[13px] text-white transition-all duration-300 ${
              uploadedFile && uploadProgress >= 100 ? 'hover:shadow-[0_0_20px_rgba(0,184,147,0.25)]' : 'opacity-40 cursor-not-allowed'
            }`}
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #00B893, #00D4AA)' }}
            disabled={!uploadedFile || uploadProgress < 100}>
            Import 24 Employees
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Employee Detail Slide-over ─── */
function EmployeeDetail({
  dark,
  employee,
  onClose,
}: {
  dark: boolean;
  employee: Employee;
  onClose: () => void;
}) {
  const theme = getTeamTheme(dark);
  const primaryRole = employee.roles[0] || 'Unassigned';
  const color = roleColors[primaryRole] || '#635BFF';
  const empStatus = statusConfig[employee.status];
  const reliabilityColor = getReliabilityColor(employee.reliability);

  const [email, setEmail] = useState(employee.email);
  const [phone, setPhone] = useState(employee.phone);
  const [roles, setRoles] = useState<string[]>(employee.roles);
  const [locations, setLocations] = useState<EmployeeLocation[]>(employee.locations);
  const [customRole, setCustomRole] = useState('');

  const availableRoles = curatedRoles.filter((r) => !roles.includes(r));
  const availableLocations = allBusinessLocations.filter((bl) => !locations.some((l) => l.name === bl.name));

  const addRole = (role: string) => setRoles((prev) => [...prev, role]);
  const removeRole = (role: string) => setRoles((prev) => prev.filter((r) => r !== role));
  const addAllRoles = () => setRoles((prev) => [...new Set([...prev, ...curatedRoles])]);
  const addCustom = () => {
    const trimmed = customRole.trim();
    if (trimmed && !roles.includes(trimmed)) {
      setRoles((prev) => [...prev, trimmed]);
      setCustomRole('');
    }
  };

  const addLocation = (loc: { name: string; emoji: string }) => {
    setLocations((prev) => [...prev, { ...loc, primary: prev.length === 0 }]);
  };
  const removeLocation = (name: string) => {
    setLocations((prev) => {
      const next = prev.filter((l) => l.name !== name);
      if (next.length > 0 && !next.some((l) => l.primary)) {
        next[0].primary = true;
      }
      return [...next];
    });
  };
  const setPrimary = (name: string) => {
    setLocations((prev) => prev.map((l) => ({ ...l, primary: l.name === name })));
  };
  const addAllLocations = () => {
    setLocations((prev) => {
      const existing = new Set(prev.map((l) => l.name));
      const newLocs = allBusinessLocations.filter((bl) => !existing.has(bl.name)).map((bl) => ({ ...bl, primary: false }));
      return [...prev, ...newLocs];
    });
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"
      onClick={onClose}>
      <motion.div initial={{ x: 460 }} animate={{ x: 0 }} exit={{ x: 460 }}
        transition={{ duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
        className={`w-full sm:w-[460px] h-full shadow-2xl flex flex-col overflow-hidden ${theme.overlayPanelClass}`}
        onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={`px-6 py-5 border-b shrink-0 ${theme.borderClass}`}>
          <div className="flex items-center justify-between mb-4">
            <button onClick={onClose} className={`p-1.5 rounded-lg transition-colors ${theme.closeButtonClass}`}>
              <X size={18} className="text-[#8898AA]" />
            </button>
            <button
              className="px-4 py-2 rounded-full text-[12px] text-white transition-all duration-300 hover:shadow-[0_0_16px_rgba(99,91,255,0.25)]"
              style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
              Save Changes
            </button>
          </div>
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-[16px] text-white shrink-0"
              style={{ fontWeight: 600, background: `linear-gradient(135deg, ${color}, ${color}CC)` }}>
              {employee.avatar}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2.5">
                <h2 className={`text-[18px] tracking-[-0.01em] truncate ${theme.textPrimary}`} style={{ fontWeight: 600 }}>{employee.name}</h2>
                <div className="flex items-center gap-1 px-2 py-0.5 rounded-full shrink-0" style={{ background: `${reliabilityColor}12` }}>
                  <ShieldCheck size={12} style={{ color: reliabilityColor }} />
                  <span className="text-[12px] tabular-nums" style={{ fontWeight: 580, color: reliabilityColor }}>{employee.reliability}%</span>
                </div>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ fontWeight: 480, color: empStatus.color, background: `${empStatus.bg}15` }}>{empStatus.label}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* Editable Contact */}
          <div>
            <h3 className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-3" style={{ fontWeight: 500 }}>Contact</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Email</label>
                <div className="relative">
                  <div className={`absolute left-3 top-1/2 -translate-y-1/2 w-7 h-7 rounded-md flex items-center justify-center ${theme.subtleSurfaceClass}`}>
                    <Mail size={13} className="text-[#8898AA]" />
                  </div>
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                    className={`w-full pl-12 pr-3.5 py-2.5 rounded-lg border text-[13px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${theme.inputClass}`}
                    style={{ fontWeight: 440 }} />
                </div>
              </div>
              <div>
                <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Phone</label>
                <div className="relative">
                  <div className={`absolute left-3 top-1/2 -translate-y-1/2 w-7 h-7 rounded-md flex items-center justify-center ${theme.subtleSurfaceClass}`}>
                    <Phone size={13} className="text-[#8898AA]" />
                  </div>
                  <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
                    className={`w-full pl-12 pr-3.5 py-2.5 rounded-lg border text-[13px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${theme.inputClass}`}
                    style={{ fontWeight: 440 }} />
                </div>
              </div>
            </div>
          </div>

          {/* Locations */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 500 }}>Locations</h3>
              <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>{locations.length} assigned</span>
            </div>
            <div className="space-y-2 mb-4">
              <AnimatePresence>
                {locations.map((loc) => (
                  <motion.div key={loc.name} layout initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                    className={`flex items-center gap-3 p-2.5 rounded-lg border ${theme.subtleBorderClass} ${dark ? 'bg-white/[0.03]' : 'bg-white'}`}>
                    <span className="text-[16px]">{loc.emoji}</span>
                    <div className="flex-1 min-w-0">
                      <p className={`text-[12px] truncate ${theme.textPrimary}`} style={{ fontWeight: 480 }}>{loc.name}</p>
                    </div>
                    <button onClick={() => setPrimary(loc.name)}
                      className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] transition-all ${
                        loc.primary
                          ? 'bg-[#635BFF]/10 text-[#635BFF] border border-[#635BFF]/20'
                          : `${theme.subtleSurfaceClass} text-[#8898AA] border border-transparent hover:border-[#635BFF]/20 hover:text-[#635BFF]`
                      }`}
                      style={{ fontWeight: loc.primary ? 540 : 440 }}>
                      {loc.primary ? 'Primary' : 'Set Primary'}
                    </button>
                    <button onClick={() => removeLocation(loc.name)} className={`p-0.5 rounded transition-colors ${theme.closeButtonClass}`}>
                      <X size={13} className="text-[#8898AA] hover:text-[#E5484D]" />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
              {locations.length === 0 && (
                <p className={`text-[12px] py-2 ${theme.textSecondary}`} style={{ fontWeight: 420 }}>No locations assigned. Add from the list below.</p>
              )}
            </div>

            {availableLocations.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2.5">
                  <h3 className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 500 }}>Available Locations</h3>
                  {availableLocations.length > 1 && (
                    <button onClick={addAllLocations}
                      className="text-[11px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors" style={{ fontWeight: 520 }}>
                      + Add All
                    </button>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {availableLocations.map((loc) => (
                    <button key={loc.name} onClick={() => addLocation(loc)}
                      className={`group flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all duration-200 ${
                        dark
                          ? 'bg-white/[0.03] border-white/[0.08] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]'
                          : 'bg-[#F7F8FA] border-[#E5E7EB] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]'
                      }`}>
                      <Plus size={11} className="text-[#8898AA] group-hover:text-[#635BFF] transition-colors" />
                      <span className="text-[14px] mr-0.5">{loc.emoji}</span>
                      <span className={`text-[12px] transition-colors ${dark ? 'text-[#C1CED8] group-hover:text-white' : 'text-[#5E6D7A] group-hover:text-[#0A2540]'}`} style={{ fontWeight: 440 }}>{loc.name.split(' ')[0]}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Roles */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 500 }}>Roles</h3>
              <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>{roles.length} roles</span>
            </div>
            <div className="flex flex-wrap gap-2 mb-4">
              <AnimatePresence>
                {roles.map((role) => (
                  <motion.div key={role} layout initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                    className={`flex items-center gap-1.5 pl-3 pr-2 py-1.5 rounded-lg border ${
                      dark
                        ? 'bg-[#635BFF]/[0.12] border-[#635BFF]/25'
                        : 'bg-[#635BFF]/[0.06] border-[#635BFF]/15'
                    }`}>
                    <Tag size={11} className="text-[#635BFF]" />
                    <span className={`text-[12px] ${theme.textPrimary}`} style={{ fontWeight: 480 }}>{role}</span>
                    <button onClick={() => removeRole(role)} className="p-0.5 rounded hover:bg-[#635BFF]/10 transition-colors ml-0.5">
                      <X size={12} className="text-[#8898AA] hover:text-[#E5484D]" />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
              {roles.length === 0 && (
                <p className={`text-[12px] py-2 ${theme.textSecondary}`} style={{ fontWeight: 420 }}>No roles assigned yet. Add from the list below.</p>
              )}
            </div>

            {availableRoles.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2.5">
                  <h3 className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 500 }}>Available Roles</h3>
                  <button onClick={addAllRoles}
                    className="text-[11px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors" style={{ fontWeight: 520 }}>
                    + Add All
                  </button>
                </div>
                <div className="flex flex-wrap gap-2 mb-4">
                  {availableRoles.map((role) => (
                    <button key={role} onClick={() => addRole(role)}
                      className={`group flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all duration-200 ${
                        dark
                          ? 'bg-white/[0.03] border-white/[0.08] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]'
                          : 'bg-[#F7F8FA] border-[#E5E7EB] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]'
                      }`}>
                      <Plus size={11} className="text-[#8898AA] group-hover:text-[#635BFF] transition-colors" />
                      <span className={`text-[12px] transition-colors ${dark ? 'text-[#C1CED8] group-hover:text-white' : 'text-[#5E6D7A] group-hover:text-[#0A2540]'}`} style={{ fontWeight: 440 }}>{role}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Add Custom Role */}
            <div>
              <h3 className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-2" style={{ fontWeight: 500 }}>Custom Role</h3>
              <div className="flex items-center gap-2">
                <input type="text" value={customRole} onChange={(e) => setCustomRole(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addCustom()}
                  placeholder="Type a new role name..."
                  className={`flex-1 px-3.5 py-2.5 rounded-lg border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${theme.inputClass}`}
                  style={{ fontWeight: 440 }} />
                <button onClick={addCustom} disabled={!customRole.trim()}
                  className="px-3.5 py-2.5 rounded-lg text-[12px] text-white transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed hover:shadow-[0_0_12px_rgba(99,91,255,0.2)]"
                  style={{ fontWeight: 520, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
                  Add
                </button>
              </div>
            </div>
          </div>

          {/* Danger Zone */}
          <div className={`pt-4 border-t ${theme.borderClass}`}>
            <button className="flex items-center gap-2 px-3.5 py-2.5 rounded-lg text-[12px] text-[#E5484D] border border-[#E5484D]/20 hover:bg-[#E5484D]/[0.04] transition-all" style={{ fontWeight: 500 }}>
              <Trash2 size={13} /> Remove Employee
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Main Team Page ─── */
export default function Team({
  embeddedInShell = false,
}: {
  embeddedInShell?: boolean;
}) {
  const isDark = useResolvedAppAppearance() === 'dark';
  const theme = getTeamTheme(isDark);
  const [searchQuery, setSearchQuery] = useState('');
  const [locationFilter, setLocationFilter] = useState('All Locations');
  const [statusFilter, setStatusFilter] = useState('All Status');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [sortField, setSortField] = useState<'name' | 'reliability'>('name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [showLocationDropdown, setShowLocationDropdown] = useState(false);
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);

  const filtered = employees
    .filter((e) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch = !q || e.name.toLowerCase().includes(q) || e.roles.some((r) => r.toLowerCase().includes(q)) || e.email.toLowerCase().includes(q);
      const matchesLocation = locationFilter === 'All Locations' || e.locations.some((l) => l.name === locationFilter);
      const matchesStatus = statusFilter === 'All Status' || statusConfig[e.status].label === statusFilter;
      return matchesSearch && matchesLocation && matchesStatus;
    })
    .sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1;
      if (sortField === 'name') return a.name.localeCompare(b.name) * dir;
      return (a.reliability - b.reliability) * dir;
    });

  const toggleSort = (field: 'name' | 'reliability') => {
    if (sortField === field) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
  };

  const content = (
    <>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className={`text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] mb-1 ${theme.textPrimary}`} style={{ fontWeight: 620 }}>
              Team
            </h1>
            <p className={`text-[13px] sm:text-[15px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
              Manage your employees across all locations.
            </p>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <button onClick={() => setShowBulkModal(true)}
              className={`hidden sm:flex items-center gap-2 px-4 py-2.5 rounded-lg text-[13px] border transition-all ${theme.secondaryButtonClass}`}
              style={{ fontWeight: 480 }}>
              <Upload size={15} /> Bulk Upload
            </button>
            <button onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 px-3 sm:px-5 py-2.5 rounded-full text-[12px] sm:text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)]"
              style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
              <Plus size={15} /> <span className="hidden sm:inline">Add Employee</span><span className="sm:hidden">Add</span>
            </button>
          </div>
        </div>

        {/* Filters + Search */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-sm">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8898AA]" />
            <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, role, email..."
              className={`w-full pl-9 pr-4 py-2.5 rounded-lg border text-[12px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${theme.inputClass}`}
              style={{ fontWeight: 420 }} />
          </div>

          <div className="flex items-center gap-2">
            {/* Location filter */}
            <div className="relative">
              <button onClick={() => { setShowLocationDropdown(!showLocationDropdown); setShowStatusDropdown(false); }}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-[12px] transition-all ${theme.filterButtonClass}`}
                style={{ fontWeight: 440 }}>
                <MapPin size={13} />
                <span className="max-w-[140px] truncate">{locationFilter}</span>
                <ChevronDown size={13} />
              </button>
              <AnimatePresence>
                {showLocationDropdown && (
                  <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
                    className={`absolute top-full mt-1 left-0 w-64 rounded-xl border overflow-hidden z-40 ${theme.dropdownClass}`}>
                    {locationOptions.map((opt) => (
                      <button key={opt} onClick={() => { setLocationFilter(opt); setShowLocationDropdown(false); }}
                        className={`w-full text-left px-4 py-2.5 text-[12px] transition-colors ${
                          locationFilter === opt
                            ? 'text-[#635BFF] bg-[#635BFF]/[0.08]'
                            : `${theme.rowText} ${isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]'}`
                        }`}
                        style={{ fontWeight: locationFilter === opt ? 520 : 420 }}>
                        {opt}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Status filter */}
            <div className="relative">
              <button onClick={() => { setShowStatusDropdown(!showStatusDropdown); setShowLocationDropdown(false); }}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-[12px] transition-all ${theme.filterButtonClass}`}
                style={{ fontWeight: 440 }}>
                <Filter size={13} />
                <span>{statusFilter}</span>
                <ChevronDown size={13} />
              </button>
              <AnimatePresence>
                {showStatusDropdown && (
                  <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
                    className={`absolute top-full mt-1 left-0 w-48 rounded-xl border overflow-hidden z-40 ${theme.dropdownClass}`}>
                    {statusOptions.map((opt) => (
                      <button key={opt} onClick={() => { setStatusFilter(opt); setShowStatusDropdown(false); }}
                        className={`w-full text-left px-4 py-2.5 text-[12px] transition-colors ${
                          statusFilter === opt
                            ? 'text-[#635BFF] bg-[#635BFF]/[0.08]'
                            : `${theme.rowText} ${isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]'}`
                        }`}
                        style={{ fontWeight: statusFilter === opt ? 520 : 420 }}>
                        {opt}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          <span className={`text-[12px] ml-auto ${theme.textSecondary}`} style={{ fontWeight: 420 }}>{filtered.length} employee{filtered.length !== 1 ? 's' : ''}</span>
        </div>
      </motion.div>

      {/* Employee Table */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}
        className={`rounded-2xl border overflow-hidden ${theme.panelClass}`}>
        {/* Table Header - Desktop only */}
        <div className={`hidden md:grid grid-cols-[2fr_1fr_1fr_1fr_0.8fr_44px] gap-4 px-5 py-3 border-b ${theme.borderClass} ${theme.softSurfaceClass}`}>
          <button onClick={() => toggleSort('name')} className={`flex items-center gap-1.5 text-[11px] uppercase tracking-[0.04em] transition-colors ${theme.textSecondary} ${isDark ? 'hover:text-white' : 'hover:text-[#5E6D7A]'}`} style={{ fontWeight: 500 }}>
            Employee <ArrowUpDown size={11} />
          </button>
          <span className={`text-[11px] uppercase tracking-[0.04em] ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Roles</span>
          <span className={`text-[11px] uppercase tracking-[0.04em] ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Location</span>
          <span className={`text-[11px] uppercase tracking-[0.04em] ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Status</span>
          <button onClick={() => toggleSort('reliability')} className={`flex items-center gap-1.5 text-[11px] uppercase tracking-[0.04em] transition-colors ${theme.textSecondary} ${isDark ? 'hover:text-white' : 'hover:text-[#5E6D7A]'}`} style={{ fontWeight: 500 }}>
            Reliability <ArrowUpDown size={11} />
          </button>
          <span />
        </div>

        {/* Mobile sort bar */}
        <div className={`md:hidden flex items-center gap-2 px-4 py-3 border-b overflow-x-auto ${theme.borderClass} ${theme.softSurfaceClass}`}>
          <span className={`text-[10px] uppercase tracking-[0.04em] shrink-0 ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Sort:</span>
          {(['name', 'reliability'] as const).map((field) => (
            <button key={field} onClick={() => toggleSort(field)}
              className={`shrink-0 px-2.5 py-1 rounded-full text-[11px] transition-colors ${sortField === field ? 'bg-[#635BFF]/10 text-[#635BFF]' : `${theme.textSecondary} ${theme.subtleSurfaceClass}`}`}
              style={{ fontWeight: sortField === field ? 520 : 420 }}>
              {field.charAt(0).toUpperCase() + field.slice(1)} {sortField === field && (sortDir === 'asc' ? '\u2191' : '\u2193')}
            </button>
          ))}
        </div>

        {/* Rows - Desktop Table */}
        <div className="hidden md:block">
          {filtered.map((emp, i) => {
            const primaryRole = emp.roles[0] || 'Unassigned';
            const color = roleColors[primaryRole] || '#635BFF';
            const primaryLoc = getPrimaryLocation(emp);
            const reliabilityColor = getReliabilityColor(emp.reliability);
            return (
              <motion.div key={emp.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, delay: i * 0.02 }}
                onClick={() => setSelectedEmployee(emp)}
                className={`grid grid-cols-[2fr_1fr_1fr_1fr_0.8fr_44px] gap-4 px-5 py-3.5 border-b last:border-0 cursor-pointer transition-colors group ${theme.rowBorderClass} ${theme.rowHoverClass}`}>
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-full flex items-center justify-center text-[11px] text-white shrink-0"
                    style={{ fontWeight: 600, background: `linear-gradient(135deg, ${color}, ${color}CC)` }}>
                    {emp.avatar}
                  </div>
                  <div className="min-w-0">
                    <p className={`text-[13px] truncate ${theme.textPrimary}`} style={{ fontWeight: 520 }}>{emp.name}</p>
                    <p className={`text-[11px] truncate ${theme.textSecondary}`} style={{ fontWeight: 400 }}>{emp.email}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[11px] px-2.5 py-1 rounded-full" style={{ fontWeight: 500, color, background: `${color}10` }}>{primaryRole}</span>
                  {emp.roles.length > 1 && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${theme.pillClass}`} style={{ fontWeight: 440 }}>+{emp.roles.length - 1}</span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 min-w-0">
                  {primaryLoc && (
                    <>
                      <span className="text-[13px]">{primaryLoc.emoji}</span>
                      <span className={`text-[12px] truncate ${theme.textTertiary}`} style={{ fontWeight: 440 }}>{primaryLoc.name.split(' ')[0]}</span>
                      {emp.locations.length > 1 && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${theme.pillClass}`} style={{ fontWeight: 440 }}>+{emp.locations.length - 1}</span>
                      )}
                    </>
                  )}
                </div>
                <div className="flex items-center">
                  <StatusWithInfo dark={isDark} status={emp.status} />
                </div>
                <div className="flex items-center gap-1.5">
                  <ShieldCheck size={13} style={{ color: reliabilityColor }} />
                  <span className="text-[13px] tabular-nums" style={{ fontWeight: 520, color: reliabilityColor }}>{emp.reliability}%</span>
                </div>
                <div className="flex items-center justify-center">
                  <button onClick={(e) => { e.stopPropagation(); setSelectedEmployee(emp); }}
                    className={`p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-all ${theme.closeButtonClass}`}>
                    <Eye size={14} className="text-[#8898AA]" />
                  </button>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Rows - Mobile Cards */}
        <div className={`md:hidden divide-y ${isDark ? 'divide-white/[0.06]' : 'divide-[#F7F8FA]'}`}>
          {filtered.map((emp, i) => {
            const primaryRole = emp.roles[0] || 'Unassigned';
            const color = roleColors[primaryRole] || '#635BFF';
            const primaryLoc = getPrimaryLocation(emp);
            const reliabilityColor = getReliabilityColor(emp.reliability);
            return (
              <motion.div key={emp.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, delay: i * 0.02 }}
                onClick={() => setSelectedEmployee(emp)}
                className={`px-4 py-3.5 cursor-pointer transition-colors ${isDark ? 'active:bg-white/[0.03]' : 'active:bg-[#FAFBFC]'}`}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center text-[12px] text-white shrink-0"
                    style={{ fontWeight: 600, background: `linear-gradient(135deg, ${color}, ${color}CC)` }}>
                    {emp.avatar}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className={`text-[14px] truncate ${theme.textPrimary}`} style={{ fontWeight: 520 }}>{emp.name}</p>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <ShieldCheck size={12} style={{ color: reliabilityColor }} />
                        <span className="text-[11px] tabular-nums" style={{ fontWeight: 520, color: reliabilityColor }}>{emp.reliability}%</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ fontWeight: 500, color, background: `${color}10` }}>{primaryRole}</span>
                      {primaryLoc && <span className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>{primaryLoc.emoji} {primaryLoc.name.split(' ')[0]}</span>}
                      <div className="flex items-center gap-1.5 ml-auto shrink-0">
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: statusConfig[emp.status].color }} />
                        <span className="text-[11px]" style={{ fontWeight: 460, color: statusConfig[emp.status].color }}>{statusConfig[emp.status].label}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

        {filtered.length === 0 && (
          <div className="px-8 py-16 text-center">
            <AlertCircle size={32} className={`mx-auto mb-3 ${theme.emptyIconClass}`} />
            <p className={`text-[14px] ${theme.textSecondary}`} style={{ fontWeight: 480 }}>No employees match your filters</p>
            <p className={`mt-1 text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Try adjusting your search or filter criteria</p>
          </div>
        )}
      </motion.div>

      {/* Modals */}
      <AnimatePresence>
        {showAddModal && <AddEmployeeModal dark={isDark} onClose={() => setShowAddModal(false)} />}
        {showBulkModal && <BulkUploadModal dark={isDark} onClose={() => setShowBulkModal(false)} />}
        {selectedEmployee && <EmployeeDetail dark={isDark} employee={selectedEmployee} onClose={() => setSelectedEmployee(null)} />}
      </AnimatePresence>
    </>
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav="Team">{content}</DashboardShell>;
}
