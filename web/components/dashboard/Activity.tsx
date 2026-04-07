"use client";

import { useState } from 'react';
import { motion } from 'motion/react';
import {
  CheckCircle2,
  AlertCircle,
  Activity as ActivityIcon,
  Filter,
  ChevronDown,
  Clock,
  UserPlus,
  UserMinus,
  CalendarPlus,
  CalendarX,
  FileText,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import DashboardShell from './DashboardShell';

/* ─── Activity Data ─── */
type ActivityType = 'success' | 'warning' | 'info';

interface ActivityItem {
  id: number;
  text: string;
  time: string;
  type: ActivityType;
  location: string;
  locationEmoji: string;
  category: string;
  icon: typeof CheckCircle2;
}

const allActivity: ActivityItem[] = [
  { id: 1, text: 'Sarah M. accepted Night Shift — ICU', time: '2 min ago', type: 'success', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', category: 'Shifts', icon: CheckCircle2 },
  { id: 2, text: '3 open shifts posted for ER coverage', time: '18 min ago', type: 'info', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', category: 'Shifts', icon: CalendarPlus },
  { id: 3, text: 'New caregiver onboarded successfully', time: '25 min ago', type: 'success', location: 'Sunrise Senior Living', locationEmoji: '\u{1F305}', category: 'Team', icon: UserPlus },
  { id: 4, text: '5 weekend shifts still need coverage', time: '45 min ago', type: 'warning', location: 'Sunrise Senior Living', locationEmoji: '\u{1F305}', category: 'Shifts', icon: AlertCircle },
  { id: 5, text: 'Marcus T. called out — Shift reassigned', time: '1 hr ago', type: 'warning', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', category: 'Shifts', icon: RefreshCw },
  { id: 6, text: '12 shifts broadcast to available staff', time: '1 hr ago', type: 'info', location: 'Bay Area Staffing Co.', locationEmoji: '\u{1F3E2}', category: 'Shifts', icon: CalendarPlus },
  { id: 7, text: 'Weekly compliance report generated', time: '2 hrs ago', type: 'info', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', category: 'Reports', icon: FileText },
  { id: 8, text: 'All shifts fully staffed for the week', time: '3 hrs ago', type: 'success', location: 'Coastal Hospitality Group', locationEmoji: '\u{1F3E8}', category: 'Shifts', icon: CheckCircle2 },
  { id: 9, text: 'James Chen credentials verified', time: '3 hrs ago', type: 'success', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', category: 'Compliance', icon: ShieldCheck },
  { id: 10, text: 'Overtime limit reached for Carlos Rivera', time: '4 hrs ago', type: 'warning', location: 'Bay Area Staffing Co.', locationEmoji: '\u{1F3E2}', category: 'Compliance', icon: AlertCircle },
  { id: 11, text: 'Emily Ross promoted to Shift Lead', time: '5 hrs ago', type: 'success', location: 'Sunrise Senior Living', locationEmoji: '\u{1F305}', category: 'Team', icon: UserPlus },
  { id: 12, text: 'Night shift coverage confirmed — Med-Surg', time: '5 hrs ago', type: 'success', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', category: 'Shifts', icon: CheckCircle2 },
  { id: 13, text: '4 new applications received', time: '6 hrs ago', type: 'info', location: 'Bay Area Staffing Co.', locationEmoji: '\u{1F3E2}', category: 'Team', icon: UserPlus },
  { id: 14, text: 'Weekend schedule published', time: '8 hrs ago', type: 'info', location: 'Coastal Hospitality Group', locationEmoji: '\u{1F3E8}', category: 'Shifts', icon: CalendarPlus },
  { id: 15, text: 'Break compliance audit passed', time: '9 hrs ago', type: 'success', location: 'Sunrise Senior Living', locationEmoji: '\u{1F305}', category: 'Compliance', icon: ShieldCheck },
  { id: 16, text: 'Lisa Park removed from active roster', time: '10 hrs ago', type: 'warning', location: 'Bay Area Staffing Co.', locationEmoji: '\u{1F3E2}', category: 'Team', icon: UserMinus },
  { id: 17, text: 'Shift swap approved: Aisha ↔ David', time: '12 hrs ago', type: 'info', location: 'Downtown Medical Center', locationEmoji: '\u{1F3E5}', category: 'Shifts', icon: RefreshCw },
  { id: 18, text: 'Monthly payroll report exported', time: '14 hrs ago', type: 'info', location: 'Bay Area Staffing Co.', locationEmoji: '\u{1F3E2}', category: 'Reports', icon: FileText },
  { id: 19, text: '2 shifts cancelled due to low census', time: '1 day ago', type: 'warning', location: 'Sunrise Senior Living', locationEmoji: '\u{1F305}', category: 'Shifts', icon: CalendarX },
  { id: 20, text: 'New location onboarding completed', time: '1 day ago', type: 'success', location: 'Coastal Hospitality Group', locationEmoji: '\u{1F3E8}', category: 'Team', icon: CheckCircle2 },
];

const locations = ['All locations', 'Downtown Medical Center', 'Sunrise Senior Living', 'Bay Area Staffing Co.', 'Coastal Hospitality Group'];
const categories = ['All categories', 'Shifts', 'Team', 'Compliance', 'Reports'];

export default function Activity({
  embeddedInShell = false,
}: {
  embeddedInShell?: boolean;
}) {
  const [selectedLocation, setSelectedLocation] = useState('All locations');
  const [selectedCategory, setSelectedCategory] = useState('All categories');
  const [locationOpen, setLocationOpen] = useState(false);
  const [categoryOpen, setCategoryOpen] = useState(false);

  const filtered = allActivity.filter((a) => {
    if (selectedLocation !== 'All locations' && a.location !== selectedLocation) return false;
    if (selectedCategory !== 'All categories' && a.category !== selectedCategory) return false;
    return true;
  });

  // Group by time buckets
  const today = filtered.filter((a) => !a.time.includes('day'));
  const older = filtered.filter((a) => a.time.includes('day'));

  const typeColors = {
    success: { bg: 'bg-[#00B893]/10', text: 'text-[#00B893]' },
    warning: { bg: 'bg-[#E5484D]/10', text: 'text-[#E5484D]' },
    info: { bg: 'bg-[#635BFF]/10', text: 'text-[#635BFF]' },
  };

  const content = (
    <>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-[24px] sm:text-[28px] md:text-[32px] text-[#0A2540] tracking-[-0.025em]" style={{ fontWeight: 620 }}>
                Activity
              </h1>
              <p className="text-[14px] text-[#8898AA] mt-1" style={{ fontWeight: 420 }}>
                Everything happening across your locations in one place.
              </p>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-6">
          <div className="flex items-center gap-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 440 }}>
            <Filter size={14} />
            <span>Filter by</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {/* Location Filter */}
            <div className="relative">
              <button onClick={() => { setLocationOpen(!locationOpen); setCategoryOpen(false); }}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[12px] transition-all ${
                  selectedLocation !== 'All locations'
                    ? 'bg-[#635BFF]/[0.06] border-[#635BFF]/20 text-[#635BFF]'
                    : 'bg-white border-[#E5E7EB] text-[#5E6D7A] hover:border-[#D1D5DB]'
                }`} style={{ fontWeight: 480 }}>
                {selectedLocation === 'All locations' ? 'Location' : selectedLocation.split(' ')[0]}
                <ChevronDown size={12} className={`transition-transform ${locationOpen ? 'rotate-180' : ''}`} />
              </button>
              {locationOpen && (
                <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
                  className="absolute left-0 top-full mt-1 w-64 bg-white border border-[#E5E7EB] rounded-xl shadow-xl overflow-hidden z-30">
                  {locations.map((loc) => (
                    <button key={loc} onClick={() => { setSelectedLocation(loc); setLocationOpen(false); }}
                      className={`w-full text-left px-4 py-2.5 text-[12px] transition-colors ${
                        selectedLocation === loc ? 'bg-[#635BFF]/[0.06] text-[#635BFF]' : 'text-[#5E6D7A] hover:bg-[#F7F8FA]'
                      }`} style={{ fontWeight: selectedLocation === loc ? 520 : 440 }}>
                      {loc}
                    </button>
                  ))}
                </motion.div>
              )}
            </div>

            {/* Category Filter */}
            <div className="relative">
              <button onClick={() => { setCategoryOpen(!categoryOpen); setLocationOpen(false); }}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[12px] transition-all ${
                  selectedCategory !== 'All categories'
                    ? 'bg-[#635BFF]/[0.06] border-[#635BFF]/20 text-[#635BFF]'
                    : 'bg-white border-[#E5E7EB] text-[#5E6D7A] hover:border-[#D1D5DB]'
                }`} style={{ fontWeight: 480 }}>
                {selectedCategory === 'All categories' ? 'Category' : selectedCategory}
                <ChevronDown size={12} className={`transition-transform ${categoryOpen ? 'rotate-180' : ''}`} />
              </button>
              {categoryOpen && (
                <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
                  className="absolute left-0 top-full mt-1 w-48 bg-white border border-[#E5E7EB] rounded-xl shadow-xl overflow-hidden z-30">
                  {categories.map((cat) => (
                    <button key={cat} onClick={() => { setSelectedCategory(cat); setCategoryOpen(false); }}
                      className={`w-full text-left px-4 py-2.5 text-[12px] transition-colors ${
                        selectedCategory === cat ? 'bg-[#635BFF]/[0.06] text-[#635BFF]' : 'text-[#5E6D7A] hover:bg-[#F7F8FA]'
                      }`} style={{ fontWeight: selectedCategory === cat ? 520 : 440 }}>
                      {cat}
                    </button>
                  ))}
                </motion.div>
              )}
            </div>

            {(selectedLocation !== 'All locations' || selectedCategory !== 'All categories') && (
              <button onClick={() => { setSelectedLocation('All locations'); setSelectedCategory('All categories'); }}
                className="px-3 py-2 rounded-lg text-[12px] text-[#8898AA] hover:text-[#5E6D7A] transition-colors" style={{ fontWeight: 460 }}>
                Clear filters
              </button>
            )}
          </div>
        </div>

        {/* Activity Feed */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.04)] overflow-hidden">
          {/* Today */}
          {today.length > 0 && (
            <div>
              <div className="px-5 sm:px-6 py-3 bg-[#FAFBFC] border-b border-[#F0F0F5]">
                <div className="flex items-center gap-2">
                  <Clock size={13} className="text-[#8898AA]" />
                  <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 500 }}>Today</span>
                  <span className="text-[11px] text-[#C1CED8] ml-1" style={{ fontWeight: 420 }}>{today.length} events</span>
                </div>
              </div>
              {today.map((item, i) => (
                <motion.div key={item.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: i * 0.03 }}
                  className="flex items-start gap-3 sm:gap-4 px-5 sm:px-6 py-4 border-b border-[#F0F0F5] last:border-0 hover:bg-[#FAFBFC] transition-colors">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${typeColors[item.type].bg}`}>
                    <item.icon size={14} className={typeColors[item.type].text} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] text-[#3E4C59]" style={{ fontWeight: 440 }}>{item.text}</p>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
                      <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>{item.time}</span>
                      <div className="flex items-center gap-1">
                        <span className="text-[12px]">{item.locationEmoji}</span>
                        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>{item.location}</span>
                      </div>
                      <span className="text-[10px] text-[#8898AA] bg-[#F0F0F5] px-2 py-0.5 rounded-full" style={{ fontWeight: 460 }}>{item.category}</span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}

          {/* Older */}
          {older.length > 0 && (
            <div>
              <div className="px-5 sm:px-6 py-3 bg-[#FAFBFC] border-b border-[#F0F0F5] border-t border-t-[#E5E7EB]">
                <div className="flex items-center gap-2">
                  <Clock size={13} className="text-[#8898AA]" />
                  <span className="text-[11px] text-[#8898AA] uppercase tracking-[0.04em]" style={{ fontWeight: 500 }}>Earlier</span>
                  <span className="text-[11px] text-[#C1CED8] ml-1" style={{ fontWeight: 420 }}>{older.length} events</span>
                </div>
              </div>
              {older.map((item, i) => (
                <motion.div key={item.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.2 + i * 0.03 }}
                  className="flex items-start gap-3 sm:gap-4 px-5 sm:px-6 py-4 border-b border-[#F0F0F5] last:border-0 hover:bg-[#FAFBFC] transition-colors">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${typeColors[item.type].bg}`}>
                    <item.icon size={14} className={typeColors[item.type].text} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] text-[#3E4C59]" style={{ fontWeight: 440 }}>{item.text}</p>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
                      <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>{item.time}</span>
                      <div className="flex items-center gap-1">
                        <span className="text-[12px]">{item.locationEmoji}</span>
                        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>{item.location}</span>
                      </div>
                      <span className="text-[10px] text-[#8898AA] bg-[#F0F0F5] px-2 py-0.5 rounded-full" style={{ fontWeight: 460 }}>{item.category}</span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}

          {filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16">
              <ActivityIcon size={32} className="text-[#E5E7EB] mb-3" />
              <p className="text-[14px] text-[#8898AA]" style={{ fontWeight: 480 }}>No activity matching your filters</p>
              <button onClick={() => { setSelectedLocation('All locations'); setSelectedCategory('All categories'); }}
                className="text-[12px] text-[#635BFF] mt-2 hover:text-[#4B3FD9] transition-colors" style={{ fontWeight: 500 }}>
                Clear filters
              </button>
            </div>
          )}
        </div>
      </motion.div>
    </>
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav="Activity">{content}</DashboardShell>;
}
