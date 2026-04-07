"use client";

import { useState, useRef, useEffect, useMemo } from 'react';
import { useNavigate } from './router-shim';
import { motion, AnimatePresence } from 'motion/react';
import {
  useResolvedAppAppearance,
  useSessionUserDisplay,
} from '@/components/app-session-gate';
import {
  getWorkspace,
  type WorkspaceLocation,
} from '@/lib/api/workspace';
import { buildDashboardLocationBasePathFromAny } from '@/lib/dashboard-paths';
import DashboardShell from './DashboardShell';
import {
  findSourceDashboardLocationBySlug,
  type SourceDashboardLocation,
} from './mock-data';
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

const copilotSuggestions = [
  'Show me open shifts this week',
  'Who has the most hours?',
  'Draft a shift for tomorrow 7am',
];

interface ChatMessage { id: number; role: 'user' | 'assistant'; text: string; }

type DashboardSurfaceLocation = Omit<SourceDashboardLocation, "id"> & {
  id: string | number;
  business_slug?: string;
  location_slug?: string;
  business_name?: string;
  location_name?: string;
  location_id?: string;
  isWorkspaceBacked?: boolean;
};

type CoverageDateParts = {
  dayOfMonth: string;
  monthLabel: string;
  weekdayLabel: string;
};

function buildInitialMessages(firstName: string): ChatMessage[] {
  return [
    {
      id: 1,
      role: 'assistant',
      text: `Hi ${firstName}! I'm your Backfill Copilot. I can help you manage shifts, find available staff, generate reports, and more. What can I help with?`,
    },
  ];
}

function resolveCoverageDateParts(timeZone: string): CoverageDateParts {
  const now = new Date();

  try {
    const dayOfMonth = new Intl.DateTimeFormat('en-US', {
      day: 'numeric',
      timeZone,
    }).format(now);
    const monthLabel = new Intl.DateTimeFormat('en-US', {
      month: 'long',
      timeZone,
    }).format(now);
    const weekdayLabel = new Intl.DateTimeFormat('en-US', {
      weekday: 'long',
      timeZone,
    }).format(now);

    return { dayOfMonth, monthLabel, weekdayLabel };
  } catch {
    return {
      dayOfMonth: String(now.getDate()),
      monthLabel: now.toLocaleString('en-US', { month: 'long' }),
      weekdayLabel: now.toLocaleString('en-US', { weekday: 'long' }),
    };
  }
}

function useCoverageDateParts(timeZone: string): CoverageDateParts {
  const [dateParts, setDateParts] = useState<CoverageDateParts>(() =>
    resolveCoverageDateParts(timeZone),
  );

  useEffect(() => {
    const updateDateParts = () => {
      setDateParts(resolveCoverageDateParts(timeZone));
    };

    updateDateParts();
    const intervalId = window.setInterval(updateDateParts, 60_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [timeZone]);

  return dateParts;
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
  const { isDark } = useDashboardTheme();
  const max = Math.max(...data);
  return (
    <div className="flex items-end gap-[3px]" style={{ height }}>
      {data.map((v, i) => (
        <div
          key={i}
          className={`flex-1 transition-all duration-300 ${
            isDark ? 'backfill-ui-radius' : 'rounded-sm'
          }`}
          style={{
            height: `${(v / max) * 100}%`,
            background: i === data.length - 1 ? color : `${color}30`,
            minWidth: 4,
          }}
        />
      ))}
    </div>
  );
}

function LocationCard({ location, index, onClick }: { location: DashboardSurfaceLocation; index: number; onClick: () => void }) {
  const {
    isDark,
    headingClass,
    bodyClass,
    mutedClass,
    borderClass,
  } = useDashboardTheme();
  const cardRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-2xl';
  const iconRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-xl';
  const buttonRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-lg';
  const [hovered, setHovered] = useState(false);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.08, ease: [0.25, 0.46, 0.45, 0.94] }}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      onClick={onClick} className="group relative cursor-pointer"
    >
      <div className={`relative border overflow-hidden transition-all duration-500 ${cardRadiusClass}`} style={{
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
              <div className={`w-11 h-11 flex items-center justify-center text-[20px] transition-transform duration-300 group-hover:scale-110 ${iconRadiusClass}`} style={{ background: `${location.color}10` }}>
                {location.logo}
              </div>
              <div>
                <h3 className={`text-[15px] tracking-[-0.01em] ${headingClass}`} style={{ fontWeight: 580 }}>{location.name}</h3>
                <span className={`text-[12px] tracking-[0.02em] uppercase ${mutedClass}`} style={{ fontWeight: 480 }}>{location.type}</span>
              </div>
            </div>
            <button className={`p-1.5 transition-colors opacity-0 group-hover:opacity-100 ${buttonRadiusClass} ${isDark ? 'hover:bg-white/[0.06]' : 'hover:bg-black/[0.04]'}`} onClick={(e) => e.stopPropagation()}>
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
function SingleLocationView({ location }: { location: SourceDashboardLocation }) {
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
  const heroIconRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-2xl';
  const primarySurfaceRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-2xl';
  const secondarySurfaceRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-xl';
  const rowRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-lg';
  const ctaRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-full';
  const actionCardRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-xl';
  const actionIconRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-lg';
  const progressRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-full';
  const navigate = useNavigate();
  const { timeZone } = useSmartGreeting();
  const coverageDate = useCoverageDateParts(timeZone);
  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className={`w-14 h-14 flex items-center justify-center text-[28px] ${heroIconRadiusClass}`} style={{ background: `${location.color}10` }}>
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
            className={`hidden sm:flex items-center gap-2 px-5 py-2.5 text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)] ${ctaRadiusClass}`}
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
            <Plus size={15} />Add Location
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Today's Coverage */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.05 }}
            className={`${surfaceClass} ${secondarySurfaceRadiusClass} p-5 flex flex-col overflow-hidden`}>
            <div className="flex items-center gap-4 mb-4">
              <div className="flex items-center gap-3">
                <span className={`text-[42px] tracking-[-0.04em] leading-none ${headingClass}`} style={{ fontWeight: 720 }}>
                  {coverageDate.dayOfMonth}
                </span>
                <div className="flex flex-col">
                  <span className={`text-[13px] leading-tight ${headingClass}`} style={{ fontWeight: 580 }}>
                    {coverageDate.monthLabel}
                  </span>
                  <span className={`text-[13px] leading-tight ${mutedClass}`} style={{ fontWeight: 440 }}>
                    {coverageDate.weekdayLabel}
                  </span>
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
              <div className={`w-full h-1.5 mb-2 overflow-hidden ${progressRadiusClass} ${isDark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]'}`}>
                <div className={`h-full bg-gradient-to-r from-[#00B893] to-[#00D4AA] ${progressRadiusClass}`} style={{ width: '88%' }} />
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
                className={`${surfaceClass} ${secondarySurfaceRadiusClass} px-4 py-4 flex flex-col`}>
                <div className="flex items-center justify-between mb-auto">
                  <span className={`text-[11px] uppercase tracking-[0.04em] ${mutedClass}`} style={{ fontWeight: 480 }}>{stat.label}</span>
                  <stat.icon size={14} style={{ color: stat.color }} />
                </div>
                <span className={`text-[26px] tracking-[-0.02em] mt-1 whitespace-nowrap ${headingClass}`} style={{ fontWeight: 660 }}>{stat.value}</span>
              </motion.div>
            ))}
          </div>

          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
            className={`${surfaceClass} ${secondarySurfaceRadiusClass} p-5 flex flex-col overflow-hidden`}>
            <h3 className={`text-[13px] uppercase tracking-[0.04em] mb-3 shrink-0 ${mutedClass}`} style={{ fontWeight: 480 }}>Top Performers</h3>
            <div className="space-y-1 flex-1 min-h-0">
              {location.topStaff.slice(0, 4).map((s, i) => (
                <div key={i} className={`flex items-center gap-2.5 p-2 transition-colors ${rowRadiusClass} ${rowHoverClass}`}>
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
            className={`${surfaceClass} ${primarySurfaceRadiusClass} p-6`}>
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
            className={`${surfaceClass} ${primarySurfaceRadiusClass} p-6`}>
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
                <button key={action.label} className={`group flex items-center gap-4 p-4 border transition-all duration-300 text-left ${actionCardRadiusClass} ${
                  isDark
                    ? 'bg-white/[0.03] border-white/[0.06] hover:bg-white/[0.05] hover:border-white/[0.12]'
                    : 'bg-white border-[#E5E7EB] hover:border-[#D1D5DB] hover:shadow-[0_4px_12px_rgba(0,0,0,0.04)]'
                }`}>
                  <div className={`w-9 h-9 flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110 ${actionIconRadiusClass}`} style={{ background: `${action.color}10` }}>
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
            className={`${surfaceClass} ${primarySurfaceRadiusClass} p-6`}>
            <h3 className={`text-[15px] mb-4 ${headingClass}`} style={{ fontWeight: 560 }}>Coverage</h3>
            <div className="mb-4">
              <div className="flex justify-between mb-2">
                <span className={`text-[12px] ${mutedClass}`} style={{ fontWeight: 440 }}>Fill rate</span>
                <span className={`text-[12px] ${headingClass}`} style={{ fontWeight: 560 }}>{location.fillRate}%</span>
              </div>
              <div className={`h-2 overflow-hidden ${progressRadiusClass} ${isDark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]'}`}>
                <motion.div initial={{ width: 0 }} animate={{ width: `${location.fillRate}%` }} transition={{ duration: 1, delay: 0.5, ease: 'easeOut' }}
                  className={`h-full ${progressRadiusClass}`} style={{ background: `linear-gradient(90deg, ${location.color}, ${location.color}CC)` }} />
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
            className={`${surfaceClass} ${primarySurfaceRadiusClass} p-6`}>
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
function MultiLocationView({
  locations,
  locationsLoaded,
}: {
  locations: DashboardSurfaceLocation[];
  locationsLoaded: boolean;
}) {
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
  const ctaRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-full';
  const secondarySurfaceRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-xl';
  const rowRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-lg';
  const pillRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-full';
  const emptyCardRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-2xl';
  const emptyIconRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-xl';
  const actionCardRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-xl';
  const actionIconRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-lg';
  const progressRadiusClass = isDark ? 'backfill-ui-radius' : 'rounded-full';
  const navigate = useNavigate();
  const { greeting, timeZone } = useSmartGreeting();
  const coverageDate = useCoverageDateParts(timeZone);
  const totalStaff = locations.reduce((a, b) => a + b.totalStaff, 0);
  const totalActive = locations.reduce((a, b) => a + b.activeShifts, 0);
  const avgFillRate =
    locations.length > 0
      ? Math.round(locations.reduce((a, b) => a + b.fillRate, 0) / locations.length)
      : 0;
  const totalOpen = locations.reduce((a, b) => a + b.openShifts, 0);
  const totalScheduled = totalActive + totalOpen;
  const coverageRate =
    totalScheduled > 0 ? Math.round((totalActive / totalScheduled) * 100) : 0;
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
            className={`hidden sm:flex items-center gap-2 px-5 py-2.5 text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)] ${ctaRadiusClass}`}
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
            <Plus size={15} />Add Location
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Today's Coverage */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.05 }}
            className={`${surfaceClass} ${secondarySurfaceRadiusClass} p-5 flex flex-col overflow-hidden`}>
            <div className="flex items-center gap-4 mb-4">
              <div className="flex items-center gap-3">
                <span className={`text-[42px] tracking-[-0.04em] leading-none ${headingClass}`} style={{ fontWeight: 720 }}>
                  {coverageDate.dayOfMonth}
                </span>
                <div className="flex flex-col">
                  <span className={`text-[13px] leading-tight ${headingClass}`} style={{ fontWeight: 580 }}>
                    {coverageDate.monthLabel}
                  </span>
                  <span className={`text-[13px] leading-tight ${mutedClass}`} style={{ fontWeight: 440 }}>
                    {coverageDate.weekdayLabel}
                  </span>
                </div>
              </div>
              <div className="ml-auto">
                <span className={`text-[11px] uppercase tracking-[0.06em] ${mutedClass}`} style={{ fontWeight: 500 }}>Today's Coverage</span>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto min-h-0 space-y-2 mb-3 pr-1">
              {!locationsLoaded ? (
                Array.from({ length: 3 }).map((_, index) => (
                  <div
                    key={`coverage-skeleton-${index}`}
                    className={`h-8 animate-pulse ${rowRadiusClass} ${
                      isDark ? 'bg-white/[0.05]' : 'bg-[#F7F8FA]'
                    }`}
                  />
                ))
              ) : locations.length > 0 ? (
                locations.map((loc) => (
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
                ))
              ) : (
                <div className={`pt-2 text-[12px] ${mutedClass}`} style={{ fontWeight: 440 }}>
                  Add your first location to start tracking coverage here.
                </div>
              )}
            </div>
            <div className={`pt-3 border-t shrink-0 ${borderClass}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-[22px] tracking-[-0.03em] ${headingClass}`} style={{ fontWeight: 660 }}>{coverageRate}%</span>
                  <span className={`text-[11px] ${mutedClass}`} style={{ fontWeight: 440 }}>covered</span>
                </div>
                <span className={`text-[11px] tabular-nums ${mutedClass}`} style={{ fontWeight: 460 }}>
                  {totalActive} of {totalScheduled}
                </span>
              </div>
              <div className={`w-full h-1.5 mb-2 overflow-hidden ${progressRadiusClass} ${isDark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]'}`}>
                <div className={`h-full bg-gradient-to-r from-[#00B893] to-[#00D4AA] ${progressRadiusClass}`} style={{ width: `${coverageRate}%` }} />
              </div>
              {totalOpen > 0 ? (
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-[#F59E0B] animate-pulse" />
                  <span className={`text-[10px] ${bodyClass}`} style={{ fontWeight: 460 }}>{totalOpen} filling now · ~8 min</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-[#00B893]" />
                  <span className={`text-[10px] ${bodyClass}`} style={{ fontWeight: 460 }}>
                    {locationsLoaded ? 'No open shifts right now.' : 'Loading coverage...'}
                  </span>
                </div>
              )}
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
                className={`${surfaceClass} ${secondarySurfaceRadiusClass} px-4 py-4 flex flex-col`}>
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
            className={`${surfaceClass} ${secondarySurfaceRadiusClass} p-5 flex flex-col overflow-hidden`}>
            <h3 className={`text-[13px] uppercase tracking-[0.04em] mb-3 shrink-0 ${mutedClass}`} style={{ fontWeight: 480 }}>Top Performers</h3>
            <div className="space-y-1 flex-1 min-h-0">
              {!locationsLoaded ? (
                Array.from({ length: 4 }).map((_, index) => (
                  <div
                    key={`performer-skeleton-${index}`}
                    className={`h-12 animate-pulse ${rowRadiusClass} ${
                      isDark ? 'bg-white/[0.05]' : 'bg-[#F7F8FA]'
                    }`}
                  />
                ))
              ) : locations.length > 0 ? (
                locations.flatMap((loc) =>
                  loc.topStaff.map((s) => ({ ...s, locationName: loc.name, locationLogo: loc.logo, locationColor: loc.color }))
                ).sort((a, b) => b.rating - a.rating).slice(0, 4).map((s, i) => (
                  <div key={`${s.name}-${i}`} className={`flex items-center gap-2.5 p-2 transition-colors ${rowRadiusClass} ${rowHoverClass}`}>
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
                ))
              ) : (
                <div className={`pt-2 text-[12px] ${mutedClass}`} style={{ fontWeight: 440 }}>
                  Add staff and locations to see your top performers here.
                </div>
              )}
            </div>
          </motion.div>
        </div>
      </motion.div>

      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className={`text-[18px] tracking-[-0.01em] ${headingClass}`} style={{ fontWeight: 580 }}>Your Locations</h2>
          <span className={`text-[12px] px-2.5 py-0.5 ${pillRadiusClass} ${pillClass}`} style={{ fontWeight: 500 }}>
            {locationsLoaded ? locations.length : '...'}
          </span>
        </div>
        <button className="flex items-center gap-1 text-[13px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors" style={{ fontWeight: 500 }}>
          View all <ChevronRight size={14} />
        </button>
      </div>

      {!locationsLoaded ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 2 }).map((_, index) => (
            <div
              key={`location-card-skeleton-${index}`}
              className={`h-[248px] animate-pulse border ${emptyCardRadiusClass} ${
                isDark ? 'border-white/[0.06] bg-white/[0.04]' : 'border-[#E5E7EB] bg-[#F7F8FA]'
              }`}
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {locations.map((loc, i) => (
            <LocationCard
              key={String(loc.location_id ?? loc.id)}
              location={loc}
              index={i}
              onClick={() =>
                navigate(
                  loc.isWorkspaceBacked
                    ? buildDashboardLocationBasePathFromAny(loc)
                    : '/onboarding',
                )
              }
            />
          ))}
        </div>
      )}

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.4 }}
        onClick={() => navigate('/onboarding')} className="mt-4 group cursor-pointer">
        <div className={`${emptyCardRadiusClass} border border-dashed transition-all duration-500 p-8 flex items-center justify-center gap-3 ${dashedCardClass}`}>
          <div className={`w-10 h-10 border flex items-center justify-center transition-all duration-300 group-hover:border-[#635BFF]/30 group-hover:bg-[#635BFF]/[0.06] ${emptyIconRadiusClass} ${isDark ? 'border-white/[0.08]' : 'border-[#E5E7EB]'}`}>
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
            <button key={action.label} className={`group flex items-center gap-4 p-4 border transition-all duration-300 text-left ${actionCardRadiusClass} ${
              isDark
                ? 'bg-white/[0.03] border-white/[0.06] hover:bg-white/[0.05] hover:border-white/[0.12]'
                : 'bg-white border-[#E5E7EB] hover:border-[#D1D5DB] hover:shadow-[0_4px_12px_rgba(0,0,0,0.04)]'
            }`}>
              <div className={`w-9 h-9 flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110 ${actionIconRadiusClass}`} style={{ background: `${action.color}10` }}>
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
  const [workspaceLocations, setWorkspaceLocations] = useState<WorkspaceLocation[] | null>(null);
  const [workspaceLocationsLoaded, setWorkspaceLocationsLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadWorkspaceLocations() {
      try {
        const workspace = await getWorkspace();
        if (cancelled) {
          return;
        }
        setWorkspaceLocations(workspace?.locations ?? []);
      } catch {
        if (!cancelled) {
          setWorkspaceLocations([]);
        }
      } finally {
        if (!cancelled) {
          setWorkspaceLocationsLoaded(true);
        }
      }
    }

    void loadWorkspaceLocations();

    return () => {
      cancelled = true;
    };
  }, []);

  const locations = useMemo<DashboardSurfaceLocation[]>(() => {
    if (workspaceLocationsLoaded && workspaceLocations && workspaceLocations.length > 0) {
      return workspaceLocations.map((location) => {
        const referenceLocation = findSourceDashboardLocationBySlug(
          location.location_slug,
        );
        return {
          id: referenceLocation?.id ?? location.location_id,
          slug: referenceLocation?.slug ?? location.location_slug,
          name: location.location_name,
          type: referenceLocation?.type ?? location.business_name,
          logo: referenceLocation?.logo ?? '\u{1F4CD}',
          color: referenceLocation?.color ?? '#635BFF',
          activeShifts: referenceLocation?.activeShifts ?? 0,
          totalStaff: referenceLocation?.totalStaff ?? 0,
          fillRate: referenceLocation?.fillRate ?? 0,
          openShifts: referenceLocation?.openShifts ?? 0,
          revenue: referenceLocation?.revenue ?? '$0',
          trend: referenceLocation?.trend ?? 0,
          weeklyShifts: referenceLocation?.weeklyShifts ?? [0, 0, 0, 0, 0, 0, 0],
          recentActivity: referenceLocation?.recentActivity ?? [],
          topStaff: referenceLocation?.topStaff ?? [],
          business_slug: location.business_slug,
          location_slug: location.location_slug,
          business_name: location.business_name,
          location_name: location.location_name,
          location_id: location.location_id,
          isWorkspaceBacked: true,
        };
      });
    }

    return [];
  }, [workspaceLocations, workspaceLocationsLoaded]);

  const content = (
    <MultiLocationView
      locations={locations}
      locationsLoaded={workspaceLocationsLoaded}
    />
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav="Overview">{content}</DashboardShell>;
}
