"use client";

import { useRef, useState } from 'react';
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

import { FloatingDropdown } from '@/components/floating-dropdown';
import { useResolvedAppAppearance } from '@/components/app-session-gate';
import DashboardShell from './DashboardShell';

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
  const isDark = useResolvedAppAppearance() === 'dark';
  const [selectedLocation, setSelectedLocation] = useState('All locations');
  const [selectedCategory, setSelectedCategory] = useState('All categories');
  const [locationOpen, setLocationOpen] = useState(false);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const locationButtonRef = useRef<HTMLButtonElement>(null);
  const categoryButtonRef = useRef<HTMLButtonElement>(null);

  const filtered = allActivity.filter((activity) => {
    if (selectedLocation !== 'All locations' && activity.location !== selectedLocation) {
      return false;
    }
    if (selectedCategory !== 'All categories' && activity.category !== selectedCategory) {
      return false;
    }
    return true;
  });

  const today = filtered.filter((activity) => !activity.time.includes('day'));
  const older = filtered.filter((activity) => activity.time.includes('day'));

  const typeColors = {
    success: { bg: 'bg-[#00B893]/10', text: 'text-[#00B893]' },
    warning: { bg: 'bg-[#E5484D]/10', text: 'text-[#E5484D]' },
    info: { bg: 'bg-[#635BFF]/10', text: 'text-[#635BFF]' },
  };

  const categoryCounts = categories.slice(1).map((category) => ({
    name: category,
    count: filtered.filter((activity) => activity.category === category).length,
  }));

  const locationCounts = [
    { emoji: '\u{1F3E5}', name: 'Downtown Medical', count: filtered.filter((activity) => activity.location === 'Downtown Medical Center').length },
    { emoji: '\u{1F305}', name: 'Sunrise Senior', count: filtered.filter((activity) => activity.location === 'Sunrise Senior Living').length },
    { emoji: '\u{1F3E2}', name: 'Bay Area Staffing', count: filtered.filter((activity) => activity.location === 'Bay Area Staffing Co.').length },
    { emoji: '\u{1F3E8}', name: 'Coastal Hospitality', count: filtered.filter((activity) => activity.location === 'Coastal Hospitality Group').length },
  ];

  const textPrimary = isDark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = isDark ? 'text-[#C1CED8]' : 'text-[#8898AA]';
  const textBody = isDark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]';
  const textStrongBody = isDark ? 'text-[#E6EDF5]' : 'text-[#3E4C59]';
  const panelClass = isDark
    ? 'bg-[#0F2E4C] border-white/[0.06] shadow-[0_18px_48px_rgba(0,0,0,0.28)]'
    : 'bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]';
  const sidePanelClass = isDark
    ? 'bg-[#0F2E4C] border-white/[0.06] shadow-[0_12px_32px_rgba(0,0,0,0.24)]'
    : 'bg-white border-[#E5E7EB] shadow-[0_1px_2px_rgba(0,0,0,0.03)]';
  const sectionHeaderClass = isDark
    ? 'bg-white/[0.03] border-white/[0.06]'
    : 'bg-[#FAFBFC] border-[#F0F0F5]';
  const rowClass = isDark
    ? 'border-white/[0.06] hover:bg-white/[0.03]'
    : 'border-[#F0F0F5] hover:bg-[#FAFBFC]';
  const filterButtonClass = isDark
    ? 'bg-white/[0.04] border-white/[0.08] text-[#C1CED8] hover:border-white/[0.14] hover:bg-white/[0.06]'
    : 'bg-white border-[#E5E7EB] text-[#5E6D7A] hover:border-[#D1D5DB]';
  const filterButtonSelectedClass = isDark
    ? 'bg-[#635BFF]/[0.14] border-[#635BFF]/30 text-[#AFAAFF]'
    : 'bg-[#635BFF]/[0.06] border-[#635BFF]/20 text-[#635BFF]';
  const dropdownClass = isDark
    ? 'bg-[#0F2E4C] border-white/[0.08] shadow-[0_24px_60px_rgba(0,0,0,0.35)]'
    : 'bg-white border-[#E5E7EB] shadow-xl';
  const pillClass = isDark
    ? 'bg-white/[0.06] text-[#C1CED8]'
    : 'bg-[#F0F0F5] text-[#8898AA]';
  const statTrackClass = isDark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]';

  const content = (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
      <div className="mb-8">
        <h1 className={`text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] ${textPrimary}`} style={{ fontWeight: 620 }}>
          Activity
        </h1>
        <p className={`mt-1 text-[14px] ${textSecondary}`} style={{ fontWeight: 420 }}>
          Everything happening across your locations in one place.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-6">
        <div className={`flex items-center gap-2 text-[12px] ${textSecondary}`} style={{ fontWeight: 440 }}>
          <Filter size={14} />
          <span>Filter by</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="relative">
            <button
              ref={locationButtonRef}
              onClick={() => {
                setLocationOpen(!locationOpen);
                setCategoryOpen(false);
              }}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[12px] transition-all ${
                selectedLocation !== 'All locations' ? filterButtonSelectedClass : filterButtonClass
              }`}
              style={{ fontWeight: 480 }}
              type="button"
            >
              {selectedLocation === 'All locations' ? 'Location' : selectedLocation.split(' ')[0]}
              <ChevronDown size={12} className={`transition-transform ${locationOpen ? 'rotate-180' : ''}`} />
            </button>
            {locationOpen ? (
              <FloatingDropdown
                open={locationOpen}
                anchorRef={locationButtonRef}
                className={`rounded-xl border overflow-hidden ${dropdownClass}`}
                onClose={() => setLocationOpen(false)}
                width={256}
                zIndex={10010}
              >
                {locations.map((location) => (
                  <button
                    key={location}
                    onClick={() => {
                      setSelectedLocation(location);
                      setLocationOpen(false);
                    }}
                    className={`w-full text-left px-4 py-2.5 text-[12px] transition-colors ${
                      selectedLocation === location
                        ? filterButtonSelectedClass
                        : `${textSecondary} ${isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]'}`
                    }`}
                    style={{ fontWeight: selectedLocation === location ? 520 : 440 }}
                    type="button"
                  >
                    {location}
                  </button>
                ))}
              </FloatingDropdown>
            ) : null}
          </div>

          <div className="relative">
            <button
              ref={categoryButtonRef}
              onClick={() => {
                setCategoryOpen(!categoryOpen);
                setLocationOpen(false);
              }}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[12px] transition-all ${
                selectedCategory !== 'All categories' ? filterButtonSelectedClass : filterButtonClass
              }`}
              style={{ fontWeight: 480 }}
              type="button"
            >
              {selectedCategory === 'All categories' ? 'Category' : selectedCategory}
              <ChevronDown size={12} className={`transition-transform ${categoryOpen ? 'rotate-180' : ''}`} />
            </button>
            {categoryOpen ? (
              <FloatingDropdown
                open={categoryOpen}
                anchorRef={categoryButtonRef}
                className={`rounded-xl border overflow-hidden ${dropdownClass}`}
                onClose={() => setCategoryOpen(false)}
                width={192}
                zIndex={10010}
              >
                {categories.map((category) => (
                  <button
                    key={category}
                    onClick={() => {
                      setSelectedCategory(category);
                      setCategoryOpen(false);
                    }}
                    className={`w-full text-left px-4 py-2.5 text-[12px] transition-colors ${
                      selectedCategory === category
                        ? filterButtonSelectedClass
                        : `${textSecondary} ${isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]'}`
                    }`}
                    style={{ fontWeight: selectedCategory === category ? 520 : 440 }}
                    type="button"
                  >
                    {category}
                  </button>
                ))}
              </FloatingDropdown>
            ) : null}
          </div>

          {selectedLocation !== 'All locations' || selectedCategory !== 'All categories' ? (
            <button
              onClick={() => {
                setSelectedLocation('All locations');
                setSelectedCategory('All categories');
              }}
              className={`px-3 py-2 rounded-lg text-[12px] transition-colors ${textSecondary} ${isDark ? 'hover:text-white' : 'hover:text-[#5E6D7A]'}`}
              style={{ fontWeight: 460 }}
              type="button"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_300px] gap-6">
        <div className={`rounded-2xl border overflow-hidden ${panelClass}`}>
          {today.length > 0 ? (
            <div>
              <div className={`px-5 sm:px-6 py-3 border-b ${sectionHeaderClass}`}>
                <div className="flex items-center gap-2">
                  <Clock size={13} className={textSecondary} />
                  <span className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 500 }}>Today</span>
                  <span className="text-[11px] text-[#C1CED8] ml-1" style={{ fontWeight: 420 }}>{today.length} events</span>
                </div>
              </div>
              {today.map((item, index) => (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: index * 0.03 }}
                  className={`flex items-start gap-3 sm:gap-4 px-5 sm:px-6 py-4 border-b last:border-0 transition-colors ${rowClass}`}
                >
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${typeColors[item.type].bg}`}>
                    <item.icon size={14} className={typeColors[item.type].text} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <p className={`text-[13px] ${textStrongBody}`} style={{ fontWeight: 440 }}>{item.text}</p>
                      <span className={`text-[11px] shrink-0 hidden sm:block ${textSecondary}`} style={{ fontWeight: 420 }}>{item.time}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
                      <span className={`text-[11px] sm:hidden ${textSecondary}`} style={{ fontWeight: 420 }}>{item.time}</span>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[12px]">{item.locationEmoji}</span>
                        <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>{item.location}</span>
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full ${pillClass}`} style={{ fontWeight: 460 }}>{item.category}</span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          ) : null}

          {older.length > 0 ? (
            <div>
              <div className={`px-5 sm:px-6 py-3 border-b border-t ${sectionHeaderClass}`}>
                <div className="flex items-center gap-2">
                  <Clock size={13} className={textSecondary} />
                  <span className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 500 }}>Earlier</span>
                  <span className="text-[11px] text-[#C1CED8] ml-1" style={{ fontWeight: 420 }}>{older.length} events</span>
                </div>
              </div>
              {older.map((item, index) => (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.2 + index * 0.03 }}
                  className={`flex items-start gap-3 sm:gap-4 px-5 sm:px-6 py-4 border-b last:border-0 transition-colors ${rowClass}`}
                >
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${typeColors[item.type].bg}`}>
                    <item.icon size={14} className={typeColors[item.type].text} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-4">
                      <p className={`text-[13px] ${textStrongBody}`} style={{ fontWeight: 440 }}>{item.text}</p>
                      <span className={`text-[11px] shrink-0 hidden sm:block ${textSecondary}`} style={{ fontWeight: 420 }}>{item.time}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
                      <span className={`text-[11px] sm:hidden ${textSecondary}`} style={{ fontWeight: 420 }}>{item.time}</span>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[12px]">{item.locationEmoji}</span>
                        <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>{item.location}</span>
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full ${pillClass}`} style={{ fontWeight: 460 }}>{item.category}</span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          ) : null}

          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <ActivityIcon size={32} className={`mb-3 ${isDark ? 'text-white/[0.16]' : 'text-[#E5E7EB]'}`} />
              <p className={`text-[14px] ${textSecondary}`} style={{ fontWeight: 480 }}>No activity matching your filters</p>
              <button
                onClick={() => {
                  setSelectedLocation('All locations');
                  setSelectedCategory('All categories');
                }}
                className="text-[12px] text-[#635BFF] mt-2 hover:text-[#4B3FD9] transition-colors"
                style={{ fontWeight: 500 }}
                type="button"
              >
                Clear filters
              </button>
            </div>
          ) : null}
        </div>

        <div className="space-y-4">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className={`rounded-2xl border p-5 ${sidePanelClass}`}
          >
            <h3 className={`text-[13px] mb-4 ${textPrimary}`} style={{ fontWeight: 560 }}>Summary</h3>
            <div className="flex items-baseline gap-2 mb-4">
              <span className={`text-[32px] tracking-[-0.03em] ${textPrimary}`} style={{ fontWeight: 660 }}>{filtered.length}</span>
              <span className={`text-[13px] ${textSecondary}`} style={{ fontWeight: 420 }}>events</span>
            </div>
            <div className="space-y-2.5">
              {categoryCounts.map((category) => (
                <div key={category.name} className="flex items-center justify-between gap-3">
                  <span className={`text-[12px] ${textBody}`} style={{ fontWeight: 440 }}>{category.name}</span>
                  <div className="flex items-center gap-2">
                    <div className={`w-16 h-1.5 rounded-full overflow-hidden ${statTrackClass}`}>
                      <div
                        className="h-full rounded-full bg-[#635BFF]/40"
                        style={{ width: `${filtered.length ? (category.count / filtered.length) * 100 : 0}%` }}
                      />
                    </div>
                    <span className={`text-[12px] tabular-nums w-5 text-right ${textPrimary}`} style={{ fontWeight: 520 }}>{category.count}</span>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className={`rounded-2xl border p-5 ${sidePanelClass}`}
          >
            <h3 className={`text-[13px] mb-4 ${textPrimary}`} style={{ fontWeight: 560 }}>By Location</h3>
            <div className="space-y-3">
              {locationCounts.map((location) => (
                <div key={location.name} className="flex items-center gap-2.5">
                  <span className="text-[14px]">{location.emoji}</span>
                  <span className={`text-[12px] flex-1 truncate ${textBody}`} style={{ fontWeight: 440 }}>{location.name}</span>
                  <span className={`text-[12px] tabular-nums ${textPrimary}`} style={{ fontWeight: 520 }}>{location.count}</span>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className={`rounded-2xl border p-5 ${sidePanelClass}`}
          >
            <h3 className={`text-[13px] mb-4 ${textPrimary}`} style={{ fontWeight: 560 }}>By Status</h3>
            <div className="space-y-3">
              {[
                { label: 'Completed', count: filtered.filter((activity) => activity.type === 'success').length, color: '#00B893' },
                { label: 'Needs attention', count: filtered.filter((activity) => activity.type === 'warning').length, color: '#E5484D' },
                { label: 'Informational', count: filtered.filter((activity) => activity.type === 'info').length, color: '#635BFF' },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ background: item.color }} />
                    <span className={`text-[12px] ${textBody}`} style={{ fontWeight: 440 }}>{item.label}</span>
                  </div>
                  <span className={`text-[12px] tabular-nums ${textPrimary}`} style={{ fontWeight: 520 }}>{item.count}</span>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </motion.div>
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav="Activity">{content}</DashboardShell>;
}
