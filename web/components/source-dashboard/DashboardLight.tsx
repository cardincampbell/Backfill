"use client";

import { useState, useRef, useEffect } from 'react';
import { Link, useNavigate } from './router-shim';
import { motion, AnimatePresence } from 'motion/react';
import {
  useResolvedAppAppearance,
  useSessionUserDisplay,
} from '@/components/app-session-gate';
import DashboardShell from './DashboardShell';
import { useSmartGreeting } from './use-smart-greeting';
import {
  Plus,
  MoreHorizontal,
  Users,
  CalendarDays,
  TrendingUp,
  Clock,
  ChevronRight,
  Bell,
  Search,
  Settings,
  CheckCircle2,
  AlertCircle,
  ArrowUpRight,
  LayoutGrid,
  Zap,
  BarChart3,
  HelpCircle,
  Send,
  Sparkles,
  Shield,
  Activity,
  Timer,
  DollarSign,
  Hourglass,
  CircleCheck,
  Loader,
  Menu,
  X,
  Moon,
} from 'lucide-react';

/* ─── Data ─── */
const allLocations = [
  {
    id: 1, name: 'Downtown Medical Center', type: 'Healthcare', logo: '\u{1F3E5}', color: '#635BFF',
    activeShifts: 24, totalStaff: 48, fillRate: 96, openShifts: 3, revenue: '$12,400', trend: +8.2,
    weeklyShifts: [18, 22, 20, 24, 19, 21, 24],
    recentActivity: [
      { text: 'Sarah M. accepted Night Shift — ICU', time: '2 min ago', type: 'success' as const },
      { text: '3 open shifts posted for ER coverage', time: '18 min ago', type: 'info' as const },
      { text: 'Marcus T. called out — Shift reassigned', time: '1 hr ago', type: 'warning' as const },
      { text: 'Weekly compliance report generated', time: '2 hrs ago', type: 'info' as const },
    ],
    topStaff: [
      { name: 'Sarah Martinez', role: 'RN', shifts: 18, rating: 4.9 },
      { name: 'James Chen', role: 'LPN', shifts: 15, rating: 4.8 },
      { name: 'Aisha Patel', role: 'CNA', shifts: 22, rating: 4.7 },
    ],
  },
  {
    id: 2, name: 'Sunrise Senior Living', type: 'Senior Care', logo: '\u{1F305}', color: '#00B893',
    activeShifts: 18, totalStaff: 32, fillRate: 91, openShifts: 5, revenue: '$8,750', trend: +12.5,
    weeklyShifts: [14, 16, 15, 18, 17, 16, 18],
    recentActivity: [
      { text: 'New caregiver onboarded successfully', time: '15 min ago', type: 'success' as const },
      { text: '5 weekend shifts still need coverage', time: '45 min ago', type: 'warning' as const },
    ],
    topStaff: [
      { name: 'Emily Ross', role: 'Caregiver', shifts: 20, rating: 4.9 },
      { name: 'David Kim', role: 'CNA', shifts: 16, rating: 4.6 },
    ],
  },
  {
    id: 3, name: 'Bay Area Staffing Co.', type: 'Staffing Agency', logo: '\u{1F3E2}', color: '#FF6B35',
    activeShifts: 42, totalStaff: 120, fillRate: 88, openShifts: 12, revenue: '$34,200', trend: +5.1,
    weeklyShifts: [35, 38, 40, 42, 39, 41, 42],
    recentActivity: [
      { text: '12 shifts broadcast to available staff', time: '1 hr ago', type: 'info' as const },
    ],
    topStaff: [
      { name: 'Carlos Rivera', role: 'Temp RN', shifts: 24, rating: 4.8 },
    ],
  },
  {
    id: 4, name: 'Coastal Hospitality Group', type: 'Hospitality', logo: '\u{1F3E8}', color: '#3B82F6',
    activeShifts: 8, totalStaff: 15, fillRate: 100, openShifts: 0, revenue: '$4,100', trend: -2.3,
    weeklyShifts: [6, 7, 8, 8, 7, 8, 8],
    recentActivity: [
      { text: 'All shifts fully staffed for the week', time: '3 hrs ago', type: 'success' as const },
    ],
    topStaff: [
      { name: 'Mia Johnson', role: 'Server Lead', shifts: 12, rating: 4.9 },
    ],
  },
];

const notifications = [
  { id: 1, text: '3 shifts need coverage at Downtown Medical', time: '2m', urgent: true },
  { id: 2, text: 'New staff member onboarded at Sunrise Senior', time: '15m', urgent: false },
  { id: 3, text: 'Weekly report ready for Bay Area Staffing', time: '1h', urgent: false },
];

const navItems = [
  { label: 'Overview', icon: LayoutGrid, active: true },
  { label: 'Team', icon: Users, active: false },
];

const copilotSuggestions = [
  'Show me open shifts this week',
  'Who has the most hours?',
  'Draft a shift for tomorrow 7am',
];

interface ChatMessage { id: number; role: 'user' | 'assistant'; text: string; }

function buildInitialMessages(firstName: string): ChatMessage[] {
  return [
    {
      id: 1,
      role: 'assistant',
      text: `Hi ${firstName}! I'm your Backfill Copilot. I can help you manage shifts, find available staff, generate reports, and more. What can I help with?`,
    },
  ];
}

/* ─── Components ─── */

function useDashboardTheme() {
  const resolvedAppearance = useResolvedAppAppearance();
  const isDark = resolvedAppearance === 'dark';

  return {
    isDark,
    headingClass: isDark ? 'text-white' : 'text-[#0A2540]',
    bodyClass: isDark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]',
    mutedClass: 'text-[#8898AA]',
    strongBodyClass: isDark ? 'text-[#C1CED8]' : 'text-[#3E4C59]',
    surfaceClass: isDark
      ? 'bg-white/[0.03] border border-white/[0.06] shadow-[0_1px_3px_rgba(0,0,0,0.12)]'
      : 'bg-white border border-[#E5E7EB] shadow-[0_1px_2px_rgba(0,0,0,0.03)]',
    borderClass: isDark ? 'border-white/[0.06]' : 'border-[#F0F0F5]',
    rowHoverClass: isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]',
    pillClass: isDark
      ? 'bg-white/[0.06] text-[#C1CED8]'
      : 'bg-[#F0F0F5] text-[#8898AA]',
    dashedCardClass: isDark
      ? 'border-white/[0.12] bg-white/[0.02] hover:border-[#635BFF]/40 hover:bg-[#635BFF]/[0.06]'
      : 'border-[#D1D5DB] bg-white hover:border-[#635BFF]/40 hover:bg-[#635BFF]/[0.02]',
    subtleInputClass: isDark
      ? 'bg-white/[0.04] border-white/[0.06] text-white placeholder-[#8898AA]/50'
      : 'bg-[#F7F8FA] border-[#E5E7EB] text-[#0A2540] placeholder-[#8898AA]/60',
  };
}

function MiniBarChart({ data, color, height = 40 }: { data: number[]; color: string; height?: number }) {
  const max = Math.max(...data);
  return (
    <div className="flex items-end gap-[3px]" style={{ height }}>
      {data.map((v, i) => (
        <div key={i} className="flex-1 rounded-sm transition-all duration-300" style={{ height: `${(v / max) * 100}%`, background: i === data.length - 1 ? color : `${color}30`, minWidth: 4 }} />
      ))}
    </div>
  );
}

function LocationCard({ location, index, onClick }: { location: typeof allLocations[0]; index: number; onClick: () => void }) {
  const {
    isDark,
    headingClass,
    bodyClass,
    mutedClass,
    borderClass,
  } = useDashboardTheme();
  const [hovered, setHovered] = useState(false);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.08, ease: [0.25, 0.46, 0.45, 0.94] }}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      onClick={onClick} className="group relative cursor-pointer"
    >
      <div className="relative rounded-2xl border overflow-hidden transition-all duration-500" style={{
        borderColor: hovered
          ? `${location.color}30`
          : isDark
            ? 'rgba(255,255,255,0.06)'
            : '#E5E7EB',
        backgroundColor: hovered
          ? isDark
            ? 'rgba(255,255,255,0.05)'
            : '#FAFBFF'
          : isDark
            ? 'rgba(255,255,255,0.03)'
            : '#FFFFFF',
        boxShadow: hovered
          ? `0 20px 60px -12px ${location.color}18, 0 0 0 1px ${location.color}10`
          : isDark
            ? '0 1px 3px rgba(0,0,0,0.12)'
            : '0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)',
      }}>
        <div className="h-[2px] w-full transition-all duration-500" style={{
          background: hovered ? `linear-gradient(90deg, transparent, ${location.color}, transparent)` : `linear-gradient(90deg, transparent, ${location.color}30, transparent)`,
        }} />
        <div className="p-6">
          <div className="flex items-start justify-between mb-5">
            <div className="flex items-center gap-3.5">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center text-[20px] transition-transform duration-300 group-hover:scale-110" style={{ background: `${location.color}10` }}>
                {location.logo}
              </div>
              <div>
                <h3 className={`text-[15px] tracking-[-0.01em] ${headingClass}`} style={{ fontWeight: 580 }}>{location.name}</h3>
                <span className={`text-[12px] tracking-[0.02em] uppercase ${mutedClass}`} style={{ fontWeight: 480 }}>{location.type}</span>
              </div>
            </div>
            <button className={`p-1.5 rounded-lg transition-colors opacity-0 group-hover:opacity-100 ${isDark ? 'hover:bg-white/[0.06]' : 'hover:bg-black/[0.04]'}`} onClick={(e) => e.stopPropagation()}>
              <MoreHorizontal size={16} className={mutedClass} />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4 mb-5">
            <div>
              <div className={`text-[11px] mb-1 uppercase tracking-[0.04em] ${mutedClass}`} style={{ fontWeight: 480 }}>Fill Rate</div>
              <div className="flex items-baseline gap-2">
                <span className={`text-[22px] tracking-[-0.02em] ${headingClass}`} style={{ fontWeight: 640 }}>{location.fillRate}%</span>
                <span className="text-[11px] flex items-center gap-0.5" style={{ fontWeight: 520, color: location.trend >= 0 ? '#00B893' : '#E5484D' }}>
                  <TrendingUp size={10} />{location.trend > 0 ? '+' : ''}{location.trend}%
                </span>
              </div>
            </div>
            <div>
              <div className={`text-[11px] mb-1 uppercase tracking-[0.04em] ${mutedClass}`} style={{ fontWeight: 480 }}>This Period</div>
              <span className={`text-[22px] tracking-[-0.02em] ${headingClass}`} style={{ fontWeight: 640 }}>{location.revenue}</span>
            </div>
          </div>
          <div className={`flex items-center gap-4 pt-4 border-t ${borderClass}`}>
            <div className="flex items-center gap-1.5">
              <Users size={13} className={mutedClass} />
              <span className={`text-[12px] ${bodyClass}`} style={{ fontWeight: 460 }}>{location.totalStaff} staff</span>
            </div>
            <div className="flex items-center gap-1.5">
              <CalendarDays size={13} className={mutedClass} />
              <span className={`text-[12px] ${bodyClass}`} style={{ fontWeight: 460 }}>{location.activeShifts} active</span>
            </div>
            {location.openShifts > 0 ? (
              <div className="flex items-center gap-1.5 ml-auto">
                <div className="w-1.5 h-1.5 rounded-full bg-[#E5484D] animate-pulse" />
                <span className="text-[12px] text-[#E5484D]" style={{ fontWeight: 500 }}>{location.openShifts} open</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 ml-auto">
                <CheckCircle2 size={12} className="text-[#00B893]" />
                <span className="text-[12px] text-[#00B893]" style={{ fontWeight: 500 }}>All filled</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/* ─── Single Location Detail ─── */
function SingleLocationView({ location }: { location: typeof allLocations[0] }) {
  const {
    isDark,
    headingClass,
    bodyClass,
    mutedClass,
    strongBodyClass,
    surfaceClass,
    borderClass,
    rowHoverClass,
  } = useDashboardTheme();
  const navigate = useNavigate();
  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-[28px]" style={{ background: `${location.color}10` }}>
              {location.logo}
            </div>
            <div>
              <h1 className={`text-[28px] sm:text-[32px] tracking-[-0.025em] mb-0.5 ${headingClass}`} style={{ fontWeight: 620 }}>
                {location.name}
              </h1>
              <p className={`text-[14px] ${mutedClass}`} style={{ fontWeight: 420 }}>
                Here's what's happening across your business today.
              </p>
            </div>
          </div>
          <button onClick={() => navigate('/onboarding')}
            className="hidden sm:flex items-center gap-2 px-5 py-2.5 rounded-full text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)]"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
            <Plus size={15} />Add Location
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Today's Coverage */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.05 }}
            className={`${surfaceClass} rounded-xl p-5 flex flex-col overflow-hidden`}>
            <div className="flex items-center gap-4 mb-4">
              <div className="flex items-center gap-3">
                <span className={`text-[42px] tracking-[-0.04em] leading-none ${headingClass}`} style={{ fontWeight: 720 }}>3</span>
                <div className="flex flex-col">
                  <span className={`text-[13px] leading-tight ${headingClass}`} style={{ fontWeight: 580 }}>April</span>
                  <span className={`text-[13px] leading-tight ${mutedClass}`} style={{ fontWeight: 440 }}>Friday</span>
                </div>
              </div>
              <div className="ml-auto">
                <span className={`text-[11px] uppercase tracking-[0.06em] ${mutedClass}`} style={{ fontWeight: 500 }}>Today's Coverage</span>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto min-h-0 space-y-2 mb-3 pr-1">
              {[
                { name: 'ICU', covered: 6, total: 6, status: 'complete' as const },
                { name: 'ER', covered: 5, total: 6, status: 'filling' as const },
                { name: 'Med-Surg', covered: 6, total: 6, status: 'complete' as const },
                { name: 'Pediatrics', covered: 4, total: 6, status: 'complete' as const },
              ].map((unit) => (
                <div key={unit.name} className="flex items-center gap-2.5">
                  <span className={`text-[11px] ${mutedClass}`} style={{ fontWeight: 420 }}>↳</span>
                  <span className={`text-[13px] flex-1 ${strongBodyClass}`} style={{ fontWeight: 480 }}>{unit.name}</span>
                  <span className={`text-[13px] tabular-nums ${bodyClass}`} style={{ fontWeight: 520 }}>{unit.covered}/{unit.total}</span>
                  {unit.status === 'complete' ? (
                    <CircleCheck size={14} className="text-[#00B893]" />
                  ) : (
                    <div className="flex items-center gap-1">
                      <Loader size={12} className="text-[#F59E0B] animate-spin" style={{ animationDuration: '2s' }} />
                      <span className="text-[11px] text-[#F59E0B]" style={{ fontWeight: 500 }}>filling</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className={`pt-3 border-t shrink-0 ${borderClass}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-[22px] tracking-[-0.03em] ${headingClass}`} style={{ fontWeight: 660 }}>88%</span>
                  <span className={`text-[11px] ${mutedClass}`} style={{ fontWeight: 440 }}>covered</span>
                </div>
                <span className={`text-[11px] tabular-nums ${mutedClass}`} style={{ fontWeight: 460 }}>21 of 24</span>
              </div>
              <div className={`w-full h-1.5 rounded-full mb-2 overflow-hidden ${isDark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]'}`}>
                <div className="h-full rounded-full bg-gradient-to-r from-[#00B893] to-[#00D4AA]" style={{ width: '88%' }} />
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-[#F59E0B] animate-pulse" />
                <span className={`text-[10px] ${bodyClass}`} style={{ fontWeight: 460 }}>1 filling now · ~4 min</span>
              </div>
            </div>
          </motion.div>

          {/* 2×2 Stat Cards */}
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Avg Fill Time', value: '14 min', icon: Timer, color: '#635BFF' },
              { label: 'Fill Rate', value: `${location.fillRate}%`, icon: TrendingUp, color: '#00B893' },
              { label: 'Cost This Period', value: '$480', icon: DollarSign, color: '#3B82F6' },
              { label: 'Time Saved', value: '12 hrs', icon: Hourglass, color: '#8B5CF6' },
            ].map((stat, i) => (
              <motion.div key={stat.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 + i * 0.06 }}
                className={`${surfaceClass} rounded-xl px-4 py-4 flex flex-col`}>
                <div className="flex items-center justify-between mb-auto">
                  <span className={`text-[11px] uppercase tracking-[0.04em] ${mutedClass}`} style={{ fontWeight: 480 }}>{stat.label}</span>
                  <stat.icon size={14} style={{ color: stat.color }} />
                </div>
                <span className={`text-[26px] tracking-[-0.02em] mt-1 whitespace-nowrap ${headingClass}`} style={{ fontWeight: 660 }}>{stat.value}</span>
              </motion.div>
            ))}
          </div>

          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
            className={`${surfaceClass} rounded-xl p-5 flex flex-col overflow-hidden`}>
            <h3 className={`text-[13px] uppercase tracking-[0.04em] mb-3 shrink-0 ${mutedClass}`} style={{ fontWeight: 480 }}>Top Performers</h3>
            <div className="space-y-1 flex-1 min-h-0">
              {location.topStaff.slice(0, 4).map((s, i) => (
                <div key={i} className={`flex items-center gap-2.5 p-2 rounded-lg transition-colors ${rowHoverClass}`}>
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] text-white shrink-0" style={{ fontWeight: 600, background: location.color }}>
                    {s.name.split(' ').map(n => n[0]).join('')}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-[12px] truncate ${headingClass}`} style={{ fontWeight: 500 }}>{s.name}</p>
                    <span className={`text-[10px] ${mutedClass}`}>{s.role} · {s.shifts} shifts</span>
                  </div>
                  <div className="text-[11px] text-[#D4A017]" style={{ fontWeight: 540 }}>★ {s.rating}</div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          {/* Shift Volume */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
            className={`${surfaceClass} rounded-2xl p-6`}>
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className={`text-[15px] ${headingClass}`} style={{ fontWeight: 560 }}>Shift Volume</h3>
                <span className={`text-[12px] ${mutedClass}`} style={{ fontWeight: 420 }}>Last 7 days</span>
              </div>
              <div className="flex items-baseline gap-2">
                <span className={`text-[20px] tracking-[-0.02em] ${headingClass}`} style={{ fontWeight: 620 }}>{location.revenue}</span>
                <span className="text-[11px] flex items-center gap-0.5" style={{ fontWeight: 520, color: location.trend >= 0 ? '#00B893' : '#E5484D' }}>
                  <TrendingUp size={10} />{location.trend > 0 ? '+' : ''}{location.trend}%
                </span>
              </div>
            </div>
            <MiniBarChart data={location.weeklyShifts} color={location.color} height={80} />
            <div className="flex justify-between mt-2">
              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
                <span key={d} className={`text-[10px] flex-1 text-center ${mutedClass}`} style={{ fontWeight: 440, opacity: 0.7 }}>{d}</span>
              ))}
            </div>
          </motion.div>

          {/* Recent Activity */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.3 }}
            className={`${surfaceClass} rounded-2xl p-6`}>
            <h3 className={`text-[15px] mb-4 ${headingClass}`} style={{ fontWeight: 560 }}>Recent Activity</h3>
            <div className="space-y-3">
              {location.recentActivity.map((a, i) => (
                <div key={i} className="flex items-start gap-3 py-2">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                    a.type === 'success' ? 'bg-[#00B893]/10' : a.type === 'warning' ? 'bg-[#E5484D]/10' : 'bg-[#635BFF]/10'
                  }`}>
                    {a.type === 'success' ? <CheckCircle2 size={12} className="text-[#00B893]" /> :
                     a.type === 'warning' ? <AlertCircle size={12} className="text-[#E5484D]" /> :
                     <Activity size={12} className="text-[#635BFF]" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-[13px] ${strongBodyClass}`} style={{ fontWeight: 440 }}>{a.text}</p>
                    <span className={`text-[11px] ${mutedClass}`} style={{ opacity: 0.7 }}>{a.time}</span>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Quick Actions */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.4 }}>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                { label: 'Post a Shift', desc: 'Broadcast an open shift', icon: Zap, color: '#635BFF' },
                { label: 'Invite Staff', desc: 'Add to your roster', icon: Users, color: '#00B893' },
                { label: 'View Reports', desc: 'Location analytics', icon: ArrowUpRight, color: '#3B82F6' },
              ].map((action) => (
                <button key={action.label} className={`group flex items-center gap-4 p-4 rounded-xl border transition-all duration-300 text-left ${
                  isDark
                    ? 'bg-white/[0.03] border-white/[0.06] hover:bg-white/[0.05] hover:border-white/[0.12]'
                    : 'bg-white border-[#E5E7EB] hover:border-[#D1D5DB] hover:shadow-[0_4px_12px_rgba(0,0,0,0.04)]'
                }`}>
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110" style={{ background: `${action.color}10` }}>
                    <action.icon size={16} style={{ color: action.color }} />
                  </div>
                  <div>
                    <span className={`text-[13px] block ${headingClass}`} style={{ fontWeight: 540 }}>{action.label}</span>
                    <span className={`text-[11px] ${mutedClass}`} style={{ fontWeight: 420 }}>{action.desc}</span>
                  </div>
                </button>
              ))}
            </div>
          </motion.div>
        </div>

        <div className="space-y-4">
          {/* Coverage */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.35 }}
            className={`${surfaceClass} rounded-2xl p-6`}>
            <h3 className={`text-[15px] mb-4 ${headingClass}`} style={{ fontWeight: 560 }}>Coverage</h3>
            <div className="mb-4">
              <div className="flex justify-between mb-2">
                <span className={`text-[12px] ${mutedClass}`} style={{ fontWeight: 440 }}>Fill rate</span>
                <span className={`text-[12px] ${headingClass}`} style={{ fontWeight: 560 }}>{location.fillRate}%</span>
              </div>
              <div className={`h-2 rounded-full overflow-hidden ${isDark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]'}`}>
                <motion.div initial={{ width: 0 }} animate={{ width: `${location.fillRate}%` }} transition={{ duration: 1, delay: 0.5, ease: 'easeOut' }}
                  className="h-full rounded-full" style={{ background: `linear-gradient(90deg, ${location.color}, ${location.color}CC)` }} />
              </div>
            </div>
            <div className="space-y-3 pt-2">
              {[
                { label: 'Filled shifts', value: location.activeShifts, dotColor: '#00B893' },
                { label: 'Open shifts', value: location.openShifts, dotColor: '#E5484D' },
                { label: 'Available staff', value: location.totalStaff - location.activeShifts, dotColor: '#635BFF' },
              ].map((r) => (
                <div key={r.label} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ background: r.dotColor }} />
                    <span className={`text-[12px] ${bodyClass}`} style={{ fontWeight: 440 }}>{r.label}</span>
                  </div>
                  <span className={`text-[13px] ${headingClass}`} style={{ fontWeight: 540 }}>{r.value}</span>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Compliance */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.4 }}
            className={`${surfaceClass} rounded-2xl p-6`}>
            <h3 className={`text-[15px] mb-3 ${headingClass}`} style={{ fontWeight: 560 }}>Compliance</h3>
            <div className="space-y-2.5">
              {['Credentials current', 'Overtime limits met', 'Break compliance'].map((c) => (
                <div key={c} className="flex items-center gap-2.5">
                  <Shield size={13} className="text-[#00B893]" />
                  <span className={`text-[12px] ${bodyClass}`} style={{ fontWeight: 440 }}>{c}</span>
                  <CheckCircle2 size={12} className="text-[#00B893] ml-auto" />
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}

/* ─── Multi Location View ─── */
function MultiLocationView({ locations }: { locations: typeof allLocations }) {
  const {
    isDark,
    headingClass,
    bodyClass,
    mutedClass,
    strongBodyClass,
    surfaceClass,
    borderClass,
    rowHoverClass,
    pillClass,
    dashedCardClass,
  } = useDashboardTheme();
  const navigate = useNavigate();
  const { greeting } = useSmartGreeting();
  const totalStaff = locations.reduce((a, b) => a + b.totalStaff, 0);
  const totalActive = locations.reduce((a, b) => a + b.activeShifts, 0);
  const avgFillRate = Math.round(locations.reduce((a, b) => a + b.fillRate, 0) / locations.length);
  const totalOpen = locations.reduce((a, b) => a + b.openShifts, 0);
  const totalCost = `$${(totalActive * 20).toLocaleString()}`;

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className={`text-[28px] sm:text-[32px] tracking-[-0.025em] mb-1 ${headingClass}`} style={{ fontWeight: 620 }}>
              {greeting}
            </h1>
            <p className={`text-[15px] ${mutedClass}`} style={{ fontWeight: 420 }}>
              Here's what's happening across your business today.
            </p>
          </div>
          <button onClick={() => navigate('/onboarding')}
            className="hidden sm:flex items-center gap-2 px-5 py-2.5 rounded-full text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)]"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
            <Plus size={15} />Add Location
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Today's Coverage */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.05 }}
            className={`${surfaceClass} rounded-xl p-5 flex flex-col overflow-hidden`}>
            <div className="flex items-center gap-4 mb-4">
              <div className="flex items-center gap-3">
                <span className={`text-[42px] tracking-[-0.04em] leading-none ${headingClass}`} style={{ fontWeight: 720 }}>3</span>
                <div className="flex flex-col">
                  <span className={`text-[13px] leading-tight ${headingClass}`} style={{ fontWeight: 580 }}>April</span>
                  <span className={`text-[13px] leading-tight ${mutedClass}`} style={{ fontWeight: 440 }}>Friday</span>
                </div>
              </div>
              <div className="ml-auto">
                <span className={`text-[11px] uppercase tracking-[0.06em] ${mutedClass}`} style={{ fontWeight: 500 }}>Today's Coverage</span>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto min-h-0 space-y-2 mb-3 pr-1">
              {locations.map((loc) => (
                <div key={loc.id} className="flex items-center gap-2.5">
                  <span className={`text-[11px] ${mutedClass}`} style={{ fontWeight: 420 }}>↳</span>
                  <span className="text-[13px]">{loc.logo}</span>
                  <span className={`text-[13px] flex-1 truncate ${strongBodyClass}`} style={{ fontWeight: 480 }}>{loc.name.split(' ')[0]}</span>
                  <span className={`text-[13px] tabular-nums ${bodyClass}`} style={{ fontWeight: 520 }}>{loc.activeShifts}/{loc.activeShifts + loc.openShifts}</span>
                  {loc.openShifts === 0 ? (
                    <CircleCheck size={14} className="text-[#00B893]" />
                  ) : (
                    <div className="flex items-center gap-1">
                      <Loader size={12} className="text-[#F59E0B] animate-spin" style={{ animationDuration: '2s' }} />
                      <span className="text-[11px] text-[#F59E0B]" style={{ fontWeight: 500 }}>{loc.openShifts}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className={`pt-3 border-t shrink-0 ${borderClass}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-[22px] tracking-[-0.03em] ${headingClass}`} style={{ fontWeight: 660 }}>78%</span>
                  <span className={`text-[11px] ${mutedClass}`} style={{ fontWeight: 440 }}>covered</span>
                </div>
                <span className={`text-[11px] tabular-nums ${mutedClass}`} style={{ fontWeight: 460 }}>72 of 92</span>
              </div>
              <div className={`w-full h-1.5 rounded-full mb-2 overflow-hidden ${isDark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]'}`}>
                <div className="h-full rounded-full bg-gradient-to-r from-[#00B893] to-[#00D4AA]" style={{ width: '78%' }} />
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-[#F59E0B] animate-pulse" />
                <span className={`text-[10px] ${bodyClass}`} style={{ fontWeight: 460 }}>{totalOpen} filling now · ~8 min</span>
              </div>
            </div>
          </motion.div>

          {/* 2×2 Stat Cards */}
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Avg Fill Time', value: '22 min', icon: Timer, color: '#635BFF' },
              { label: 'Fill Rate', value: `${avgFillRate}%`, icon: TrendingUp, color: '#00B893' },
              { label: 'Cost This Period', value: totalCost, icon: DollarSign, color: '#3B82F6' },
              { label: 'Time Saved', value: '34 hrs', icon: Hourglass, color: '#8B5CF6' },
            ].map((stat, i) => (
              <motion.div key={stat.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 + i * 0.06 }}
                className={`${surfaceClass} rounded-xl px-4 py-4 flex flex-col`}>
                <div className="flex items-center justify-between mb-auto">
                  <span className={`text-[11px] uppercase tracking-[0.04em] ${mutedClass}`} style={{ fontWeight: 480 }}>{stat.label}</span>
                  <stat.icon size={14} style={{ color: stat.color }} />
                </div>
                <span className={`text-[26px] tracking-[-0.02em] mt-1 whitespace-nowrap ${headingClass}`} style={{ fontWeight: 660 }}>{stat.value}</span>
              </motion.div>
            ))}
          </div>

          {/* Top Performers */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
            className={`${surfaceClass} rounded-xl p-5 flex flex-col overflow-hidden`}>
            <h3 className={`text-[13px] uppercase tracking-[0.04em] mb-3 shrink-0 ${mutedClass}`} style={{ fontWeight: 480 }}>Top Performers</h3>
            <div className="space-y-1 flex-1 min-h-0">
              {locations.flatMap((loc) =>
                loc.topStaff.map((s) => ({ ...s, locationName: loc.name, locationLogo: loc.logo, locationColor: loc.color }))
              ).sort((a, b) => b.rating - a.rating).slice(0, 4).map((s, i) => (
                <div key={`${s.name}-${i}`} className={`flex items-center gap-2.5 p-2 rounded-lg transition-colors ${rowHoverClass}`}>
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] text-white shrink-0" style={{ fontWeight: 600, background: s.locationColor }}>
                    {s.name.split(' ').map(n => n[0]).join('')}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-[12px] truncate ${headingClass}`} style={{ fontWeight: 500 }}>{s.name}</p>
                    <div className="flex items-center gap-1">
                      <span className={`text-[10px] ${mutedClass}`}>{s.role} · {s.shifts} shifts</span>
                      <span className={`text-[9px] ${mutedClass}`} style={{ opacity: 0.5 }}>|</span>
                      <span className="text-[10px]">{s.locationLogo}</span>
                    </div>
                  </div>
                  <div className="text-[11px] text-[#D4A017]" style={{ fontWeight: 540 }}>★ {s.rating}</div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </motion.div>

      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className={`text-[18px] tracking-[-0.01em] ${headingClass}`} style={{ fontWeight: 580 }}>Your Locations</h2>
          <span className={`text-[12px] px-2.5 py-0.5 rounded-full ${pillClass}`} style={{ fontWeight: 500 }}>{locations.length}</span>
        </div>
        <button className="flex items-center gap-1 text-[13px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors" style={{ fontWeight: 500 }}>
          View all <ChevronRight size={14} />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {locations.map((loc, i) => (
          <LocationCard key={loc.id} location={loc} index={i} onClick={() => {}} />
        ))}
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.4 }}
        onClick={() => navigate('/onboarding')} className="mt-4 group cursor-pointer">
        <div className={`rounded-2xl border border-dashed transition-all duration-500 p-8 flex items-center justify-center gap-3 ${dashedCardClass}`}>
          <div className={`w-10 h-10 rounded-xl border flex items-center justify-center transition-all duration-300 group-hover:border-[#635BFF]/30 group-hover:bg-[#635BFF]/[0.06] ${isDark ? 'border-white/[0.08]' : 'border-[#E5E7EB]'}`}>
            <Plus size={18} className="text-[#8898AA] group-hover:text-[#635BFF] transition-colors" />
          </div>
          <div>
            <span className={`text-[14px] transition-colors ${isDark ? 'text-[#C1CED8] group-hover:text-white' : 'text-[#5E6D7A] group-hover:text-[#0A2540]'}`} style={{ fontWeight: 520 }}>Add another location</span>
            <p className={`text-[12px] ${mutedClass}`} style={{ fontWeight: 420, opacity: 0.7 }}>Set up a new location or organization</p>
          </div>
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.5 }} className="mt-10">
        <h2 className={`text-[16px] mb-4 tracking-[-0.01em] ${mutedClass}`} style={{ fontWeight: 500 }}>Quick Actions</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { label: 'Post a Shift', desc: 'Create and broadcast an open shift', icon: Zap, color: '#635BFF' },
            { label: 'Invite Staff', desc: 'Add team members to your roster', icon: Users, color: '#00B893' },
            { label: 'View Reports', desc: 'Analytics across all locations', icon: ArrowUpRight, color: '#3B82F6' },
          ].map((action) => (
            <button key={action.label} className={`group flex items-center gap-4 p-4 rounded-xl border transition-all duration-300 text-left ${
              isDark
                ? 'bg-white/[0.03] border-white/[0.06] hover:bg-white/[0.05] hover:border-white/[0.12]'
                : 'bg-white border-[#E5E7EB] hover:border-[#D1D5DB] hover:shadow-[0_4px_12px_rgba(0,0,0,0.04)]'
            }`}>
              <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110" style={{ background: `${action.color}10` }}>
                <action.icon size={16} style={{ color: action.color }} />
              </div>
              <div>
                <span className={`text-[13px] block ${headingClass}`} style={{ fontWeight: 540 }}>{action.label}</span>
                <span className={`text-[11px] ${mutedClass}`} style={{ fontWeight: 420 }}>{action.desc}</span>
              </div>
            </button>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

/* ─── Copilot Chat Panel (Light) ─── */
function CopilotPanel() {
  const { firstName } = useSessionUserDisplay();
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    buildInitialMessages(firstName),
  );
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const sendMessage = (text: string) => {
    if (!text.trim()) return;
    setMessages((m) => [...m, { id: Date.now(), role: 'user', text: text.trim() }]);
    setInput('');
    setIsTyping(true);
    setTimeout(() => {
      const responses: Record<string, string> = {
        'Show me open shifts this week': "You have 20 open shifts this week across all locations:\n\n\u2022 Downtown Medical — 3 (ER, ICU)\n\u2022 Sunrise Senior — 5 (Weekend AM/PM)\n\u2022 Bay Area Staffing — 12 (Various)\n\nWould you like me to auto-broadcast these to available staff?",
        'Who has the most hours?': "Top hours this pay period:\n\n1. Carlos Rivera — 42 hrs (Bay Area)\n2. Aisha Patel — 38 hrs (Downtown Medical)\n3. Sarah Martinez — 36 hrs (Downtown Medical)\n\nCarlos is approaching overtime. Want me to flag shifts for rebalancing?",
        'Draft a shift for tomorrow 7am': "Here's a draft shift:\n\n\u{1F4CB} **New Shift**\nDate: Tomorrow, 7:00 AM — 3:00 PM\nLocation: Downtown Medical Center\nRole: RN\nRate: $45/hr\n\nShall I post this and notify qualified staff?",
      };
      const reply = responses[text] || "I can help with that! Let me pull up the relevant data for you. What specifically would you like to know?";
      setMessages((m) => [...m, { id: Date.now() + 1, role: 'assistant', text: reply }]);
      setIsTyping(false);
    }, 1200);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
        {messages.map((msg) => (
          <motion.div key={msg.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center shrink-0 mr-2 mt-0.5">
                <Sparkles size={11} className="text-white" />
              </div>
            )}
            <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[12px] leading-relaxed ${
              msg.role === 'user' ? 'bg-[#635BFF] text-white rounded-br-md' : 'bg-[#F0F0F5] text-[#3E4C59] rounded-bl-md'
            }`} style={{ fontWeight: 420, whiteSpace: 'pre-line' }}>
              {msg.text}
            </div>
          </motion.div>
        ))}
        {isTyping && (
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center shrink-0">
              <Sparkles size={11} className="text-white" />
            </div>
            <div className="bg-[#F0F0F5] rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-[#8898AA] animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 rounded-full bg-[#8898AA] animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 rounded-full bg-[#8898AA] animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {messages.length <= 2 && (
        <div className="px-3 pb-2 space-y-1.5">
          {copilotSuggestions.map((s) => (
            <button key={s} onClick={() => sendMessage(s)}
              className="w-full text-left px-3 py-2 rounded-lg bg-[#F7F8FA] border border-[#E5E7EB] hover:bg-[#F0F0F5] transition-colors text-[11px] text-[#5E6D7A]"
              style={{ fontWeight: 440 }}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="p-3 border-t border-[#F0F0F5]">
        <div className="flex items-center gap-2 bg-[#F7F8FA] border border-[#E5E7EB] rounded-xl px-3 py-2 focus-within:border-[#635BFF]/40 focus-within:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all">
          <input type="text" value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage(input)}
            placeholder="Ask Copilot..."
            className="flex-1 bg-transparent text-[12px] text-[#0A2540] placeholder-[#8898AA]/60 focus:outline-none"
            style={{ fontWeight: 420 }} />
          <button onClick={() => sendMessage(input)} disabled={!input.trim()}
            className="p-1.5 rounded-lg hover:bg-[#E5E7EB] transition-colors disabled:opacity-30">
            <Send size={14} className="text-[#635BFF]" />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Main Dashboard Light ─── */
export default function DashboardLight({
  embeddedInShell = false,
}: {
  embeddedInShell?: boolean;
}) {
  const content = <MultiLocationView locations={allLocations} />;

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav="Overview">{content}</DashboardShell>;
}
