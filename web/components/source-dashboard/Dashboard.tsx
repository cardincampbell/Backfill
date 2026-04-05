"use client";

import { useState } from 'react';
import { Link, useNavigate } from './router-shim';
import { motion, AnimatePresence } from 'motion/react';
import { useSessionUserDisplay } from '@/components/app-session-gate';
import { useSmartGreeting } from './use-smart-greeting';
import {
  Building2,
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
  LogOut,
  CheckCircle2,
  AlertCircle,
  ArrowUpRight,
  LayoutGrid,
  Zap,
} from 'lucide-react';

const mockBusinesses = [
  {
    id: 1,
    name: 'Downtown Medical Center',
    type: 'Healthcare',
    logo: '🏥',
    color: '#635BFF',
    activeShifts: 24,
    totalStaff: 48,
    fillRate: 96,
    openShifts: 3,
    revenue: '$12,400',
    trend: +8.2,
    status: 'active' as const,
    lastActivity: '2 min ago',
    upcomingShifts: 12,
  },
  {
    id: 2,
    name: 'Sunrise Senior Living',
    type: 'Senior Care',
    logo: '🌅',
    color: '#00D4AA',
    activeShifts: 18,
    totalStaff: 32,
    fillRate: 91,
    openShifts: 5,
    revenue: '$8,750',
    trend: +12.5,
    status: 'active' as const,
    lastActivity: '15 min ago',
    upcomingShifts: 8,
  },
  {
    id: 3,
    name: 'Bay Area Staffing Co.',
    type: 'Staffing Agency',
    logo: '🏢',
    color: '#FF6B35',
    activeShifts: 42,
    totalStaff: 120,
    fillRate: 88,
    openShifts: 12,
    revenue: '$34,200',
    trend: +5.1,
    status: 'active' as const,
    lastActivity: '1 hr ago',
    upcomingShifts: 28,
  },
  {
    id: 4,
    name: 'Coastal Hospitality Group',
    type: 'Hospitality',
    logo: '🏨',
    color: '#3B82F6',
    activeShifts: 8,
    totalStaff: 15,
    fillRate: 100,
    openShifts: 0,
    revenue: '$4,100',
    trend: -2.3,
    status: 'active' as const,
    lastActivity: '3 hrs ago',
    upcomingShifts: 4,
  },
];

const notifications = [
  { id: 1, text: '3 shifts need coverage at Downtown Medical', time: '2m', urgent: true },
  { id: 2, text: 'New staff member onboarded at Sunrise Senior', time: '15m', urgent: false },
  { id: 3, text: 'Weekly report ready for Bay Area Staffing', time: '1h', urgent: false },
];

function DotGrid({ className = '' }: { className?: string }) {
  return (
    <div
      className={`absolute inset-0 pointer-events-none ${className}`}
      style={{
        backgroundImage: 'radial-gradient(circle, rgba(99,91,255,0.04) 1px, transparent 1px)',
        backgroundSize: '24px 24px',
      }}
    />
  );
}

function BusinessCard({ business, index }: { business: typeof mockBusinesses[0]; index: number }) {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.08, ease: [0.25, 0.46, 0.45, 0.94] }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => navigate('/dashboard')}
      className="group relative cursor-pointer"
    >
      {/* Card */}
      <div
        className="relative rounded-2xl border border-white/[0.06] bg-white/[0.03] backdrop-blur-sm overflow-hidden transition-all duration-500"
        style={{
          boxShadow: hovered
            ? `0 20px 60px -12px ${business.color}20, 0 0 0 1px ${business.color}15`
            : '0 1px 3px rgba(0,0,0,0.1)',
        }}
      >
        {/* Top accent line */}
        <div
          className="h-[2px] w-full transition-all duration-500"
          style={{
            background: hovered
              ? `linear-gradient(90deg, transparent, ${business.color}, transparent)`
              : `linear-gradient(90deg, transparent, ${business.color}40, transparent)`,
          }}
        />

        <div className="p-6">
          {/* Header */}
          <div className="flex items-start justify-between mb-5">
            <div className="flex items-center gap-3.5">
              <div
                className="w-11 h-11 rounded-xl flex items-center justify-center text-[20px] transition-transform duration-300 group-hover:scale-110"
                style={{ background: `${business.color}15` }}
              >
                {business.logo}
              </div>
              <div>
                <h3 className="text-[15px] text-white tracking-[-0.01em]" style={{ fontWeight: 560 }}>
                  {business.name}
                </h3>
                <span className="text-[12px] text-[#8898AA] tracking-[0.02em] uppercase" style={{ fontWeight: 480 }}>
                  {business.type}
                </span>
              </div>
            </div>
            <button
              className="p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors opacity-0 group-hover:opacity-100"
              onClick={(e) => e.stopPropagation()}
            >
              <MoreHorizontal size={16} className="text-[#8898AA]" />
            </button>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-2 gap-4 mb-5">
            <div>
              <div className="text-[11px] text-[#8898AA] mb-1 uppercase tracking-[0.04em]" style={{ fontWeight: 480 }}>
                Fill Rate
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-[22px] text-white tracking-[-0.02em]" style={{ fontWeight: 620 }}>
                  {business.fillRate}%
                </span>
                <span
                  className="text-[11px] flex items-center gap-0.5"
                  style={{
                    fontWeight: 520,
                    color: business.trend >= 0 ? '#00D4AA' : '#FF6B6B',
                  }}
                >
                  <TrendingUp size={10} />
                  {business.trend > 0 ? '+' : ''}{business.trend}%
                </span>
              </div>
            </div>
            <div>
              <div className="text-[11px] text-[#8898AA] mb-1 uppercase tracking-[0.04em]" style={{ fontWeight: 480 }}>
                This Period
              </div>
              <span className="text-[22px] text-white tracking-[-0.02em]" style={{ fontWeight: 620 }}>
                {business.revenue}
              </span>
            </div>
          </div>

          {/* Micro Stats */}
          <div className="flex items-center gap-4 pt-4 border-t border-white/[0.06]">
            <div className="flex items-center gap-1.5">
              <Users size={13} className="text-[#8898AA]" />
              <span className="text-[12px] text-[#C1CED8]" style={{ fontWeight: 460 }}>
                {business.totalStaff} staff
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <CalendarDays size={13} className="text-[#8898AA]" />
              <span className="text-[12px] text-[#C1CED8]" style={{ fontWeight: 460 }}>
                {business.activeShifts} active
              </span>
            </div>
            {business.openShifts > 0 && (
              <div className="flex items-center gap-1.5 ml-auto">
                <div className="w-1.5 h-1.5 rounded-full bg-[#FF6B6B] animate-pulse" />
                <span className="text-[12px] text-[#FF6B6B]" style={{ fontWeight: 500 }}>
                  {business.openShifts} open
                </span>
              </div>
            )}
            {business.openShifts === 0 && (
              <div className="flex items-center gap-1.5 ml-auto">
                <CheckCircle2 size={12} className="text-[#00D4AA]" />
                <span className="text-[12px] text-[#00D4AA]" style={{ fontWeight: 500 }}>
                  All filled
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Hover overlay */}
        <div
          className="absolute inset-0 rounded-2xl pointer-events-none transition-opacity duration-500"
          style={{
            opacity: hovered ? 1 : 0,
            background: `radial-gradient(600px circle at 50% 0%, ${business.color}06, transparent 70%)`,
          }}
        />
      </div>
    </motion.div>
  );
}

export default function Dashboard() {
  const [showNotifications, setShowNotifications] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const navigate = useNavigate();
  const { initials } = useSessionUserDisplay();
  const { greeting } = useSmartGreeting();

  const totalStaff = mockBusinesses.reduce((a, b) => a + b.totalStaff, 0);
  const totalActive = mockBusinesses.reduce((a, b) => a + b.activeShifts, 0);
  const avgFillRate = Math.round(mockBusinesses.reduce((a, b) => a + b.fillRate, 0) / mockBusinesses.length);
  const totalOpen = mockBusinesses.reduce((a, b) => a + b.openShifts, 0);

  return (
    <div className="min-h-screen bg-[#0A2540] relative" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
      <DotGrid />

      {/* Gradient mesh background */}
      <div className="fixed inset-0 pointer-events-none">
        <div
          className="absolute top-0 right-0 w-[800px] h-[600px]"
          style={{
            background: 'radial-gradient(ellipse at top right, rgba(99,91,255,0.08), transparent 70%)',
          }}
        />
        <div
          className="absolute bottom-0 left-0 w-[600px] h-[500px]"
          style={{
            background: 'radial-gradient(ellipse at bottom left, rgba(0,212,170,0.05), transparent 70%)',
          }}
        />
      </div>

      {/* Navigation */}
      <nav className="relative z-20 border-b border-white/[0.06]">
        <div className="max-w-[1440px] mx-auto px-6 lg:px-10">
          <div className="flex items-center justify-between h-16">
            {/* Left */}
            <div className="flex items-center gap-8">
              <Link to="/">
                <span className="text-[22px] tracking-[-0.02em] text-white" style={{ fontWeight: 620 }}>
                  Backfill
                </span>
              </Link>
              <div className="hidden md:flex items-center gap-1">
                <button className="px-3.5 py-1.5 rounded-lg text-[13px] text-white bg-white/[0.06]" style={{ fontWeight: 520 }}>
                  <LayoutGrid size={14} className="inline mr-1.5 -mt-0.5" />
                  Businesses
                </button>
                <button className="px-3.5 py-1.5 rounded-lg text-[13px] text-[#8898AA] hover:text-white hover:bg-white/[0.04] transition-colors" style={{ fontWeight: 460 }}>
                  Analytics
                </button>
                <button className="px-3.5 py-1.5 rounded-lg text-[13px] text-[#8898AA] hover:text-white hover:bg-white/[0.04] transition-colors" style={{ fontWeight: 460 }}>
                  Team
                </button>
              </div>
            </div>

            {/* Right */}
            <div className="flex items-center gap-3">
              {/* Search */}
              <div className={`relative hidden sm:block transition-all duration-300 ${searchFocused ? 'w-64' : 'w-48'}`}>
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8898AA]" />
                <input
                  type="text"
                  placeholder="Search..."
                  onFocus={() => setSearchFocused(true)}
                  onBlur={() => setSearchFocused(false)}
                  className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg pl-9 pr-3 py-1.5 text-[13px] text-white placeholder-[#8898AA]/60 focus:outline-none focus:border-[#635BFF]/40 focus:bg-white/[0.06] transition-all"
                  style={{ fontWeight: 420 }}
                />
              </div>

              {/* Notifications */}
              <div className="relative">
                <button
                  onClick={() => setShowNotifications(!showNotifications)}
                  className="relative p-2 rounded-lg hover:bg-white/[0.06] transition-colors"
                >
                  <Bell size={18} className="text-[#8898AA]" />
                  <div className="absolute top-1.5 right-1.5 w-2 h-2 bg-[#FF6B6B] rounded-full" />
                </button>

                <AnimatePresence>
                  {showNotifications && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.96 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 8, scale: 0.96 }}
                      transition={{ duration: 0.2 }}
                      className="absolute right-0 top-full mt-2 w-80 bg-[#0F2E4C] border border-white/[0.08] rounded-xl shadow-2xl overflow-hidden z-50"
                    >
                      <div className="px-4 py-3 border-b border-white/[0.06]">
                        <span className="text-[13px] text-white" style={{ fontWeight: 560 }}>Notifications</span>
                      </div>
                      {notifications.map((n) => (
                        <div key={n.id} className="px-4 py-3 hover:bg-white/[0.03] transition-colors border-b border-white/[0.04] last:border-0">
                          <div className="flex items-start gap-2.5">
                            {n.urgent ? (
                              <AlertCircle size={14} className="text-[#FF6B6B] mt-0.5 shrink-0" />
                            ) : (
                              <CheckCircle2 size={14} className="text-[#00D4AA] mt-0.5 shrink-0" />
                            )}
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

              <button className="p-2 rounded-lg hover:bg-white/[0.06] transition-colors">
                <Settings size={18} className="text-[#8898AA]" />
              </button>

              {/* Avatar */}
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center ml-1">
                <span className="text-[12px] text-white" style={{ fontWeight: 600 }}>{initials}</span>
              </div>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="relative z-10 max-w-[1440px] mx-auto px-6 lg:px-10 py-8">
        {/* Welcome Header */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-8"
        >
          <div className="flex items-end justify-between mb-6">
            <div>
              <h1 className="text-[28px] sm:text-[32px] text-white tracking-[-0.025em] mb-1" style={{ fontWeight: 620 }}>
                {greeting}
              </h1>
              <p className="text-[15px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                Here's what's happening across your businesses today.
              </p>
            </div>
            <button
              onClick={() => navigate('/onboarding')}
              className="hidden sm:flex items-center gap-2 px-5 py-2.5 backfill-ui-radius text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.3)]"
              style={{
                fontWeight: 540,
                background: 'linear-gradient(135deg, #635BFF, #8B5CF6)',
              }}
            >
              <Plus size={15} />
              Add Business
            </button>
          </div>

          {/* Summary Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { label: 'Total Staff', value: totalStaff, icon: Users, color: '#635BFF' },
              { label: 'Active Shifts', value: totalActive, icon: CalendarDays, color: '#00D4AA' },
              { label: 'Avg Fill Rate', value: `${avgFillRate}%`, icon: TrendingUp, color: '#3B82F6' },
              { label: 'Open Shifts', value: totalOpen, icon: Clock, color: totalOpen > 0 ? '#FF6B6B' : '#00D4AA' },
            ].map((stat, i) => (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.1 + i * 0.06 }}
                className="bg-white/[0.03] border border-white/[0.06] rounded-xl px-5 py-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 480 }}>
                    {stat.label}
                  </span>
                  <stat.icon size={14} style={{ color: stat.color }} />
                </div>
                <span className="text-[24px] text-white tracking-[-0.02em]" style={{ fontWeight: 640 }}>
                  {stat.value}
                </span>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Businesses Section */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-[18px] text-white tracking-[-0.01em]" style={{ fontWeight: 580 }}>
              Your Businesses
            </h2>
            <span className="text-[12px] text-[#8898AA] bg-white/[0.06] px-2.5 py-0.5 backfill-ui-radius" style={{ fontWeight: 500 }}>
              {mockBusinesses.length}
            </span>
          </div>
          <button className="flex items-center gap-1 text-[13px] text-[#635BFF] hover:text-[#8B5CF6] transition-colors" style={{ fontWeight: 500 }}>
            View all <ChevronRight size={14} />
          </button>
        </div>

        {/* Business Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-2 gap-4">
          {mockBusinesses.map((biz, i) => (
            <BusinessCard key={biz.id} business={biz} index={i} />
          ))}
        </div>

        {/* Add Business Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
          onClick={() => navigate('/onboarding')}
          className="mt-4 group cursor-pointer"
        >
          <div className="rounded-2xl border border-dashed border-white/[0.08] hover:border-[#635BFF]/30 bg-white/[0.01] hover:bg-[#635BFF]/[0.03] transition-all duration-500 p-8 flex items-center justify-center gap-3">
            <div className="w-10 h-10 rounded-xl border border-white/[0.08] group-hover:border-[#635BFF]/30 flex items-center justify-center transition-all duration-300 group-hover:bg-[#635BFF]/10">
              <Plus size={18} className="text-[#8898AA] group-hover:text-[#635BFF] transition-colors" />
            </div>
            <div>
              <span className="text-[14px] text-[#8898AA] group-hover:text-white transition-colors" style={{ fontWeight: 520 }}>
                Add another business
              </span>
              <p className="text-[12px] text-[#8898AA]/60" style={{ fontWeight: 420 }}>
                Set up a new location or organization
              </p>
            </div>
          </div>
        </motion.div>

        {/* Quick Actions */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
          className="mt-10"
        >
          <h2 className="text-[16px] text-[#8898AA] mb-4 tracking-[-0.01em]" style={{ fontWeight: 500 }}>
            Quick Actions
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { label: 'Post a Shift', desc: 'Create and broadcast an open shift', icon: Zap, color: '#635BFF' },
              { label: 'Invite Staff', desc: 'Add team members to your roster', icon: Users, color: '#00D4AA' },
              { label: 'View Reports', desc: 'Analytics across all businesses', icon: ArrowUpRight, color: '#3B82F6' },
            ].map((action) => (
              <button
                key={action.label}
                className="group flex items-center gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:bg-white/[0.04] hover:border-white/[0.1] transition-all duration-300 text-left"
              >
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110"
                  style={{ background: `${action.color}15` }}
                >
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
    </div>
  );
}
