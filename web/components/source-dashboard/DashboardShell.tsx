"use client";

import { useState, useRef, useEffect, type ReactNode } from 'react';
import { Link, useNavigate } from './router-shim';
import { motion, AnimatePresence } from 'motion/react';
import { usePathname } from 'next/navigation';
import {
  Users,
  Bell,
  Search,
  Settings,
  CheckCircle2,
  AlertCircle,
  LayoutGrid,
  HelpCircle,
  Send,
  Sparkles,
  Menu,
  X,
  Sun,
  Moon,
} from 'lucide-react';

/* ─── Shared Data ─── */
const allLocations = [
  { id: 1, name: 'Downtown Medical Center', logo: '\u{1F3E5}', openShifts: 3 },
  { id: 2, name: 'Sunrise Senior Living', logo: '\u{1F305}', openShifts: 5 },
  { id: 3, name: 'Bay Area Staffing Co.', logo: '\u{1F3E2}', openShifts: 12 },
  { id: 4, name: 'Coastal Hospitality Group', logo: '\u{1F3E8}', openShifts: 0 },
];

const notifications = [
  { id: 1, text: '3 shifts need coverage at Downtown Medical', time: '2m', urgent: true },
  { id: 2, text: 'New staff member onboarded at Sunrise Senior', time: '15m', urgent: false },
  { id: 3, text: 'Weekly report ready for Bay Area Staffing', time: '1h', urgent: false },
];

const navItems = [
  { label: 'Overview', icon: LayoutGrid, path: '/dashboard-light' },
  { label: 'Team', icon: Users, path: '/team' },
];

const copilotSuggestions = [
  'Show me open shifts this week',
  'Who has the most hours?',
  'Draft a shift for tomorrow 7am',
];

interface ChatMessage { id: number; role: 'user' | 'assistant'; text: string; }
const initialMessages: ChatMessage[] = [
  { id: 1, role: 'assistant', text: "Hi Jordan! I'm your Backfill Copilot. I can help you manage shifts, find available staff, generate reports, and more. What can I help with?" },
];

/* ─── Copilot Panel ─── */
function CopilotPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
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

/* ─── Dashboard Shell ─── */
interface DashboardShellProps {
  activeNav: string;
  children: ReactNode;
}

export default function DashboardShell({ activeNav, children }: DashboardShellProps) {
  const [showNotifications, setShowNotifications] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<'nav' | 'copilot'>('nav');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const pathname = usePathname();
  const darkMode = pathname === '/dashboard-dark';

  // Close sidebar on navigation
  const handleNav = (path: string) => {
    navigate(path);
    setSidebarOpen(false);
  };

  return (
    <div className="min-h-screen bg-[#F7F8FA] flex" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Mobile Sidebar Overlay */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Left Sidebar */}
      <aside className={`fixed top-0 left-0 h-full z-50 w-[280px] flex flex-col border-r border-[#E5E7EB] bg-white transition-transform duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] lg:translate-x-0 ${
        sidebarOpen ? 'translate-x-0' : '-translate-x-full'
      }`}>
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
                <nav className="flex-1 py-3 px-3 space-y-1 overflow-y-auto">
                  {navItems.map((item) => (
                    <button key={item.label} onClick={() => handleNav(item.path)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                        activeNav === item.label ? 'bg-[#635BFF]/[0.08] text-[#635BFF]' : 'text-[#5E6D7A] hover:text-[#0A2540] hover:bg-[#F7F8FA]'
                      }`}>
                      <item.icon size={18} className="shrink-0" />
                      <span className="text-[13px]" style={{ fontWeight: activeNav === item.label ? 540 : 440 }}>{item.label}</span>
                    </button>
                  ))}

                  {/* Location shortcuts */}
                  <div className="pt-4 mt-3 border-t border-[#F0F0F5]">
                    <span className="text-[10px] text-[#8898AA] uppercase tracking-[0.06em] px-3 mb-2 block" style={{ fontWeight: 500 }}>Locations</span>
                    {allLocations.map((loc) => (
                      <button key={loc.id} className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[#5E6D7A] hover:text-[#0A2540] hover:bg-[#F7F8FA] transition-all duration-200">
                        <span className="text-[14px]">{loc.logo}</span>
                        <span className="text-[12px] truncate" style={{ fontWeight: 440 }}>{loc.name}</span>
                        {loc.openShifts > 0 && (
                          <span className="ml-auto text-[10px] text-[#E5484D] bg-[#E5484D]/10 px-1.5 py-0.5 rounded-full" style={{ fontWeight: 540 }}>{loc.openShifts}</span>
                        )}
                      </button>
                    ))}
                  </div>
                </nav>
                <div className="border-t border-[#F0F0F5] py-3 px-3 space-y-1">
                  <button onClick={() => handleNav('/settings')}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                      activeNav === 'Settings' ? 'bg-[#635BFF]/[0.08] text-[#635BFF]' : 'text-[#5E6D7A] hover:text-[#0A2540] hover:bg-[#F7F8FA]'
                    }`}>
                    <Settings size={18} className="shrink-0" />
                    <span className="text-[13px]" style={{ fontWeight: activeNav === 'Settings' ? 540 : 440 }}>Settings</span>
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
              <span className="text-[11px] text-white" style={{ fontWeight: 600 }}>JD</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[12px] text-[#0A2540] truncate" style={{ fontWeight: 520 }}>Jordan Davis</p>
              <p className="text-[11px] text-[#8898AA] truncate">jordan@backfill.io</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Area */}
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
              {/* Mobile logo when sidebar is hidden */}
              <span className="text-[16px] tracking-[-0.02em] text-[#0A2540] lg:hidden sm:hidden" style={{ fontWeight: 620 }}>Backfill</span>
            </div>
            <div className="flex items-center gap-1.5 sm:gap-3">
              <button className="p-2 rounded-lg hover:bg-[#F7F8FA] transition-colors hidden sm:block">
                <HelpCircle size={18} className="text-[#5E6D7A]" />
              </button>
              <button
                onClick={() => navigate(darkMode ? '/dashboard-light' : '/dashboard-dark')}
                className="relative p-2 rounded-lg hover:bg-[#F7F8FA] transition-all duration-300 group"
                title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
              >
                <AnimatePresence mode="wait">
                  {darkMode ? (
                    <motion.div key="moon" initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.2 }}>
                      <Moon size={18} className="text-[#635BFF]" />
                    </motion.div>
                  ) : (
                    <motion.div key="sun" initial={{ rotate: 90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: -90, opacity: 0 }} transition={{ duration: 0.2 }}>
                      <Sun size={18} className="text-[#5E6D7A] group-hover:text-[#F59E0B]" />
                    </motion.div>
                  )}
                </AnimatePresence>
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

        {/* Content */}
        <div className="px-4 py-4 sm:px-6 sm:py-6 lg:px-8 lg:py-8">
          {children}
        </div>
      </div>
    </div>
  );
}
