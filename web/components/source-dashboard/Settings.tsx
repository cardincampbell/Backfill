"use client";

import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Building2,
  User,
  Bell,
  Shield,
  CreditCard,
  Palette,
  Globe,
  Mail,
  Phone,
  MapPin,
  Camera,
  ChevronRight,
  Check,
  Lock,
  Eye,
  EyeOff,
  Zap,
  Clock,
  Users,
  FileText,
  Link2,
  Smartphone,
  Moon,
  Sun,
  Monitor,
} from 'lucide-react';
import DashboardShell from './DashboardShell';

/* ─── Types ─── */
type SettingsScope = 'business' | 'personal';

interface ToggleProps {
  enabled: boolean;
  onChange: (val: boolean) => void;
}

function Toggle({ enabled, onChange }: ToggleProps) {
  return (
    <button onClick={() => onChange(!enabled)}
      className={`relative w-10 h-[22px] rounded-full transition-all duration-300 ${enabled ? 'bg-[#635BFF]' : 'bg-[#E5E7EB]'}`}>
      <motion.div
        animate={{ x: enabled ? 18 : 2 }}
        transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
        className="absolute top-[2px] w-[18px] h-[18px] rounded-full bg-white shadow-sm" />
    </button>
  );
}

/* ─── Business Settings Sections ─── */
function CompanyProfile() {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center text-white text-[20px]" style={{ fontWeight: 700 }}>
          B
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-[15px] text-[#0A2540]" style={{ fontWeight: 560 }}>Backfill Inc.</h3>
          <p className="text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>Workforce management platform</p>
        </div>
        <button className="hidden sm:flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#F7F8FA] border border-[#E5E7EB] text-[12px] text-[#5E6D7A] hover:bg-[#F0F0F5] transition-all" style={{ fontWeight: 460 }}>
          <Camera size={13} /> Change Logo
        </button>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Company Name</label>
            <input type="text" defaultValue="Backfill Inc."
              className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
              style={{ fontWeight: 440 }} />
          </div>
          <div>
            <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Industry</label>
            <select defaultValue="healthcare"
              className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all appearance-none bg-white"
              style={{ fontWeight: 440 }}>
              <option value="healthcare">Healthcare</option>
              <option value="hospitality">Hospitality</option>
              <option value="staffing">Staffing Agency</option>
              <option value="retail">Retail</option>
            </select>
          </div>
        </div>
        <div>
          <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Business Email</label>
          <input type="email" defaultValue="admin@backfill.io"
            className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
            style={{ fontWeight: 440 }} />
        </div>
        <div>
          <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Business Address</label>
          <input type="text" defaultValue="100 Market St, Suite 400, San Francisco, CA 94105"
            className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
            style={{ fontWeight: 440 }} />
        </div>
        <div>
          <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Timezone</label>
          <select defaultValue="pst"
            className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all appearance-none bg-white"
            style={{ fontWeight: 440 }}>
            <option value="pst">Pacific Time (PT) — UTC-8</option>
            <option value="mst">Mountain Time (MT) — UTC-7</option>
            <option value="cst">Central Time (CT) — UTC-6</option>
            <option value="est">Eastern Time (ET) — UTC-5</option>
          </select>
        </div>
      </div>
    </motion.div>
  );
}

function LocationsSettings() {
  const locations = [
    { name: 'Downtown Medical Center', type: 'Healthcare', emoji: '\u{1F3E5}', color: '#635BFF', staff: 48 },
    { name: 'Sunrise Senior Living', type: 'Senior Care', emoji: '\u{1F305}', color: '#00B893', staff: 32 },
    { name: 'Bay Area Staffing Co.', type: 'Staffing Agency', emoji: '\u{1F3E2}', color: '#FF6B35', staff: 120 },
    { name: 'Coastal Hospitality Group', type: 'Hospitality', emoji: '\u{1F3E8}', color: '#3B82F6', staff: 15 },
  ];

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="space-y-3">
        {locations.map((loc) => (
          <div key={loc.name} className="flex items-center gap-4 p-4 rounded-xl border border-[#E5E7EB] hover:border-[#D1D5DB] hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)] transition-all group">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-[18px]" style={{ background: `${loc.color}10` }}>
              {loc.emoji}
            </div>
            <div className="flex-1">
              <p className="text-[13px] text-[#0A2540]" style={{ fontWeight: 520 }}>{loc.name}</p>
              <p className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>{loc.type} \u2022 {loc.staff} staff</p>
            </div>
            <ChevronRight size={16} className="text-[#C1CED8] group-hover:text-[#8898AA] transition-colors" />
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function BillingSettings() {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      {/* Current Plan */}
      <div className="p-5 rounded-xl border border-[#635BFF]/20 bg-gradient-to-br from-[#635BFF]/[0.04] to-[#8B5CF6]/[0.02] mb-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-[#635BFF]" />
            <span className="text-[14px] text-[#0A2540]" style={{ fontWeight: 580 }}>Business Pro</span>
          </div>
          <span className="text-[11px] text-[#635BFF] px-2.5 py-1 rounded-full bg-[#635BFF]/10" style={{ fontWeight: 520 }}>Current Plan</span>
        </div>
        <div className="flex items-baseline gap-1 mb-3">
          <span className="text-[28px] text-[#0A2540] tracking-[-0.02em]" style={{ fontWeight: 660 }}>$149</span>
          <span className="text-[13px] text-[#8898AA]" style={{ fontWeight: 420 }}>/month</span>
        </div>
        <div className="flex flex-wrap gap-3">
          {['Up to 4 locations', 'Unlimited staff', 'AI Copilot', 'Priority support'].map((f) => (
            <div key={f} className="flex items-center gap-1.5">
              <Check size={12} className="text-[#00B893]" />
              <span className="text-[11px] text-[#5E6D7A]" style={{ fontWeight: 440 }}>{f}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Payment Method */}
      <div className="p-4 rounded-xl border border-[#E5E7EB] mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-7 rounded-md bg-[#1A1F36] flex items-center justify-center">
              <span className="text-[10px] text-white" style={{ fontWeight: 600 }}>VISA</span>
            </div>
            <div>
              <p className="text-[13px] text-[#0A2540]" style={{ fontWeight: 480 }}>\u2022\u2022\u2022\u2022 \u2022\u2022\u2022\u2022 \u2022\u2022\u2022\u2022 4242</p>
              <p className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>Expires 12/27</p>
            </div>
          </div>
          <button className="text-[12px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors" style={{ fontWeight: 500 }}>Update</button>
        </div>
      </div>

      {/* Billing History */}
      <div>
        <h4 className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-3" style={{ fontWeight: 500 }}>Recent Invoices</h4>
        <div className="space-y-2">
          {[
            { date: 'Apr 1, 2026', amount: '$149.00', status: 'Paid' },
            { date: 'Mar 1, 2026', amount: '$149.00', status: 'Paid' },
            { date: 'Feb 1, 2026', amount: '$149.00', status: 'Paid' },
          ].map((inv) => (
            <div key={inv.date} className="flex items-center justify-between py-2.5 border-b border-[#F7F8FA] last:border-0">
              <div className="flex items-center gap-3">
                <FileText size={14} className="text-[#8898AA]" />
                <span className="text-[12px] text-[#3E4C59]" style={{ fontWeight: 440 }}>{inv.date}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[12px] text-[#0A2540]" style={{ fontWeight: 520 }}>{inv.amount}</span>
                <span className="text-[10px] text-[#00B893] bg-[#00B893]/10 px-2 py-0.5 rounded-full" style={{ fontWeight: 500 }}>{inv.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

function BusinessNotifications() {
  const [shifts, setShifts] = useState(true);
  const [compliance, setCompliance] = useState(true);
  const [reports, setReports] = useState(false);
  const [escalations, setEscalations] = useState(true);

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="space-y-1">
        {[
          { label: 'Shift Alerts', desc: 'Get notified when shifts are posted, filled, or have callouts', enabled: shifts, onChange: setShifts },
          { label: 'Compliance Alerts', desc: 'Credential expirations, overtime limits, and break violations', enabled: compliance, onChange: setCompliance },
          { label: 'Weekly Reports', desc: 'Receive weekly summary reports via email every Monday', enabled: reports, onChange: setReports },
          { label: 'Escalations', desc: 'Urgent notifications when shifts go unfilled past threshold', enabled: escalations, onChange: setEscalations },
        ].map((item) => (
          <div key={item.label} className="flex items-center justify-between p-4 rounded-xl hover:bg-[#F7F8FA] transition-colors">
            <div>
              <p className="text-[13px] text-[#0A2540]" style={{ fontWeight: 500 }}>{item.label}</p>
              <p className="text-[11px] text-[#8898AA] mt-0.5 max-w-md" style={{ fontWeight: 420 }}>{item.desc}</p>
            </div>
            <Toggle enabled={item.enabled} onChange={item.onChange} />
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function IntegrationsSettings() {
  const integrations = [
    { name: 'Slack', desc: 'Send shift notifications to channels', connected: true, color: '#4A154B', icon: '\u{1F4AC}' },
    { name: 'Google Calendar', desc: 'Sync schedules with team calendars', connected: true, color: '#4285F4', icon: '\u{1F4C5}' },
    { name: 'QuickBooks', desc: 'Export payroll and billing data', connected: false, color: '#2CA01C', icon: '\u{1F4B0}' },
    { name: 'ADP', desc: 'Sync employee records and HR data', connected: false, color: '#D0271D', icon: '\u{1F465}' },
  ];

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="space-y-3">
        {integrations.map((int) => (
          <div key={int.name} className="flex items-center gap-3 sm:gap-4 p-3 sm:p-4 rounded-xl border border-[#E5E7EB] hover:border-[#D1D5DB] transition-all">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-[18px] shrink-0" style={{ background: `${int.color}10` }}>
              {int.icon}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[13px] text-[#0A2540] truncate" style={{ fontWeight: 520 }}>{int.name}</p>
              <p className="text-[11px] text-[#8898AA] truncate" style={{ fontWeight: 420 }}>{int.desc}</p>
            </div>
            {int.connected ? (
              <div className="flex items-center gap-2 shrink-0">
                <span className="hidden sm:inline text-[11px] text-[#00B893] bg-[#00B893]/10 px-2.5 py-1 rounded-full" style={{ fontWeight: 500 }}>Connected</span>
                <button className="text-[12px] text-[#8898AA] hover:text-[#E5484D] transition-colors" style={{ fontWeight: 440 }}>Disconnect</button>
              </div>
            ) : (
              <button className="px-3 sm:px-3.5 py-2 rounded-lg text-[12px] text-[#635BFF] border border-[#635BFF]/20 hover:bg-[#635BFF]/[0.04] transition-all shrink-0" style={{ fontWeight: 500 }}>
                Connect
              </button>
            )}
          </div>
        ))}
      </div>
    </motion.div>
  );
}

/* ─── Personal Settings Sections ─── */
function PersonalProfile() {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="flex items-center gap-4 mb-6">
        <div className="relative">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center text-white text-[18px]" style={{ fontWeight: 600 }}>
            JD
          </div>
          <button className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-white border border-[#E5E7EB] flex items-center justify-center shadow-sm hover:bg-[#F7F8FA] transition-colors">
            <Camera size={11} className="text-[#8898AA]" />
          </button>
        </div>
        <div>
          <h3 className="text-[15px] text-[#0A2540]" style={{ fontWeight: 560 }}>Jordan Davis</h3>
          <p className="text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>Account Owner \u2022 Admin</p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>First Name</label>
            <input type="text" defaultValue="Jordan"
              className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
              style={{ fontWeight: 440 }} />
          </div>
          <div>
            <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Last Name</label>
            <input type="text" defaultValue="Davis"
              className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
              style={{ fontWeight: 440 }} />
          </div>
        </div>
        <div>
          <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Email</label>
          <input type="email" defaultValue="jordan@backfill.io"
            className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
            style={{ fontWeight: 440 }} />
        </div>
        <div>
          <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Phone</label>
          <input type="tel" defaultValue="(415) 555-0100"
            className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
            style={{ fontWeight: 440 }} />
        </div>
      </div>
    </motion.div>
  );
}

function SecuritySettings() {
  const [showOld, setShowOld] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [twoFactor, setTwoFactor] = useState(true);

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="space-y-5">
        {/* Change Password */}
        <div>
          <h4 className="text-[13px] text-[#0A2540] mb-3" style={{ fontWeight: 540 }}>Change Password</h4>
          <div className="space-y-3">
            <div className="relative">
              <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Current Password</label>
              <input type={showOld ? 'text' : 'password'} defaultValue="password123"
                className="w-full px-3.5 py-2.5 pr-10 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
                style={{ fontWeight: 440 }} />
              <button onClick={() => setShowOld(!showOld)} className="absolute right-3 top-[34px] text-[#8898AA] hover:text-[#5E6D7A] transition-colors">
                {showOld ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
            <div className="relative">
              <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>New Password</label>
              <input type={showNew ? 'text' : 'password'}
                className="w-full px-3.5 py-2.5 pr-10 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
                style={{ fontWeight: 440 }} placeholder="Enter new password" />
              <button onClick={() => setShowNew(!showNew)} className="absolute right-3 top-[34px] text-[#8898AA] hover:text-[#5E6D7A] transition-colors">
                {showNew ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>
        </div>

        {/* 2FA */}
        <div className="p-4 rounded-xl border border-[#E5E7EB]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-[#00B893]/10 flex items-center justify-center">
                <Smartphone size={16} className="text-[#00B893]" />
              </div>
              <div>
                <p className="text-[13px] text-[#0A2540]" style={{ fontWeight: 500 }}>Two-Factor Authentication</p>
                <p className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>Add an extra layer of security to your account</p>
              </div>
            </div>
            <Toggle enabled={twoFactor} onChange={setTwoFactor} />
          </div>
        </div>

        {/* Sessions */}
        <div>
          <h4 className="text-[13px] text-[#0A2540] mb-3" style={{ fontWeight: 540 }}>Active Sessions</h4>
          <div className="space-y-2">
            {[
              { device: 'MacBook Pro \u2022 Chrome', location: 'San Francisco, CA', current: true },
              { device: 'iPhone 15 Pro \u2022 Safari', location: 'San Francisco, CA', current: false },
            ].map((s) => (
              <div key={s.device} className="flex items-center justify-between p-3 rounded-lg bg-[#F7F8FA]">
                <div className="flex items-center gap-3">
                  <Monitor size={15} className="text-[#8898AA]" />
                  <div>
                    <p className="text-[12px] text-[#0A2540]" style={{ fontWeight: 480 }}>{s.device}</p>
                    <p className="text-[10px] text-[#8898AA]" style={{ fontWeight: 420 }}>{s.location}</p>
                  </div>
                </div>
                {s.current ? (
                  <span className="text-[10px] text-[#00B893] bg-[#00B893]/10 px-2 py-0.5 rounded-full" style={{ fontWeight: 500 }}>This Device</span>
                ) : (
                  <button className="text-[11px] text-[#E5484D] hover:text-[#C13535] transition-colors" style={{ fontWeight: 460 }}>Revoke</button>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function PersonalNotifications() {
  const [email, setEmail] = useState(true);
  const [push, setPush] = useState(true);
  const [sms, setSms] = useState(false);
  const [digest, setDigest] = useState(true);

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="space-y-1">
        {[
          { label: 'Email Notifications', desc: 'Receive updates and alerts via email', enabled: email, onChange: setEmail },
          { label: 'Push Notifications', desc: 'Get real-time push notifications on your devices', enabled: push, onChange: setPush },
          { label: 'SMS Notifications', desc: 'Receive urgent alerts via text message', enabled: sms, onChange: setSms },
          { label: 'Daily Digest', desc: 'Get a summary of the day\'s activity each evening', enabled: digest, onChange: setDigest },
        ].map((item) => (
          <div key={item.label} className="flex items-center justify-between p-4 rounded-xl hover:bg-[#F7F8FA] transition-colors">
            <div>
              <p className="text-[13px] text-[#0A2540]" style={{ fontWeight: 500 }}>{item.label}</p>
              <p className="text-[11px] text-[#8898AA] mt-0.5" style={{ fontWeight: 420 }}>{item.desc}</p>
            </div>
            <Toggle enabled={item.enabled} onChange={item.onChange} />
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function AppearanceSettings() {
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>('light');

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="space-y-5">
        {/* Theme */}
        <div>
          <h4 className="text-[13px] text-[#0A2540] mb-3" style={{ fontWeight: 540 }}>Theme</h4>
          <div className="grid grid-cols-3 gap-3">
            {([
              { key: 'light' as const, label: 'Light', icon: Sun, colors: ['#FFFFFF', '#F7F8FA'] },
              { key: 'dark' as const, label: 'Dark', icon: Moon, colors: ['#0A2540', '#071B30'] },
              { key: 'system' as const, label: 'System', icon: Monitor, colors: ['#FFFFFF', '#0A2540'] },
            ]).map((t) => (
              <button key={t.key} onClick={() => setTheme(t.key)}
                className={`relative p-4 rounded-xl border-2 transition-all duration-300 text-center ${
                  theme === t.key ? 'border-[#635BFF] bg-[#635BFF]/[0.03] shadow-[0_0_0_3px_rgba(99,91,255,0.1)]' : 'border-[#E5E7EB] hover:border-[#D1D5DB]'
                }`}>
                {theme === t.key && (
                  <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-[#635BFF] flex items-center justify-center">
                    <Check size={11} className="text-white" />
                  </div>
                )}
                <div className="flex items-center justify-center gap-1 mb-2">
                  <div className="w-8 h-6 rounded-md border border-[#E5E7EB] overflow-hidden flex">
                    <div className="flex-1" style={{ background: t.colors[0] }} />
                    <div className="flex-1" style={{ background: t.colors[1] }} />
                  </div>
                </div>
                <t.icon size={16} className={`mx-auto mb-1.5 ${theme === t.key ? 'text-[#635BFF]' : 'text-[#8898AA]'}`} />
                <span className="text-[12px] block" style={{ fontWeight: theme === t.key ? 540 : 440, color: theme === t.key ? '#635BFF' : '#5E6D7A' }}>
                  {t.label}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Language */}
        <div>
          <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Language</label>
          <select defaultValue="en"
            className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all appearance-none bg-white"
            style={{ fontWeight: 440 }}>
            <option value="en">English (US)</option>
            <option value="es">Espa\u00F1ol</option>
            <option value="fr">Fran\u00E7ais</option>
            <option value="de">Deutsch</option>
          </select>
        </div>

        {/* Date Format */}
        <div>
          <label className="block text-[11px] text-[#8898AA] uppercase tracking-[0.04em] mb-1.5" style={{ fontWeight: 500 }}>Date Format</label>
          <select defaultValue="mdy"
            className="w-full px-3.5 py-2.5 rounded-lg border border-[#E5E7EB] text-[13px] text-[#0A2540] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all appearance-none bg-white"
            style={{ fontWeight: 440 }}>
            <option value="mdy">MM/DD/YYYY</option>
            <option value="dmy">DD/MM/YYYY</option>
            <option value="ymd">YYYY-MM-DD</option>
          </select>
        </div>
      </div>
    </motion.div>
  );
}

/* ─── Section Config ─── */
const businessSections = [
  { key: 'company', label: 'Company Profile', icon: Building2, component: CompanyProfile },
  { key: 'locations', label: 'Locations', icon: MapPin, component: LocationsSettings },
  { key: 'billing', label: 'Billing & Plan', icon: CreditCard, component: BillingSettings },
  { key: 'notifications', label: 'Notifications', icon: Bell, component: BusinessNotifications },
  { key: 'integrations', label: 'Integrations', icon: Link2, component: IntegrationsSettings },
];

const personalSections = [
  { key: 'profile', label: 'My Profile', icon: User, component: PersonalProfile },
  { key: 'security', label: 'Security', icon: Shield, component: SecuritySettings },
  { key: 'notifications', label: 'Notifications', icon: Bell, component: PersonalNotifications },
  { key: 'appearance', label: 'Appearance', icon: Palette, component: AppearanceSettings },
];

/* ─── Main Settings Page ─── */
export default function Settings() {
  const [scope, setScope] = useState<SettingsScope>('business');
  const [activeSection, setActiveSection] = useState('company');
  const [hasChanges, setHasChanges] = useState(false);

  const sections = scope === 'business' ? businessSections : personalSections;
  const currentSection = sections.find((s) => s.key === activeSection);
  const CurrentComponent = currentSection?.component || CompanyProfile;

  const switchScope = (newScope: SettingsScope) => {
    setScope(newScope);
    setActiveSection(newScope === 'business' ? 'company' : 'profile');
  };

  return (
    <DashboardShell activeNav="Settings">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="overflow-hidden">
        {/* Header */}
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1 className="text-[24px] sm:text-[28px] md:text-[32px] text-[#0A2540] tracking-[-0.025em] mb-1" style={{ fontWeight: 620 }}>
              Settings
            </h1>
            <p className="text-[13px] sm:text-[15px] text-[#8898AA]" style={{ fontWeight: 420 }}>
              Manage your business and personal preferences.
            </p>
          </div>
          {hasChanges && (
            <motion.button initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
              onClick={() => setHasChanges(false)}
              className="hidden sm:block px-5 py-2.5 rounded-full text-[13px] text-white whitespace-nowrap transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)]"
              style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
              Save Changes
            </motion.button>
          )}
        </div>

        {/* Scope Switcher */}
        <div className="mb-6">
          <div className="inline-flex items-center bg-[#F0F0F5] rounded-xl p-1 gap-0.5">
            <button onClick={() => switchScope('business')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-[13px] transition-all duration-300 ${
                scope === 'business'
                  ? 'bg-white text-[#0A2540] shadow-[0_1px_3px_rgba(0,0,0,0.08)]'
                  : 'text-[#8898AA] hover:text-[#5E6D7A]'
              }`}
              style={{ fontWeight: scope === 'business' ? 540 : 420 }}>
              <Building2 size={15} />
              Business
            </button>
            <button onClick={() => switchScope('personal')}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-[13px] transition-all duration-300 ${
                scope === 'personal'
                  ? 'bg-white text-[#0A2540] shadow-[0_1px_3px_rgba(0,0,0,0.08)]'
                  : 'text-[#8898AA] hover:text-[#5E6D7A]'
              }`}
              style={{ fontWeight: scope === 'personal' ? 540 : 420 }}>
              <User size={15} />
              Personal
            </button>
          </div>
        </div>

        {/* Two-column layout: sidebar nav + content */}
        <div className="flex flex-col md:flex-row gap-6">
          {/* Settings Nav - horizontal scrollable on mobile, vertical sidebar on desktop */}
          <motion.div key={scope} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.3 }}
            className="md:w-56 shrink-0">
            <nav className="grid grid-cols-2 sm:grid-cols-3 md:flex md:flex-col gap-1.5 md:gap-0.5 pb-2 md:pb-0 md:sticky md:top-24">
              {sections.map((section) => (
                <button key={section.key} onClick={() => { setActiveSection(section.key); setHasChanges(true); }}
                  className={`flex items-center gap-2 md:gap-3 px-3 md:px-3.5 py-2.5 md:py-2.5 rounded-lg text-left transition-all duration-200 md:w-full ${
                    activeSection === section.key
                      ? 'bg-[#635BFF]/[0.08] text-[#635BFF]'
                      : 'text-[#5E6D7A] hover:text-[#0A2540] hover:bg-[#F7F8FA]'
                  }`}>
                  <section.icon size={16} className="shrink-0" />
                  <span className="text-[13px] truncate" style={{ fontWeight: activeSection === section.key ? 540 : 440 }}>{section.label}</span>
                </button>
              ))}
            </nav>
          </motion.div>

          {/* Settings Content */}
          <div className="flex-1 min-w-0">
            <div className="bg-white border border-[#E5E7EB] rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.04)] p-4 sm:p-6">
              <div className="flex items-center gap-3 mb-6 pb-5 border-b border-[#F0F0F5]">
                {currentSection && (
                  <>
                    <div className="w-9 h-9 rounded-xl bg-[#635BFF]/10 flex items-center justify-center">
                      <currentSection.icon size={16} className="text-[#635BFF]" />
                    </div>
                    <div>
                      <h2 className="text-[16px] text-[#0A2540]" style={{ fontWeight: 580 }}>{currentSection.label}</h2>
                      <p className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                        {scope === 'business' ? 'Organization-wide setting' : 'Your personal preference'}
                      </p>
                    </div>
                  </>
                )}
              </div>

              <AnimatePresence mode="wait">
                <motion.div key={`${scope}-${activeSection}`}>
                  <CurrentComponent />
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Mobile sticky save bar */}
      <AnimatePresence>
        {hasChanges && (
          <motion.div
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="fixed bottom-0 left-0 right-0 z-30 sm:hidden px-4 pb-[calc(env(safe-area-inset-bottom)+12px)] pt-3 bg-gradient-to-t from-white via-white to-white/80 border-t border-[#E5E7EB]"
          >
            <button
              onClick={() => setHasChanges(false)}
              className="w-full py-3 rounded-full text-[14px] text-white transition-all duration-300 active:scale-[0.98]"
              style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}
            >
              Save Changes
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </DashboardShell>
  );
}