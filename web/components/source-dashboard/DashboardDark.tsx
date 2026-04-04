"use client";

import { useState, useRef, useEffect } from 'react';
import { Link, useNavigate } from './router-shim';
import { motion, AnimatePresence } from 'motion/react';
import { useSessionUserDisplay } from '@/components/app-session-gate';
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
  MessageSquare,
  Send,
  Sparkles,
  Bot,
  ArrowDown,
  Shield,
  FileText,
  Activity,
  Timer,
  DollarSign,
  Hourglass,
  CircleCheck,
  Loader,
  Menu,
  X,
  Sun,
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
    id: 2, name: 'Sunrise Senior Living', type: 'Senior Care', logo: '\u{1F305}', color: '#00D4AA',
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

/* ─── Copilot Mock ─── */
const copilotSuggestions = [
  'Show me open shifts this week',
  'Who has the most hours?',
  'Draft a shift for tomorrow 7am',
];

interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  text: string;
}

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

function DotGrid() {
  return (
    <div
      className="absolute inset-0 pointer-events-none"
      style={{
        backgroundImage: 'radial-gradient(circle, rgba(99,91,255,0.04) 1px, transparent 1px)',
        backgroundSize: '24px 24px',
      }}
    />
  );
}

function MiniBarChart({ data, color, height = 40 }: { data: number[]; color: string; height?: number }) {
  const max = Math.max(...data);
  return (
    <div className="flex items-end gap-[3px]" style={{ height }}>
      {data.map((v, i) => (
        <div
          key={i}
          className="flex-1 rounded-sm transition-all duration-300"
          style={{
            height: `${(v / max) * 100}%`,
            background: i === data.length - 1 ? color : `${color}40`,
            minWidth: 4,
          }}
        />
      ))}
    </div>
  );
}

function LocationCard({ location, index, onClick }: { location: typeof allLocations[0]; index: number; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.08, ease: [0.25, 0.46, 0.45, 0.94] }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onClick}
      className="group relative cursor-pointer"
    >
      <div
        className="relative rounded-2xl border border-white/[0.06] bg-white/[0.03] backdrop-blur-sm overflow-hidden transition-all duration-500"
        style={{
          boxShadow: hovered
            ? `0 20px 60px -12px ${location.color}20, 0 0 0 1px ${location.color}15`
            : '0 1px 3px rgba(0,0,0,0.1)',
        }}
      >
        <div className="h-[2px] w-full transition-all duration-500" style={{
          background: hovered
            ? `linear-gradient(90deg, transparent, ${location.color}, transparent)`
            : `linear-gradient(90deg, transparent, ${location.color}40, transparent)`,
        }} />
        <div className="p-6">
          <div className="flex items-start justify-between mb-5">
            <div className="flex items-center gap-3.5">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center text-[20px] transition-transform duration-300 group-hover:scale-110" style={{ background: `${location.color}15` }}>
                {location.logo}
              </div>
              <div>
                <h3 className="text-[15px] text-white tracking-[-0.01em]" style={{ fontWeight: 560 }}>{location.name}</h3>
                <span className="text-[12px] text-[#8898AA] tracking-[0.02em] uppercase" style={{ fontWeight: 480 }}>{location.type}</span>
              </div>
            </div>
            <button className="p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors opacity-0 group-hover:opacity-100" onClick={(e) => e.stopPropagation()}>
              <MoreHorizontal size={16} className="text-[#8898AA]" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4 mb-5">
            <div>
              <div className="text-[11px] text-[#8898AA] mb-1 uppercase tracking-[0.04em]" style={{ fontWeight: 480 }}>Fill Rate</div>
              <div className="flex items-baseline gap-2">
                <span className="text-[22px] text-white tracking-[-0.02em]" style={{ fontWeight: 620 }}>{location.fillRate}%</span>
                <span className="text-[11px] flex items-center gap-0.5" style={{ fontWeight: 520, color: location.trend >= 0 ? '#00D4AA' : '#FF6B6B' }}>
                  <TrendingUp size={10} />{location.trend > 0 ? '+' : ''}{location.trend}%
                </span>
              </div>
            </div>
            <div>
              <div className="text-[11px] text-[#8898AA] mb-1 uppercase tracking-[0.04em]" style={{ fontWeight: 480 }}>This Period</div>
              <span className="text-[22px] text-white tracking-[-0.02em]" style={{ fontWeight: 620 }}>{location.revenue}</span>
            </div>
          </div>
          <div className="flex items-center gap-4 pt-4 border-t border-white/[0.06]">
            <div className="flex items-center gap-1.5">
              <Users size={13} className="text-[#8898AA]" />
              <span className="text-[12px] text-[#C1CED8]" style={{ fontWeight: 460 }}>{location.totalStaff} staff</span>
            </div>
            <div className="flex items-center gap-1.5">
              <CalendarDays size={13} className="text-[#8898AA]" />
              <span className="text-[12px] text-[#C1CED8]" style={{ fontWeight: 460 }}>{location.activeShifts} active</span>
            </div>
            {location.openShifts > 0 ? (
              <div className="flex items-center gap-1.5 ml-auto">
                <div className="w-1.5 h-1.5 rounded-full bg-[#FF6B6B] animate-pulse" />
                <span className="text-[12px] text-[#FF6B6B]" style={{ fontWeight: 500 }}>{location.openShifts} open</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 ml-auto">
                <CheckCircle2 size={12} className="text-[#00D4AA]" />
                <span className="text-[12px] text-[#00D4AA]" style={{ fontWeight: 500 }}>All filled</span>
              </div>
            )}
          </div>
        </div>
        <div className="absolute inset-0 rounded-2xl pointer-events-none transition-opacity duration-500" style={{ opacity: hovered ? 1 : 0, background: `radial-gradient(600px circle at 50% 0%, ${location.color}06, transparent 70%)` }} />
      </div>
    </motion.div>
  );
}

/* ─── Single Location Detail View ─── */
function SingleLocationView({ location }: { location: typeof allLocations[0] }) {
  const navigate = useNavigate();
  return (
    <div>
      {/* Location Header */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-[28px]" style={{ background: `${location.color}15` }}>
              {location.logo}
            </div>
            <div>
              <h1 className="text-[28px] sm:text-[32px] text-white tracking-[-0.025em] mb-0.5" style={{ fontWeight: 620 }}>
                {location.name}
              </h1>
              <p className="text-[14px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                Here's what's happening across your business today.
              </p>
            </div>
          </div>
          <button
            onClick={() => navigate('/onboarding')}
            className="hidden sm:flex items-center gap-2 px-5 py-2.5 rounded-full text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.3)]"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}
          >
            <Plus size={15} />
            Add Location
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Today's Coverage */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.05 }}
            className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 flex flex-col overflow-hidden">
            <div className="flex items-center gap-4 mb-4">
              <div className="flex items-center gap-3">
                <span className="text-[42px] text-white tracking-[-0.04em] leading-none" style={{ fontWeight: 720 }}>3</span>
                <div className="flex flex-col">
                  <span className="text-[13px] text-white leading-tight" style={{ fontWeight: 580 }}>April</span>
                  <span className="text-[13px] text-[#8898AA] leading-tight" style={{ fontWeight: 440 }}>Friday</span>
                </div>
              </div>
              <div className="ml-auto">
                <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.06em]" style={{ fontWeight: 500 }}>Today's Coverage</span>
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
                  <span className="text-[11px] text-[#8898AA]/50" style={{ fontWeight: 420 }}>↳</span>
                  <span className="text-[13px] text-[#C1CED8] flex-1" style={{ fontWeight: 480 }}>{unit.name}</span>
                  <span className="text-[13px] text-[#8898AA] tabular-nums" style={{ fontWeight: 520 }}>{unit.covered}/{unit.total}</span>
                  {unit.status === 'complete' ? (
                    <CircleCheck size={13} className="text-[#00D4AA]" />
                  ) : (
                    <div className="flex items-center gap-1">
                      <Loader size={11} className="text-[#FFB224] animate-spin" style={{ animationDuration: '2s' }} />
                      <span className="text-[10px] text-[#FFB224]" style={{ fontWeight: 500 }}>filling</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="pt-3 border-t border-white/[0.06] shrink-0">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-[22px] text-white tracking-[-0.03em]" style={{ fontWeight: 660 }}>88%</span>
                  <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>covered</span>
                </div>
                <span className="text-[11px] text-[#8898AA] tabular-nums" style={{ fontWeight: 460 }}>21 of 24</span>
              </div>
              <div className="w-full h-1.5 rounded-full bg-white/[0.06] mb-2 overflow-hidden">
                <div className="h-full rounded-full bg-gradient-to-r from-[#00D4AA] to-[#00F0C0]" style={{ width: '88%' }} />
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-[#FFB224] animate-pulse" />
                <span className="text-[10px] text-white/50" style={{ fontWeight: 460 }}>1 filling now · ~4 min</span>
              </div>
            </div>
          </motion.div>

          {/* 2×2 Stat Cards */}
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Avg Fill Time', value: '14 min', icon: Timer, color: '#635BFF' },
              { label: 'Fill Rate', value: `${location.fillRate}%`, icon: TrendingUp, color: '#3B82F6' },
              { label: 'Cost This Period', value: '$480', icon: DollarSign, color: '#00D4AA' },
              { label: 'Time Saved', value: '12 hrs', icon: Hourglass, color: '#8B5CF6' },
            ].map((stat, i) => (
              <motion.div key={stat.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 + i * 0.06 }}
                className="bg-white/[0.03] border border-white/[0.06] rounded-xl px-4 py-4 flex flex-col">
                <div className="flex items-center justify-between mb-auto">
                  <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 480 }}>{stat.label}</span>
                  <stat.icon size={14} style={{ color: stat.color }} />
                </div>
                <span className="text-[26px] text-white tracking-[-0.02em] mt-1 whitespace-nowrap" style={{ fontWeight: 660 }}>{stat.value}</span>
              </motion.div>
            ))}
          </div>

          {/* Top Performers — vertical */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
            className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 flex flex-col overflow-hidden">
            <h3 className="text-[13px] text-[#8898AA] uppercase tracking-[0.04em] mb-3 shrink-0" style={{ fontWeight: 480 }}>Top Performers</h3>
            <div className="space-y-1 flex-1 min-h-0">
              {location.topStaff.slice(0, 4).map((s, i) => (
                <div key={i} className="flex items-center gap-2.5 p-2 rounded-lg hover:bg-white/[0.03] transition-colors">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] text-white shrink-0" style={{ fontWeight: 600, background: `${location.color}` }}>
                    {s.name.split(' ').map(n => n[0]).join('')}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] text-white truncate" style={{ fontWeight: 500 }}>{s.name}</p>
                    <span className="text-[10px] text-[#8898AA]">{s.role} · {s.shifts} shifts</span>
                  </div>
                  <div className="text-[11px] text-[#FFD700]" style={{ fontWeight: 540 }}>★ {s.rating}</div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </motion.div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left — Activity + Shifts Chart */}
        <div className="lg:col-span-2 space-y-4">
          {/* Weekly Shifts Chart */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
            className="bg-white/[0.03] border border-white/[0.06] rounded-2xl p-6">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-[15px] text-white" style={{ fontWeight: 560 }}>Shift Volume</h3>
                <span className="text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>Last 7 days</span>
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-[20px] text-white tracking-[-0.02em]" style={{ fontWeight: 620 }}>{location.revenue}</span>
                <span className="text-[11px] flex items-center gap-0.5" style={{ fontWeight: 520, color: location.trend >= 0 ? '#00D4AA' : '#FF6B6B' }}>
                  <TrendingUp size={10} />{location.trend > 0 ? '+' : ''}{location.trend}%
                </span>
              </div>
            </div>
            <MiniBarChart data={location.weeklyShifts} color={location.color} height={80} />
            <div className="flex justify-between mt-2">
              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
                <span key={d} className="text-[10px] text-[#8898AA]/60 flex-1 text-center" style={{ fontWeight: 440 }}>{d}</span>
              ))}
            </div>
          </motion.div>

          {/* Recent Activity */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.3 }}
            className="bg-white/[0.03] border border-white/[0.06] rounded-2xl p-6">
            <h3 className="text-[15px] text-white mb-4" style={{ fontWeight: 560 }}>Recent Activity</h3>
            <div className="space-y-3">
              {location.recentActivity.map((a, i) => (
                <div key={i} className="flex items-start gap-3 py-2">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                    a.type === 'success' ? 'bg-[#00D4AA]/15' : a.type === 'warning' ? 'bg-[#FF6B6B]/15' : 'bg-[#635BFF]/15'
                  }`}>
                    {a.type === 'success' ? <CheckCircle2 size={12} className="text-[#00D4AA]" /> :
                     a.type === 'warning' ? <AlertCircle size={12} className="text-[#FF6B6B]" /> :
                     <Activity size={12} className="text-[#635BFF]" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] text-[#C1CED8]" style={{ fontWeight: 440 }}>{a.text}</p>
                    <span className="text-[11px] text-[#8898AA]/70">{a.time}</span>
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
                { label: 'Invite Staff', desc: 'Add to your roster', icon: Users, color: '#00D4AA' },
                { label: 'View Reports', desc: 'Location analytics', icon: ArrowUpRight, color: '#3B82F6' },
              ].map((action) => (
                <button key={action.label} className="group flex items-center gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:bg-white/[0.04] hover:border-white/[0.1] transition-all duration-300 text-left">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110" style={{ background: `${action.color}15` }}>
                    <action.icon size={16} style={{ color: action.color }} />
                  </div>
                  <div>
                    <span className="text-[13px] text-white block" style={{ fontWeight: 540 }}>{action.label}</span>
                    <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>{action.desc}</span>
                  </div>
                </button>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Right — Coverage */}
        <div className="space-y-4">
          {/* Coverage Summary */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.35 }}
            className="bg-white/[0.03] border border-white/[0.06] rounded-2xl p-6">
            <h3 className="text-[15px] text-white mb-4" style={{ fontWeight: 560 }}>Coverage</h3>
            {/* Fill rate visual */}
            <div className="mb-4">
              <div className="flex justify-between mb-2">
                <span className="text-[12px] text-[#8898AA]" style={{ fontWeight: 440 }}>Fill rate</span>
                <span className="text-[12px] text-white" style={{ fontWeight: 560 }}>{location.fillRate}%</span>
              </div>
              <div className="h-2 bg-white/[0.06] rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${location.fillRate}%` }}
                  transition={{ duration: 1, delay: 0.5, ease: 'easeOut' }}
                  className="h-full rounded-full"
                  style={{ background: `linear-gradient(90deg, ${location.color}, ${location.color}CC)` }}
                />
              </div>
            </div>
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-[#00D4AA]" />
                  <span className="text-[12px] text-[#C1CED8]" style={{ fontWeight: 440 }}>Filled shifts</span>
                </div>
                <span className="text-[13px] text-white" style={{ fontWeight: 540 }}>{location.activeShifts}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-[#FF6B6B]" />
                  <span className="text-[12px] text-[#C1CED8]" style={{ fontWeight: 440 }}>Open shifts</span>
                </div>
                <span className="text-[13px] text-white" style={{ fontWeight: 540 }}>{location.openShifts}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-[#635BFF]" />
                  <span className="text-[12px] text-[#C1CED8]" style={{ fontWeight: 440 }}>Available staff</span>
                </div>
                <span className="text-[13px] text-white" style={{ fontWeight: 540 }}>{location.totalStaff - location.activeShifts}</span>
              </div>
            </div>
          </motion.div>

          {/* Compliance */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.4 }}
            className="bg-white/[0.03] border border-white/[0.06] rounded-2xl p-6">
            <h3 className="text-[15px] text-white mb-3" style={{ fontWeight: 560 }}>Compliance</h3>
            <div className="space-y-2.5">
              {[
                { label: 'Credentials current', ok: true },
                { label: 'Overtime limits met', ok: true },
                { label: 'Break compliance', ok: true },
              ].map((c) => (
                <div key={c.label} className="flex items-center gap-2.5">
                  <Shield size={13} className="text-[#00D4AA]" />
                  <span className="text-[12px] text-[#C1CED8]" style={{ fontWeight: 440 }}>{c.label}</span>
                  <CheckCircle2 size={12} className="text-[#00D4AA] ml-auto" />
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
  const navigate = useNavigate();
  const { firstName } = useSessionUserDisplay();
  const totalStaff = locations.reduce((a, b) => a + b.totalStaff, 0);
  const totalActive = locations.reduce((a, b) => a + b.activeShifts, 0);
  const avgFillRate = Math.round(locations.reduce((a, b) => a + b.fillRate, 0) / locations.length);
  const totalOpen = locations.reduce((a, b) => a + b.openShifts, 0);
  const totalCost = `$${(totalActive * 20).toLocaleString()}`;

  const allStaff = locations.flatMap((loc) =>
    loc.topStaff.map((s) => ({ ...s, locationName: loc.name, locationLogo: loc.logo, locationColor: loc.color }))
  ).sort((a, b) => b.rating - a.rating).slice(0, 5);

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className="text-[28px] sm:text-[32px] text-white tracking-[-0.025em] mb-1" style={{ fontWeight: 620 }}>
              Good evening, {firstName}
            </h1>
            <p className="text-[15px] text-[#8898AA]" style={{ fontWeight: 420 }}>
              Here's what's happening across your business today.
            </p>
          </div>
          <button
            onClick={() => navigate('/onboarding')}
            className="hidden sm:flex items-center gap-2 px-5 py-2.5 rounded-full text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.3)]"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}
          >
            <Plus size={15} />
            Add Location
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Today's Coverage */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.05 }}
            className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 flex flex-col overflow-hidden">
            <div className="flex items-center gap-4 mb-4">
              <div className="flex items-center gap-3">
                <span className="text-[42px] text-white tracking-[-0.04em] leading-none" style={{ fontWeight: 720 }}>3</span>
                <div className="flex flex-col">
                  <span className="text-[13px] text-white leading-tight" style={{ fontWeight: 580 }}>April</span>
                  <span className="text-[13px] text-[#8898AA] leading-tight" style={{ fontWeight: 440 }}>Friday</span>
                </div>
              </div>
              <div className="ml-auto">
                <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.06em]" style={{ fontWeight: 500 }}>Today's Coverage</span>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto min-h-0 space-y-2 mb-3 pr-1">
              {locations.map((loc) => (
                <div key={loc.id} className="flex items-center gap-2.5">
                  <span className="text-[11px] text-[#8898AA]/50" style={{ fontWeight: 420 }}>↳</span>
                  <span className="text-[13px]">{loc.logo}</span>
                  <span className="text-[13px] text-[#C1CED8] flex-1 truncate" style={{ fontWeight: 480 }}>{loc.name.split(' ')[0]}</span>
                  <span className="text-[13px] text-[#8898AA] tabular-nums" style={{ fontWeight: 520 }}>{loc.activeShifts}/{loc.activeShifts + loc.openShifts}</span>
                  {loc.openShifts === 0 ? (
                    <CircleCheck size={13} className="text-[#00D4AA]" />
                  ) : (
                    <div className="flex items-center gap-1">
                      <Loader size={11} className="text-[#FFB224] animate-spin" style={{ animationDuration: '2s' }} />
                      <span className="text-[10px] text-[#FFB224]" style={{ fontWeight: 500 }}>{loc.openShifts}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="pt-3 border-t border-white/[0.06] shrink-0">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-[22px] text-white tracking-[-0.03em]" style={{ fontWeight: 660 }}>78%</span>
                  <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>covered</span>
                </div>
                <span className="text-[11px] text-[#8898AA] tabular-nums" style={{ fontWeight: 460 }}>72 of 92</span>
              </div>
              <div className="w-full h-1.5 rounded-full bg-white/[0.06] mb-2 overflow-hidden">
                <div className="h-full rounded-full bg-gradient-to-r from-[#00D4AA] to-[#00F0C0]" style={{ width: '78%' }} />
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-[#FFB224] animate-pulse" />
                <span className="text-[10px] text-white/50" style={{ fontWeight: 460 }}>{totalOpen} filling now · ~8 min</span>
              </div>
            </div>
          </motion.div>

          {/* 2×2 Stat Cards */}
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Avg Fill Time', value: '22 min', icon: Timer, color: '#635BFF' },
              { label: 'Fill Rate', value: `${avgFillRate}%`, icon: TrendingUp, color: '#3B82F6' },
              { label: 'Cost This Period', value: totalCost, icon: DollarSign, color: '#00D4AA' },
              { label: 'Time Saved', value: '34 hrs', icon: Hourglass, color: '#8B5CF6' },
            ].map((stat, i) => (
              <motion.div key={stat.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 + i * 0.06 }}
                className="bg-white/[0.03] border border-white/[0.06] rounded-xl px-4 py-4 flex flex-col">
                <div className="flex items-center justify-between mb-auto">
                  <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 480 }}>{stat.label}</span>
                  <stat.icon size={14} style={{ color: stat.color }} />
                </div>
                <span className="text-[26px] text-white tracking-[-0.02em] mt-1 whitespace-nowrap" style={{ fontWeight: 660 }}>{stat.value}</span>
              </motion.div>
            ))}
          </div>

          {/* Top Performers */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
            className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 flex flex-col overflow-hidden">
            <h3 className="text-[13px] text-[#8898AA] uppercase tracking-[0.04em] mb-3 shrink-0" style={{ fontWeight: 480 }}>Top Performers</h3>
            <div className="space-y-1 flex-1 min-h-0">
              {allStaff.slice(0, 4).map((s, i) => (
                <div key={`${s.name}-${i}`} className="flex items-center gap-2.5 p-2 rounded-lg hover:bg-white/[0.03] transition-colors">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] text-white shrink-0" style={{ fontWeight: 600, background: s.locationColor }}>
                    {s.name.split(' ').map(n => n[0]).join('')}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] text-white truncate" style={{ fontWeight: 500 }}>{s.name}</p>
                    <div className="flex items-center gap-1">
                      <span className="text-[10px] text-[#8898AA]">{s.role} · {s.shifts} shifts</span>
                      <span className="text-[9px] text-[#8898AA]/50">|</span>
                      <span className="text-[10px]">{s.locationLogo}</span>
                    </div>
                  </div>
                  <div className="text-[11px] text-[#FFD700]" style={{ fontWeight: 540 }}>★ {s.rating}</div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </motion.div>

      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-[18px] text-white tracking-[-0.01em]" style={{ fontWeight: 580 }}>Your Locations</h2>
          <span className="text-[12px] text-[#8898AA] bg-white/[0.06] px-2.5 py-0.5 rounded-full" style={{ fontWeight: 500 }}>{locations.length}</span>
        </div>
        <button className="flex items-center gap-1 text-[13px] text-[#635BFF] hover:text-[#8B5CF6] transition-colors" style={{ fontWeight: 500 }}>
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
        <div className="rounded-2xl border border-dashed border-white/[0.08] hover:border-[#635BFF]/30 bg-white/[0.01] hover:bg-[#635BFF]/[0.03] transition-all duration-500 p-8 flex items-center justify-center gap-3">
          <div className="w-10 h-10 rounded-xl border border-white/[0.08] group-hover:border-[#635BFF]/30 flex items-center justify-center transition-all duration-300 group-hover:bg-[#635BFF]/10">
            <Plus size={18} className="text-[#8898AA] group-hover:text-[#635BFF] transition-colors" />
          </div>
          <div>
            <span className="text-[14px] text-[#8898AA] group-hover:text-white transition-colors" style={{ fontWeight: 520 }}>Add another location</span>
            <p className="text-[12px] text-[#8898AA]/60" style={{ fontWeight: 420 }}>Set up a new location or organization</p>
          </div>
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.5 }} className="mt-10">
        <h2 className="text-[16px] text-[#8898AA] mb-4 tracking-[-0.01em]" style={{ fontWeight: 500 }}>Quick Actions</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { label: 'Post a Shift', desc: 'Create and broadcast an open shift', icon: Zap, color: '#635BFF' },
            { label: 'Invite Staff', desc: 'Add team members to your roster', icon: Users, color: '#00D4AA' },
            { label: 'View Reports', desc: 'Analytics across all locations', icon: ArrowUpRight, color: '#3B82F6' },
          ].map((action) => (
            <button key={action.label} className="group flex items-center gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:bg-white/[0.04] hover:border-white/[0.1] transition-all duration-300 text-left">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110" style={{ background: `${action.color}15` }}>
                <action.icon size={16} style={{ color: action.color }} />
              </div>
              <div>
                <span className="text-[13px] text-white block" style={{ fontWeight: 540 }}>{action.label}</span>
                <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>{action.desc}</span>
              </div>
            </button>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

/* ─── Copilot Chat Panel ─── */
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
    const userMsg: ChatMessage = { id: Date.now(), role: 'user', text: text.trim() };
    setMessages((m) => [...m, userMsg]);
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
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-3 scrollbar-thin">
        {messages.map((msg) => (
          <motion.div
            key={msg.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center shrink-0 mr-2 mt-0.5">
                <Sparkles size={11} className="text-white" />
              </div>
            )}
            <div
              className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[12px] leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-[#635BFF] text-white rounded-br-md'
                  : 'bg-white/[0.06] text-[#C1CED8] rounded-bl-md'
              }`}
              style={{ fontWeight: 420, whiteSpace: 'pre-line' }}
            >
              {msg.text}
            </div>
          </motion.div>
        ))}
        {isTyping && (
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center shrink-0">
              <Sparkles size={11} className="text-white" />
            </div>
            <div className="bg-white/[0.06] rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-[#8898AA] animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 rounded-full bg-[#8898AA] animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 rounded-full bg-[#8898AA] animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 2 && (
        <div className="px-3 pb-2 space-y-1.5">
          {copilotSuggestions.map((s) => (
            <button
              key={s}
              onClick={() => sendMessage(s)}
              className="w-full text-left px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] transition-colors text-[11px] text-[#C1CED8]"
              style={{ fontWeight: 440 }}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="p-3 border-t border-white/[0.06]">
        <div className="flex items-center gap-2 bg-white/[0.04] border border-white/[0.06] rounded-xl px-3 py-2 focus-within:border-[#635BFF]/40 transition-colors">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage(input)}
            placeholder="Ask Copilot..."
            className="flex-1 bg-transparent text-[12px] text-white placeholder-[#8898AA]/50 focus:outline-none"
            style={{ fontWeight: 420 }}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim()}
            className="p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors disabled:opacity-30"
          >
            <Send size={14} className="text-[#635BFF]" />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Main Dashboard ─── */
export default function DashboardDark() {
  const [showNotifications, setShowNotifications] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<'nav' | 'copilot'>('nav');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const { fullName, email, phone, initials } = useSessionUserDisplay();

  const locations = allLocations;

  return (
    <div className="min-h-screen bg-[#0A2540] flex" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Left Sidebar */}
      <aside className={`fixed top-0 left-0 h-full z-50 w-[280px] flex flex-col border-r border-white/[0.06] bg-[#071B30]/80 backdrop-blur-xl transition-transform duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        {/* Logo */}
        <div className="flex items-center justify-between h-16 px-5 border-b border-white/[0.06]">
          <Link to="/" className="flex items-center gap-2.5">
            <span className="text-[18px] tracking-[-0.02em] text-white" style={{ fontWeight: 620 }}>Backfill</span>
          </Link>
          <button onClick={() => setSidebarOpen(false)} className="p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors lg:hidden">
            <X size={18} className="text-[#8898AA]" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="px-3 pt-3 pb-1">
          <div className="flex items-center bg-white/[0.04] rounded-lg p-0.5">
            <button
              onClick={() => setSidebarTab('nav')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-[12px] transition-all duration-200 ${
                sidebarTab === 'nav' ? 'bg-white/[0.08] text-white shadow-sm' : 'text-[#8898AA] hover:text-white'
              }`}
              style={{ fontWeight: sidebarTab === 'nav' ? 520 : 440 }}
            >
              <LayoutGrid size={13} />
              Navigate
            </button>
            <button
              onClick={() => setSidebarTab('copilot')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-[12px] transition-all duration-200 ${
                sidebarTab === 'copilot' ? 'bg-[#635BFF]/20 text-[#A5A0FF] shadow-sm' : 'text-[#8898AA] hover:text-white'
              }`}
              style={{ fontWeight: sidebarTab === 'copilot' ? 520 : 440 }}
            >
              <Sparkles size={13} />
              Copilot
            </button>
          </div>
        </div>

        {/* Tab Content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <AnimatePresence mode="wait">
            {sidebarTab === 'nav' ? (
              <motion.div
                key="nav"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                transition={{ duration: 0.2 }}
                className="flex-1 flex flex-col"
              >
                <nav className="flex-1 py-3 px-3 space-y-1">
                  {navItems.map((item) => (
                    <button
                      key={item.label}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                        item.active ? 'bg-white/[0.08] text-white' : 'text-[#8898AA] hover:text-white hover:bg-white/[0.04]'
                      }`}
                    >
                      <item.icon size={18} className="shrink-0" />
                      <span className="text-[13px]" style={{ fontWeight: item.active ? 520 : 440 }}>{item.label}</span>
                    </button>
                  ))}

                  {/* Location shortcuts */}
                  <div className="pt-4 mt-3 border-t border-white/[0.06]">
                    <span className="text-[10px] text-[#8898AA] uppercase tracking-[0.06em] px-3 mb-2 block" style={{ fontWeight: 500 }}>Locations</span>
                    {locations.map((loc) => (
                      <button key={loc.id} className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[#8898AA] hover:text-white hover:bg-white/[0.04] transition-all duration-200">
                        <span className="text-[14px]">{loc.logo}</span>
                        <span className="text-[12px] truncate" style={{ fontWeight: 440 }}>{loc.name}</span>
                        {loc.openShifts > 0 && (
                          <span className="ml-auto text-[10px] text-[#FF6B6B] bg-[#FF6B6B]/15 px-1.5 py-0.5 rounded-full" style={{ fontWeight: 540 }}>{loc.openShifts}</span>
                        )}
                      </button>
                    ))}
                  </div>
                </nav>

                <div className="border-t border-white/[0.06] py-3 px-3 space-y-1">
                  <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#8898AA] hover:text-white hover:bg-white/[0.04] transition-all duration-200">
                    <Settings size={18} className="shrink-0" />
                    <span className="text-[13px]" style={{ fontWeight: 440 }}>Settings</span>
                  </button>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="copilot"
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                transition={{ duration: 0.2 }}
                className="flex-1 flex flex-col overflow-hidden"
              >
                <CopilotPanel />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* User — always visible */}
        <div className="border-t border-white/[0.06] p-3">
          <div className="flex items-center gap-3 rounded-lg p-2 bg-white/[0.03]">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center shrink-0">
              <span className="text-[11px] text-white" style={{ fontWeight: 600 }}>{initials}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12px] text-white truncate" style={{ fontWeight: 520 }}>{fullName}</p>
              <p className="text-[11px] text-[#8898AA] truncate">{email ?? phone ?? 'Phone sign-in'}</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Area */}
      <div className="flex-1 min-h-screen relative lg:ml-[280px]">
        <DotGrid />
        <div className="fixed inset-0 pointer-events-none">
          <div className="absolute top-0 right-0 w-[800px] h-[600px]" style={{ background: 'radial-gradient(ellipse at top right, rgba(99,91,255,0.08), transparent 70%)' }} />
          <div className="absolute bottom-0 left-0 w-[600px] h-[500px]" style={{ background: 'radial-gradient(ellipse at bottom left, rgba(0,212,170,0.05), transparent 70%)' }} />
        </div>

        {/* Top Bar */}
        <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-[#0A2540]/80 backdrop-blur-xl">
          <div className="flex items-center justify-between h-14 sm:h-16 px-4 sm:px-8">
            <div className="flex items-center gap-3">
              <button onClick={() => setSidebarOpen(true)} className="p-2 rounded-lg hover:bg-white/[0.06] transition-colors lg:hidden">
                <Menu size={20} className="text-[#8898AA]" />
              </button>
              <div className="relative hidden sm:block">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8898AA]" />
                <input
                  type="text"
                  placeholder="Search..."
                  className="w-48 md:w-64 pl-9 pr-4 py-2 rounded-lg bg-white/[0.04] border border-white/[0.06] text-[12px] text-white placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 transition-all"
                  style={{ fontWeight: 420 }}
                />
              </div>
            </div>
            <div className="flex items-center gap-1.5 sm:gap-3">
              <button className="p-2 rounded-lg hover:bg-white/[0.06] transition-colors hidden sm:block">
                <HelpCircle size={18} className="text-[#8898AA]" />
              </button>
              <button
                onClick={() => navigate('/dashboard-light')}
                className="p-2 rounded-lg hover:bg-white/[0.06] transition-colors"
                title="Switch to light mode"
              >
                <Sun size={18} className="text-[#8898AA]" />
              </button>
              <div className="relative">
                <button onClick={() => setShowNotifications(!showNotifications)} className="relative p-2 rounded-lg hover:bg-white/[0.06] transition-colors">
                  <Bell size={18} className="text-[#8898AA]" />
                  <div className="absolute top-1.5 right-1.5 w-2 h-2 bg-[#FF6B6B] rounded-full" />
                </button>
                <AnimatePresence>
                  {showNotifications && (
                    <motion.div initial={{ opacity: 0, y: 8, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.96 }} transition={{ duration: 0.2 }}
                      className="absolute right-0 top-full mt-2 w-[calc(100vw-2rem)] sm:w-80 max-w-80 bg-[#0F2E4C] border border-white/[0.08] rounded-xl shadow-2xl overflow-hidden z-50">
                      <div className="px-4 py-3 border-b border-white/[0.06]">
                        <span className="text-[13px] text-white" style={{ fontWeight: 560 }}>Notifications</span>
                      </div>
                      {notifications.map((n) => (
                        <div key={n.id} className="px-4 py-3 hover:bg-white/[0.03] transition-colors border-b border-white/[0.04] last:border-0">
                          <div className="flex items-start gap-2.5">
                            {n.urgent ? <AlertCircle size={14} className="text-[#FF6B6B] mt-0.5 shrink-0" /> : <CheckCircle2 size={14} className="text-[#00D4AA] mt-0.5 shrink-0" />}
                            <div>
                              <p className="text-[12px] text-[#C1CED8]" style={{ fontWeight: 440 }}>{n.text}</p>
                              <span className="text-[11px] text-[#8898AA]">{n.time} ago</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </div>
        </header>

        {/* Content */}
        <div className="relative z-10 px-4 py-4 sm:px-6 sm:py-6 lg:px-8 lg:py-8">
          <AnimatePresence mode="wait">
            {locations.length === 1 ? (
              <motion.div key="single" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
                <SingleLocationView location={locations[0]} />
              </motion.div>
            ) : (
              <motion.div key="multi" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
                <MultiLocationView locations={locations} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
