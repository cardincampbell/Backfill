"use client";

import { useState, useRef, useEffect } from 'react';
import { Link, useNavigate } from './router-shim';
import { motion, AnimatePresence } from 'motion/react';
import { useSessionUserDisplay } from '@/components/app-session-gate';
import {
  Plus,
  Users,
  CalendarDays,
  TrendingUp,
  Clock,
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
} from 'lucide-react';

/* ─── Data ─── */
const location = {
  id: 1,
  name: 'Downtown Medical Center',
  type: 'Healthcare',
  logo: '\u{1F3E5}',
  color: '#635BFF',
  activeShifts: 24,
  totalStaff: 48,
  fillRate: 96,
  openShifts: 3,
  revenue: '$12,400',
  trend: +8.2,
  weeklyShifts: [18, 22, 20, 24, 19, 21, 24],
  recentActivity: [
    { text: 'Sarah M. accepted Night Shift — ICU', time: '2 min ago', type: 'success' as const },
    { text: '3 open shifts posted for ER coverage', time: '18 min ago', type: 'info' as const },
    { text: 'Marcus T. called out — Shift reassigned', time: '1 hr ago', type: 'warning' as const },
    { text: 'Weekly compliance report generated', time: '2 hrs ago', type: 'info' as const },
    { text: 'Payroll summary exported for review', time: '3 hrs ago', type: 'info' as const },
  ],
  topStaff: [
    { name: 'Sarah Martinez', role: 'RN', shifts: 18, rating: 4.9 },
    { name: 'James Chen', role: 'LPN', shifts: 15, rating: 4.8 },
    { name: 'Aisha Patel', role: 'CNA', shifts: 22, rating: 4.7 },
  ],
  upcomingShifts: [
    { role: 'RN', time: 'Today, 3:00 PM — 11:00 PM', unit: 'ICU', filled: true, assignee: 'Sarah M.' },
    { role: 'CNA', time: 'Today, 7:00 PM — 7:00 AM', unit: 'ER', filled: false, assignee: null },
    { role: 'LPN', time: 'Tomorrow, 7:00 AM — 3:00 PM', unit: 'Med-Surg', filled: true, assignee: 'James C.' },
    { role: 'RN', time: 'Tomorrow, 3:00 PM — 11:00 PM', unit: 'ICU', filled: false, assignee: null },
    { role: 'CNA', time: 'Tomorrow, 11:00 PM — 7:00 AM', unit: 'ER', filled: true, assignee: 'Aisha P.' },
  ],
};

const notifications = [
  { id: 1, text: '3 shifts need coverage in the ER', time: '2m', urgent: true },
  { id: 2, text: 'Sarah Martinez accepted ICU Night Shift', time: '15m', urgent: false },
  { id: 3, text: 'Weekly compliance report is ready', time: '1h', urgent: false },
];

const navItems = [
  { label: 'Overview', icon: LayoutGrid, active: true },
  { label: 'Team', icon: Users, active: false },
];

const copilotSuggestions = [
  'Show me open shifts this week',
  'Who is available for ER tonight?',
  'Draft a shift for tomorrow 7am',
  'How is our overtime looking?',
];

interface ChatMessage { id: number; role: 'user' | 'assistant'; text: string; }

function buildInitialMessages(firstName: string): ChatMessage[] {
  return [
    {
      id: 1,
      role: 'assistant',
      text: `Hi ${firstName}! I'm your Backfill Copilot. I can see Downtown Medical Center has 3 open shifts that need coverage. Want me to find available staff, or is there something else I can help with?`,
    },
  ];
}

/* ─── Shared Components ─── */

function MiniBarChart({ data, color, height = 40 }: { data: number[]; color: string; height?: number }) {
  const max = Math.max(...data);
  return (
    <div className="flex items-end gap-[3px]" style={{ height }}>
      {data.map((v, i) => (
        <div key={i} className="flex-1 rounded-sm transition-all duration-300" style={{
          height: `${(v / max) * 100}%`,
          background: i === data.length - 1 ? color : `${color}30`,
          minWidth: 4,
        }} />
      ))}
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
    setMessages((m) => [...m, { id: Date.now(), role: 'user', text: text.trim() }]);
    setInput('');
    setIsTyping(true);
    setTimeout(() => {
      const responses: Record<string, string> = {
        'Show me open shifts this week': "You have 3 open shifts this week at Downtown Medical:\n\n\u2022 CNA — Today 7PM–7AM (ER)\n\u2022 RN — Tomorrow 3PM–11PM (ICU)\n\u2022 RN — Friday 7AM–3PM (Med-Surg)\n\nWould you like me to broadcast these to qualified staff?",
        'Who is available for ER tonight?': "Checking availability for ER tonight (7PM–7AM):\n\n\u2705 Aisha Patel — CNA, 4.7\u2605, available\n\u2705 Marcus Thompson — CNA, 4.5\u2605, available\n\u26a0\ufe0f David Kim — CNA, 4.6\u2605, approaching OT\n\nShall I send Aisha a shift offer first?",
        'Draft a shift for tomorrow 7am': "Here's a draft shift:\n\n\ud83d\udccb **New Shift**\nDate: Tomorrow, 7:00 AM — 3:00 PM\nLocation: Downtown Medical Center\nUnit: Med-Surg\nRole: RN\nRate: $45/hr\n\nShall I post this and notify qualified staff?",
        'How is our overtime looking?': "Overtime report for this pay period:\n\n\u2705 44 of 48 staff under 40 hrs\n\u26a0\ufe0f 3 staff approaching overtime:\n   \u2022 Aisha Patel — 38.5 hrs\n   \u2022 Sarah Martinez — 37 hrs\n   \u2022 James Chen — 36 hrs\n\n\u274c 1 staff over limit:\n   \u2022 Marcus T. — 41.5 hrs\n\nWant me to flag these for the next schedule?",
      };
      const reply = responses[text] || "I can help with that! Let me pull up the relevant data for Downtown Medical Center. Is there anything specific you'd like me to focus on?";
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

/* ─── Main Page ─── */
export default function DashboardSingle() {
  const [showNotifications, setShowNotifications] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<'nav' | 'copilot'>('nav');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const { fullName, email, phone, initials } = useSessionUserDisplay();

  return (
    <div className="min-h-screen bg-[#F7F8FA] flex" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm lg:hidden" onClick={() => setSidebarOpen(false)} />
        )}
      </AnimatePresence>

      {/* ─── Left Sidebar ─── */}
      <aside className={`fixed top-0 left-0 h-full z-50 w-[280px] flex flex-col border-r border-[#E5E7EB] bg-white transition-transform duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        {/* Logo */}
        <div className="flex items-center justify-between h-16 px-5 border-b border-[#F0F0F5]">
          <Link to="/" className="flex items-center gap-2.5">
            <span className="text-[18px] tracking-[-0.02em] text-[#0A2540]" style={{ fontWeight: 620 }}>Backfill</span>
          </Link>
          <button onClick={() => setSidebarOpen(false)} className="p-1.5 rounded-lg hover:bg-[#F7F8FA] transition-colors lg:hidden">
            <X size={18} className="text-[#8898AA]" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="px-3 pt-3 pb-1">
          <div className="flex items-center bg-[#F0F0F5] rounded-lg p-0.5">
            <button onClick={() => setSidebarTab('nav')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-[12px] transition-all duration-200 ${
                sidebarTab === 'nav' ? 'bg-white text-[#0A2540] shadow-sm' : 'text-[#8898AA] hover:text-[#0A2540]'
              }`} style={{ fontWeight: sidebarTab === 'nav' ? 520 : 440 }}>
              <LayoutGrid size={13} />Navigate
            </button>
            <button onClick={() => setSidebarTab('copilot')}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-[12px] transition-all duration-200 ${
                sidebarTab === 'copilot' ? 'bg-[#635BFF]/10 text-[#635BFF] shadow-sm' : 'text-[#8898AA] hover:text-[#0A2540]'
              }`} style={{ fontWeight: sidebarTab === 'copilot' ? 520 : 440 }}>
              <Sparkles size={13} />Copilot
            </button>
          </div>
        </div>

        {/* Tab Content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <AnimatePresence mode="wait">
            {sidebarTab === 'nav' ? (
              <motion.div key="nav" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} transition={{ duration: 0.2 }}
                className="flex-1 flex flex-col">
                <nav className="flex-1 py-3 px-3 space-y-1">
                  {navItems.map((item) => (
                    <button key={item.label} className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                      item.active ? 'bg-[#635BFF]/[0.08] text-[#635BFF]' : 'text-[#5E6D7A] hover:text-[#0A2540] hover:bg-[#F7F8FA]'
                    }`}>
                      <item.icon size={18} className="shrink-0" />
                      <span className="text-[13px]" style={{ fontWeight: item.active ? 540 : 440 }}>{item.label}</span>
                    </button>
                  ))}

                  {/* Location shortcut */}
                  <div className="pt-4 mt-3 border-t border-[#F0F0F5]">
                    <span className="text-[10px] text-[#8898AA] uppercase tracking-[0.06em] px-3 mb-2 block" style={{ fontWeight: 500 }}>Locations</span>
                    <button className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg bg-[#635BFF]/[0.08] text-[#635BFF] transition-all duration-200">
                      <span className="text-[14px]">{location.logo}</span>
                      <span className="text-[12px] truncate" style={{ fontWeight: 480 }}>{location.name}</span>
                      {location.openShifts > 0 && (
                        <span className="ml-auto text-[10px] text-[#E5484D] bg-[#E5484D]/10 px-1.5 py-0.5 rounded-full" style={{ fontWeight: 540 }}>{location.openShifts}</span>
                      )}
                    </button>
                  </div>
                </nav>
                <div className="border-t border-[#F0F0F5] py-3 px-3 space-y-1">
                  <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#5E6D7A] hover:text-[#0A2540] hover:bg-[#F7F8FA] transition-all duration-200">
                    <Settings size={18} className="shrink-0" /><span className="text-[13px]" style={{ fontWeight: 440 }}>Settings</span>
                  </button>
                </div>
              </motion.div>
            ) : (
              <motion.div key="copilot" initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }} transition={{ duration: 0.2 }}
                className="flex-1 flex flex-col overflow-hidden">
                <CopilotPanel />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* User */}
        <div className="border-t border-[#F0F0F5] p-3">
          <div className="flex items-center gap-3 rounded-lg p-2 bg-[#F7F8FA]">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center shrink-0">
              <span className="text-[11px] text-white" style={{ fontWeight: 600 }}>{initials}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12px] text-[#0A2540] truncate" style={{ fontWeight: 520 }}>{fullName}</p>
              <p className="text-[11px] text-[#8898AA] truncate">{email ?? phone ?? 'Phone sign-in'}</p>
            </div>
          </div>
        </div>
      </aside>

      {/* ─── Main Area ─── */}
      <div className="flex-1 min-h-screen lg:ml-[280px]">
        {/* Top Bar */}
        <header className="sticky top-0 z-20 border-b border-[#E5E7EB] bg-white/80 backdrop-blur-xl">
          <div className="flex items-center justify-between h-14 sm:h-16 px-4 sm:px-8">
            <div className="flex items-center gap-3">
              <button onClick={() => setSidebarOpen(true)} className="p-2 rounded-lg hover:bg-[#F7F8FA] transition-colors lg:hidden">
                <Menu size={20} className="text-[#5E6D7A]" />
              </button>
              <div className="relative hidden sm:block">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8898AA]" />
                <input
                  type="text"
                  placeholder="Search..."
                  className="w-48 md:w-64 pl-9 pr-4 py-2 rounded-lg bg-[#F7F8FA] border border-[#E5E7EB] text-[12px] text-[#0A2540] placeholder-[#8898AA]/60 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all"
                  style={{ fontWeight: 420 }}
                />
              </div>
            </div>
            <div className="flex items-center gap-1.5 sm:gap-3">
              <button className="p-2 rounded-lg hover:bg-[#F7F8FA] transition-colors hidden sm:block">
                <HelpCircle size={18} className="text-[#5E6D7A]" />
              </button>
              <div className="relative">
                <button onClick={() => setShowNotifications(!showNotifications)} className="relative p-2 rounded-lg hover:bg-[#F7F8FA] transition-colors">
                  <Bell size={18} className="text-[#5E6D7A]" />
                  <div className="absolute top-1.5 right-1.5 w-2 h-2 bg-[#E5484D] rounded-full" />
                </button>
                <AnimatePresence>
                  {showNotifications && (
                    <motion.div initial={{ opacity: 0, y: 8, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.96 }} transition={{ duration: 0.2 }}
                      className="absolute right-0 top-full mt-2 w-[calc(100vw-2rem)] sm:w-80 max-w-80 bg-white border border-[#E5E7EB] rounded-xl shadow-xl overflow-hidden z-50">
                      <div className="px-4 py-3 border-b border-[#F0F0F5]">
                        <span className="text-[13px] text-[#0A2540]" style={{ fontWeight: 560 }}>Notifications</span>
                      </div>
                      {notifications.map((n) => (
                        <div key={n.id} className="px-4 py-3 hover:bg-[#F7F8FA] transition-colors border-b border-[#F0F0F5] last:border-0">
                          <div className="flex items-start gap-2.5">
                            {n.urgent ? <AlertCircle size={14} className="text-[#E5484D] mt-0.5 shrink-0" /> : <CheckCircle2 size={14} className="text-[#00B893] mt-0.5 shrink-0" />}
                            <div>
                              <p className="text-[12px] text-[#3E4C59]" style={{ fontWeight: 440 }}>{n.text}</p>
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

        {/* ─── Content ─── */}
        <div className="px-4 py-4 sm:px-6 sm:py-6 lg:px-8 lg:py-8">
          {/* Location Header */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-[28px]" style={{ background: `${location.color}10` }}>
                  {location.logo}
                </div>
                <div>
                  <h1 className="text-[28px] sm:text-[32px] text-[#0A2540] tracking-[-0.025em] mb-0.5" style={{ fontWeight: 620 }}>
                    {location.name}
                  </h1>
                  <p className="text-[14px] text-[#8898AA]" style={{ fontWeight: 420 }}>
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

            {/* Stats Cluster + Top Performers */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Today's Coverage */}
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.05 }}
                className="bg-white border border-[#E5E7EB] rounded-xl p-5 shadow-[0_1px_2px_rgba(0,0,0,0.03)] flex flex-col overflow-hidden">
                <div className="flex items-center gap-4 mb-4">
                  <div className="flex items-center gap-3">
                    <span className="text-[42px] text-[#0A2540] tracking-[-0.04em] leading-none" style={{ fontWeight: 720 }}>3</span>
                    <div className="flex flex-col">
                      <span className="text-[13px] text-[#0A2540] leading-tight" style={{ fontWeight: 580 }}>April</span>
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
                      <span className="text-[11px] text-[#C1CED8]" style={{ fontWeight: 420 }}>↳</span>
                      <span className="text-[13px] text-[#3E4C59] flex-1" style={{ fontWeight: 480 }}>{unit.name}</span>
                      <span className="text-[13px] text-[#5E6D7A] tabular-nums" style={{ fontWeight: 520 }}>{unit.covered}/{unit.total}</span>
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
                <div className="pt-3 border-t border-[#F0F0F5] shrink-0">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[22px] text-[#0A2540] tracking-[-0.03em]" style={{ fontWeight: 660 }}>88%</span>
                      <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>covered</span>
                    </div>
                    <span className="text-[11px] text-[#8898AA] tabular-nums" style={{ fontWeight: 460 }}>21 of 24</span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-[#F0F0F5] mb-2 overflow-hidden">
                    <div className="h-full rounded-full bg-gradient-to-r from-[#00B893] to-[#00D4AA]" style={{ width: '88%' }} />
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-[#F59E0B] animate-pulse" />
                    <span className="text-[10px] text-[#5E6D7A]" style={{ fontWeight: 460 }}>1 filling now · ~4 min</span>
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
                    className="bg-white border border-[#E5E7EB] rounded-xl px-4 py-4 shadow-[0_1px_2px_rgba(0,0,0,0.03)] flex flex-col">
                    <div className="flex items-center justify-between mb-auto">
                      <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 480 }}>{stat.label}</span>
                      <stat.icon size={14} style={{ color: stat.color }} />
                    </div>
                    <span className="text-[26px] text-[#0A2540] tracking-[-0.02em] mt-1 whitespace-nowrap" style={{ fontWeight: 660 }}>{stat.value}</span>
                  </motion.div>
                ))}
              </div>

              {/* Top Performers — vertical */}
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
                className="bg-white border border-[#E5E7EB] rounded-xl p-5 shadow-[0_1px_2px_rgba(0,0,0,0.03)] flex flex-col overflow-hidden">
                <h3 className="text-[13px] text-[#8898AA] uppercase tracking-[0.04em] mb-3 shrink-0" style={{ fontWeight: 480 }}>Top Performers</h3>
                <div className="space-y-1 flex-1 min-h-0">
                  {location.topStaff.slice(0, 4).map((s, i) => (
                    <div key={i} className="flex items-center gap-2.5 p-2 rounded-lg hover:bg-[#F7F8FA] transition-colors">
                      <div className="w-8 h-8 rounded-full flex items-center justify-center text-[11px] text-white shrink-0" style={{ fontWeight: 600, background: location.color }}>
                        {s.name.split(' ').map(n => n[0]).join('')}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[12px] text-[#0A2540] truncate" style={{ fontWeight: 500 }}>{s.name}</p>
                        <span className="text-[10px] text-[#8898AA]">{s.role} · {s.shifts} shifts</span>
                      </div>
                      <div className="text-[11px] text-[#D4A017]" style={{ fontWeight: 540 }}>★ {s.rating}</div>
                    </div>
                  ))}
                </div>
              </motion.div>
            </div>
          </motion.div>

          {/* Two Column Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Left Column */}
            <div className="lg:col-span-2 space-y-4">
              {/* Shift Volume */}
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}
                className="bg-white border border-[#E5E7EB] rounded-2xl p-6 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                <div className="flex items-center justify-between mb-5">
                  <div>
                    <h3 className="text-[15px] text-[#0A2540]" style={{ fontWeight: 560 }}>Shift Volume</h3>
                    <span className="text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>Last 7 days</span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-[20px] text-[#0A2540] tracking-[-0.02em]" style={{ fontWeight: 620 }}>{location.revenue}</span>
                    <span className="text-[11px] flex items-center gap-0.5" style={{ fontWeight: 520, color: '#00B893' }}>
                      <TrendingUp size={10} />+{location.trend}%
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

              {/* Upcoming Shifts */}
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.25 }}
                className="bg-white border border-[#E5E7EB] rounded-2xl p-6 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-[15px] text-[#0A2540]" style={{ fontWeight: 560 }}>Upcoming Shifts</h3>
                  <button className="text-[12px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors" style={{ fontWeight: 500 }}>View all</button>
                </div>
                <div className="space-y-2">
                  {location.upcomingShifts.map((shift, i) => (
                    <div key={i} className="flex items-center gap-4 p-3 rounded-xl hover:bg-[#F7F8FA] transition-colors">
                      <div className={`w-2 h-2 rounded-full shrink-0 ${shift.filled ? 'bg-[#00B893]' : 'bg-[#E5484D] animate-pulse'}`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] text-[#0A2540]" style={{ fontWeight: 520 }}>{shift.role}</span>
                          <span className="text-[11px] text-[#8898AA] bg-[#F0F0F5] px-1.5 py-0.5 rounded" style={{ fontWeight: 440 }}>{shift.unit}</span>
                        </div>
                        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>{shift.time}</span>
                      </div>
                      {shift.filled ? (
                        <span className="text-[12px] text-[#5E6D7A]" style={{ fontWeight: 460 }}>{shift.assignee}</span>
                      ) : (
                        <button className="text-[11px] text-[#635BFF] border border-[#635BFF]/20 rounded-full px-3 py-1 hover:bg-[#635BFF]/5 transition-colors" style={{ fontWeight: 500 }}>
                          Fill shift
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </motion.div>

              {/* Recent Activity */}
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.3 }}
                className="bg-white border border-[#E5E7EB] rounded-2xl p-6 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                <h3 className="text-[15px] text-[#0A2540] mb-4" style={{ fontWeight: 560 }}>Recent Activity</h3>
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
                        <p className="text-[13px] text-[#3E4C59]" style={{ fontWeight: 440 }}>{a.text}</p>
                        <span className="text-[11px] text-[#8898AA]/70">{a.time}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>

              {/* Quick Actions */}
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.35 }}>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {[
                    { label: 'Post a Shift', desc: 'Broadcast an open shift', icon: Zap, color: '#635BFF' },
                    { label: 'Invite Staff', desc: 'Add to your roster', icon: Users, color: '#00B893' },
                    { label: 'View Reports', desc: 'Location analytics', icon: ArrowUpRight, color: '#3B82F6' },
                  ].map((action) => (
                    <button key={action.label} className="group flex items-center gap-4 p-4 rounded-xl bg-white border border-[#E5E7EB] hover:border-[#D1D5DB] hover:shadow-[0_4px_12px_rgba(0,0,0,0.04)] transition-all duration-300 text-left">
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-transform duration-300 group-hover:scale-110" style={{ background: `${action.color}10` }}>
                        <action.icon size={16} style={{ color: action.color }} />
                      </div>
                      <div>
                        <span className="text-[13px] text-[#0A2540] block" style={{ fontWeight: 540 }}>{action.label}</span>
                        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>{action.desc}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </motion.div>
            </div>

            {/* Right Column */}
            <div className="space-y-4">
              {/* Coverage */}
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.3 }}
                className="bg-white border border-[#E5E7EB] rounded-2xl p-6 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                <h3 className="text-[15px] text-[#0A2540] mb-4" style={{ fontWeight: 560 }}>Coverage</h3>
                <div className="mb-4">
                  <div className="flex justify-between mb-2">
                    <span className="text-[12px] text-[#8898AA]" style={{ fontWeight: 440 }}>Fill rate</span>
                    <span className="text-[12px] text-[#0A2540]" style={{ fontWeight: 560 }}>{location.fillRate}%</span>
                  </div>
                  <div className="h-2 bg-[#F0F0F5] rounded-full overflow-hidden">
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
                        <span className="text-[12px] text-[#5E6D7A]" style={{ fontWeight: 440 }}>{r.label}</span>
                      </div>
                      <span className="text-[13px] text-[#0A2540]" style={{ fontWeight: 540 }}>{r.value}</span>
                    </div>
                  ))}
                </div>
              </motion.div>

              {/* Compliance */}
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.35 }}
                className="bg-white border border-[#E5E7EB] rounded-2xl p-6 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                <h3 className="text-[15px] text-[#0A2540] mb-3" style={{ fontWeight: 560 }}>Compliance</h3>
                <div className="space-y-2.5">
                  {['Credentials current', 'Overtime limits met', 'Break compliance'].map((c) => (
                    <div key={c} className="flex items-center gap-2.5">
                      <Shield size={13} className="text-[#00B893]" />
                      <span className="text-[12px] text-[#5E6D7A]" style={{ fontWeight: 440 }}>{c}</span>
                      <CheckCircle2 size={12} className="text-[#00B893] ml-auto" />
                    </div>
                  ))}
                </div>
              </motion.div>

              {/* Add Location CTA */}
              <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.4 }}
                onClick={() => navigate('/onboarding')} className="group cursor-pointer">
                <div className="rounded-2xl border border-dashed border-[#D1D5DB] hover:border-[#635BFF]/40 bg-white hover:bg-[#635BFF]/[0.02] transition-all duration-500 p-5 flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl border border-[#E5E7EB] group-hover:border-[#635BFF]/30 flex items-center justify-center transition-all duration-300 group-hover:bg-[#635BFF]/[0.06] shrink-0">
                    <Plus size={16} className="text-[#8898AA] group-hover:text-[#635BFF] transition-colors" />
                  </div>
                  <div>
                    <span className="text-[13px] text-[#5E6D7A] group-hover:text-[#0A2540] transition-colors" style={{ fontWeight: 520 }}>Add another location</span>
                    <p className="text-[11px] text-[#8898AA]/70" style={{ fontWeight: 420 }}>Expand your business on Backfill</p>
                  </div>
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
