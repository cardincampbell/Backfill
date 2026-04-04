"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Calendar, CheckCircle2, ChevronLeft, ChevronRight, Clock, Filter, MoreHorizontal, Plus, Send, Sparkles } from "lucide-react";

export function LandingBackfillShiftsInterface() {
  const [animPhase, setAnimPhase] = useState(0);
  // 0: idle, 1: typing chat, 2: message sent, 3: AI thinking, 4: AI responds, 5: shifts flash/swap, 6: done
  const [hasTriggered, setHasTriggered] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [typedText, setTypedText] = useState('');
  const fullMessage = "Swap Maya & James' shifts on Saturday.";

  // IntersectionObserver trigger
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasTriggered) {
          setHasTriggered(true);
        }
      },
      { threshold: 0.4 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [hasTriggered]);

  // Animation sequence
  useEffect(() => {
    if (!hasTriggered) return;
    const t1 = setTimeout(() => setAnimPhase(1), 800); // start typing
    return () => clearTimeout(t1);
  }, [hasTriggered]);

  // Typing effect
  useEffect(() => {
    if (animPhase !== 1) return;
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setTypedText(fullMessage.slice(0, i));
      if (i >= fullMessage.length) {
        clearInterval(interval);
        setTimeout(() => setAnimPhase(2), 400); // message sent
      }
    }, 35);
    return () => clearInterval(interval);
  }, [animPhase]);

  // After message sent -> AI thinking -> AI responds -> swap
  useEffect(() => {
    if (animPhase === 2) {
      const t = setTimeout(() => setAnimPhase(3), 600);
      return () => clearTimeout(t);
    }
    if (animPhase === 3) {
      const t = setTimeout(() => setAnimPhase(4), 1200);
      return () => clearTimeout(t);
    }
    if (animPhase === 4) {
      const t = setTimeout(() => setAnimPhase(5), 800);
      return () => clearTimeout(t);
    }
    if (animPhase === 5) {
      const t = setTimeout(() => setAnimPhase(6), 600);
      return () => clearTimeout(t);
    }
  }, [animPhase]);

  const swapped = animPhase >= 5;

  const days = [
    { date: '12', day: 'Mon', isToday: false },
    { date: '13', day: 'Tue', isToday: true },
    { date: '14', day: 'Wed', isToday: false },
    { date: '15', day: 'Thu', isToday: false },
    { date: '16', day: 'Fri', isToday: false },
    { date: '17', day: 'Sat', isToday: false },
    { date: '18', day: 'Sun', isToday: false },
  ];

  type Shift = {
    day: number;
    start: string;
    end: string;
    label: string;
    color: string;
    status?: 'callout' | 'covered';
  };

  type Employee = {
    name: string;
    role: string;
    initials: string;
    avatarColor: string;
    hours: number;
    shifts: Shift[];
  };

  // Before swap: Maya has Brunch Sat (day 5), James has Closing Sat (day 5)
  // After swap: Maya gets Closing Sat, James gets Brunch Sat
  const getEmployees = (): Employee[] => [
    {
      name: 'Sarah Martinez', role: 'Server', initials: 'SM',
      avatarColor: 'from-[#3A3A3A] to-[#2A2A2A]', hours: 32,
      shifts: [
        { day: 0, start: '11:00a', end: '7:00p', label: 'Dinner', color: 'blue' },
        { day: 1, start: '11:00a', end: '7:00p', label: 'Dinner', color: 'blue', status: 'callout' },
        { day: 2, start: '11:00a', end: '7:00p', label: 'Dinner', color: 'blue' },
        { day: 4, start: '11:00a', end: '7:00p', label: 'Dinner', color: 'blue' },
        { day: 6, start: '10:00a', end: '6:00p', label: 'Brunch', color: 'slate' },
      ],
    },
    {
      name: 'James Chen', role: 'Server', initials: 'JC',
      avatarColor: 'from-[#3A3A3A] to-[#2A2A2A]', hours: swapped ? 26 : 24,
      shifts: [
        { day: 1, start: '5:00p', end: '12:00a', label: 'Closing', color: 'amber' },
        { day: 3, start: '5:00p', end: '12:00a', label: 'Closing', color: 'amber' },
        ...(swapped
          ? [{ day: 5, start: '10:00a', end: '6:00p', label: 'Brunch', color: 'slate' as string }]
          : [{ day: 5, start: '5:00p', end: '12:00a', label: 'Closing', color: 'amber' as string }]
        ),
      ],
    },
    {
      name: 'Maya Thompson', role: 'Server', initials: 'MT',
      avatarColor: 'from-[#3A3A3A] to-[#2A2A2A]', hours: swapped ? 34 : 36,
      shifts: [
        { day: 0, start: '5:00p', end: '12:00a', label: 'Closing', color: 'amber' },
        { day: 1, start: '11:00a', end: '7:00p', label: 'Dinner', color: 'blue', status: 'covered' },
        { day: 2, start: '5:00p', end: '12:00a', label: 'Closing', color: 'amber' },
        { day: 4, start: '5:00p', end: '12:00a', label: 'Closing', color: 'amber' },
        ...(swapped
          ? [{ day: 5, start: '5:00p', end: '12:00a', label: 'Closing', color: 'amber' as string }]
          : [{ day: 5, start: '10:00a', end: '6:00p', label: 'Brunch', color: 'slate' as string }]
        ),
      ],
    },
    {
      name: 'Alex Rivera', role: 'Host', initials: 'AR',
      avatarColor: 'from-[#3A3A3A] to-[#2A2A2A]', hours: 28,
      shifts: [
        { day: 1, start: '11:00a', end: '7:00p', label: 'Lunch', color: 'cool' },
        { day: 3, start: '11:00a', end: '7:00p', label: 'Lunch', color: 'cool' },
        { day: 5, start: '11:00a', end: '7:00p', label: 'Lunch', color: 'cool' },
        { day: 6, start: '10:00a', end: '6:00p', label: 'Brunch', color: 'slate' },
      ],
    },
    {
      name: 'Priya Patel', role: 'Server', initials: 'PP',
      avatarColor: 'from-[#3A3A3A] to-[#2A2A2A]', hours: 20,
      shifts: [
        { day: 0, start: '11:00a', end: '7:00p', label: 'Lunch', color: 'cool' },
        { day: 3, start: '11:00a', end: '7:00p', label: 'Dinner', color: 'blue' },
        { day: 6, start: '5:00p', end: '12:00a', label: 'Closing', color: 'amber' },
      ],
    },
    {
      name: 'David Kim', role: 'Bartender', initials: 'DK',
      avatarColor: 'from-[#3A3A3A] to-[#2A2A2A]', hours: 30,
      shifts: [
        { day: 0, start: '4:00p', end: '12:00a', label: 'Bar', color: 'sage' },
        { day: 2, start: '4:00p', end: '12:00a', label: 'Bar', color: 'sage' },
        { day: 4, start: '4:00p', end: '12:00a', label: 'Bar', color: 'sage' },
        { day: 5, start: '4:00p', end: '12:00a', label: 'Bar', color: 'sage' },
      ],
    },
    {
      name: 'Lena Nguyen', role: 'Host', initials: 'LN',
      avatarColor: 'from-[#3A3A3A] to-[#2A2A2A]', hours: 16,
      shifts: [
        { day: 0, start: '11:00a', end: '5:00p', label: 'Lunch', color: 'cool' },
        { day: 2, start: '11:00a', end: '5:00p', label: 'Lunch', color: 'cool' },
      ],
    },
  ];

  const employees = getEmployees();

  // Monochromatic blues palette
  const getShiftStyles = (color: string, status?: string) => {
    const base: Record<string, { bg: string; border: string; text: string }> = {
      blue:  { bg: '#E8EEF6', border: '#5B82B5', text: '#3A5E8C' },
      amber: { bg: '#E4EAF3', border: '#7090B8', text: '#4A6A90' },
      slate: { bg: '#DFE6F0', border: '#8AA0C0', text: '#5A7498' },
      cool:  { bg: '#EAF0F8', border: '#6888B0', text: '#3F5F88' },
      sage:  { bg: '#E1E9F4', border: '#7C98BE', text: '#4E6E96' },
    };
    const s = base[color] || base.blue;
    if (status === 'callout') {
      return { backgroundColor: '#F0E8EC', borderColor: '#A07080', color: '#7A4A5A' };
    }
    return { backgroundColor: s.bg, borderColor: s.border, color: s.text };
  };

  const roleGroups: Record<string, Employee[]> = {};
  employees.forEach(emp => {
    const r = emp.role;
    if (!roleGroups[r]) roleGroups[r] = [];
    roleGroups[r].push(emp);
  });

  // Determine if a cell is one of the swapped cells (for highlight)
  const isSwapCell = (empName: string, dayIndex: number) => {
    return dayIndex === 5 && (empName === 'James Chen' || empName === 'Maya Thompson');
  };

  return (
    <div ref={containerRef} className="w-full flex rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.12)] overflow-hidden border border-[#d8dee6]">
      {/* AI Chat Panel */}
      <div className="hidden md:flex flex-col w-[260px] bg-[#0D1B2A] border-r border-white/[0.06] shrink-0">
        {/* Chat Header */}
        <div className="px-4 py-3 border-b border-white/[0.06] flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-lg bg-[#635BFF]/20 flex items-center justify-center">
            <Sparkles className="h-3 w-3 text-[#635BFF]" />
          </div>
          <span className="text-[13px] text-white/80" style={{ fontWeight: 600 }}>Backfill Copilot</span>
          <div className="ml-auto w-1.5 h-1.5 rounded-full bg-[#4ADE80] animate-pulse" />
        </div>

        {/* Chat Messages */}
        <div className="flex-1 px-3 py-4 flex flex-col justify-end gap-3 overflow-hidden">
          {/* Previous context messages */}
          <div className="flex flex-col gap-1">
            <div className="self-end bg-white/[0.08] rounded-xl rounded-br-sm px-3 py-2 max-w-[200px]">
              <p className="text-[11px] text-white/50 leading-[1.5]">Add Sarah to dinner on Monday.</p>
            </div>
            <div className="self-start bg-[#635BFF]/15 rounded-xl rounded-bl-sm px-3 py-2 max-w-[200px]">
              <p className="text-[11px] text-[#a5a0ff]/70 leading-[1.5]">Done. Sarah is on Dinner Mon 11a–7p.</p>
            </div>
          </div>

          {/* User's animated message */}
          {animPhase >= 1 && (
            <div className="flex flex-col gap-1">
              <div className="self-end bg-white/[0.08] rounded-xl rounded-br-sm px-3 py-2 max-w-[210px]" style={{ animation: animPhase === 2 ? 'none' : undefined }}>
                <p className="text-[11px] text-white/70 leading-[1.5]">
                  {animPhase >= 2 ? fullMessage : typedText}
                  {animPhase === 1 && <span className="inline-block w-[1px] h-[12px] bg-white/50 ml-[1px] align-middle animate-pulse" />}
                </p>
              </div>
            </div>
          )}

          {/* AI thinking indicator */}
          {animPhase === 3 && (
            <div className="self-start bg-[#635BFF]/15 rounded-xl rounded-bl-sm px-3 py-2.5">
              <div className="flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-[#635BFF]/60 animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-1.5 h-1.5 rounded-full bg-[#635BFF]/60 animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-1.5 h-1.5 rounded-full bg-[#635BFF]/60 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          )}

          {/* AI response */}
          {animPhase >= 4 && (
            <div className="self-start bg-[#635BFF]/15 rounded-xl rounded-bl-sm px-3 py-2 max-w-[220px]" style={{ animation: 'fadeSlideUp 0.3s ease-out' }}>
              <p className="text-[11px] text-[#a5a0ff]/80 leading-[1.5]">
                Done. Swapped Maya & James on Sat.
              </p>
              {animPhase >= 5 && (
                <div className="flex items-center gap-1 mt-1.5">
                  <CheckCircle2 className="h-2.5 w-2.5 text-[#4ADE80]/70" />
                  <span className="text-[9px] text-[#4ADE80]/60" style={{ fontWeight: 600 }}>Schedule updated</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Chat Input */}
        <div className="px-3 pb-3">
          <div className="flex items-center gap-2 bg-white/[0.06] rounded-xl px-3 py-2.5 border border-white/[0.06]">
            <input
              type="text"
              placeholder="Ask Backfill AI..."
              className="flex-1 bg-transparent text-[11px] text-white/40 placeholder:text-white/20 outline-none"
              readOnly
            />
            <Send className="h-3 w-3 text-white/20" />
          </div>
        </div>
      </div>

      {/* Main Schedule Panel */}
      <div className="flex-1 bg-white flex flex-col min-w-0">
        {/* Top Toolbar */}
        <div className="bg-[#0A2540] px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#635BFF] flex items-center justify-center">
                <Calendar className="h-3.5 w-3.5 text-white" />
              </div>
              <span className="text-white text-[15px] tracking-[-0.01em]" style={{ fontWeight: 600 }}>Backfill Shifts</span>
            </div>
            <div className="hidden sm:flex items-center ml-4 bg-white/[0.08] rounded-lg p-0.5">
              <button className="px-3 py-1.5 text-[12px] text-white bg-white/[0.15] rounded-md" style={{ fontWeight: 500 }}>Schedule</button>
              <button className="px-3 py-1.5 text-[12px] text-white/50 hover:text-white/70 rounded-md transition-colors" style={{ fontWeight: 500 }}>Availability</button>
              <button className="px-3 py-1.5 text-[12px] text-white/50 hover:text-white/70 rounded-md transition-colors" style={{ fontWeight: 500 }}>Time Off</button>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-[#635BFF] text-white rounded-lg text-[12px] hover:bg-[#5850d6] transition-colors" style={{ fontWeight: 500 }}>
              <Plus className="h-3.5 w-3.5" />
              Add shift
            </button>
            <button className="p-1.5 hover:bg-white/10 rounded-lg transition-colors">
              <Filter className="h-4 w-4 text-white/50" />
            </button>
            <button className="p-1.5 hover:bg-white/10 rounded-lg transition-colors">
              <MoreHorizontal className="h-4 w-4 text-white/50" />
            </button>
          </div>
        </div>

        {/* Date Navigation */}
        <div className="bg-white px-5 py-2.5 flex items-center justify-between border-b border-[#e8ecf0]">
          <div className="flex items-center gap-2">
            <select className="brand-select min-w-[180px] py-1.5 text-[13px]" style={{ fontWeight: 500 }}>
              <option>Downtown Location</option>
            </select>
          </div>
          <div className="flex items-center gap-1">
            <button className="p-1.5 hover:bg-[#f5f7fa] rounded-lg transition-colors">
              <ChevronLeft className="h-4 w-4 text-[#425466]" />
            </button>
            <button className="px-3 py-1.5 text-[13px] text-[#0A2540] hover:bg-[#f5f7fa] rounded-lg transition-colors" style={{ fontWeight: 600 }}>
              Mar 12 – 18, 2026
            </button>
            <button className="p-1.5 hover:bg-[#f5f7fa] rounded-lg transition-colors">
              <ChevronRight className="h-4 w-4 text-[#425466]" />
            </button>
            <button className="hidden sm:flex ml-2 px-2.5 py-1.5 text-[12px] text-[#635BFF] bg-[#635BFF]/[0.06] hover:bg-[#635BFF]/[0.1] rounded-lg transition-colors" style={{ fontWeight: 500 }}>
              Today
            </button>
          </div>
          <div className="hidden sm:flex items-center gap-2 text-[12px] text-[#8898AA]">
            <div className="flex items-center gap-1 text-[#C08080]">
              <AlertTriangle className="h-3 w-3" />
              <span style={{ fontWeight: 500 }}>1 callout</span>
            </div>
            <div className="w-px h-4 bg-[#e2e8f0]" />
            <div className="flex items-center gap-1 text-[#5B8A7A]">
              <CheckCircle2 className="h-3 w-3" />
              <span style={{ fontWeight: 500 }}>1 covered</span>
            </div>
          </div>
        </div>

        {/* Schedule Grid */}
        <div className="overflow-x-auto flex-1">
          <div className="min-w-[660px]">
            {/* Column Headers */}
            <div className="grid grid-cols-[190px_repeat(7,1fr)] bg-[#fafbfd] border-b border-[#e8ecf0]">
              <div className="px-4 py-2.5 flex items-center justify-between">
                <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.08em]" style={{ fontWeight: 600 }}>Team ({employees.length})</span>
                <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.08em]" style={{ fontWeight: 600 }}>Hrs</span>
              </div>
              {days.map((day, i) => (
                <div key={i} className={`px-2 py-2.5 text-center border-l border-[#e8ecf0] ${day.isToday ? 'bg-[#635BFF]/[0.04]' : ''}`}>
                  <div className="text-[10px] text-[#8898AA] uppercase tracking-[0.06em] mb-0.5" style={{ fontWeight: 600 }}>{day.day}</div>
                  <div className={`text-[14px] inline-flex items-center justify-center ${day.isToday ? 'bg-[#635BFF] text-white w-6 h-6 rounded-full' : 'text-[#0A2540]'}`} style={{ fontWeight: 600 }}>
                    {day.date}
                  </div>
                </div>
              ))}
            </div>

            {/* Role Groups */}
            {Object.entries(roleGroups).map(([role, members]) => (
              <div key={role}>
                <div className="bg-[#f7f8fa] px-4 py-1.5 border-b border-[#e8ecf0] flex items-center gap-2">
                  <div className="w-1 h-3.5 rounded-full bg-[#635BFF]/30" />
                  <span className="text-[11px] text-[#425466] uppercase tracking-[0.06em]" style={{ fontWeight: 700 }}>{role}s</span>
                  <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 500 }}>({members.length})</span>
                </div>

                {members.map((employee, empIndex) => (
                  <div key={empIndex} className="grid grid-cols-[190px_repeat(7,1fr)] border-b border-[#f0f2f5] hover:bg-[#fafbfd] transition-colors group">
                    <div className="px-4 py-3 flex items-center gap-2.5 border-r border-[#f0f2f5]">
                      <div className={`w-7 h-7 rounded-full bg-gradient-to-br ${employee.avatarColor} flex items-center justify-center text-white text-[9px] shrink-0`} style={{ fontWeight: 700 }}>
                        {employee.initials}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[12px] text-[#0A2540] truncate" style={{ fontWeight: 500 }}>{employee.name}</div>
                      </div>
                      <div className="text-[11px] text-[#8898AA] tabular-nums shrink-0" style={{ fontWeight: 500 }}>{employee.hours}h</div>
                    </div>

                    {[...Array(7)].map((_, dayIndex) => {
                      const shift = employee.shifts.find(s => s.day === dayIndex);
                      const isToday = days[dayIndex]?.isToday;
                      const isSwapping = isSwapCell(employee.name, dayIndex);
                      const showHighlight = isSwapping && animPhase === 5;
                      const showDone = isSwapping && animPhase >= 6;

                      return (
                        <div
                          key={dayIndex}
                          className={`px-1 py-1.5 border-l border-[#f0f2f5] relative ${isToday ? 'bg-[#635BFF]/[0.02]' : ''}`}
                        >
                          {shift ? (
                            <div
                              className={`rounded-md px-1.5 py-1.5 cursor-pointer transition-all relative overflow-hidden ${showHighlight ? 'ring-2 ring-[#635BFF]/40 scale-[1.03]' : ''} ${showDone ? 'ring-1 ring-[#4ADE80]/30' : ''}`}
                              style={{
                                backgroundColor: getShiftStyles(shift.color, shift.status).backgroundColor,
                                borderLeft: `2.5px solid ${getShiftStyles(shift.color, shift.status).borderColor}`,
                                transition: 'all 0.5s ease',
                              }}
                            >
                              {shift.status === 'callout' && (
                                <div className="absolute top-1 right-1">
                                  <AlertTriangle className="h-2.5 w-2.5 text-[#C08080]" />
                                </div>
                              )}
                              {shift.status === 'covered' && (
                                <div className="absolute top-1 right-1">
                                  <CheckCircle2 className="h-2.5 w-2.5 text-[#5B8A7A]" />
                                </div>
                              )}
                              <div className="text-[10px] leading-tight" style={{ fontWeight: 600, color: getShiftStyles(shift.color, shift.status).color }}>
                                {shift.label}
                              </div>
                              <div className="text-[9px] mt-0.5 opacity-60" style={{ color: getShiftStyles(shift.color, shift.status).color }}>
                                {shift.start} – {shift.end}
                              </div>
                              {shift.status === 'callout' && (
                                <div className="text-[8px] mt-1 text-[#C08080] flex items-center gap-0.5" style={{ fontWeight: 600 }}>
                                  <Clock className="h-2 w-2" />
                                  Needs coverage
                                </div>
                              )}
                              {shift.status === 'covered' && (
                                <div className="text-[8px] mt-1 text-[#5B8A7A] flex items-center gap-0.5" style={{ fontWeight: 600 }}>
                                  <CheckCircle2 className="h-2 w-2" />
                                  Auto-filled
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="h-full min-h-[38px] rounded-md border border-transparent hover:border-dashed hover:border-[#d0d7de] transition-colors group-hover:opacity-100 opacity-0 flex items-center justify-center">
                              <Plus className="h-3 w-3 text-[#c0c8d0]" />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="bg-[#fafbfd] px-5 py-2.5 flex items-center justify-between border-t border-[#e8ecf0]">
          <div className="flex items-center gap-4 text-[11px] text-[#8898AA]">
            <span><span className="text-[#0A2540]" style={{ fontWeight: 600 }}>22 shifts</span> this week</span>
            <span className="hidden sm:inline">·</span>
            <span className="hidden sm:inline"><span className="text-[#0A2540]" style={{ fontWeight: 600 }}>186 hrs</span> total</span>
          </div>
          <div className="hidden sm:flex items-center gap-3 text-[11px] text-[#8898AA]">
            {[
              { label: 'Dinner', color: '#5B82B5' },
              { label: 'Closing', color: '#7090B8' },
              { label: 'Brunch', color: '#8AA0C0' },
              { label: 'Lunch', color: '#6888B0' },
              { label: 'Bar', color: '#7C98BE' },
            ].map(item => (
              <div key={item.label} className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: item.color }} />
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Inline animation keyframes */}
      <style>{`
        @keyframes fadeSlideUp {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
