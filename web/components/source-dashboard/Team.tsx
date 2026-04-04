"use client";

import { useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useResolvedAppAppearance } from '@/components/app-session-gate';
import {
  Plus,
  Upload,
  Search,
  Filter,
  MoreHorizontal,
  Mail,
  Phone,
  Star,
  ChevronDown,
  X,
  CheckCircle2,
  AlertCircle,
  FileSpreadsheet,
  UserPlus,
  ArrowUpDown,
  Download,
  Eye,
  Edit3,
  Trash2,
  Clock,
  MapPin,
  Shield,
  Activity,
} from 'lucide-react';
import { BrandedSelect } from './BrandedSelect';
import DashboardShell from './DashboardShell';

/* ─── Types ─── */
interface Employee {
  id: number;
  name: string;
  email: string;
  phone: string;
  role: string;
  department: string;
  location: string;
  locationEmoji: string;
  status: 'active' | 'on-leave' | 'inactive';
  hireDate: string;
  shifts: number;
  rating: number;
  avatar: string;
  certifications: string[];
}

/* ─── Mock Data ─── */
const employees: Employee[] = [
  { id: 1, name: 'Sarah Martinez', email: 'sarah.m@backfill.io', phone: '(415) 555-0142', role: 'RN', department: 'ICU', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', status: 'active', hireDate: 'Jan 2024', shifts: 18, rating: 4.9, avatar: 'SM', certifications: ['BLS', 'ACLS'] },
  { id: 2, name: 'James Chen', email: 'james.c@backfill.io', phone: '(415) 555-0198', role: 'LPN', department: 'Med-Surg', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', status: 'active', hireDate: 'Mar 2024', shifts: 15, rating: 4.8, avatar: 'JC', certifications: ['BLS'] },
  { id: 3, name: 'Aisha Patel', email: 'aisha.p@backfill.io', phone: '(415) 555-0176', role: 'CNA', department: 'ER', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', status: 'active', hireDate: 'Nov 2023', shifts: 22, rating: 4.7, avatar: 'AP', certifications: ['BLS', 'CPR'] },
  { id: 4, name: 'Emily Ross', email: 'emily.r@backfill.io', phone: '(510) 555-0234', role: 'Caregiver', department: 'Memory Care', location: 'Sunrise Senior Living', locationEmoji: '\u{1F305}', status: 'active', hireDate: 'Feb 2024', shifts: 20, rating: 4.9, avatar: 'ER', certifications: ['CPR', 'First Aid'] },
  { id: 5, name: 'David Kim', email: 'david.k@backfill.io', phone: '(510) 555-0187', role: 'CNA', department: 'Assisted Living', location: 'Sunrise Senior Living', locationEmoji: '\u{1F305}', status: 'on-leave', hireDate: 'Jun 2024', shifts: 16, rating: 4.6, avatar: 'DK', certifications: ['BLS'] },
  { id: 6, name: 'Carlos Rivera', email: 'carlos.r@backfill.io', phone: '(408) 555-0165', role: 'Temp RN', department: 'General', location: 'Bay Area Staffing Co.', locationEmoji: '\u{1F3E2}', status: 'active', hireDate: 'Sep 2023', shifts: 24, rating: 4.8, avatar: 'CR', certifications: ['BLS', 'ACLS', 'PALS'] },
  { id: 7, name: 'Mia Johnson', email: 'mia.j@backfill.io', phone: '(831) 555-0119', role: 'Server Lead', department: 'F&B', location: 'Coastal Hospitality Group', locationEmoji: '\u{1F3E8}', status: 'active', hireDate: 'Apr 2024', shifts: 12, rating: 4.9, avatar: 'MJ', certifications: ['Food Safety'] },
  { id: 8, name: 'Marcus Thompson', email: 'marcus.t@backfill.io', phone: '(415) 555-0203', role: 'RN', department: 'Pediatrics', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', status: 'inactive', hireDate: 'Dec 2023', shifts: 8, rating: 4.5, avatar: 'MT', certifications: ['BLS', 'PALS'] },
  { id: 9, name: 'Priya Sharma', email: 'priya.s@backfill.io', phone: '(408) 555-0291', role: 'Temp LPN', department: 'General', location: 'Bay Area Staffing Co.', locationEmoji: '\u{1F3E2}', status: 'active', hireDate: 'Jul 2024', shifts: 19, rating: 4.7, avatar: 'PS', certifications: ['BLS', 'IV Cert'] },
  { id: 10, name: 'Alex Morgan', email: 'alex.m@backfill.io', phone: '(510) 555-0148', role: 'Caregiver', department: 'Hospice', location: 'Sunrise Senior Living', locationEmoji: '\u{1F305}', status: 'active', hireDate: 'Aug 2024', shifts: 14, rating: 4.8, avatar: 'AM', certifications: ['CPR', 'Hospice Cert'] },
  { id: 11, name: 'Jordan Lee', email: 'jordan.l@backfill.io', phone: '(415) 555-0177', role: 'CNA', department: 'ICU', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', status: 'active', hireDate: 'Oct 2024', shifts: 11, rating: 4.6, avatar: 'JL', certifications: ['BLS'] },
  { id: 12, name: 'Nina Patel', email: 'nina.p@backfill.io', phone: '(831) 555-0205', role: 'Bartender', department: 'F&B', location: 'Coastal Hospitality Group', locationEmoji: '\u{1F3E8}', status: 'active', hireDate: 'May 2024', shifts: 10, rating: 4.7, avatar: 'NP', certifications: ['Food Safety', 'TIPS'] },
];

const roleColors: Record<string, string> = {
  'RN': '#635BFF',
  'LPN': '#3B82F6',
  'CNA': '#00B893',
  'Caregiver': '#8B5CF6',
  'Temp RN': '#F59E0B',
  'Temp LPN': '#F59E0B',
  'Server Lead': '#FF6B35',
  'Bartender': '#E5484D',
};

const statusConfig = {
  active: { label: 'Active', color: '#00B893', bg: '#00B893' },
  'on-leave': { label: 'On Leave', color: '#F59E0B', bg: '#F59E0B' },
  inactive: { label: 'Inactive', color: '#8898AA', bg: '#8898AA' },
};

const locationOptions = ['All Locations', 'Downtown Medical Center', 'Sunrise Senior Living', 'Bay Area Staffing Co.', 'Coastal Hospitality Group'];
const statusOptions = ['All Status', 'Active', 'On Leave', 'Inactive'];
const rosterTemplateHref = '/backfill-employee-roster-template.xlsx';

/* ─── Add Employee Modal ─── */
function AddEmployeeModal({ onClose, dark }: { onClose: () => void; dark: boolean }) {
  const [formData, setFormData] = useState({
    firstName: '', lastName: '', email: '', phone: '', role: '', department: '', location: '',
  });
  const modalBg = dark ? 'bg-[#0F2E4C]' : 'bg-white';
  const border = dark ? 'border-white/[0.08]' : 'border-[#F0F0F5]';
  const textPrimary = dark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = dark ? 'text-[#C1CED8]' : 'text-[#8898AA]';
  const inputClass = dark
    ? 'border-white/[0.08] bg-white/[0.04] text-white'
    : 'border-[#E5E7EB] bg-white text-[#0A2540]';
  const subtlePanel = dark ? 'bg-white/[0.04]' : 'bg-[#635BFF]/[0.04]';
  const subtleBorder = dark ? 'border-white/[0.08]' : 'border-[#635BFF]/10';
  const footerBg = dark ? 'bg-white/[0.03]' : 'bg-[#FAFBFC]';
  const ghostButton = dark
    ? 'text-[#C1CED8] border-white/[0.08] hover:bg-white/[0.06]'
    : 'text-[#5E6D7A] border-[#E5E7EB] hover:bg-[#F7F8FA]';

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}>
      <motion.div initial={{ opacity: 0, y: 8, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
        className={`w-full max-w-lg ${modalBg} backfill-ui-radius shadow-2xl overflow-hidden mx-4 sm:mx-0 border ${dark ? 'border-white/[0.08]' : 'border-transparent'}`}
        onClick={(e) => e.stopPropagation()}>
        <div className={`flex items-center justify-between px-4 sm:px-6 py-5 border-b ${border}`}>
          <div className="flex items-center gap-3">
            <div className={`w-9 h-9 backfill-ui-radius ${dark ? 'bg-white/[0.06]' : 'bg-[#635BFF]/10'} flex items-center justify-center`}>
              <UserPlus size={18} className="text-[#635BFF]" />
            </div>
            <div>
              <h2 className={`text-[16px] ${textPrimary}`} style={{ fontWeight: 600 }}>Add Employee</h2>
              <p className={`text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>Add a new team member to your roster</p>
            </div>
          </div>
          <button onClick={onClose} className={`p-2 backfill-ui-radius ${dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]'} transition-colors`}>
            <X size={18} className="text-[#8898AA]" />
          </button>
        </div>

        <div className="px-4 sm:px-6 py-5 space-y-4 max-h-[60vh] overflow-y-auto">
          <div className={`flex items-center gap-3 p-3.5 backfill-ui-radius ${subtlePanel} border ${subtleBorder}`}>
            <FileSpreadsheet size={18} className="text-[#635BFF] shrink-0" />
            <div className="flex-1">
              <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 500 }}>Uploading a full roster instead?</p>
              <p className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>Download the workbook template with instructions, then use Bulk Upload.</p>
            </div>
            <a
              href={rosterTemplateHref}
              download
              className={`flex items-center gap-1.5 px-3 py-1.5 backfill-ui-radius border text-[11px] text-[#635BFF] transition-all ${dark ? 'bg-white/[0.06] border-white/[0.08] hover:bg-white/[0.1]' : 'bg-white border-[#E5E7EB] hover:bg-[#F7F8FA]'}`}
              style={{ fontWeight: 500 }}
            >
              <Download size={12} /> Template
            </a>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={`block text-[11px] ${textSecondary} uppercase tracking-[0.04em] mb-1.5`} style={{ fontWeight: 500 }}>First Name</label>
              <input type="text" value={formData.firstName} onChange={(e) => setFormData({ ...formData, firstName: e.target.value })}
                className={`w-full px-3.5 py-2.5 backfill-ui-radius border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${inputClass}`}
                style={{ fontWeight: 440 }} placeholder="Sarah" />
            </div>
            <div>
              <label className={`block text-[11px] ${textSecondary} uppercase tracking-[0.04em] mb-1.5`} style={{ fontWeight: 500 }}>Last Name</label>
              <input type="text" value={formData.lastName} onChange={(e) => setFormData({ ...formData, lastName: e.target.value })}
                className={`w-full px-3.5 py-2.5 backfill-ui-radius border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${inputClass}`}
                style={{ fontWeight: 440 }} placeholder="Martinez" />
            </div>
          </div>

          <div>
            <label className={`block text-[11px] ${textSecondary} uppercase tracking-[0.04em] mb-1.5`} style={{ fontWeight: 500 }}>Email</label>
            <input type="email" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className={`w-full px-3.5 py-2.5 backfill-ui-radius border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${inputClass}`}
              style={{ fontWeight: 440 }} placeholder="sarah.m@company.com" />
          </div>

          <div>
            <label className={`block text-[11px] ${textSecondary} uppercase tracking-[0.04em] mb-1.5`} style={{ fontWeight: 500 }}>Phone</label>
            <input type="tel" value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              className={`w-full px-3.5 py-2.5 backfill-ui-radius border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${inputClass}`}
              style={{ fontWeight: 440 }} placeholder="(415) 555-0142" />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={`block text-[11px] ${textSecondary} uppercase tracking-[0.04em] mb-1.5`} style={{ fontWeight: 500 }}>Role</label>
              <BrandedSelect
                dark={dark}
                onChange={(e: { target: { value: string } }) => setFormData({ ...formData, role: e.target.value })}
                value={formData.role}
              >
                <option value="">Select role</option>
                <option>RN</option><option>LPN</option><option>CNA</option><option>Caregiver</option>
                <option>Temp RN</option><option>Temp LPN</option><option>Server Lead</option><option>Bartender</option>
              </BrandedSelect>
            </div>
            <div>
              <label className={`block text-[11px] ${textSecondary} uppercase tracking-[0.04em] mb-1.5`} style={{ fontWeight: 500 }}>Department</label>
              <input type="text" value={formData.department} onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                className={`w-full px-3.5 py-2.5 backfill-ui-radius border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${inputClass}`}
                style={{ fontWeight: 440 }} placeholder="ICU" />
            </div>
          </div>

            <div>
              <label className={`block text-[11px] ${textSecondary} uppercase tracking-[0.04em] mb-1.5`} style={{ fontWeight: 500 }}>Location</label>
              <BrandedSelect
                dark={dark}
                onChange={(e: { target: { value: string } }) => setFormData({ ...formData, location: e.target.value })}
                value={formData.location}
              >
              <option value="">Select location</option>
              {locationOptions.slice(1).map((l) => <option key={l}>{l}</option>)}
            </BrandedSelect>
          </div>
        </div>

        <div className={`flex items-center justify-end gap-3 px-4 sm:px-6 py-4 border-t ${border} ${footerBg}`}>
          <button onClick={onClose}
            className={`px-4 py-2.5 backfill-ui-radius text-[13px] border transition-all ${ghostButton}`}
            style={{ fontWeight: 480 }}>
            Cancel
          </button>
          <button
            className="px-5 py-2.5 backfill-ui-radius text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_20px_rgba(99,91,255,0.25)]"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
            Add Employee
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Bulk Upload Modal ─── */
function BulkUploadModal({ onClose, dark }: { onClose: () => void; dark: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const modalBg = dark ? 'bg-[#0F2E4C]' : 'bg-white';
  const border = dark ? 'border-white/[0.08]' : 'border-[#F0F0F5]';
  const textPrimary = dark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = dark ? 'text-[#C1CED8]' : 'text-[#8898AA]';
  const actionSurface = dark ? 'bg-white/[0.06] border-white/[0.08] hover:bg-white/[0.1]' : 'bg-white border-[#E5E7EB] hover:bg-[#F7F8FA]';
  const footerBg = dark ? 'bg-white/[0.03]' : 'bg-[#FAFBFC]';
  const ghostButton = dark
    ? 'text-[#C1CED8] border-white/[0.08] hover:bg-white/[0.06]'
    : 'text-[#5E6D7A] border-[#E5E7EB] hover:bg-[#F7F8FA]';

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
        className={`w-full max-w-lg ${modalBg} backfill-ui-radius shadow-2xl overflow-hidden border ${dark ? 'border-white/[0.08]' : 'border-transparent'}`}
        onClick={(e) => e.stopPropagation()}>
        <div className={`flex items-center justify-between px-6 py-5 border-b ${border}`}>
          <div className="flex items-center gap-3">
            <div className={`w-9 h-9 backfill-ui-radius ${dark ? 'bg-white/[0.06]' : 'bg-[#00B893]/10'} flex items-center justify-center`}>
              <Upload size={18} className="text-[#00B893]" />
            </div>
            <div>
              <h2 className={`text-[16px] ${textPrimary}`} style={{ fontWeight: 600 }}>Bulk Upload</h2>
              <p className={`text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>Import employees from a CSV or Excel file</p>
            </div>
          </div>
          <button onClick={onClose} className={`p-2 backfill-ui-radius ${dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]'} transition-colors`}>
            <X size={18} className="text-[#8898AA]" />
          </button>
        </div>

        <div className="px-6 py-6">
          {/* Download template */}
          <div className={`flex items-center gap-3 p-3.5 backfill-ui-radius ${dark ? 'bg-white/[0.04] border-white/[0.08]' : 'bg-[#635BFF]/[0.04] border-[#635BFF]/10'} border mb-5`}>
            <FileSpreadsheet size={18} className="text-[#635BFF] shrink-0" />
            <div className="flex-1">
              <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 500 }}>Need a template?</p>
              <p className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>Download the roster workbook with an instructions tab and a clean upload tab.</p>
            </div>
            <a
              href={rosterTemplateHref}
              download
              className={`flex items-center gap-1.5 px-3 py-1.5 backfill-ui-radius border text-[11px] text-[#635BFF] transition-all ${actionSurface}`}
              style={{ fontWeight: 500 }}
            >
              <Download size={12} /> Template
            </a>
          </div>

          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            className={`relative cursor-pointer backfill-ui-radius border-2 border-dashed transition-all duration-300 p-8 text-center ${
              isDragging ? 'border-[#635BFF] bg-[#635BFF]/[0.04]' :
              uploadedFile ? 'border-[#00B893]/40 bg-[#00B893]/[0.02]' :
              dark ? 'border-white/[0.08] hover:border-[#635BFF]/30 hover:bg-white/[0.04]' : 'border-[#E5E7EB] hover:border-[#635BFF]/30 hover:bg-[#F7F8FA]'
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
                <p className="text-[13px] text-[#0A2540] mb-1" style={{ fontWeight: 520 }}>{uploadedFile}</p>
                {uploadProgress < 100 ? (
                  <div className="w-48 mx-auto">
                    <div className="h-1.5 rounded-full bg-[#F0F0F5] overflow-hidden mt-2">
                      <motion.div className="h-full rounded-full bg-gradient-to-r from-[#00B893] to-[#00D4AA]"
                        initial={{ width: 0 }} animate={{ width: `${Math.min(uploadProgress, 100)}%` }} />
                    </div>
                    <p className="text-[11px] text-[#8898AA] mt-1.5" style={{ fontWeight: 420 }}>Processing...</p>
                  </div>
                ) : (
                  <p className="text-[12px] text-[#00B893]" style={{ fontWeight: 480 }}>Ready to import \u2022 24 employees found</p>
                )}
              </div>
            ) : (
              <div>
                <div className={`w-12 h-12 rounded-full ${dark ? 'bg-white/[0.06]' : 'bg-[#F0F0F5]'} flex items-center justify-center mx-auto mb-3`}>
                  <Upload size={20} className="text-[#8898AA]" />
                </div>
                <p className={`text-[13px] ${textPrimary} mb-1`} style={{ fontWeight: 520 }}>Drop your file here, or click to browse</p>
                <p className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>Supports CSV, XLS, XLSX \u2022 Max 5MB</p>
              </div>
            )}
          </div>

          {/* Column mapping preview */}
          {uploadedFile && uploadProgress >= 100 && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.1 }}
              className={`mt-4 p-4 backfill-ui-radius border ${dark ? 'bg-white/[0.04] border-white/[0.08]' : 'bg-[#F7F8FA] border-[#E5E7EB]'}`}>
              <p className={`text-[11px] ${textSecondary} uppercase tracking-[0.04em] mb-3`} style={{ fontWeight: 500 }}>Column Mapping Preview</p>
              <div className="space-y-2">
                {[
                  { csv: 'full_name', mapped: 'Employee Name', icon: '✓' },
                  { csv: 'email_address', mapped: 'Email', icon: '✓' },
                  { csv: 'phone', mapped: 'Phone Number', icon: '✓' },
                  { csv: 'job_title', mapped: 'Role', icon: '✓' },
                  { csv: 'work_location', mapped: 'Location', icon: '✓' },
                ].map((col) => (
                  <div key={col.csv} className="flex items-center gap-3 text-[12px]">
                    <span className="text-[#00B893]">{col.icon}</span>
                    <span className={`w-28 truncate ${textSecondary}`} style={{ fontWeight: 420 }}>{col.csv}</span>
                    <span className={textSecondary}>\u2192</span>
                    <span className={textPrimary} style={{ fontWeight: 480 }}>{col.mapped}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </div>

        <div className={`flex items-center justify-end gap-3 px-6 py-4 border-t ${border} ${footerBg}`}>
          <button onClick={onClose}
            className={`px-4 py-2.5 backfill-ui-radius text-[13px] border transition-all ${ghostButton}`}
            style={{ fontWeight: 480 }}>
            Cancel
          </button>
          <button
            className={`px-5 py-2.5 backfill-ui-radius text-[13px] text-white transition-all duration-300 ${
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
function EmployeeDetail({ employee, onClose, dark }: { employee: Employee; onClose: () => void; dark: boolean }) {
  const color = roleColors[employee.role] || '#635BFF';
  const status = statusConfig[employee.status];
  const panelBg = dark ? 'bg-[#0F2E4C]' : 'bg-white';
  const border = dark ? 'border-white/[0.08]' : 'border-[#F0F0F5]';
  const textPrimary = dark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = dark ? 'text-[#C1CED8]' : 'text-[#3E4C59]';
  const mutedText = 'text-[#8898AA]';
  const surface = dark ? 'bg-white/[0.04]' : 'bg-[#F7F8FA]';
  const surfaceBorder = dark ? 'border-white/[0.08]' : 'border-[#E5E7EB]';
  const rowBorder = dark ? 'border-white/[0.06]' : 'border-[#F7F8FA]';

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"
      onClick={onClose}>
      <motion.div initial={{ x: 420 }} animate={{ x: 0 }} exit={{ x: 420 }}
        transition={{ duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
        className={`w-full sm:w-[420px] h-full ${panelBg} shadow-2xl flex flex-col overflow-hidden border-l ${dark ? 'border-white/[0.08]' : 'border-transparent'}`}
        onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={`px-6 py-5 border-b ${border}`}>
          <div className="flex items-center justify-between mb-4">
            <button onClick={onClose} className={`p-1.5 backfill-ui-radius ${dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]'} transition-colors`}>
              <X size={18} className="text-[#8898AA]" />
            </button>
            <div className="flex items-center gap-2">
              <button className={`p-1.5 backfill-ui-radius ${dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]'} transition-colors`}>
                <Edit3 size={15} className="text-[#8898AA]" />
              </button>
              <button className="p-1.5 backfill-ui-radius hover:bg-[#FEE2E2] transition-colors">
                <Trash2 size={15} className="text-[#E5484D]" />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 backfill-ui-radius flex items-center justify-center text-[16px] text-white shrink-0"
              style={{ fontWeight: 600, background: `linear-gradient(135deg, ${color}, ${color}CC)` }}>
              {employee.avatar}
            </div>
            <div>
              <h2 className={`text-[18px] ${textPrimary} tracking-[-0.01em]`} style={{ fontWeight: 600 }}>{employee.name}</h2>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[12px] px-2 py-0.5 backfill-ui-radius" style={{ fontWeight: 500, color, background: `${color}10` }}>{employee.role}</span>
                <span className="text-[11px] px-2 py-0.5 backfill-ui-radius" style={{ fontWeight: 480, color: status.color, background: `${status.bg}15` }}>{status.label}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* Contact Info */}
          <div>
            <h3 className={`text-[11px] ${mutedText} uppercase tracking-[0.04em] mb-3`} style={{ fontWeight: 500 }}>Contact</h3>
            <div className="space-y-2.5">
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 backfill-ui-radius ${surface} flex items-center justify-center`}><Mail size={14} className="text-[#8898AA]" /></div>
                <span className={`text-[13px] ${textSecondary}`} style={{ fontWeight: 440 }}>{employee.email}</span>
              </div>
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 backfill-ui-radius ${surface} flex items-center justify-center`}><Phone size={14} className="text-[#8898AA]" /></div>
                <span className={`text-[13px] ${textSecondary}`} style={{ fontWeight: 440 }}>{employee.phone}</span>
              </div>
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 backfill-ui-radius ${surface} flex items-center justify-center`}><MapPin size={14} className="text-[#8898AA]" /></div>
                <span className={`text-[13px] ${textSecondary}`} style={{ fontWeight: 440 }}>{employee.locationEmoji} {employee.location}</span>
              </div>
            </div>
          </div>

          {/* Stats */}
          <div>
            <h3 className={`text-[11px] ${mutedText} uppercase tracking-[0.04em] mb-3`} style={{ fontWeight: 500 }}>Performance</h3>
            <div className="grid grid-cols-3 gap-3">
              <div className={`p-3 backfill-ui-radius ${surface} text-center`}>
                <span className={`text-[20px] ${textPrimary} tracking-[-0.02em] block`} style={{ fontWeight: 640 }}>{employee.shifts}</span>
                <span className={`text-[10px] ${mutedText} uppercase tracking-[0.04em]`} style={{ fontWeight: 460 }}>Shifts</span>
              </div>
              <div className={`p-3 backfill-ui-radius ${surface} text-center`}>
                <div className="flex items-center justify-center gap-0.5">
                  <Star size={14} className="text-[#D4A017] fill-[#D4A017]" />
                  <span className={`text-[20px] ${textPrimary} tracking-[-0.02em]`} style={{ fontWeight: 640 }}>{employee.rating}</span>
                </div>
                <span className={`text-[10px] ${mutedText} uppercase tracking-[0.04em]`} style={{ fontWeight: 460 }}>Rating</span>
              </div>
              <div className={`p-3 backfill-ui-radius ${surface} text-center`}>
                <span className={`text-[20px] ${textPrimary} tracking-[-0.02em] block`} style={{ fontWeight: 640 }}>98%</span>
                <span className={`text-[10px] ${mutedText} uppercase tracking-[0.04em]`} style={{ fontWeight: 460 }}>On-Time</span>
              </div>
            </div>
          </div>

          {/* Details */}
          <div>
            <h3 className={`text-[11px] ${mutedText} uppercase tracking-[0.04em] mb-3`} style={{ fontWeight: 500 }}>Details</h3>
            <div className="space-y-3">
              {[
                { label: 'Department', value: employee.department, icon: MoreHorizontal },
                { label: 'Hire Date', value: employee.hireDate, icon: Clock },
              ].map((item) => (
                <div key={item.label} className={`flex items-center justify-between py-2 border-b ${rowBorder}`}>
                  <div className="flex items-center gap-2">
                    <item.icon size={13} className="text-[#8898AA]" />
                    <span className={`text-[12px] ${mutedText}`} style={{ fontWeight: 440 }}>{item.label}</span>
                  </div>
                  <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 500 }}>{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Certifications */}
          <div>
            <h3 className={`text-[11px] ${mutedText} uppercase tracking-[0.04em] mb-3`} style={{ fontWeight: 500 }}>Certifications</h3>
            <div className="flex flex-wrap gap-2">
              {employee.certifications.map((cert) => (
                <div key={cert} className={`flex items-center gap-1.5 px-3 py-1.5 backfill-ui-radius ${surface} border ${surfaceBorder}`}>
                  <Shield size={12} className="text-[#00B893]" />
                  <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 480 }}>{cert}</span>
                </div>
              ))}
            </div>
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
  const [searchQuery, setSearchQuery] = useState('');
  const [locationFilter, setLocationFilter] = useState('All Locations');
  const [statusFilter, setStatusFilter] = useState('All Status');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [sortField, setSortField] = useState<'name' | 'shifts' | 'rating'>('name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [showLocationDropdown, setShowLocationDropdown] = useState(false);
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);

  const filtered = employees
    .filter((e) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch = !q || e.name.toLowerCase().includes(q) || e.role.toLowerCase().includes(q) || e.email.toLowerCase().includes(q) || e.department.toLowerCase().includes(q);
      const matchesLocation = locationFilter === 'All Locations' || e.location === locationFilter;
      const matchesStatus = statusFilter === 'All Status' || statusConfig[e.status].label === statusFilter;
      return matchesSearch && matchesLocation && matchesStatus;
    })
    .sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1;
      if (sortField === 'name') return a.name.localeCompare(b.name) * dir;
      if (sortField === 'shifts') return (a.shifts - b.shifts) * dir;
      return (a.rating - b.rating) * dir;
    });

  const toggleSort = (field: 'name' | 'shifts' | 'rating') => {
    if (sortField === field) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
  };

  const activeCount = employees.filter((e) => e.status === 'active').length;
  const leaveCount = employees.filter((e) => e.status === 'on-leave').length;
  const inactiveCount = employees.filter((e) => e.status === 'inactive').length;
  const cardBg = isDark ? 'bg-[#0F2E4C] border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.25)]' : 'bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]';
  const cardHeaderBg = isDark ? 'bg-white/[0.03] border-white/[0.06]' : 'bg-[#FAFBFC] border-[#F0F0F5]';
  const textPrimary = isDark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = isDark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]';
  const textMuted = 'text-[#8898AA]';
  const inputBg = isDark ? 'bg-white/[0.04] border-white/[0.08] text-white' : 'bg-white border-[#E5E7EB] text-[#0A2540]';
  const hoverRow = isDark ? 'hover:bg-white/[0.03]' : 'hover:bg-[#FAFBFC]';
  const divider = isDark ? 'border-white/[0.06]' : 'border-[#F0F0F5]';
  const softDivider = isDark ? 'divide-white/[0.06]' : 'divide-[#F7F8FA]';

  const content = (
    <>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className={`text-[24px] sm:text-[28px] md:text-[32px] ${textPrimary} tracking-[-0.025em] mb-1`} style={{ fontWeight: 620 }}>
              Team
            </h1>
            <p className={`text-[13px] sm:text-[15px] ${isDark ? 'text-[#C1CED8]' : 'text-[#8898AA]'}`} style={{ fontWeight: 420 }}>
              Manage your employees across all locations.
            </p>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <button onClick={() => setShowBulkModal(true)}
              className={`hidden sm:flex items-center gap-2 px-4 py-2.5 backfill-ui-radius text-[13px] border transition-all ${isDark ? 'text-[#C1CED8] border-white/[0.08] hover:bg-white/[0.06] hover:border-white/[0.14]' : 'text-[#5E6D7A] border-[#E5E7EB] hover:bg-[#F7F8FA] hover:border-[#D1D5DB]'}`}
              style={{ fontWeight: 480 }}>
              <Upload size={15} /> Bulk Upload
            </button>
            <button onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 px-3 sm:px-5 py-2.5 backfill-ui-radius text-[12px] sm:text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)]"
              style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
              <Plus size={15} /> <span className="hidden sm:inline">Add Employee</span><span className="sm:hidden">Add</span>
            </button>
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Total Employees', value: employees.length, color: '#635BFF' },
            { label: 'Active', value: activeCount, color: '#00B893' },
            { label: 'On Leave', value: leaveCount, color: '#F59E0B' },
            { label: 'Inactive', value: inactiveCount, color: '#8898AA' },
          ].map((stat, i) => (
            <motion.div key={stat.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: i * 0.05 }}
              className={`${cardBg} backfill-ui-radius px-4 py-4`}>
              <div className="flex items-center justify-between mb-1">
                <span className={`text-[11px] ${textMuted} uppercase tracking-[0.04em]`} style={{ fontWeight: 480 }}>{stat.label}</span>
                <div className="w-2 h-2 rounded-full" style={{ background: stat.color }} />
              </div>
              <span className={`text-[26px] ${textPrimary} tracking-[-0.02em]`} style={{ fontWeight: 660 }}>{stat.value}</span>
            </motion.div>
          ))}
        </div>

        {/* Filters + Search */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-sm">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8898AA]" />
            <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, role, email..."
              className={`w-full pl-9 pr-4 py-2.5 backfill-ui-radius border text-[12px] placeholder-[#8898AA]/60 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${inputBg}`}
              style={{ fontWeight: 420 }} />
          </div>

          <div className="flex items-center gap-2">
            {/* Location filter */}
            <div className="relative">
              <button onClick={() => { setShowLocationDropdown(!showLocationDropdown); setShowStatusDropdown(false); }}
                className={`flex items-center gap-2 px-3 py-2.5 backfill-ui-radius border text-[12px] transition-all ${isDark ? 'bg-white/[0.04] border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]' : 'bg-white border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]'}`}
                style={{ fontWeight: 440 }}>
                <MapPin size={13} />
                <span className="max-w-[140px] truncate">{locationFilter}</span>
                <ChevronDown size={13} />
              </button>
              <AnimatePresence>
                {showLocationDropdown && (
                  <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
                    className={`absolute top-full mt-1 left-0 w-64 backfill-ui-radius shadow-xl overflow-hidden z-40 border ${isDark ? 'bg-[#0F2E4C] border-white/[0.08]' : 'bg-white border-[#E5E7EB]'}`}>
                    {locationOptions.map((opt) => (
                      <button key={opt} onClick={() => { setLocationFilter(opt); setShowLocationDropdown(false); }}
                        className={`w-full text-left px-4 py-2.5 text-[12px] transition-colors ${locationFilter === opt ? 'text-[#635BFF] bg-[#635BFF]/[0.08]' : isDark ? 'text-[#C1CED8] hover:bg-white/[0.04]' : 'text-[#3E4C59] hover:bg-[#F7F8FA]'}`}
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
                className={`flex items-center gap-2 px-3 py-2.5 backfill-ui-radius border text-[12px] transition-all ${isDark ? 'bg-white/[0.04] border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]' : 'bg-white border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]'}`}
                style={{ fontWeight: 440 }}>
                <Filter size={13} />
                <span>{statusFilter}</span>
                <ChevronDown size={13} />
              </button>
              <AnimatePresence>
                {showStatusDropdown && (
                  <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
                    className={`absolute top-full mt-1 left-0 w-40 backfill-ui-radius shadow-xl overflow-hidden z-40 border ${isDark ? 'bg-[#0F2E4C] border-white/[0.08]' : 'bg-white border-[#E5E7EB]'}`}>
                    {statusOptions.map((opt) => (
                      <button key={opt} onClick={() => { setStatusFilter(opt); setShowStatusDropdown(false); }}
                        className={`w-full text-left px-4 py-2.5 text-[12px] transition-colors ${statusFilter === opt ? 'text-[#635BFF] bg-[#635BFF]/[0.08]' : isDark ? 'text-[#C1CED8] hover:bg-white/[0.04]' : 'text-[#3E4C59] hover:bg-[#F7F8FA]'}`}
                        style={{ fontWeight: statusFilter === opt ? 520 : 420 }}>
                        {opt}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          <span className={`text-[12px] ${textMuted} ml-auto`} style={{ fontWeight: 420 }}>{filtered.length} employee{filtered.length !== 1 ? 's' : ''}</span>
        </div>
      </motion.div>

      {/* Employee Table */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}
        className={`${cardBg} backfill-ui-radius overflow-hidden`}>
        {/* Table Header - Desktop only */}
        <div className={`hidden md:grid grid-cols-[2fr_1fr_1fr_1fr_0.7fr_0.7fr_44px] gap-4 px-5 py-3 border-b ${cardHeaderBg}`}>
          <button onClick={() => toggleSort('name')} className={`flex items-center gap-1.5 text-[11px] ${textMuted} uppercase tracking-[0.04em] ${isDark ? 'hover:text-[#C1CED8]' : 'hover:text-[#5E6D7A]'} transition-colors`} style={{ fontWeight: 500 }}>
            Employee <ArrowUpDown size={11} />
          </button>
          <span className={`text-[11px] ${textMuted} uppercase tracking-[0.04em]`} style={{ fontWeight: 500 }}>Role</span>
          <span className={`text-[11px] ${textMuted} uppercase tracking-[0.04em]`} style={{ fontWeight: 500 }}>Location</span>
          <span className={`text-[11px] ${textMuted} uppercase tracking-[0.04em]`} style={{ fontWeight: 500 }}>Status</span>
          <button onClick={() => toggleSort('shifts')} className={`flex items-center gap-1.5 text-[11px] ${textMuted} uppercase tracking-[0.04em] ${isDark ? 'hover:text-[#C1CED8]' : 'hover:text-[#5E6D7A]'} transition-colors`} style={{ fontWeight: 500 }}>
            Shifts <ArrowUpDown size={11} />
          </button>
          <button onClick={() => toggleSort('rating')} className={`flex items-center gap-1.5 text-[11px] ${textMuted} uppercase tracking-[0.04em] ${isDark ? 'hover:text-[#C1CED8]' : 'hover:text-[#5E6D7A]'} transition-colors`} style={{ fontWeight: 500 }}>
            Rating <ArrowUpDown size={11} />
          </button>
          <span />
        </div>

        {/* Mobile sort bar */}
        <div className={`md:hidden flex items-center gap-2 px-4 py-3 border-b ${cardHeaderBg} overflow-x-auto`}>
          <span className={`text-[10px] ${textMuted} uppercase tracking-[0.04em] shrink-0`} style={{ fontWeight: 500 }}>Sort:</span>
          {(['name', 'shifts', 'rating'] as const).map((field) => (
            <button key={field} onClick={() => toggleSort(field)}
              className={`shrink-0 px-2.5 py-1 backfill-ui-radius text-[11px] transition-colors ${sortField === field ? 'bg-[#635BFF]/10 text-[#635BFF]' : isDark ? 'text-[#C1CED8] bg-white/[0.04]' : 'text-[#8898AA] bg-[#F7F8FA]'}`}
              style={{ fontWeight: sortField === field ? 520 : 420 }}>
              {field.charAt(0).toUpperCase() + field.slice(1)} {sortField === field && (sortDir === 'asc' ? '↑' : '↓')}
            </button>
          ))}
        </div>

        {/* Rows - Desktop Table */}
        <div className="hidden md:block">
          {filtered.map((emp, i) => {
            const color = roleColors[emp.role] || '#635BFF';
            const status = statusConfig[emp.status];
            return (
              <motion.div key={emp.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, delay: i * 0.02 }}
                onClick={() => setSelectedEmployee(emp)}
                className={`grid grid-cols-[2fr_1fr_1fr_1fr_0.7fr_0.7fr_44px] gap-4 px-5 py-3.5 border-b ${isDark ? 'border-white/[0.06]' : 'border-[#F7F8FA]'} last:border-0 ${hoverRow} cursor-pointer transition-colors group`}>
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-full flex items-center justify-center text-[11px] text-white shrink-0"
                    style={{ fontWeight: 600, background: `linear-gradient(135deg, ${color}, ${color}CC)` }}>
                    {emp.avatar}
                  </div>
                  <div className="min-w-0">
                    <p className={`text-[13px] ${textPrimary} truncate`} style={{ fontWeight: 520 }}>{emp.name}</p>
                    <p className={`text-[11px] ${textMuted} truncate`} style={{ fontWeight: 400 }}>{emp.email}</p>
                  </div>
                </div>
                <div className="flex items-center">
                  <span className="text-[11px] px-2.5 py-1 backfill-ui-radius" style={{ fontWeight: 500, color, background: `${color}10` }}>{emp.role}</span>
                </div>
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="text-[13px]">{emp.locationEmoji}</span>
                  <span className={`text-[12px] ${textSecondary} truncate`} style={{ fontWeight: 440 }}>{emp.location.split(' ')[0]}</span>
                </div>
                <div className="flex items-center">
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full" style={{ background: status.color }} />
                    <span className="text-[12px]" style={{ fontWeight: 460, color: status.color }}>{status.label}</span>
                  </div>
                </div>
                <div className="flex items-center">
                  <span className={`text-[13px] ${textPrimary} tabular-nums`} style={{ fontWeight: 520 }}>{emp.shifts}</span>
                </div>
                <div className="flex items-center gap-1">
                  <Star size={12} className="text-[#D4A017] fill-[#D4A017]" />
                  <span className={`text-[12px] ${textPrimary} tabular-nums`} style={{ fontWeight: 500 }}>{emp.rating}</span>
                </div>
                <div className="flex items-center justify-center">
                  <button onClick={(e) => { e.stopPropagation(); setSelectedEmployee(emp); }}
                    className={`p-1.5 backfill-ui-radius opacity-0 group-hover:opacity-100 ${isDark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F0F0F5]'} transition-all`}>
                    <Eye size={14} className="text-[#8898AA]" />
                  </button>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Rows - Mobile Cards */}
        <div className={`md:hidden divide-y ${softDivider}`}>
          {filtered.map((emp, i) => {
            const color = roleColors[emp.role] || '#635BFF';
            const status = statusConfig[emp.status];
            return (
              <motion.div key={emp.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, delay: i * 0.02 }}
                onClick={() => setSelectedEmployee(emp)}
                className={`px-4 py-3.5 ${isDark ? 'active:bg-white/[0.03]' : 'active:bg-[#FAFBFC]'} cursor-pointer transition-colors`}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center text-[12px] text-white shrink-0"
                    style={{ fontWeight: 600, background: `linear-gradient(135deg, ${color}, ${color}CC)` }}>
                    {emp.avatar}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className={`text-[14px] ${textPrimary} truncate`} style={{ fontWeight: 520 }}>{emp.name}</p>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: status.color }} />
                        <span className="text-[11px]" style={{ fontWeight: 460, color: status.color }}>{status.label}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[11px] px-2 py-0.5 backfill-ui-radius" style={{ fontWeight: 500, color, background: `${color}10` }}>{emp.role}</span>
                      <span className={`text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>{emp.locationEmoji} {emp.location.split(' ')[0]}</span>
                      <span className={`text-[11px] ${textMuted} ml-auto tabular-nums`} style={{ fontWeight: 460 }}>{emp.shifts} shifts</span>
                      <div className="flex items-center gap-0.5">
                        <Star size={10} className="text-[#D4A017] fill-[#D4A017]" />
                        <span className={`text-[11px] ${textPrimary} tabular-nums`} style={{ fontWeight: 480 }}>{emp.rating}</span>
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
            <AlertCircle size={32} className="text-[#E5E7EB] mx-auto mb-3" />
            <p className={`text-[14px] ${textMuted}`} style={{ fontWeight: 480 }}>No employees match your filters</p>
            <p className={`text-[12px] ${isDark ? 'text-[#5E6D7A]' : 'text-[#C1CED8]'} mt-1`} style={{ fontWeight: 420 }}>Try adjusting your search or filter criteria</p>
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
