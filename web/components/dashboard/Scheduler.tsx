"use client";

import { useState, useRef, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { useRouter } from 'next/navigation';
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  X,
  Trash2,
  Check,
  ChevronDown,
  Zap,
  Sun,
  Moon,
  Sunrise,
  Sunset,
  ClipboardCopy,
} from 'lucide-react';
import { useResolvedAppAppearance } from '@/components/app-session-gate';
import { FloatingDropdown } from '@/components/floating-dropdown';
import type { WorkspaceLocation } from '@/lib/api/workspace';
import { buildDashboardLocationBasePathFromAny } from '@/lib/dashboard-paths';
import DashboardShell from './DashboardShell';
import { getLocationReference } from './location-role-reference';
import { PublishWeekModal } from './PublishWeekModal';

/* ─── Types ─── */
interface Employee { id: string; name: string; avatar: string; role: string; }
interface Shift { id: string; employeeId: string; day: number; startHour: number; endHour: number; role: string; color: string; }

const DRAG_TYPE = 'SHIFT';
interface DragItem { type: string; shiftId: string; }

/* ─── Role colors ─── */
const roleColors: Record<string, string> = {
  'RN': '#635BFF', 'LPN': '#8B5CF6', 'CNA': '#00B893', 'NP': '#3B82F6', 'Medical Assistant': '#EC4899',
};
const roleOrder = ['RN', 'LPN', 'CNA', 'NP', 'Medical Assistant'];

/* ─── Employees ─── */
const employees: Employee[] = [
  { id: 'e1', name: 'Sarah Martinez', role: 'RN', avatar: 'https://images.unsplash.com/photo-1594824476967-48c8b964273f?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e2', name: 'Carlos Rivera', role: 'RN', avatar: 'https://images.unsplash.com/photo-1627093143401-2ade923be6c2?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e3', name: 'Emily Chen', role: 'RN', avatar: 'https://images.unsplash.com/photo-1678695972687-033fa0bdbac9?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e4', name: 'Jordan Lee', role: 'RN', avatar: 'https://images.unsplash.com/photo-1622253694238-3b22139576c6?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e5', name: 'David Kim', role: 'LPN', avatar: 'https://images.unsplash.com/photo-1762522926157-bcc04bf0b10a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e6', name: 'Nicole Adams', role: 'LPN', avatar: 'https://images.unsplash.com/photo-1756699197173-5ef672a423fa?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e7', name: 'Aisha Patel', role: 'CNA', avatar: 'https://images.unsplash.com/photo-1581322929625-f4aab333778a?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e8', name: 'Alex Thompson', role: 'CNA', avatar: 'https://images.unsplash.com/photo-1645736594095-b9a4cabc1a7c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e9', name: 'Taylor Brooks', role: 'NP', avatar: 'https://images.unsplash.com/photo-1756699280573-85c5628a4c6c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e10', name: 'Maria Santos', role: 'Medical Assistant', avatar: 'https://images.unsplash.com/photo-1731005116674-062a313bc7ab?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
  { id: 'e11', name: 'Ryan Murphy', role: 'Medical Assistant', avatar: 'https://images.unsplash.com/photo-1622253694238-3b22139576c6?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=100' },
];

/* ─── Helpers ─── */
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const FULL_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

function formatHour(h: number) {
  if (h === 0 || h === 24) return '12 AM';
  if (h === 12) return '12 PM';
  return h < 12 ? `${h} AM` : `${h - 12} PM`;
}

function shiftDuration(s: Shift) {
  return s.endHour > s.startHour ? s.endHour - s.startHour : 24 - s.startHour + s.endHour;
}

function getShiftDescriptor(start: number, end: number): { label: string; icon: typeof Sunrise } {
  const mid = end > start ? (start + end) / 2 : (start + (24 - start + end)) / 2;
  if (mid < 12) return { label: 'Morning', icon: Sunrise };
  if (mid < 16) return { label: 'Afternoon', icon: Sun };
  if (mid < 20) return { label: 'Evening', icon: Sunset };
  return { label: 'Night', icon: Moon };
}

function getWeekDates(offset: number) {
  const today = new Date();
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7) + offset * 7);
  return Array.from({ length: 7 }, (_, i) => { const d = new Date(monday); d.setDate(monday.getDate() + i); return d; });
}

function isToday(date: Date) {
  const t = new Date();
  return date.getDate() === t.getDate() && date.getMonth() === t.getMonth() && date.getFullYear() === t.getFullYear();
}

const uid = () => Math.random().toString(36).slice(2, 10);

/* ─── Quick Shift Templates ─── */
const shiftTemplates = [
  { label: 'Morning', icon: Sunrise, start: 7, end: 15 },
  { label: 'Afternoon', icon: Sun, start: 11, end: 19 },
  { label: 'Evening', icon: Sunset, start: 15, end: 23 },
  { label: 'Night', icon: Moon, start: 23, end: 7 },
];

function getSchedulerTheme(isDark: boolean) {
  return {
    pageClass: isDark ? 'bg-[#081A2C]' : 'bg-[#F7F8FA]',
    topBarClass: isDark
      ? 'border-white/[0.08] bg-[#0B2239]/88 backdrop-blur-xl'
      : 'border-[#F0F0F5] bg-white/80 backdrop-blur-sm',
    mobileDayBorderClass: isDark ? 'border-white/[0.08]' : 'border-[#F0F0F5]',
    stickyHeaderClass: isDark ? 'bg-[#0B2239] border-white/[0.08]' : 'bg-white border-[#E5E7EB]',
    roleBandClass: isDark ? 'bg-white/[0.04] border-white/[0.08]' : 'bg-[#F5F6F8] border-[#F0F0F5]',
    rowClass: isDark ? 'border-white/[0.06] hover:bg-white/[0.02]' : 'border-[#F0F0F5] hover:bg-[#FAFBFC]/50',
    cellBorderClass: isDark ? 'border-white/[0.06]' : 'border-[#F0F0F5]',
    todayCellClass: isDark ? 'bg-[#635BFF]/[0.08]' : 'bg-[#635BFF]/[0.015]',
    todayHeaderClass: isDark ? 'bg-[#635BFF]/[0.06]' : 'bg-[#635BFF]/[0.02]',
    todayRoleBandClass: isDark ? 'bg-[#635BFF]/[0.04]' : 'bg-[#635BFF]/[0.01]',
    textPrimary: isDark ? 'text-white' : 'text-[#0A2540]',
    textSecondary: isDark ? 'text-[#C1CED8]' : 'text-[#8898AA]',
    textMuted: isDark ? 'text-[#8FA3B8]' : 'text-[#5E6D7A]',
    textSubtle: isDark ? 'text-[#708399]' : 'text-[#B0B8C1]',
    ghostButtonClass: isDark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]',
    daySelectorIdleClass: isDark ? 'text-[#C1CED8] hover:bg-white/[0.06]' : 'text-[#5E6D7A] hover:bg-[#F7F8FA]',
    todaySelectorClass: isDark ? 'bg-[#635BFF]/[0.14] text-[#AFAAFF]' : 'bg-[#635BFF]/[0.06] text-[#635BFF]',
    mobileSelectedDayClass: isDark ? 'bg-[#635BFF] text-white' : 'bg-[#635BFF] text-white',
    cardClass: isDark ? 'bg-[#0F2E4C] border-white/[0.08]' : 'bg-white border-[#E5E7EB]',
    modalClass: isDark ? 'bg-[#0F2E4C] border border-white/[0.08]' : 'bg-white border border-[#E5E7EB]',
    modalBorderClass: isDark ? 'border-white/[0.08]' : 'border-[#F0F0F5]',
    inputButtonClass: isDark
      ? 'bg-white/[0.05] border-white/[0.1] text-white hover:border-[#635BFF]/40'
      : 'bg-[#F7F8FA] border-[#E5E7EB] text-[#0A2540] hover:border-[#635BFF]/30',
    dropdownClass: isDark
      ? 'bg-[#102B46] border border-white/[0.08] shadow-[0_24px_60px_rgba(0,0,0,0.4)]'
      : 'bg-white border border-[#E5E7EB] shadow-lg',
    iconButtonClass: isDark ? 'bg-white/[0.92] border-white/10' : 'bg-white/90 border-[#E5E7EB]',
    emptyStateClass: isDark
      ? 'border border-dashed border-white/[0.08] hover:bg-white/[0.04] hover:border-[#635BFF]/30'
      : 'border border-transparent hover:bg-[#635BFF]/[0.03] hover:border-dashed hover:border-[#635BFF]/20',
    toastClass: isDark
      ? 'bg-[#0B2239] border border-white/[0.08]'
      : 'bg-[#0A2540] border border-[#1A3A5C]',
  };
}

/* ─── Initial shifts ─── */
function generateInitialShifts(): Shift[] {
  return [
    { id: uid(), employeeId: 'e1', day: 0, startHour: 7, endHour: 15, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e1', day: 2, startHour: 7, endHour: 15, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e1', day: 4, startHour: 7, endHour: 15, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e2', day: 0, startHour: 15, endHour: 23, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e2', day: 1, startHour: 15, endHour: 23, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e2', day: 3, startHour: 15, endHour: 23, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e3', day: 1, startHour: 7, endHour: 15, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e3', day: 3, startHour: 7, endHour: 15, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e3', day: 5, startHour: 7, endHour: 19, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e4', day: 2, startHour: 15, endHour: 23, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e4', day: 4, startHour: 15, endHour: 23, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e1', day: 1, startHour: 19, endHour: 23, role: 'RN', color: roleColors['RN'] },
    { id: uid(), employeeId: 'e5', day: 1, startHour: 8, endHour: 16, role: 'LPN', color: roleColors['LPN'] },
    { id: uid(), employeeId: 'e5', day: 3, startHour: 8, endHour: 16, role: 'LPN', color: roleColors['LPN'] },
    { id: uid(), employeeId: 'e5', day: 5, startHour: 8, endHour: 16, role: 'LPN', color: roleColors['LPN'] },
    { id: uid(), employeeId: 'e6', day: 0, startHour: 7, endHour: 15, role: 'LPN', color: roleColors['LPN'] },
    { id: uid(), employeeId: 'e6', day: 2, startHour: 7, endHour: 15, role: 'LPN', color: roleColors['LPN'] },
    { id: uid(), employeeId: 'e7', day: 0, startHour: 7, endHour: 15, role: 'CNA', color: roleColors['CNA'] },
    { id: uid(), employeeId: 'e7', day: 1, startHour: 7, endHour: 15, role: 'CNA', color: roleColors['CNA'] },
    { id: uid(), employeeId: 'e7', day: 2, startHour: 7, endHour: 15, role: 'CNA', color: roleColors['CNA'] },
    { id: uid(), employeeId: 'e8', day: 3, startHour: 7, endHour: 15, role: 'CNA', color: roleColors['CNA'] },
    { id: uid(), employeeId: 'e8', day: 4, startHour: 7, endHour: 15, role: 'CNA', color: roleColors['CNA'] },
    { id: uid(), employeeId: 'e9', day: 2, startHour: 9, endHour: 17, role: 'NP', color: roleColors['NP'] },
    { id: uid(), employeeId: 'e9', day: 4, startHour: 9, endHour: 17, role: 'NP', color: roleColors['NP'] },
    { id: uid(), employeeId: 'e10', day: 0, startHour: 9, endHour: 17, role: 'Medical Assistant', color: roleColors['Medical Assistant'] },
    { id: uid(), employeeId: 'e10', day: 2, startHour: 9, endHour: 17, role: 'Medical Assistant', color: roleColors['Medical Assistant'] },
    { id: uid(), employeeId: 'e10', day: 4, startHour: 9, endHour: 17, role: 'Medical Assistant', color: roleColors['Medical Assistant'] },
    { id: uid(), employeeId: 'e11', day: 1, startHour: 9, endHour: 17, role: 'Medical Assistant', color: roleColors['Medical Assistant'] },
    { id: uid(), employeeId: 'e11', day: 3, startHour: 9, endHour: 17, role: 'Medical Assistant', color: roleColors['Medical Assistant'] },
  ];
}

/* ─── InlineSelect ─── */
function InlineSelect({
  value,
  options,
  onChange,
  placeholder,
  dark = false,
}: {
  value: string;
  options: { label: string; value: string }[];
  onChange: (v: string) => void;
  placeholder?: string;
  dark?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const theme = getSchedulerTheme(dark);
  return (
    <div className="relative">
      <button ref={buttonRef} onClick={() => setOpen(!open)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all text-[12px] min-w-[120px] justify-between ${theme.inputButtonClass}`}
        style={{ fontWeight: 460 }}>
        <span className={value ? '' : theme.textSecondary}>{value || placeholder || 'Select...'}</span>
        <ChevronDown size={12} className={theme.textSecondary} />
      </button>
      <FloatingDropdown
        open={open}
        anchorRef={buttonRef}
        className={`${theme.dropdownClass} rounded-xl py-1 overflow-y-auto`}
        maxHeight={240}
        minWidth={180}
        onClose={() => setOpen(false)}
        width={180}
        zIndex={10020}
      >
        {options.map(opt => (
          <button key={opt.value} onClick={() => { onChange(opt.value); setOpen(false); }}
            className={`w-full text-left px-3 py-2 text-[12px] transition-colors flex items-center gap-2 ${
              value === opt.value
                ? 'text-[#635BFF] bg-[#635BFF]/[0.08]'
                : `${theme.textPrimary} ${theme.ghostButtonClass}`
            }`} style={{ fontWeight: value === opt.value ? 520 : 440 }}>
            {value === opt.value && <Check size={12} className="text-[#635BFF]" />}
            <span className={value === opt.value ? '' : 'ml-5'}>{opt.label}</span>
          </button>
        ))}
      </FloatingDropdown>
    </div>
  );
}

/* ─── Draggable Shift Chip ─── */
function DraggableShiftChip({ shift, isMulti, onEdit, onDelete, dark = false }: {
  shift: Shift; isMulti: boolean; onEdit: () => void; onDelete: () => void; dark?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const descriptor = getShiftDescriptor(shift.startHour, shift.endHour);
  const DescIcon = descriptor.icon;
  const dur = shiftDuration(shift);
  const theme = getSchedulerTheme(dark);

  const [{ isDragging }, dragRef] = useDrag(() => ({
    type: DRAG_TYPE,
    item: { type: DRAG_TYPE, shiftId: shift.id } as DragItem,
    collect: (monitor) => ({ isDragging: monitor.isDragging() }),
  }), [shift.id]);

  /* Single shift: stacked layout showing descriptor + time + hours clearly.
     Multi shift: compact inline row to fit multiple in one cell. */
  if (!isMulti) {
    return (
      <div
        ref={dragRef as unknown as React.RefObject<HTMLDivElement>}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={onEdit}
        className={`relative rounded-lg cursor-grab active:cursor-grabbing overflow-hidden transition-all mx-1 my-0.5 ${
          isDragging ? 'opacity-40 scale-95' : 'hover:shadow-md'
        }`}
        style={{ minHeight: 52 }}
      >
        <div className="absolute inset-0 rounded-lg" style={{ background: shift.color, opacity: 0.08 }} />
        <div className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg" style={{ background: shift.color }} />

        <div className="relative pl-2.5 pr-2 py-2 flex items-start gap-1.5">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1">
              <DescIcon size={11} style={{ color: shift.color }} className="shrink-0" />
              <span className="text-[10px] truncate" style={{ fontWeight: 560, color: shift.color }}>
                {descriptor.label}
              </span>
            </div>
            <p className={`text-[9px] mt-0.5 ${theme.textMuted}`} style={{ fontWeight: 420 }}>
              {formatHour(shift.startHour)} – {formatHour(shift.endHour)}
            </p>
            <p className={`text-[9px] mt-px ${theme.textSubtle}`} style={{ fontWeight: 400 }}>
              {dur}h
            </p>
          </div>

          <AnimatePresence>
            {hovered && !isDragging && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="flex flex-col gap-0.5 shrink-0">
                <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
                  className={`p-0.5 rounded shadow-sm border transition-all ${theme.iconButtonClass} hover:border-red-300`} title="Delete">
                  <Trash2 size={9} className={theme.textMuted} />
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    );
  }

  /* Multi-shift compact row */
  return (
    <div
      ref={dragRef as unknown as React.RefObject<HTMLDivElement>}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onEdit}
      className={`relative rounded-lg cursor-grab active:cursor-grabbing overflow-hidden transition-all mx-1 my-[1px] ${
        isDragging ? 'opacity-40 scale-95' : 'hover:shadow-md'
      }`}
      style={{ minHeight: 38 }}
    >
      <div className="absolute inset-0 rounded-lg" style={{ background: shift.color, opacity: 0.08 }} />
      <div className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg" style={{ background: shift.color }} />

      <div className="relative pl-2.5 pr-2 py-1.5">
        {/* Row 1: label + hours top-right */}
        <div className="flex items-center justify-between gap-1">
          <div className="flex items-center gap-1 min-w-0">
            <DescIcon size={9} style={{ color: shift.color }} className="shrink-0" />
            <span className="text-[9px] truncate" style={{ fontWeight: 540, color: shift.color }}>
              {descriptor.label}
            </span>
          </div>
          <div className="flex items-center gap-0.5 shrink-0">
            <span className={`text-[8px] ${theme.textSubtle}`} style={{ fontWeight: 420 }}>
              {dur}h
            </span>
            <AnimatePresence>
              {hovered && !isDragging && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="flex gap-0.5">
                  <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
                    className={`p-0.5 rounded shadow-sm border transition-all ${theme.iconButtonClass} hover:border-red-300`} title="Delete">
                    <Trash2 size={7} className={theme.textMuted} />
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
        {/* Row 2: time span */}
        <p className={`text-[8px] mt-0.5 truncate ${theme.textMuted}`} style={{ fontWeight: 420 }}>
          {formatHour(shift.startHour)} – {formatHour(shift.endHour)}
        </p>
      </div>
    </div>
  );
}

/* ─── Droppable Cell ─── */
function DroppableCell({ employeeId, day, children, onDrop, onClickEmpty, isToday: isTodayCell, dark = false }: {
  employeeId: string; day: number; children: React.ReactNode;
  onDrop: (shiftId: string, newEmpId: string, newDay: number) => void;
  onClickEmpty: () => void; isToday: boolean; dark?: boolean;
}) {
  const [{ isOver, canDrop }, dropRef] = useDrop(() => ({
    accept: DRAG_TYPE,
    drop: (item: DragItem) => { onDrop(item.shiftId, employeeId, day); },
    collect: (monitor) => ({ isOver: monitor.isOver(), canDrop: monitor.canDrop() }),
  }), [employeeId, day]);

  const hasChildren = Array.isArray(children) ? children.some(Boolean) : !!children;
  const theme = getSchedulerTheme(dark);

  return (
    <div
      ref={dropRef as unknown as React.RefObject<HTMLDivElement>}
      className={`flex-1 border-l py-0.5 flex flex-col justify-center min-h-[52px] transition-colors ${theme.cellBorderClass} ${
        isTodayCell ? theme.todayCellClass : ''
      } ${isOver && canDrop ? 'bg-[#635BFF]/[0.06]' : ''} ${canDrop && !isOver ? '' : ''}`}
    >
      {hasChildren ? children : (
        <div onClick={onClickEmpty}
          className={`h-full min-h-[44px] flex items-center justify-center cursor-pointer group/empty mx-0.5 my-0.5 rounded-lg transition-colors ${theme.emptyStateClass}`}>
          <div className="opacity-0 group-hover/empty:opacity-100 transition-opacity">
            <Plus size={12} className="text-[#635BFF]/50" />
          </div>
        </div>
      )}
    </div>
  );
}

type SchedulerProps = {
  embeddedInShell?: boolean;
  location: WorkspaceLocation;
  backHref?: string;
};

/* ─── Main Scheduler ─── */
function SchedulerContent({
  embeddedInShell = false,
  location,
  backHref,
}: SchedulerProps) {
  const router = useRouter();
  const isDark = useResolvedAppAppearance() === 'dark';
  const theme = getSchedulerTheme(isDark);
  const locationDisplayName = location.location_display_name ?? location.location_name;
  const locationReference = getLocationReference({
    name: locationDisplayName,
    slug: location.location_slug,
  });
  const resolvedBackHref = backHref ?? buildDashboardLocationBasePathFromAny(location);
  const loc = {
    name: locationDisplayName,
    emoji: locationReference.logo,
    color: locationReference.color,
    type: locationReference.typeLabel,
  };

  const [weekOffset, setWeekOffset] = useState(0);
  const [shifts, setShifts] = useState<Shift[]>(generateInitialShifts);
  const [editingShift, setEditingShift] = useState<Shift | null>(null);
  const [creatingAt, setCreatingAt] = useState<{ employeeId: string; day: number; role: string } | null>(null);
  const [showPublishToast, setShowPublishToast] = useState(false);
  const [showCopyToast, setShowCopyToast] = useState(false);
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [showPublishModal, setShowPublishModal] = useState(false);
  const [collapsedRoles, setCollapsedRoles] = useState<Set<string>>(new Set());
  const [mobileDay, setMobileDay] = useState(() => (new Date().getDay() + 6) % 7);

  const weekDates = useMemo(() => getWeekDates(weekOffset), [weekOffset]);

  const filteredRoles = roleOrder.filter(r => employees.some(e => e.role === r));

  const getEmployeeWeekHours = useCallback((empId: string) =>
    shifts.filter(s => s.employeeId === empId).reduce((sum, s) => sum + shiftDuration(s), 0), [shifts]);

  const getDayTotalHours = useCallback((day: number) =>
    shifts.filter(s => s.day === day).reduce((sum, s) => sum + shiftDuration(s), 0), [shifts]);

  const weekTotalHours = useMemo(() =>
    shifts.reduce((sum, s) => sum + shiftDuration(s), 0), [shifts]);

  const getShiftsForCell = useCallback((empId: string, day: number) =>
    shifts.filter(s => s.employeeId === empId && s.day === day), [shifts]);

  const deleteShift = (id: string) => setShifts(prev => prev.filter(s => s.id !== id));

  const updateShift = (updated: Shift) => {
    setShifts(prev => prev.map(s => s.id === updated.id ? updated : s));
    setEditingShift(null);
  };

  const moveShift = useCallback((shiftId: string, newEmpId: string, newDay: number) => {
    setShifts(prev => prev.map(s => {
      if (s.id !== shiftId) return s;
      const newEmp = employees.find(e => e.id === newEmpId);
      return {
        ...s,
        employeeId: newEmpId,
        day: newDay,
        role: newEmp?.role || s.role,
        color: roleColors[newEmp?.role || s.role] || s.color,
      };
    }));
  }, []);

  const copySchedule = (targetWeekOffset: number) => {
    const copied = shifts.map(s => ({ ...s, id: uid() }));
    setShifts(copied);
    setWeekOffset(targetWeekOffset);
    setShowCopyModal(false);
    setShowCopyToast(true);
    setTimeout(() => setShowCopyToast(false), 3000);
  };

  const toggleRoleCollapse = (role: string) => {
    setCollapsedRoles(prev => {
      const next = new Set(prev);
      if (next.has(role)) next.delete(role); else next.add(role);
      return next;
    });
  };

  /* ─── Week Label ─── */
  const weekLabel = useMemo(() => {
    const s = weekDates[0];
    const e = weekDates[6];
    const sm = s.toLocaleString('default', { month: 'short' });
    const em = e.toLocaleString('default', { month: 'short' });
    if (sm === em) return `${sm} ${s.getDate()} – ${e.getDate()}, ${s.getFullYear()}`;
    return `${sm} ${s.getDate()} – ${em} ${e.getDate()}, ${s.getFullYear()}`;
  }, [weekDates]);

  const EMP_COL = 'w-[180px] min-w-[180px]';

  const content = (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }} className={`flex flex-col h-full -mx-4 sm:-mx-6 md:-mx-8 -mt-2 ${theme.pageClass}`}>

        {/* ─── Top Bar: Location | Week Nav | Buttons ─── */}
        <div className={`px-4 sm:px-6 md:px-8 py-3.5 border-b sticky top-0 z-30 ${theme.topBarClass}`}>
          {/* Row 1: Location name + subtext */}
          <div className="flex items-center gap-2.5 mb-3">
            <button onClick={() => router.push(resolvedBackHref)}
              className={`flex items-center transition-colors ${theme.textSecondary} ${isDark ? 'hover:text-white' : 'hover:text-[#5E6D7A]'}`}
              style={{ fontWeight: 440 }}>
              <ChevronLeft size={16} />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center text-[14px]"
                style={{ background: `${loc.color}10` }}>
                {loc.emoji}
              </div>
              <div>
                <h1 className={`text-[18px] sm:text-[20px] tracking-[-0.02em] leading-none ${theme.textPrimary}`} style={{ fontWeight: 600 }}>
                  {loc.name}
                </h1>
                <p className={`text-[11px] mt-1 ${theme.textSecondary}`} style={{ fontWeight: 440 }}>
                  Weekly Scheduler
                </p>
              </div>
            </div>
          </div>

          {/* Row 2: Today + ‹ dates › + Buttons, horizontally aligned */}
          <div className="flex items-center justify-between gap-4">
            {/* Week navigation: Today button, then arrows around week dates */}
            <div className="flex items-center gap-2">
              <button onClick={() => setWeekOffset(0)}
                className={`text-[12px] px-2.5 py-1.5 rounded-lg transition-colors ${
                  weekOffset === 0 ? theme.todaySelectorClass : theme.daySelectorIdleClass
                }`} style={{ fontWeight: 500 }}>
                Today
              </button>
              <button onClick={() => setWeekOffset(w => w - 1)} className={`p-1 rounded-lg transition-colors ${theme.ghostButtonClass}`}>
                <ChevronLeft size={15} className={theme.textMuted} />
              </button>
              <span className={`text-[12px] hidden md:inline ${theme.textPrimary}`} style={{ fontWeight: 520 }}>
                {weekLabel}
              </span>
              <button onClick={() => setWeekOffset(w => w + 1)} className={`p-1 rounded-lg transition-colors ${theme.ghostButtonClass}`}>
                <ChevronRight size={15} className={theme.textMuted} />
              </button>
            </div>

            {/* Copy Schedule + Publish Week */}
            <div className="flex items-center gap-2">
              <button onClick={() => setShowCopyModal(true)}
                className={`hidden sm:flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12px] border hover:border-[#635BFF]/30 transition-all cursor-pointer ${theme.cardClass} ${theme.textMuted} ${theme.ghostButtonClass}`}
                style={{ fontWeight: 500 }}>
                <ClipboardCopy size={13} />
                <span className="hidden lg:inline">Copy Schedule</span>
                <span className="lg:hidden">Copy</span>
              </button>
              <motion.button whileTap={{ scale: 0.97 }}
                onClick={() => setShowPublishModal(true)}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12px] text-white cursor-pointer transition-all hover:shadow-[0_0_20px_rgba(99,91,255,0.3)]"
                style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
                <Zap size={13} />
                <span className="hidden lg:inline">Publish Week</span>
                <span className="lg:hidden">Publish</span>
              </motion.button>
            </div>
          </div>
        </div>

        {/* ─── Mobile Day Selector ─── */}
        <div className={`lg:hidden px-4 py-2 border-b flex gap-1 overflow-x-auto no-scrollbar ${theme.mobileDayBorderClass}`}>
          {DAYS.map((day, i) => (
            <button key={day} onClick={() => setMobileDay(i)}
              className={`flex flex-col items-center px-3 py-1.5 rounded-xl transition-all min-w-[44px] ${
                mobileDay === i ? theme.mobileSelectedDayClass
                  : isToday(weekDates[i]) ? theme.todaySelectorClass
                  : theme.daySelectorIdleClass
              }`}>
              <span className="text-[14px]" style={{ fontWeight: mobileDay === i ? 600 : 500 }}>{weekDates[i].getDate()}</span>
              <span className="text-[10px]" style={{ fontWeight: 480 }}>{day}</span>
            </button>
          ))}
        </div>

        {/* ─── Desktop Grid ─── */}
        <div className="flex-1 overflow-auto hidden lg:block">
          <div className="min-w-[900px]">
            {/* Sticky Header: Consolidated day + hours row */}
            <div className={`sticky top-0 z-20 border-b ${theme.stickyHeaderClass}`}>
              <div className="flex">
                {/* Left column: Week total */}
                <div className={`${EMP_COL} shrink-0 px-4 py-3 flex items-end`}>
                  <span className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 480 }}>
                    Week: {weekTotalHours}h
                  </span>
                </div>
                {/* Day columns */}
                {DAYS.map((day, i) => {
                  const dayHours = getDayTotalHours(i);
                  const today = isToday(weekDates[i]);
                  return (
                    <div key={day} className={`flex-1 border-l px-3 py-3 flex items-end justify-between ${theme.cellBorderClass} ${
                      today ? theme.todayHeaderClass : ''
                    }`}>
                      {/* Left-aligned: date + day name */}
                      <div>
                        <p className={`text-[24px] leading-none ${
                          today ? 'text-[#635BFF]' : theme.textPrimary
                        }`} style={{ fontWeight: today ? 620 : 540 }}>
                          {weekDates[i].getDate()}
                        </p>
                        <p className={`text-[10px] uppercase tracking-[0.04em] mt-1 ${theme.textSecondary}`} style={{ fontWeight: 460 }}>
                          {day}
                        </p>
                      </div>
                      {/* Right-aligned: hours */}
                      <span className={`text-[11px] ${theme.textSecondary}`}
                        style={{ fontWeight: 440 }}>
                        {dayHours}h
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Role Groups */}
            {filteredRoles.map(role => {
              const roleEmps = employees.filter(e => e.role === role);
              const isCollapsed = collapsedRoles.has(role);
              const roleColor = roleColors[role] || '#635BFF';

              return (
                <div key={role}>
                  {/* Role Header Row */}
                  <div className={`flex border-b ${theme.roleBandClass}`}>
                    <div className={`${EMP_COL} shrink-0 px-4 py-2 flex items-center gap-2`}>
                      <button onClick={() => toggleRoleCollapse(role)} className="flex items-center gap-2 group">
                        <motion.div animate={{ rotate: isCollapsed ? -90 : 0 }} transition={{ duration: 0.2 }}>
                          <ChevronDown size={12} className={`${theme.textSecondary} transition-colors ${isDark ? 'group-hover:text-white' : 'group-hover:text-[#5E6D7A]'}`} />
                        </motion.div>
                        <div className="w-2 h-2 rounded-full" style={{ background: roleColor }} />
                        <span className={`text-[11px] uppercase tracking-[0.03em] ${theme.textPrimary}`} style={{ fontWeight: 580 }}>
                          {role}
                        </span>
                        <span className={`text-[10px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                          {roleEmps.length}
                        </span>
                      </button>
                    </div>
                    {DAYS.map((day, i) => (
                      <div key={day} className={`flex-1 border-l ${theme.cellBorderClass} ${isToday(weekDates[i]) ? theme.todayRoleBandClass : ''}`} />
                    ))}
                  </div>

                  {/* Employee Rows */}
                  <AnimatePresence>
                    {!isCollapsed && roleEmps.map(emp => {
                      const empWeekHours = getEmployeeWeekHours(emp.id);
                      return (
                        <motion.div key={emp.id}
                          initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.2 }}
                          className={`flex border-b transition-colors ${theme.rowClass}`}>
                          {/* Employee Info */}
                          <div className={`${EMP_COL} shrink-0 px-4 py-3 flex items-center gap-2.5`}>
                            <img src={emp.avatar} alt={emp.name}
                              className={`w-7 h-7 rounded-full object-cover shrink-0 ring-1 ${isDark ? 'ring-white/[0.08]' : 'ring-[#E5E7EB]'}`} />
                            <div className="min-w-0">
                              <p className={`text-[12px] truncate ${theme.textPrimary}`} style={{ fontWeight: 500 }}>
                                {emp.name}
                              </p>
                              <p className={`text-[10px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                                {empWeekHours}h this week
                              </p>
                            </div>
                          </div>

                          {/* Day cells */}
                          {DAYS.map((_day, dayIdx) => {
                            const cellShifts = getShiftsForCell(emp.id, dayIdx);
                            const isMulti = cellShifts.length > 1;
                            return (
                              <DroppableCell key={dayIdx} employeeId={emp.id} day={dayIdx}
                                onDrop={moveShift}
                                onClickEmpty={() => setCreatingAt({ employeeId: emp.id, day: dayIdx, role: emp.role })}
                                isToday={isToday(weekDates[dayIdx])}
                                dark={isDark}>
                                {cellShifts.length > 0 ? (
                                  cellShifts.map(shift => (
                                    <DraggableShiftChip key={shift.id} shift={shift} isMulti={isMulti}
                                      dark={isDark}
                                      onEdit={() => setEditingShift(shift)}
                                      onDelete={() => deleteShift(shift.id)} />
                                  ))
                                ) : null}
                              </DroppableCell>
                            );
                          })}
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        </div>

        {/* ─── Mobile View ─── */}
        <div className="flex-1 overflow-auto lg:hidden">
          <div className="px-4 py-3">
            <div className="flex items-center justify-between mb-3">
                <h2 className={`text-[15px] ${theme.textPrimary}`} style={{ fontWeight: 580 }}>
                  {FULL_DAYS[mobileDay]}, {weekDates[mobileDay]?.toLocaleString('default', { month: 'short' })} {weekDates[mobileDay]?.getDate()}
                </h2>
                <span className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 440 }}>
                  {getDayTotalHours(mobileDay)}h
                </span>
              </div>

            {filteredRoles.map(role => {
              const roleEmps = employees.filter(e => e.role === role);
              const roleColor = roleColors[role] || '#635BFF';

              return (
                <div key={role} className="mb-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-2 h-2 rounded-full" style={{ background: roleColor }} />
                    <span className={`text-[11px] uppercase tracking-[0.03em] ${theme.textPrimary}`} style={{ fontWeight: 580 }}>{role}</span>
                    <span className={`text-[10px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>{roleEmps.length}</span>
                  </div>

                  <div className="space-y-1.5">
                    {roleEmps.map(emp => {
                      const cellShifts = getShiftsForCell(emp.id, mobileDay);
                      const empWeekHours = getEmployeeWeekHours(emp.id);

                      return (
                        <div key={emp.id} className={`flex items-center gap-3 p-2.5 rounded-xl border ${theme.cardClass}`}>
                          <img src={emp.avatar} alt={emp.name}
                            className={`w-8 h-8 rounded-full object-cover shrink-0 ring-1 ${isDark ? 'ring-white/[0.08]' : 'ring-[#E5E7EB]'}`} />
                          <div className="flex-1 min-w-0">
                            <p className={`text-[12px] truncate ${theme.textPrimary}`} style={{ fontWeight: 500 }}>{emp.name}</p>
                            <p className={`text-[10px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>{empWeekHours}h this week</p>
                          </div>
                          {cellShifts.length > 0 ? (
                            <div className="flex flex-col gap-1">
                              {cellShifts.map(shift => {
                                const desc = getShiftDescriptor(shift.startHour, shift.endHour);
                                const DescIcon = desc.icon;
                                const dur = shiftDuration(shift);
                                return (
                                  <button key={shift.id} onClick={() => setEditingShift(shift)}
                                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-all"
                                    style={{ background: `${shift.color}10` }}>
                                    <DescIcon size={10} style={{ color: shift.color }} />
                                    <span className="text-[10px]" style={{ fontWeight: 520, color: shift.color }}>{desc.label}</span>
                                    <span className={`text-[9px] ${theme.textSecondary}`} style={{ fontWeight: 400 }}>{dur}h</span>
                                  </button>
                                );
                              })}
                            </div>
                          ) : (
                            <button onClick={() => setCreatingAt({ employeeId: emp.id, day: mobileDay, role: emp.role })}
                              className={`p-1.5 rounded-lg transition-colors border border-dashed ${isDark ? 'border-white/[0.08] hover:bg-white/[0.04]' : 'border-[#E5E7EB] hover:bg-[#F7F8FA]'}`}>
                              <Plus size={14} className="text-[#C1CED8]" />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ─── Quick Create Modal ─── */}
        <AnimatePresence>
          {creatingAt && (
            <QuickCreateModal
              dark={isDark}
              employeeName={employees.find(e => e.id === creatingAt.employeeId)?.name || ''}
              dayLabel={`${FULL_DAYS[creatingAt.day]}, ${weekDates[creatingAt.day]?.toLocaleString('default', { month: 'short' })} ${weekDates[creatingAt.day]?.getDate()}`}
              role={creatingAt.role}
              onClose={() => setCreatingAt(null)}
              onCreate={(start, end) => {
                setShifts(prev => [...prev, {
                  id: uid(), employeeId: creatingAt.employeeId, day: creatingAt.day,
                  startHour: start, endHour: end, role: creatingAt.role,
                  color: roleColors[creatingAt.role] || '#635BFF',
                }]);
                setCreatingAt(null);
              }}
            />
          )}
        </AnimatePresence>

        {/* ─── Edit Shift Modal ─── */}
        <AnimatePresence>
          {editingShift && (
            <EditShiftModal
              dark={isDark}
              shift={editingShift}
              employeeName={employees.find(e => e.id === editingShift.employeeId)?.name || 'Unassigned'}
              onClose={() => setEditingShift(null)}
              onSave={updateShift}
              onDelete={() => { deleteShift(editingShift.id); setEditingShift(null); }}
            />
          )}
        </AnimatePresence>

        {/* ─── Copy Schedule Modal ─── */}
        <AnimatePresence>
          {showCopyModal && (
            <CopyScheduleModal
              dark={isDark}
              currentWeek={weekLabel}
              shiftsCount={shifts.length}
              employeesCount={new Set(shifts.map(s => s.employeeId)).size}
              onClose={() => setShowCopyModal(false)}
              onCopy={copySchedule}
              currentWeekOffset={weekOffset}
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {showPublishModal && (
            <PublishWeekModal
              dark={isDark}
              weekLabel={weekLabel}
              shifts={shifts}
              employees={employees}
              onClose={() => setShowPublishModal(false)}
              onComplete={() => {
                setShowPublishModal(false);
                setShowPublishToast(true);
                setTimeout(() => setShowPublishToast(false), 3000);
              }}
            />
          )}
        </AnimatePresence>

        {/* ─── Toasts ─── */}
        <AnimatePresence>
          {showPublishToast && (
            <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 30 }}
              className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-5 py-3.5 rounded-2xl shadow-2xl ${theme.toastClass}`}>
              <div className="w-7 h-7 rounded-full bg-[#00B893]/20 flex items-center justify-center">
                <Check size={14} className="text-[#00B893]" />
              </div>
              <div>
                <p className="text-[12px] text-white" style={{ fontWeight: 520 }}>Schedule published!</p>
                <p className={`text-[10px] mt-0.5 ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                  {shifts.length} shifts sent to {new Set(shifts.map(s => s.employeeId)).size} staff
                </p>
              </div>
              <button onClick={() => setShowPublishToast(false)} className="p-1 rounded-lg hover:bg-white/10 transition-colors ml-2">
                <X size={12} className={theme.textSecondary} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
        <AnimatePresence>
          {showCopyToast && (
            <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 30 }}
              className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-5 py-3.5 rounded-2xl shadow-2xl ${theme.toastClass}`}>
              <div className="w-7 h-7 rounded-full bg-[#635BFF]/20 flex items-center justify-center">
                <ClipboardCopy size={14} className="text-[#635BFF]" />
              </div>
              <div>
                <p className="text-[12px] text-white" style={{ fontWeight: 520 }}>Schedule copied!</p>
                <p className={`text-[10px] mt-0.5 ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                  {shifts.length} shifts duplicated to next week
                </p>
              </div>
              <button onClick={() => setShowCopyToast(false)} className="p-1 rounded-lg hover:bg-white/10 transition-colors ml-2">
                <X size={12} className={theme.textSecondary} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
    </motion.div>
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav={loc.name}>{content}</DashboardShell>;
}

export default function Scheduler(props: SchedulerProps) {
  return (
    <DndProvider backend={HTML5Backend}>
      <SchedulerContent {...props} />
    </DndProvider>
  );
}

/* ─── Quick Create Modal ─── */
function QuickCreateModal({ employeeName, dayLabel, role, onClose, onCreate, dark = false }: {
  employeeName: string; dayLabel: string; role: string;
  onClose: () => void; onCreate: (start: number, end: number) => void; dark?: boolean;
}) {
  const [startHour, setStartHour] = useState(7);
  const [endHour, setEndHour] = useState(15);
  const roleColor = roleColors[role] || '#635BFF';
  const hourOptions = HOURS.map(h => ({ label: formatHour(h), value: String(h) }));
  const theme = getSchedulerTheme(dark);

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90vw] max-w-[380px] rounded-2xl shadow-2xl overflow-hidden ${theme.modalClass}`}>
        <div className={`px-5 py-4 border-b flex items-center justify-between ${theme.modalBorderClass}`}>
          <div>
            <h3 className={`text-[15px] ${theme.textPrimary}`} style={{ fontWeight: 600 }}>New Shift</h3>
            <p className={`text-[11px] mt-0.5 ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
              {employeeName} · {dayLabel}
            </p>
          </div>
          <button onClick={onClose} className={`p-1.5 rounded-lg transition-colors ${theme.ghostButtonClass}`}>
            <X size={16} className={theme.textSecondary} />
          </button>
        </div>
        <div className="px-5 pt-4 pb-1">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg w-fit" style={{ background: `${roleColor}10` }}>
            <div className="w-2 h-2 rounded-full" style={{ background: roleColor }} />
            <span className="text-[11px]" style={{ fontWeight: 520, color: roleColor }}>{role}</span>
          </div>
        </div>
        <div className="px-5 pt-3 pb-2">
          <p className={`text-[10px] uppercase tracking-[0.05em] mb-2 ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Quick Fill</p>
          <div className="grid grid-cols-4 gap-2">
            {shiftTemplates.map(t => {
              const resolvedEnd = t.end > t.start ? t.end : 23;
              const isActive = startHour === t.start && endHour === resolvedEnd;
              return (
                <button key={t.label}
                  onClick={() => { setStartHour(t.start); setEndHour(resolvedEnd); }}
                  className={`flex flex-col items-center gap-1 py-2 rounded-xl border transition-all ${
                    isActive
                      ? 'border-[#635BFF]/30 bg-[#635BFF]/[0.08]'
                      : dark
                        ? 'border-white/[0.08] hover:border-[#635BFF]/20 hover:bg-[#635BFF]/[0.04]'
                        : 'border-[#E5E7EB] hover:border-[#635BFF]/20 hover:bg-[#635BFF]/[0.02]'
                  }`}>
                  <t.icon size={13} className={isActive ? 'text-[#635BFF]' : dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'} />
                  <span className={`text-[10px] ${isActive ? 'text-[#635BFF]' : dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'}`} style={{ fontWeight: isActive ? 540 : 480 }}>{t.label}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="px-5 py-3">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className={`text-[10px] uppercase tracking-[0.05em] block mb-1.5 ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Start</label>
              <InlineSelect value={formatHour(startHour)} onChange={v => setStartHour(Number(v))} options={hourOptions} dark={dark} />
            </div>
            <div className="flex-1">
              <label className={`text-[10px] uppercase tracking-[0.05em] block mb-1.5 ${theme.textSecondary}`} style={{ fontWeight: 500 }}>End</label>
              <InlineSelect value={formatHour(endHour)} onChange={v => setEndHour(Number(v))} options={hourOptions} dark={dark} />
            </div>
          </div>
        </div>
        <div className={`px-5 py-4 border-t flex gap-2 ${theme.modalBorderClass}`}>
          <button onClick={onClose}
            className={`flex-1 py-2.5 rounded-xl border text-[12px] transition-colors ${dark ? 'border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]' : 'border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]'}`}
            style={{ fontWeight: 500 }}>Cancel</button>
          <motion.button whileTap={{ scale: 0.97 }}
            onClick={() => onCreate(startHour, endHour)}
            className="flex-1 py-2.5 rounded-xl text-[12px] text-white transition-all hover:shadow-[0_0_16px_rgba(99,91,255,0.3)]"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
            Create Shift
          </motion.button>
        </div>
      </motion.div>
    </>
  );
}

/* ─── Edit Shift Modal ─── */
function EditShiftModal({ shift, employeeName, onClose, onSave, onDelete, dark = false }: {
  shift: Shift; employeeName: string; onClose: () => void; onSave: (s: Shift) => void; onDelete: () => void; dark?: boolean;
}) {
  const [startHour, setStartHour] = useState(shift.startHour);
  const [endHour, setEndHour] = useState(shift.endHour);
  const roleColor = roleColors[shift.role] || shift.color;
  const descriptor = getShiftDescriptor(startHour, endHour);
  const hourOptions = HOURS.map(h => ({ label: formatHour(h), value: String(h) }));
  const theme = getSchedulerTheme(dark);

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90vw] max-w-[380px] rounded-2xl shadow-2xl overflow-hidden ${theme.modalClass}`}>
        <div className={`px-5 py-4 border-b flex items-center justify-between ${theme.modalBorderClass}`}>
          <div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ background: roleColor }} />
              <h3 className={`text-[15px] ${theme.textPrimary}`} style={{ fontWeight: 600 }}>Edit Shift</h3>
            </div>
            <p className={`text-[11px] mt-1 ml-5 ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
              {employeeName} · {shift.role}
            </p>
          </div>
          <button onClick={onClose} className={`p-1.5 rounded-lg transition-colors ${theme.ghostButtonClass}`}>
            <X size={16} className={theme.textSecondary} />
          </button>
        </div>
        <div className="px-5 pt-4 pb-1 flex items-center gap-2">
          <descriptor.icon size={14} style={{ color: roleColor }} />
          <span className="text-[12px]" style={{ fontWeight: 520, color: roleColor }}>{descriptor.label} Shift</span>
          <span className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
            · {endHour > startHour ? endHour - startHour : 24 - startHour + endHour}h
          </span>
        </div>
        <div className="px-5 pt-3 pb-2">
          <div className="grid grid-cols-4 gap-2">
            {shiftTemplates.map(t => {
              const resolvedEnd = t.end > t.start ? t.end : 23;
              const isActive = startHour === t.start && endHour === resolvedEnd;
              return (
                <button key={t.label}
                  onClick={() => { setStartHour(t.start); setEndHour(resolvedEnd); }}
                  className={`flex flex-col items-center gap-1 py-2 rounded-xl border transition-all ${
                    isActive
                      ? 'border-[#635BFF]/30 bg-[#635BFF]/[0.08]'
                      : dark
                        ? 'border-white/[0.08] hover:border-[#635BFF]/20 hover:bg-[#635BFF]/[0.04]'
                        : 'border-[#E5E7EB] hover:border-[#635BFF]/20 hover:bg-[#635BFF]/[0.02]'
                  }`}>
                  <t.icon size={13} className={isActive ? 'text-[#635BFF]' : dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'} />
                  <span className={`text-[10px] ${isActive ? 'text-[#635BFF]' : dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'}`} style={{ fontWeight: isActive ? 540 : 480 }}>{t.label}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="px-5 py-3">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className={`text-[10px] uppercase tracking-[0.05em] block mb-1.5 ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Start</label>
              <InlineSelect value={formatHour(startHour)} onChange={v => setStartHour(Number(v))} options={hourOptions} dark={dark} />
            </div>
            <div className="flex-1">
              <label className={`text-[10px] uppercase tracking-[0.05em] block mb-1.5 ${theme.textSecondary}`} style={{ fontWeight: 500 }}>End</label>
              <InlineSelect value={formatHour(endHour)} onChange={v => setEndHour(Number(v))} options={hourOptions} dark={dark} />
            </div>
          </div>
        </div>
        <div className={`px-5 py-4 border-t flex items-center justify-between ${theme.modalBorderClass}`}>
          <button onClick={onDelete}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-[12px] transition-colors ${dark ? 'border-red-400/25 text-red-300 hover:bg-red-500/10' : 'border-red-200 text-red-500 hover:bg-red-50'}`}
            style={{ fontWeight: 500 }}>
            <Trash2 size={12} /> Remove
          </button>
          <div className="flex gap-2">
            <button onClick={onClose}
              className={`px-4 py-2 rounded-xl border text-[12px] transition-colors ${dark ? 'border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]' : 'border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]'}`}
              style={{ fontWeight: 500 }}>Cancel</button>
            <motion.button whileTap={{ scale: 0.97 }}
              onClick={() => onSave({ ...shift, startHour, endHour })}
              className="px-4 py-2 rounded-xl text-[12px] text-white transition-all hover:shadow-[0_0_16px_rgba(99,91,255,0.3)]"
              style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
              Save
            </motion.button>
          </div>
        </div>
      </motion.div>
    </>
  );
}

/* ─── Copy Schedule Modal ─── */
function CopyScheduleModal({ currentWeek, shiftsCount, employeesCount, onClose, onCopy, currentWeekOffset, dark = false }: {
  currentWeek: string; shiftsCount: number; employeesCount: number;
  onClose: () => void; onCopy: (targetWeek: number) => void; currentWeekOffset: number; dark?: boolean;
}) {
  const [selectedWeek, setSelectedWeek] = useState(currentWeekOffset + 1);
  const theme = getSchedulerTheme(dark);

  const getWeekLabel = (offset: number) => {
    const dates = getWeekDates(offset);
    const s = dates[0];
    const e = dates[6];
    const sm = s.toLocaleString('default', { month: 'short' });
    const em = e.toLocaleString('default', { month: 'short' });
    if (sm === em) return `${sm} ${s.getDate()} – ${e.getDate()}, ${s.getFullYear()}`;
    return `${sm} ${s.getDate()} – ${em} ${e.getDate()}, ${s.getFullYear()}`;
  };

  const weekOptions = [
    { offset: currentWeekOffset + 1, label: 'Next Week', sublabel: getWeekLabel(currentWeekOffset + 1) },
    { offset: currentWeekOffset + 2, label: 'Two Weeks Out', sublabel: getWeekLabel(currentWeekOffset + 2) },
    { offset: currentWeekOffset + 3, label: 'Three Weeks Out', sublabel: getWeekLabel(currentWeekOffset + 3) },
    { offset: currentWeekOffset + 4, label: 'Four Weeks Out', sublabel: getWeekLabel(currentWeekOffset + 4) },
  ];

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90vw] max-w-[480px] rounded-2xl shadow-2xl overflow-hidden ${theme.modalClass}`}>
        
        {/* Header */}
        <div className={`px-6 py-5 border-b flex items-center justify-between ${theme.modalBorderClass}`}>
          <div>
            <h3 className={`text-[17px] ${theme.textPrimary}`} style={{ fontWeight: 600 }}>Copy Schedule</h3>
            <p className={`text-[11px] mt-1 ${theme.textSecondary}`} style={{ fontWeight: 440 }}>
              Duplicate {shiftsCount} shifts for {employeesCount} employees
            </p>
          </div>
          <button onClick={onClose} className={`p-1.5 rounded-lg transition-colors ${theme.ghostButtonClass}`}>
            <X size={18} className={theme.textSecondary} />
          </button>
        </div>

        {/* Current Week Info */}
        <div className="px-6 pt-5 pb-3">
          <div className="flex items-center gap-2.5 mb-1">
            <div className="w-7 h-7 rounded-lg bg-[#635BFF]/[0.08] flex items-center justify-center">
              <ClipboardCopy size={13} className="text-[#635BFF]" />
            </div>
            <div>
              <p className={`text-[11px] uppercase tracking-[0.05em] ${theme.textSecondary}`} style={{ fontWeight: 500 }}>
                Copying from
              </p>
              <p className={`text-[13px] mt-0.5 ${theme.textPrimary}`} style={{ fontWeight: 520 }}>
                {currentWeek}
              </p>
            </div>
          </div>
        </div>

        {/* Week Selection */}
        <div className="px-6 pb-4">
          <p className={`text-[11px] uppercase tracking-[0.05em] mb-3 ${theme.textSecondary}`} style={{ fontWeight: 500 }}>
            Copy to
          </p>
          <div className="space-y-2">
            {weekOptions.map(opt => (
              <button
                key={opt.offset}
                onClick={() => setSelectedWeek(opt.offset)}
                className={`w-full text-left px-4 py-3.5 rounded-xl border transition-all ${
                  selectedWeek === opt.offset
                    ? 'border-[#635BFF]/30 bg-[#635BFF]/[0.08] shadow-sm'
                    : dark
                      ? 'border-white/[0.08] hover:border-[#635BFF]/20 hover:bg-white/[0.04]'
                      : 'border-[#E5E7EB] hover:border-[#635BFF]/20 hover:bg-[#F7F8FA]'
                }`}>
                <div className="flex items-center justify-between">
                  <div>
                    <p className={`text-[13px] ${
                      selectedWeek === opt.offset ? 'text-[#635BFF]' : theme.textPrimary
                    }`} style={{ fontWeight: 540 }}>
                      {opt.label}
                    </p>
                    <p className={`text-[11px] mt-0.5 ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                      {opt.sublabel}
                    </p>
                  </div>
                  {selectedWeek === opt.offset && (
                    <div className="w-5 h-5 rounded-full bg-[#635BFF] flex items-center justify-center">
                      <Check size={12} className="text-white" />
                    </div>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Footer Actions */}
        <div className={`px-6 py-4 border-t flex gap-2.5 ${theme.modalBorderClass}`}>
          <button onClick={onClose}
            className={`flex-1 py-2.5 rounded-xl border text-[12px] transition-colors ${dark ? 'border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]' : 'border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]'}`}
            style={{ fontWeight: 500 }}>
            Cancel
          </button>
          <motion.button 
            whileTap={{ scale: 0.97 }}
            onClick={() => onCopy(selectedWeek)}
            className="flex-1 py-2.5 rounded-xl text-[12px] text-white transition-all hover:shadow-[0_0_20px_rgba(99,91,255,0.3)] flex items-center justify-center gap-2"
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
            <ClipboardCopy size={13} />
            Copy Schedule
          </motion.button>
        </div>
      </motion.div>
    </>
  );
}
