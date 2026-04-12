"use client";

import { useState, useRef, useMemo, useCallback, useEffect, type TouchEvent } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { useRouter } from 'next/navigation';
import {
  Copy,
  ChevronLeft,
  ChevronRight,
  Plus,
  X,
  Trash2,
  Check,
  ChevronDown,
  Zap,
  Sun,
  CloudMoon,
  Sunrise,
  Sunset,
  ClipboardCopy,
  Edit3,
  Settings,
  UserMinus,
  UserPlus,
  AlertTriangle,
  GripVertical,
  Info,
} from 'lucide-react';
import { useAppWorkspaceRefresh } from '@/components/app-workspace';
import { useResolvedAppAppearance } from '@/components/app-session-gate';
import { FloatingDropdown } from '@/components/floating-dropdown';
import {
  getBusinessLocation,
  getLocationDeleteReadiness,
  getLocationRoles,
  listBusinessLocations,
  listBusinessRoles,
  replaceLocationRoles,
  type BusinessLocation,
  type BusinessRole,
  type LocationRoleAssignment,
} from '@/lib/api/businesses';
import {
  assignShift as assignWorkspaceShift,
  createShift as createWorkspaceShift,
  deleteLocation as deleteWorkspaceLocation,
  deleteShift as deleteWorkspaceShift,
  getLocationBoard,
  getLocationShiftDefaults,
  ShiftAssignmentConflictError,
  updateLocationShiftDefaults,
  updateShift as updateWorkspaceShift,
  type ShiftCreatePayload,
  type ShiftAssignmentMutationResponse,
  type ShiftDefault,
  type ShiftDefaultKey,
  type LocationShiftDefaults,
  type WorkspaceBoard,
  type WorkspaceLocation,
} from '@/lib/api/workspace';
import {
  listEmployees,
  updateEmployee,
  type EmployeeSummary,
} from '@/lib/api/workforce';
import {
  buildDashboardLocationBasePathFromAny,
  buildSchedulerBasePathFromAny,
  buildSchedulerLocationEditPathFromAny,
} from '@/lib/dashboard-paths';
import { useSetLocationEntryMode } from '@/components/location-entry-provider';
import DashboardShell from './DashboardShell';
import {
  formatLocationSaveSummary,
  LocationRoleEditor,
  type LocationDeleteState,
  type LocationRoleEditorFeedback,
  type LocationRoleEditorSaveSummary,
} from './LocationRoleEditor';
import {
  buildEmployeeLocationAssignments,
  buildInheritedLocationRoleIds,
  employeeAssignedHere,
  mergeUpdatedEmployees,
} from './location-employee-utils';
import { getLocationReference } from './location-role-reference';
import { PublishWeekModal } from './PublishWeekModal';
import {
  SchedulerEmployeeEnrollmentModal,
} from './LocationEmployeeActions';
import {
  getShiftDefaultColor,
  getShiftDefaultIcon,
  normalizeShiftDefaults,
  resolveShiftLabel,
  SHIFT_DEFAULT_FALLBACKS,
} from './shift-defaults';

/* ─── Types ─── */
interface Employee { id: string; name: string; avatar: string; role: string; }
interface Shift {
  id: string;
  employeeId: string | null;
  displayEmployeeId: string | null;
  displayEmployeeName?: string | null;
  currentAssignmentId?: string | null;
  roleId: string;
  day: number;
  startHour: number;
  endHour: number;
  role: string;
  color: string;
  presetKey?: ShiftDefaultKey | null;
  presetLabel?: string | null;
}

const DRAG_TYPE = 'SHIFT';
interface DragItem { type: string; shiftId: string; }
/* ─── Role colors ─── */
const roleColors: Record<string, string> = {
  'RN': '#635BFF', 'LPN': '#8B5CF6', 'CNA': '#00B893', 'NP': '#3B82F6', 'Medical Assistant': '#EC4899',
};
const roleOrder = ['RN', 'LPN', 'CNA', 'NP', 'Medical Assistant'];
const ROLE_COLOR_PALETTE = ['#635BFF', '#8B5CF6', '#00B893', '#3B82F6', '#EC4899', '#F59E0B', '#14B8A6'];
const OPEN_SHIFT_COLOR = '#E5484D';

function employeeInitials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('') || 'E';
}

function buildAvatarDataUri(name: string) {
  const initials = employeeInitials(name);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80"><rect width="80" height="80" rx="40" fill="#EEF0FF"/><text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="28" font-weight="600" fill="#635BFF">${initials}</text></svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

/* ─── Helpers ─── */
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const FULL_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const TIME_VALUES = Array.from({ length: 48 }, (_, i) => i / 2);

function formatHour(h: number) {
  const normalized = ((h % 24) + 24) % 24;
  const wholeHours = Math.floor(normalized);
  const minutes = Math.round((normalized - wholeHours) * 60);
  const hour12 = wholeHours === 0 ? 12 : wholeHours > 12 ? wholeHours - 12 : wholeHours;
  const suffix = wholeHours < 12 ? 'AM' : 'PM';
  if (minutes === 0) {
    return `${hour12} ${suffix}`;
  }
  return `${hour12}:${String(minutes).padStart(2, '0')} ${suffix}`;
}

function shiftDuration(s: Shift) {
  return s.endHour > s.startHour ? s.endHour - s.startHour : 24 - s.startHour + s.endHour;
}

function getShiftDescriptor(start: number, end: number): { label: string; icon: typeof Sunrise } {
  const mid = end > start ? (start + end) / 2 : (start + (24 - start + end)) / 2;
  if (mid < 12) return { label: 'Morning', icon: Sunrise };
  if (mid < 16) return { label: 'Afternoon', icon: Sun };
  if (mid < 20) return { label: 'Evening', icon: Sunset };
  return { label: 'Night', icon: CloudMoon };
}

function getWeekDates(offset: number) {
  const today = new Date();
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7) + offset * 7);
  return Array.from({ length: 7 }, (_, i) => { const d = new Date(monday); d.setDate(monday.getDate() + i); return d; });
}

function parseDateKey(dateKey: string) {
  const [year, month, day] = dateKey.split('-').map(Number);
  return { year, month, day };
}

function formatDateKey(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatUtcDateKey(value: Date) {
  const year = value.getUTCFullYear();
  const month = String(value.getUTCMonth() + 1).padStart(2, '0');
  const day = String(value.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function addDaysToDateKey(dateKey: string, days: number) {
  const { year, month, day } = parseDateKey(dateKey);
  return formatUtcDateKey(new Date(Date.UTC(year, month - 1, day + days)));
}

function buildWeekDatesFromWeekStart(weekStartDate: string) {
  const { year, month, day } = parseDateKey(weekStartDate);
  return Array.from({ length: 7 }, (_, index) => new Date(year, month - 1, day + index));
}

function mondayDateKeyFor(timeZone: string, offset: number) {
  const today = getZonedParts(new Date(), timeZone);
  const weekday = new Date(Date.UTC(today.year, today.month - 1, today.day)).getUTCDay();
  const mondayOffset = (weekday + 6) % 7;
  return addDaysToDateKey(today.dateKey, offset * 7 - mondayOffset);
}

function dayDifference(startDateKey: string, endDateKey: string) {
  const start = parseDateKey(startDateKey);
  const end = parseDateKey(endDateKey);
  const startUtc = Date.UTC(start.year, start.month - 1, start.day);
  const endUtc = Date.UTC(end.year, end.month - 1, end.day);
  return Math.round((endUtc - startUtc) / 86_400_000);
}

function getZonedParts(value: Date | string, timeZone: string) {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const parts = formatter.formatToParts(typeof value === 'string' ? new Date(value) : value);
  const lookup = new Map(parts.map((part) => [part.type, part.value]));
  const year = Number(lookup.get('year'));
  const month = Number(lookup.get('month'));
  const day = Number(lookup.get('day'));
  const hour = Number(lookup.get('hour'));
  const minute = Number(lookup.get('minute'));
  return {
    year,
    month,
    day,
    hour,
    minute,
    dateKey: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
  };
}

function zonedDateTimeToIso(dateKey: string, hourValue: number, timeZone: string) {
  const { year, month, day } = parseDateKey(dateKey);
  const hours = Math.floor(hourValue);
  const minutes = Math.round((hourValue - hours) * 60);
  let guess = new Date(Date.UTC(year, month - 1, day, hours, minutes, 0, 0));

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const actual = getZonedParts(guess, timeZone);
    const desiredUtc = Date.UTC(year, month - 1, day, hours, minutes);
    const actualUtc = Date.UTC(
      actual.year,
      actual.month - 1,
      actual.day,
      actual.hour,
      actual.minute,
    );
    const diffMinutes = (desiredUtc - actualUtc) / 60_000;
    if (diffMinutes === 0) {
      break;
    }
    guess = new Date(guess.getTime() + diffMinutes * 60_000);
  }

  return guess.toISOString();
}

function buildShiftPayload(
  location: WorkspaceLocation,
  roleId: string,
  dateKey: string,
  startHour: number,
  endHour: number,
): ShiftCreatePayload {
  return {
    location_id: location.location_id,
    role_id: roleId,
    timezone: location.timezone,
    starts_at: zonedDateTimeToIso(dateKey, startHour, location.timezone),
    ends_at: zonedDateTimeToIso(dateKey, endHour > startHour ? endHour : endHour + 24, location.timezone),
    seats_requested: 1,
    requires_manager_approval: false,
    premium_cents: 0,
    source_system: 'backfill_native',
  };
}

function roleColor(roleName: string) {
  if (roleColors[roleName]) {
    return roleColors[roleName];
  }
  const hash = Array.from(roleName).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return ROLE_COLOR_PALETTE[hash % ROLE_COLOR_PALETTE.length];
}

function roleSortValue(roleName: string) {
  const matchIndex = roleOrder.indexOf(roleName);
  if (matchIndex >= 0) {
    return matchIndex;
  }
  return roleOrder.length;
}

function boardWorkerToSchedulerEmployee(
  employee: EmployeeSummary,
  worker: WorkspaceBoard['workers'][number] | null,
): Employee {
  return {
    id: employee.id,
    name: employee.full_name,
    avatar: buildAvatarDataUri(employee.full_name),
    role:
      worker?.role_names[0]
      ?? employee.primary_role_name
      ?? employee.role_names[0]
      ?? 'Unassigned',
  };
}

function inferShiftPreset(
  startHour: number,
  endHour: number,
  shiftDefaults: ShiftDefault[],
): Pick<Shift, 'presetKey' | 'presetLabel'> {
  const matched = shiftDefaults.find(
    (preset) => preset.start_hour === startHour && preset.end_hour === endHour,
  );
  if (!matched) {
    return { presetKey: null, presetLabel: null };
  }
  return {
    presetKey: matched.key,
    presetLabel: matched.label,
  };
}

function boardShiftToSchedulerShift(
  shift: WorkspaceBoard['shifts'][number],
  board: WorkspaceBoard,
  shiftDefaults: ShiftDefault[],
): Shift | null {
  const startsAt = getZonedParts(shift.starts_at, board.timezone);
  const endsAt = getZonedParts(shift.ends_at, board.timezone);
  const day = dayDifference(board.week_start_date, startsAt.dateKey);
  if (day < 0 || day > 6) {
    return null;
  }
  const startHour = startsAt.hour + startsAt.minute / 60;
  const crossesIntoNextDay = dayDifference(startsAt.dateKey, endsAt.dateKey) > 0;
  const endHourBase = endsAt.hour + endsAt.minute / 60;
  const endHour = crossesIntoNextDay && endHourBase <= startHour ? endHourBase + 24 : endHourBase;
  const preset = inferShiftPreset(startHour, endHour, shiftDefaults);
  return {
    id: shift.shift_id,
    employeeId: shift.current_assignment?.employee_id ?? null,
    displayEmployeeId:
      shift.current_assignment?.employee_id ??
      shift.last_assignment?.employee_id ??
      null,
    displayEmployeeName:
      shift.current_assignment?.employee_name ??
      shift.last_assignment?.employee_name ??
      null,
    currentAssignmentId: shift.current_assignment?.assignment_id ?? null,
    roleId: shift.role_id,
    day,
    startHour,
    endHour,
    role: shift.role_name,
    color: roleColor(shift.role_name),
    presetKey: preset.presetKey,
    presetLabel: preset.presetLabel,
  };
}

function isToday(date: Date) {
  const t = new Date();
  return date.getDate() === t.getDate() && date.getMonth() === t.getMonth() && date.getFullYear() === t.getFullYear();
}

function adaptWorkspaceLocation(location: WorkspaceLocation): BusinessLocation {
  return {
    id: location.location_id,
    business_id: location.business_id,
    name: location.location_name,
    display_name: location.location_display_name,
    slug: location.location_slug,
    address_line_1: location.address_line_1 ?? null,
    address_line_2: null,
    locality: location.locality ?? null,
    region: location.region ?? null,
    postal_code: location.postal_code ?? null,
    country_code: location.country_code,
    timezone: location.timezone,
    latitude: null,
    longitude: null,
    google_place_id: location.google_place_id ?? null,
    google_place_metadata: {},
    is_active: true,
    settings: {},
    created_at: '',
    updated_at: '',
  };
}

function getSchedulerTheme(isDark: boolean) {
  return {
    pageClass: isDark ? 'bg-[#081A2C]' : 'bg-[#F7F8FA]',
    topBarClass: isDark
      ? 'border-white/[0.08] bg-[#0B2239]/88 backdrop-blur-xl'
      : 'border-[#F0F0F5] bg-white/80 backdrop-blur-sm',
    mobileDayBorderClass: isDark ? 'border-white/[0.08]' : 'border-[#F0F0F5]',
    stickyHeaderClass: isDark ? 'bg-[#0B2239] border-white/[0.08]' : 'bg-white border-[#E5E7EB]',
    roleBandClass: isDark ? 'bg-white/[0.08] border-white/[0.12]' : 'bg-[#E8EBF0] border-[#DADDE3]',
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
function DraggableShiftChip({
  shift,
  isMulti,
  onEdit,
  onDelete,
  onDuplicate,
  onDragCopy,
  onDragCopyPreview,
  dark = false,
  draggable = true,
}: {
  shift: Shift;
  isMulti: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onDragCopy?: (targetDays: number[]) => void;
  onDragCopyPreview?: (days: number[] | null) => void;
  dark?: boolean;
  draggable?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const [isDragCopying, setIsDragCopying] = useState(false);
  const descriptor = getShiftDescriptor(shift.startHour, shift.endHour);
  const DescIcon = shift.presetKey ? getShiftDefaultIcon(shift.presetKey) : descriptor.icon;
  const shiftLabel = shift.presetLabel?.trim() || descriptor.label;
  const dur = shiftDuration(shift);
  const theme = getSchedulerTheme(dark);

  const [{ isDragging }, dragRef] = useDrag(() => ({
    type: DRAG_TYPE,
    item: { type: DRAG_TYPE, shiftId: shift.id } as DragItem,
    canDrag: draggable,
    collect: (monitor) => ({ isDragging: monitor.isDragging() }),
  }), [draggable, shift.id]);

  const handleDragCopyStart = (event: React.MouseEvent) => {
    if (!onDragCopy) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    setIsDragCopying(true);
    onDragCopyPreview?.([shift.day]);

    const startX = event.clientX;
    const cellWidth = 100;
    let previewDays = [shift.day];

    const handleMouseMove = (moveEvent: MouseEvent) => {
      moveEvent.preventDefault();
      const deltaX = moveEvent.clientX - startX;
      const daysDelta = Math.round(deltaX / cellWidth);
      const targetDay = shift.day + daysDelta;
      const minDay = Math.max(0, Math.min(shift.day, targetDay));
      const maxDay = Math.min(6, Math.max(shift.day, targetDay));
      const nextDays: number[] = [];
      for (let day = minDay; day <= maxDay; day += 1) {
        nextDays.push(day);
      }
      if (JSON.stringify(nextDays) === JSON.stringify(previewDays)) {
        return;
      }
      previewDays = nextDays;
      onDragCopyPreview?.(nextDays);
    };

    const handleMouseUp = () => {
      setIsDragCopying(false);
      const targetDays = previewDays.filter((day) => day !== shift.day);
      if (targetDays.length > 0) {
        onDragCopy(targetDays);
      }
      onDragCopyPreview?.(null);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  /* Single shift: stacked layout showing descriptor + time + hours clearly.
     Multi shift: compact inline row to fit multiple in one cell. */
  if (!isMulti) {
    return (
      <div
        ref={dragRef as unknown as React.RefObject<HTMLDivElement>}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={onEdit}
        className={`relative rounded-lg overflow-hidden transition-all mx-1 my-0.5 ${
          draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'
        } ${
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
                {shiftLabel}
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
                className="mr-1 flex flex-col gap-0.5 shrink-0">
                <button onClick={(e) => { e.stopPropagation(); onDuplicate(); }}
                  className={`p-0.5 rounded shadow-sm border transition-all ${theme.iconButtonClass} hover:border-[#635BFF]/30`} title="Copy shift">
                  <Copy size={9} className={theme.textMuted} />
                </button>
                <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
                  className={`p-0.5 rounded shadow-sm border transition-all ${theme.iconButtonClass} hover:border-red-300`} title="Delete">
                  <Trash2 size={9} className={theme.textMuted} />
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <AnimatePresence>
          {hovered && !isDragging && !isDragCopying && onDragCopy ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute right-0 top-1/2 z-10 flex h-8 w-2 -translate-y-1/2 cursor-ew-resize items-center justify-center"
              draggable={false}
              onMouseDown={handleDragCopyStart}
              style={{ background: shift.color, opacity: 0.4, borderRadius: '0 4px 4px 0' }}
              title="Drag to copy across days"
            >
              <GripVertical size={10} className="text-white" style={{ opacity: 0.8 }} />
            </motion.div>
          ) : null}
        </AnimatePresence>
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
      className={`relative rounded-lg overflow-hidden transition-all mx-1 my-[1px] ${
        draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'
      } ${
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
              {shiftLabel}
            </span>
          </div>
          <div className="flex items-center gap-0.5 shrink-0">
            <span className={`text-[8px] ${theme.textSubtle}`} style={{ fontWeight: 420 }}>
              {dur}h
            </span>
            <AnimatePresence>
              {hovered && !isDragging && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="mr-1 flex gap-0.5">
                  <button onClick={(e) => { e.stopPropagation(); onDuplicate(); }}
                    className={`p-0.5 rounded shadow-sm border transition-all ${theme.iconButtonClass} hover:border-[#635BFF]/30`} title="Copy shift">
                    <Copy size={7} className={theme.textMuted} />
                  </button>
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

      <AnimatePresence>
        {hovered && !isDragging && !isDragCopying && onDragCopy ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute right-0 top-1/2 z-10 flex h-6 w-2 -translate-y-1/2 cursor-ew-resize items-center justify-center"
            draggable={false}
            onMouseDown={handleDragCopyStart}
            style={{ background: shift.color, opacity: 0.4, borderRadius: '0 4px 4px 0' }}
            title="Drag to copy across days"
          >
            <GripVertical size={8} className="text-white" style={{ opacity: 0.8 }} />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

/* ─── Droppable Cell ─── */
function DroppableCell({
  employeeId,
  day,
  children,
  onDrop,
  onClickEmpty,
  isToday: isTodayCell,
  isDragCopyTarget = false,
  dragCopyColor,
  dark = false,
}: {
  employeeId: string;
  day: number;
  children: React.ReactNode;
  onDrop?: (shiftId: string, newEmpId: string, newDay: number) => void;
  onClickEmpty?: () => void;
  isToday: boolean;
  isDragCopyTarget?: boolean;
  dragCopyColor?: string;
  dark?: boolean;
}) {
  const [{ isOver, canDrop }, dropRef] = useDrop(() => ({
    accept: DRAG_TYPE,
    canDrop: () => Boolean(onDrop),
    drop: (item: DragItem) => { onDrop?.(item.shiftId, employeeId, day); },
    collect: (monitor) => ({ isOver: monitor.isOver(), canDrop: monitor.canDrop() }),
  }), [day, employeeId, onDrop]);

  const hasChildren = Array.isArray(children) ? children.some(Boolean) : !!children;
  const theme = getSchedulerTheme(dark);

  return (
    <div
      ref={dropRef as unknown as React.RefObject<HTMLDivElement>}
      className={`relative flex-1 border-l py-0.5 flex flex-col justify-center min-h-[52px] transition-colors ${theme.cellBorderClass} ${
        isTodayCell ? theme.todayCellClass : ''
      } ${isOver && canDrop ? 'bg-[#635BFF]/[0.06]' : ''} ${canDrop && !isOver ? '' : ''}`}
    >
      {isDragCopyTarget && dragCopyColor ? (
        <div
          className="pointer-events-none absolute inset-0 m-0.5 rounded-md border-2 border-dashed"
          style={{
            borderColor: dragCopyColor,
            backgroundColor: `${dragCopyColor}08`,
          }}
        />
      ) : null}
      {hasChildren ? children : (
        <div onClick={onClickEmpty}
          className={`h-full min-h-[44px] flex items-center justify-center mx-0.5 my-0.5 rounded-lg transition-colors ${
            onClickEmpty ? `cursor-pointer group/empty ${theme.emptyStateClass}` : ''
          }`}>
          <div className={`transition-opacity ${onClickEmpty ? 'opacity-0 group-hover/empty:opacity-100' : 'opacity-0'}`}>
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
  editingLocation?: boolean;
};

/* ─── Main Scheduler ─── */
function SchedulerContent({
  embeddedInShell = false,
  location,
  backHref,
  editingLocation = false,
}: SchedulerProps) {
  const router = useRouter();
  const refreshWorkspace = useAppWorkspaceRefresh();
  const setLocationEntryMode = useSetLocationEntryMode();
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
  const [board, setBoard] = useState<WorkspaceBoard | null>(null);
  const [businessEmployees, setBusinessEmployees] = useState<EmployeeSummary[]>([]);
  const [businessRoles, setBusinessRoles] = useState<BusinessRole[]>([]);
  const [businessLocations, setBusinessLocations] = useState<BusinessLocation[]>([]);
  const [loadingSchedulerData, setLoadingSchedulerData] = useState(false);
  const [schedulerError, setSchedulerError] = useState<string | null>(null);
  const [editingShift, setEditingShift] = useState<Shift | null>(null);
  const [creatingAt, setCreatingAt] = useState<{
    day: number;
    roleId: string;
    roleName: string;
    employeeId?: string | null;
    employeeName?: string | null;
  } | null>(null);
  const [schedulerNotice, setSchedulerNotice] = useState<{
    tone: 'success' | 'error' | 'info';
    title: string;
    detail?: string;
  } | null>(null);
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [showPublishModal, setShowPublishModal] = useState(false);
  const [collapsedRoles, setCollapsedRoles] = useState<Set<string>>(new Set());
  const [mobileDay, setMobileDay] = useState(() => (new Date().getDay() + 6) % 7);
  const [removingEmployee, setRemovingEmployee] = useState<{ id: string; name: string; hasShifts: boolean } | null>(null);
  const [isRemovingEmployee, setIsRemovingEmployee] = useState(false);
  const [addEmployeeContext, setAddEmployeeContext] = useState<{
    roleId: string;
    roleName: string;
  } | null>(null);
  const [addEmployeeTab, setAddEmployeeTab] = useState<'existing' | 'new'>('existing');
  const [hoveredEmployeeId, setHoveredEmployeeId] = useState<string | null>(null);
  const [swipedEmployeeId, setSwipedEmployeeId] = useState<string | null>(null);
  const [shiftDefaults, setShiftDefaults] = useState<ShiftDefault[]>(() =>
    normalizeShiftDefaults(SHIFT_DEFAULT_FALLBACKS),
  );
  const [dragCopyPreview, setDragCopyPreview] = useState<{
    employeeId: string;
    days: number[];
    color: string;
  } | null>(null);
  const [showLocationMenu, setShowLocationMenu] = useState(false);
  const locationMenuButtonRef = useRef<HTMLButtonElement>(null);
  const [editorLocation, setEditorLocation] = useState<BusinessLocation | null>(null);
  const [editorEmployees, setEditorEmployees] = useState<EmployeeSummary[]>([]);
  const [editorAssignments, setEditorAssignments] = useState<LocationRoleAssignment[]>([]);
  const [editorShiftDefaults, setEditorShiftDefaults] = useState<LocationShiftDefaults | null>(null);
  const [editorStaffCount, setEditorStaffCount] = useState<number | null>(null);
  const [editorDeleteState, setEditorDeleteState] = useState<LocationDeleteState | undefined>();
  const [editorLoading, setEditorLoading] = useState(false);
  const [editorFeedback, setEditorFeedback] = useState<LocationRoleEditorFeedback>(null);
  const [deletingLocationId, setDeletingLocationId] = useState<string | null>(null);
  const [isSavingEditor, setIsSavingEditor] = useState(false);
  const [locationDeleteState, setLocationDeleteState] = useState<LocationDeleteState>({
    canDelete: false,
    checking: true,
  });
  const editorLocationAssignmentsByRoleId = useMemo(
    () => new Map(editorAssignments.map((assignment) => [assignment.role_id, assignment])),
    [editorAssignments],
  );
  const effectiveDeleteState = editorLocation ? (editorDeleteState ?? locationDeleteState) : locationDeleteState;

  const closeLocationEditor = useCallback(() => {
    setEditorLocation(null);
    setEditorFeedback(null);
    setEditorStaffCount(null);
    setEditorEmployees([]);
    setEditorAssignments([]);
    setEditorShiftDefaults(null);
    setEditorDeleteState(undefined);
    router.replace(buildSchedulerBasePathFromAny(location), { scroll: false });
  }, [location, router]);

  const requestedWeekStart = useMemo(
    () => mondayDateKeyFor(location.timezone, weekOffset),
    [location.timezone, weekOffset],
  );

  const refreshSchedulerData = useCallback(async () => {
    try {
      setLoadingSchedulerData(true);
      setSchedulerError(null);
      const [nextBoard, employeeDirectory, roleDirectory, locationDirectory] = await Promise.all([
        getLocationBoard(location.business_id, location.location_id, requestedWeekStart),
        listEmployees(location.business_id),
        listBusinessRoles(location.business_id),
        listBusinessLocations(location.business_id),
      ]);
      setBoard(nextBoard);
      setBusinessEmployees(employeeDirectory);
      setBusinessRoles(roleDirectory);
      setBusinessLocations(locationDirectory);
    } catch (error) {
      setBoard(null);
      setBusinessEmployees([]);
      setBusinessRoles([]);
      setBusinessLocations([]);
      setSchedulerError(
        error instanceof Error ? error.message : 'Could not load scheduler data.',
      );
    } finally {
      setLoadingSchedulerData(false);
    }
  }, [location.business_id, location.location_id, requestedWeekStart]);

  useEffect(() => {
    void refreshSchedulerData();
  }, [refreshSchedulerData]);

  useEffect(() => {
    let cancelled = false;

    async function loadShiftDefaults() {
      try {
        const payload = await getLocationShiftDefaults(
          location.business_id,
          location.location_id,
        );
        if (cancelled) {
          return;
        }
        setShiftDefaults(normalizeShiftDefaults(payload?.presets ?? SHIFT_DEFAULT_FALLBACKS));
      } catch (_error) {
        if (!cancelled) {
          setShiftDefaults(normalizeShiftDefaults(SHIFT_DEFAULT_FALLBACKS));
        }
      }
    }

    void loadShiftDefaults();
    return () => {
      cancelled = true;
    };
  }, [location.business_id, location.location_id]);

  useEffect(() => {
    let cancelled = false;

    async function loadDeleteReadiness() {
      try {
        setLocationDeleteState({ canDelete: false, checking: true });
        const readiness = await getLocationDeleteReadiness(
          location.business_id,
          location.location_id,
        );
        if (cancelled) {
          return;
        }
        setLocationDeleteState({
          canDelete: readiness.can_delete,
          reason: readiness.reason,
        });
      } catch {
        if (cancelled) {
          return;
        }
        setLocationDeleteState({
          canDelete: false,
          reason: 'Could not determine whether this location can be removed.',
        });
      }
    }

    void loadDeleteReadiness();
    return () => {
      cancelled = true;
    };
  }, [location.business_id, location.location_id]);

  const weekDates = useMemo(
    () => (board ? buildWeekDatesFromWeekStart(board.week_start_date) : buildWeekDatesFromWeekStart(requestedWeekStart)),
    [board, requestedWeekStart],
  );

  const shifts = useMemo(
    () => {
      if (!board) {
        return [];
      }
      return board.shifts
        .map((shift) => boardShiftToSchedulerShift(shift, board, shiftDefaults))
        .filter((shift): shift is Shift => shift !== null);
    },
    [board, shiftDefaults],
  );

  const boardWorkersById = useMemo(
    () => new Map((board?.workers ?? []).map((worker) => [worker.employee_id, worker])),
    [board],
  );

  const schedulerEmployeeIds = useMemo(() => {
    const next = new Set<string>();
    (board?.workers ?? []).forEach((worker) => {
      if (worker.can_cover_here) {
        next.add(worker.employee_id);
      }
    });
    shifts.forEach((shift) => {
      if (shift.displayEmployeeId) {
        next.add(shift.displayEmployeeId);
      }
    });
    return next;
  }, [board, shifts]);

  const locationEmployeeIds = useMemo(() => {
    const next = new Set<string>();
    businessEmployees.forEach((employee) => {
      if (employee.location_ids.includes(location.location_id)) {
        next.add(employee.id);
      }
    });
    shifts.forEach((shift) => {
      if (shift.displayEmployeeId) {
        next.add(shift.displayEmployeeId);
      }
    });
    return next;
  }, [businessEmployees, location.location_id, shifts]);

  const schedulerEmployees = useMemo(() => {
    const employeeMap = new Map(businessEmployees.map((employee) => [employee.id, employee]));
    const assignedShiftNames = new Map<string, string>();
    shifts.forEach((shift) => {
      if (!shift.displayEmployeeId) {
        return;
      }
      const assignmentName =
        board?.shifts.find((item) => item.shift_id === shift.id)?.current_assignment?.employee_name ??
        shift.displayEmployeeName;
      if (assignmentName) {
        assignedShiftNames.set(shift.displayEmployeeId, assignmentName);
      }
    });

    return Array.from(schedulerEmployeeIds)
      .map((employeeId) => {
        const employee = employeeMap.get(employeeId);
        if (employee) {
          return boardWorkerToSchedulerEmployee(
            employee,
            boardWorkersById.get(employeeId) ?? null,
          );
        }
        const fallbackName = assignedShiftNames.get(employeeId);
        if (!fallbackName) {
          return null;
        }
        const assignedRole =
          shifts.find((shift) => shift.displayEmployeeId === employeeId)?.role ?? 'Assigned';
        return {
          id: employeeId,
          name: fallbackName,
          avatar: buildAvatarDataUri(fallbackName),
          role: assignedRole,
        } satisfies Employee;
      })
      .filter((employee): employee is Employee => employee !== null)
      .sort((left, right) => left.name.localeCompare(right.name));
  }, [board?.shifts, boardWorkersById, businessEmployees, schedulerEmployeeIds, shifts]);

  const activeEmployees = schedulerEmployees;

  const filteredRoles = useMemo(() => {
    const rolesById = new Map<string, { id: string; name: string }>();
    (board?.roles ?? []).forEach((role) => {
      rolesById.set(role.role_id, {
        id: role.role_id,
        name: role.role_name,
      });
    });
    shifts.forEach((shift) => {
      if (!rolesById.has(shift.roleId)) {
        rolesById.set(shift.roleId, {
          id: shift.roleId,
          name: shift.role,
        });
      }
    });
    return Array.from(rolesById.values())
      .sort((left, right) => {
        const sortDelta = roleSortValue(left.name) - roleSortValue(right.name);
        if (sortDelta !== 0) {
          return sortDelta;
        }
        return left.name.localeCompare(right.name);
      });
  }, [activeEmployees, board?.roles, shifts]);

  const roleColorById = useMemo(() => {
    const next = new Map<string, string>();
    let previousColor: string | null = null;

    filteredRoles.forEach((roleEntry, index) => {
      const preferredColor = roleColors[roleEntry.name] ?? ROLE_COLOR_PALETTE[index % ROLE_COLOR_PALETTE.length];
      let color = preferredColor;
      if (color === previousColor) {
        color =
          ROLE_COLOR_PALETTE.find((candidate) => candidate !== previousColor) ??
          preferredColor;
      }
      next.set(roleEntry.id, color);
      previousColor = color;
    });

    return next;
  }, [filteredRoles]);

  const displayShifts = useMemo(
    () =>
      shifts.map((shift) => ({
        ...shift,
        color: shift.employeeId ? roleColorById.get(shift.roleId) ?? shift.color : OPEN_SHIFT_COLOR,
      })),
    [roleColorById, shifts],
  );

  const removeEmployee = useCallback((employeeId: string) => {
    const employee = schedulerEmployees.find((item) => item.id === employeeId);
    if (!employee) {
      return;
    }
    setRemovingEmployee({
      id: employeeId,
      name: employee.name,
      hasShifts: shifts.some((shift) => shift.employeeId === employeeId),
    });
  }, [schedulerEmployees, shifts]);

  const confirmRemoveEmployee = useCallback(() => {
    if (!removingEmployee) {
      return;
    }
    if (removingEmployee.hasShifts) {
      setSchedulerNotice({
        tone: 'info',
        title: 'Remove assigned shifts first',
        detail: `${removingEmployee.name} still has scheduled shifts. Manual reassignment and shift deletion for assigned shifts are not wired yet.`,
      });
      setRemovingEmployee(null);
      setSwipedEmployeeId(null);
      return;
    }
    const employee = businessEmployees.find((item) => item.id === removingEmployee.id);
    if (!employee) {
      setRemovingEmployee(null);
      return;
    }

    setIsRemovingEmployee(true);
    void (async () => {
      try {
        await updateEmployee(location.business_id, employee.id, {
          locations: buildEmployeeLocationAssignments(employee, location.location_id, false),
        });
        await refreshSchedulerData();
        setSchedulerNotice({
          tone: 'success',
          title: 'Employee removed',
          detail: `${removingEmployee.name} is no longer assigned to this location.`,
        });
      } catch (error) {
        setSchedulerNotice({
          tone: 'error',
          title: 'Could not remove employee',
          detail: error instanceof Error ? error.message : 'Please try again.',
        });
      } finally {
        setIsRemovingEmployee(false);
        setRemovingEmployee(null);
        setSwipedEmployeeId(null);
      }
    })();
  }, [businessEmployees, location.business_id, location.location_id, refreshSchedulerData, removingEmployee]);

  const addEmployeeToLocation = useCallback((employee: EmployeeSummary) => {
    void (async () => {
      try {
        await updateEmployee(location.business_id, employee.id, {
          locations: buildEmployeeLocationAssignments(employee, location.location_id, true),
        });
        await refreshSchedulerData();
        setSchedulerNotice({
          tone: 'success',
          title: 'Employee added',
          detail: `${employee.full_name} is now available on this scheduler.`,
        });
        setAddEmployeeTab('existing');
        setAddEmployeeContext(null);
      } catch (error) {
        setSchedulerNotice({
          tone: 'error',
          title: 'Could not add employee',
          detail: error instanceof Error ? error.message : 'Please try again.',
        });
      }
    })();
  }, [location.business_id, location.location_id, refreshSchedulerData]);

  const openAddEmployeeModal = useCallback((roleId: string, roleName: string) => {
    setAddEmployeeTab('existing');
    setAddEmployeeContext({ roleId, roleName });
  }, []);

  const getEmployeeWeekHours = useCallback((empId: string) =>
    displayShifts.filter(s => s.employeeId === empId).reduce((sum, s) => sum + shiftDuration(s), 0), [displayShifts]);

  const getDayTotalHours = useCallback((day: number) =>
    displayShifts.filter(s => s.day === day).reduce((sum, s) => sum + shiftDuration(s), 0), [displayShifts]);

  const weekTotalHours = useMemo(() =>
    displayShifts.reduce((sum, s) => sum + shiftDuration(s), 0), [displayShifts]);

  const getShiftsForCell = useCallback((empId: string, day: number) =>
    displayShifts.filter((shift) => shift.displayEmployeeId === empId && shift.day === day), [displayShifts]);

  const assignedShiftsForPublishing = useMemo(
    () =>
      displayShifts
        .filter((shift): shift is Shift & { employeeId: string } => shift.employeeId !== null)
        .map((shift) => ({ ...shift, employeeId: shift.employeeId })),
    [displayShifts],
  );

  const deleteShift = useCallback((id: string) => {
    void (async () => {
      try {
        await deleteWorkspaceShift(location.business_id, id);
        await refreshSchedulerData();
        setSchedulerNotice({
          tone: 'success',
          title: 'Shift removed',
        });
      } catch (error) {
        setSchedulerNotice({
          tone: 'error',
          title: 'Could not remove shift',
          detail: error instanceof Error ? error.message : 'Please try again.',
        });
      }
    })();
  }, [location.business_id, refreshSchedulerData]);

  const updateShift = useCallback((updated: Shift) => {
    const weekDate = weekDates[updated.day];
    if (!weekDate) {
      return;
    }
    void (async () => {
      try {
        await updateWorkspaceShift(location.business_id, updated.id, {
          role_id: updated.roleId,
          timezone: location.timezone,
          starts_at: zonedDateTimeToIso(formatDateKey(weekDate), updated.startHour, location.timezone),
          ends_at: zonedDateTimeToIso(formatDateKey(weekDate), updated.endHour > updated.startHour ? updated.endHour : updated.endHour + 24, location.timezone),
        });
        await refreshSchedulerData();
        setEditingShift(null);
        setSchedulerNotice({
          tone: 'success',
          title: 'Shift updated',
        });
      } catch (error) {
        setSchedulerNotice({
          tone: 'error',
          title: 'Could not update shift',
          detail: error instanceof Error ? error.message : 'Please try again.',
        });
      }
    })();
  }, [location.business_id, location.timezone, refreshSchedulerData, weekDates]);

  const moveShiftToDay = useCallback(async (shift: Shift, targetDay: number) => {
    if (targetDay === shift.day) {
      return;
    }
    const weekDate = weekDates[targetDay];
    if (!weekDate) {
      throw new Error('Could not resolve the target day for this shift.');
    }
    await updateWorkspaceShift(location.business_id, shift.id, {
      role_id: shift.roleId,
      timezone: location.timezone,
      starts_at: zonedDateTimeToIso(formatDateKey(weekDate), shift.startHour, location.timezone),
      ends_at: zonedDateTimeToIso(
        formatDateKey(weekDate),
        shift.endHour > shift.startHour ? shift.endHour : shift.endHour + 24,
        location.timezone,
      ),
    });
  }, [location.business_id, location.timezone, weekDates]);

  const applyShiftAssignment = useCallback(async (
    shift: Shift,
    targetEmployeeId: string | null,
  ): Promise<ShiftAssignmentMutationResponse> => {
    return assignWorkspaceShift(location.business_id, shift.id, {
      employee_id: targetEmployeeId,
      source: 'scheduler_ui',
      expected_assignment_id: shift.currentAssignmentId ?? null,
    });
  }, [location.business_id]);

  const handleShiftDrop = useCallback((shiftId: string, newEmpId: string, newDay: number) => {
    const shift = shifts.find((entry) => entry.id === shiftId);
    if (!shift) {
      return;
    }

    const targetEmployeeId = newEmpId;
    const assignmentChanged = targetEmployeeId !== shift.employeeId;
    const dayChanged = newDay !== shift.day;
    if (!assignmentChanged && !dayChanged) {
      return;
    }

    if (targetEmployeeId) {
      const targetEmployee = businessEmployees.find((employee) => employee.id === targetEmployeeId);
      if (!targetEmployee) {
        setSchedulerNotice({
          tone: 'error',
          title: 'Could not move shift',
          detail: 'The target employee could not be found.',
        });
        return;
      }
      if (!targetEmployee.role_ids.includes(shift.roleId)) {
        setSchedulerNotice({
          tone: 'error',
          title: 'Role mismatch',
          detail: `${targetEmployee.full_name} does not have the ${shift.role} role.`,
        });
        return;
      }
    }

    void (async () => {
      try {
        if (assignmentChanged) {
          await applyShiftAssignment(shift, targetEmployeeId);
        }
        if (dayChanged) {
          await moveShiftToDay(shift, newDay);
        }
        await refreshSchedulerData();
        setSchedulerNotice({
          tone: 'success',
          title: assignmentChanged
            ? targetEmployeeId
              ? 'Shift reassigned'
              : 'Shift updated'
            : 'Shift moved',
          detail: dayChanged ? 'The shift was updated for the new day.' : undefined,
        });
      } catch (error) {
        await refreshSchedulerData();
        if (error instanceof ShiftAssignmentConflictError) {
          setSchedulerNotice({
            tone: 'info',
            title: 'Schedule changed',
            detail: 'Someone else updated this shift first. The scheduler was refreshed.',
          });
          return;
        }
        setSchedulerNotice({
          tone: 'error',
          title: 'Could not move shift',
          detail: error instanceof Error ? error.message : 'Please try again.',
        });
      }
    })();
  }, [applyShiftAssignment, businessEmployees, moveShiftToDay, refreshSchedulerData, shifts]);

  const copySchedule = (targetWeekOffset: number) => {
    const targetWeekStart = mondayDateKeyFor(location.timezone, targetWeekOffset);
    const targetWeekDates = buildWeekDatesFromWeekStart(targetWeekStart);
    const targetWeekLabel = (() => {
      const start = targetWeekDates[0];
      const end = targetWeekDates[6];
      const startMonth = start.toLocaleString('default', { month: 'short' });
      const endMonth = end.toLocaleString('default', { month: 'short' });
      if (startMonth === endMonth) {
        return `${startMonth} ${start.getDate()} – ${end.getDate()}, ${start.getFullYear()}`;
      }
      return `${startMonth} ${start.getDate()} – ${endMonth} ${end.getDate()}, ${start.getFullYear()}`;
    })();

    void (async () => {
      let createdCount = 0;
      let openedCount = 0;
      let assignmentFailureCount = 0;

      try {
        for (const shift of shifts) {
          const targetDateKey = addDaysToDateKey(targetWeekStart, shift.day);
          const createdShift = await createWorkspaceShift(
            location.business_id,
            buildShiftPayload(
              location,
              shift.roleId,
              targetDateKey,
              shift.startHour,
              shift.endHour,
            ),
          );
          createdCount += 1;

          if (shift.employeeId) {
            try {
              await assignWorkspaceShift(location.business_id, createdShift.id, {
                employee_id: shift.employeeId,
                source: 'scheduler_ui',
                expected_assignment_id: null,
              });
            } catch {
              assignmentFailureCount += 1;
              openedCount += 1;
            }
          } else {
            openedCount += 1;
          }
        }

        setWeekOffset(targetWeekOffset);
        setShowCopyModal(false);
        await refreshSchedulerData();
        setSchedulerNotice({
          tone: assignmentFailureCount ? 'info' : 'success',
          title: 'Schedule copied',
          detail: assignmentFailureCount
            ? `${createdCount} shifts copied. ${assignmentFailureCount} assignment${assignmentFailureCount === 1 ? '' : 's'} could not be applied and ${openedCount} shift${openedCount === 1 ? ' is' : 's are'} open.`
            : `${createdCount} shifts copied into ${targetWeekLabel}.`,
        });
      } catch (error) {
        setSchedulerNotice({
          tone: 'error',
          title: 'Could not copy schedule',
          detail: error instanceof Error ? error.message : 'Please try again.',
        });
      }
    })();
  };

  const duplicateShift = useCallback((shift: Shift) => {
    const targetDay = (shift.day + 1) % 7;
    const targetDate = weekDates[targetDay];
    if (!targetDate) {
      return;
    }

    void (async () => {
      try {
        const createdShift = await createWorkspaceShift(
          location.business_id,
          buildShiftPayload(
            location,
            shift.roleId,
            formatDateKey(targetDate),
            shift.startHour,
            shift.endHour,
          ),
        );

        let assignmentFailure = false;
        if (shift.employeeId) {
          try {
            await assignWorkspaceShift(location.business_id, createdShift.id, {
              employee_id: shift.employeeId,
              source: 'scheduler_ui',
              expected_assignment_id: null,
            });
          } catch {
            assignmentFailure = true;
          }
        }

        await refreshSchedulerData();
        setSchedulerNotice({
          tone: assignmentFailure ? 'info' : 'success',
          title: 'Shift copied',
          detail: assignmentFailure
            ? 'The copied shift was created, but assignment could not be applied and it is now open.'
            : undefined,
        });
      } catch (error) {
        setSchedulerNotice({
          tone: 'error',
          title: 'Could not copy shift',
          detail: error instanceof Error ? error.message : 'Please try again.',
        });
      }
    })();
  }, [location, refreshSchedulerData, weekDates]);

  const dragCopyShift = useCallback((shift: Shift, targetDays: number[]) => {
    const validDays = Array.from(new Set(targetDays))
      .filter((day) => day >= 0 && day <= 6 && day !== shift.day);
    if (!validDays.length) {
      return;
    }

    void (async () => {
      let createdCount = 0;
      let assignmentFailureCount = 0;

      try {
        for (const day of validDays) {
          const targetDate = weekDates[day];
          if (!targetDate) {
            continue;
          }
          const createdShift = await createWorkspaceShift(
            location.business_id,
            buildShiftPayload(
              location,
              shift.roleId,
              formatDateKey(targetDate),
              shift.startHour,
              shift.endHour,
            ),
          );
          createdCount += 1;

          if (!shift.employeeId) {
            continue;
          }

          try {
            await assignWorkspaceShift(location.business_id, createdShift.id, {
              employee_id: shift.employeeId,
              source: 'scheduler_ui',
              expected_assignment_id: null,
            });
          } catch {
            assignmentFailureCount += 1;
          }
        }

        await refreshSchedulerData();
        setSchedulerNotice({
          tone: assignmentFailureCount ? 'info' : 'success',
          title: createdCount === 1 ? 'Shift copied' : 'Shifts copied',
          detail: assignmentFailureCount
            ? `${assignmentFailureCount} copied shift assignment${assignmentFailureCount === 1 ? '' : 's'} could not be applied.`
            : undefined,
        });
      } catch (error) {
        setSchedulerNotice({
          tone: 'error',
          title: 'Could not copy shifts',
          detail: error instanceof Error ? error.message : 'Please try again.',
        });
      } finally {
        setDragCopyPreview(null);
      }
    })();
  }, [location, refreshSchedulerData, weekDates]);

  const toggleRoleCollapse = (role: string) => {
    setCollapsedRoles(prev => {
      const next = new Set(prev);
      if (next.has(role)) next.delete(role); else next.add(role);
      return next;
    });
  };

  const openLocationEditor = useCallback(async () => {
    const editableLocation = adaptWorkspaceLocation(location);
    setEditorLocation(editableLocation);
    setEditorEmployees([]);
    setEditorAssignments([]);
    setEditorShiftDefaults(null);
    setEditorStaffCount(null);
    setEditorDeleteState({ canDelete: false, checking: true });
    setEditorLoading(true);
    setEditorFeedback(null);

    try {
      const [
        nextLocation,
        nextAssignments,
        nextShiftDefaults,
        nextDeleteReadiness,
        employees,
      ] =
        await Promise.all([
          getBusinessLocation(location.business_id, location.location_id),
          getLocationRoles(location.business_id, location.location_id),
          getLocationShiftDefaults(location.business_id, location.location_id),
          getLocationDeleteReadiness(location.business_id, location.location_id),
          listEmployees(location.business_id),
        ]);
      setEditorLocation(nextLocation);
      setEditorEmployees(employees);
      setEditorAssignments(nextAssignments);
      setEditorShiftDefaults(nextShiftDefaults);
      setEditorStaffCount(
        employees.filter((employee) => employee.location_ids.includes(location.location_id))
          .length,
      );
      const nextDeleteState = {
        canDelete: nextDeleteReadiness.can_delete,
        reason: nextDeleteReadiness.reason,
      };
      setEditorDeleteState(nextDeleteState);
      setLocationDeleteState(nextDeleteState);
    } catch (error) {
      setEditorFeedback({
        tone: 'error',
        message:
          error instanceof Error ? error.message : 'Could not load location settings.',
      });
      setEditorDeleteState({
        canDelete: false,
        reason: 'Could not determine whether this location can be removed.',
      });
    } finally {
      setEditorLoading(false);
    }
  }, [location]);

  useEffect(() => {
    if (editingLocation) {
      if (!editorLocation && !editorLoading) {
        void openLocationEditor();
      }
      return;
    }

    if (editorLocation) {
      setEditorLocation(null);
      setEditorFeedback(null);
      setEditorStaffCount(null);
    }
  }, [editingLocation, editorLoading, editorLocation, openLocationEditor]);

  const handleSaveEditor = (
    employeeIds: string[],
    locationShiftPresets: ShiftDefault[] | null,
    saveSummary: LocationRoleEditorSaveSummary,
  ) => {
    if (!editorLocation || isSavingEditor) {
      return;
    }

    setIsSavingEditor(true);
    setEditorFeedback(null);

    void (async () => {
      try {
        const roleIds = buildInheritedLocationRoleIds(
          editorAssignments,
          editorEmployees,
          employeeIds,
        );
        const changedEmployees = editorEmployees.filter((employee) => {
          const currentlyAssigned = employeeAssignedHere(employee, editorLocation.id);
          const shouldBeAssigned = employeeIds.includes(employee.id);
          return currentlyAssigned !== shouldBeAssigned;
        });
        const [replacedAssignments, updatedShiftDefaults, updatedEmployees] = await Promise.all([
          replaceLocationRoles(
            editorLocation.business_id,
            editorLocation.id,
            roleIds.map((roleId) => {
              const existing = editorLocationAssignmentsByRoleId.get(roleId);
              return existing
                ? {
                    role_id: roleId,
                    min_headcount: existing.min_headcount,
                    max_headcount: existing.max_headcount,
                    premium_rules: existing.premium_rules,
                    coverage_settings: existing.coverage_settings,
                  }
                : { role_id: roleId };
            }),
          ),
          updateLocationShiftDefaults(
            editorLocation.business_id,
            editorLocation.id,
            locationShiftPresets,
          ),
          Promise.all(
            changedEmployees.map((employee) =>
              updateEmployee(editorLocation.business_id, employee.id, {
                locations: buildEmployeeLocationAssignments(
                  employee,
                  editorLocation.id,
                  employeeIds.includes(employee.id),
                ),
              }),
            ),
          ),
        ]);
        setEditorAssignments(replacedAssignments);
        setEditorEmployees((current) => mergeUpdatedEmployees(current, updatedEmployees));
        setEditorShiftDefaults(updatedShiftDefaults);
        setShiftDefaults(normalizeShiftDefaults(updatedShiftDefaults.presets));
        const board = await getLocationBoard(editorLocation.business_id, editorLocation.id);
        setLocationEntryMode(
          editorLocation.id,
          board?.location_setup_required ? 'setup' : 'scheduler',
        );
        if (board?.location_setup_required) {
          router.replace(resolvedBackHref);
        }
        setEditorFeedback({
          tone: 'success',
          message: formatLocationSaveSummary(
            saveSummary,
            editorLocation.display_name ?? editorLocation.name,
          ),
        });
      } catch (error) {
        setEditorFeedback({
          tone: 'error',
          message:
            error instanceof Error ? error.message : 'Could not update location configuration.',
        });
      } finally {
        setIsSavingEditor(false);
      }
    })();
  };

  const handleDeleteLocation = async () => {
    if (!effectiveDeleteState.canDelete || deletingLocationId === location.location_id) {
      return;
    }

    const confirmed = window.confirm(
      `Delete ${locationDisplayName}? This only works for locations that do not already have operational data.`,
    );
    if (!confirmed) {
      return;
    }

    try {
      setDeletingLocationId(location.location_id);
      setEditorFeedback(null);
      await deleteWorkspaceLocation(location.business_id, location.location_id);
      await refreshWorkspace();
      router.replace('/dashboard');
    } catch (error) {
      setEditorFeedback({
        tone: 'error',
        message:
          error instanceof Error ? error.message : 'Could not remove this location.',
      });
    } finally {
      setDeletingLocationId(null);
    }
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

  const EMP_COL = 'w-[220px] min-w-[220px]';

  const content = (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }} className={`flex flex-col h-full -mx-4 sm:-mx-6 md:-mx-8 -mt-2 ${theme.pageClass}`}>

        {/* ─── Top Bar: Location | Week Nav | Buttons ─── */}
        <div className={`px-4 sm:px-6 md:px-8 py-3.5 border-b sticky top-0 z-30 ${theme.topBarClass}`}>
          {/* Row 1: Location name + subtext */}
          <div className="mb-3 flex items-center justify-between gap-3">
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
            <div className="relative">
              <button
                ref={locationMenuButtonRef}
                onClick={() => setShowLocationMenu((current) => !current)}
                className={`flex h-9 w-9 items-center justify-center rounded-full border transition-colors ${theme.cardClass} ${theme.ghostButtonClass}`}
                type="button"
              >
                <Settings size={15} className={theme.textMuted} />
              </button>
              <FloatingDropdown
                open={showLocationMenu}
                anchorRef={locationMenuButtonRef}
                align="right"
                minWidth={220}
                className={`overflow-hidden border ${isDark ? 'border-white/[0.08] bg-[#0F2E4C]' : 'border-[#E5E7EB] bg-white'} rounded-2xl`}
                maxHeight={220}
                onClose={() => setShowLocationMenu(false)}
                sideOffset={10}
                zIndex={10050}
              >
                <div className="py-1.5">
                  <button
                    onClick={() => {
                      setShowLocationMenu(false);
                      router.push(buildSchedulerLocationEditPathFromAny(location), {
                        scroll: false,
                      });
                    }}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 transition-colors ${isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]'}`}
                    type="button"
                  >
                    <Edit3 size={15} className={theme.textMuted} />
                    <span className={`text-[12px] ${theme.textPrimary}`} style={{ fontWeight: 520 }}>
                      Edit Location
                    </span>
                  </button>
                  <div className="group relative">
                    <button
                      onClick={() => {
                        setShowLocationMenu(false);
                        void handleDeleteLocation();
                      }}
                      className={`w-full flex items-center gap-3 px-4 py-2.5 transition-colors ${
                        locationDeleteState.canDelete
                          ? isDark ? 'hover:bg-[#E5484D]/15' : 'hover:bg-[#E5484D]/10'
                          : ''
                      }`}
                      disabled={!locationDeleteState.canDelete || locationDeleteState.checking || deletingLocationId === location.location_id}
                      type="button"
                    >
                      <Trash2 size={15} className={locationDeleteState.canDelete ? 'text-[#E5484D]' : 'text-[#8898AA]'} />
                      <span
                        className={`text-[12px] ${locationDeleteState.canDelete ? 'text-[#E5484D]' : theme.textSecondary}`}
                        style={{ fontWeight: 520 }}
                      >
                        {deletingLocationId === location.location_id
                          ? 'Deleting...'
                          : locationDeleteState.checking
                            ? 'Checking...'
                            : 'Delete Location'}
                      </span>
                    </button>
                    {!locationDeleteState.canDelete && locationDeleteState.reason ? (
                      <div
                        className={`pointer-events-none absolute bottom-full right-3 mb-2 w-64 rounded-lg px-3 py-2 text-[11px] opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 ${
                          isDark
                            ? 'border border-white/[0.08] bg-[#102B46] text-[#C1CED8]'
                            : 'border border-[#E5E7EB] bg-white text-[#5E6D7A]'
                        }`}
                        style={{ fontWeight: 440 }}
                      >
                        {locationDeleteState.reason}
                      </div>
                    ) : null}
                  </div>
                </div>
              </FloatingDropdown>
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
              {loadingSchedulerData ? (
                <span className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 440 }}>
                  Refreshing…
                </span>
              ) : null}
              <button onClick={() => setWeekOffset(w => w + 1)} className={`p-1 rounded-lg transition-colors ${theme.ghostButtonClass}`}>
                <ChevronRight size={15} className={theme.textMuted} />
              </button>
            </div>

            {/* Copy Schedule + Publish Week */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowCopyModal(true)}
                className={`flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12px] border transition-all ${theme.cardClass} ${theme.textMuted} ${theme.ghostButtonClass}`}
                style={{ fontWeight: 500 }}>
                <ClipboardCopy size={13} />
                <span className="hidden lg:inline">Copy Schedule</span>
                <span className="lg:hidden">Copy</span>
              </button>
              <motion.button
                whileTap={{ scale: 0.97 }}
                disabled
                title="Publish week is not wired yet"
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-full text-[12px] text-white cursor-not-allowed opacity-50 transition-all"
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

        {schedulerError && !board ? (
          <div className="flex-1 flex items-center justify-center px-6">
            <div className={`max-w-md rounded-2xl border px-6 py-5 text-center ${theme.cardClass}`}>
              <p className={`text-[14px] ${theme.textPrimary}`} style={{ fontWeight: 560 }}>
                Could not load the scheduler
              </p>
              <p className={`mt-1 text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                {schedulerError}
              </p>
              <button
                onClick={() => void refreshSchedulerData()}
                className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#635BFF] px-4 py-2 text-[12px] text-white"
                style={{ fontWeight: 540 }}
                type="button"
              >
                Retry
              </button>
            </div>
          </div>
        ) : (
        <>
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
            {filteredRoles.map((roleEntry) => {
              const roleEmps = activeEmployees.filter((employee) => employee.role === roleEntry.name);
              const isCollapsed = collapsedRoles.has(roleEntry.name);
              const roleAccent = roleColorById.get(roleEntry.id) ?? roleColor(roleEntry.name);

              return (
                <div key={roleEntry.id}>
                  {/* Role Header Row */}
                  <div className={`flex border-b ${theme.roleBandClass}`}>
                    <div className={`${EMP_COL} shrink-0 px-4 py-2 flex items-center gap-2`}>
                      <button onClick={() => toggleRoleCollapse(roleEntry.name)} className="flex items-center gap-2 group">
                        <motion.div animate={{ rotate: isCollapsed ? -90 : 0 }} transition={{ duration: 0.2 }}>
                          <ChevronDown size={12} className={`${theme.textSecondary} transition-colors ${isDark ? 'group-hover:text-white' : 'group-hover:text-[#5E6D7A]'}`} />
                        </motion.div>
                        <div className="w-2 h-2 rounded-full" style={{ background: roleAccent }} />
                        <span className={`text-[11px] uppercase tracking-[0.03em] whitespace-nowrap ${theme.textPrimary}`} style={{ fontWeight: 580 }}>
                          {roleEntry.name}
                        </span>
                        <span className={`text-[10px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                          {roleEmps.length}
                        </span>
                      </button>
                    </div>
                    <div className="flex-1" />
                  </div>

                  {/* Employee Rows */}
                  <AnimatePresence>
                    {!isCollapsed && roleEmps.map(emp => {
                      const empWeekHours = getEmployeeWeekHours(emp.id);
                      const isHovered = hoveredEmployeeId === emp.id;
                      return (
                        <motion.div key={emp.id}
                          initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.2 }}
                          onMouseEnter={() => setHoveredEmployeeId(emp.id)}
                          onMouseLeave={() => setHoveredEmployeeId(null)}
                          className={`flex border-b transition-colors ${theme.rowClass}`}>
                          {/* Employee Info */}
                          <div className={`${EMP_COL} shrink-0 px-4 py-3 flex items-center gap-2.5`}>
                            <img src={emp.avatar} alt={emp.name}
                              className={`w-7 h-7 rounded-full object-cover shrink-0 ring-1 ${isDark ? 'ring-white/[0.08]' : 'ring-[#E5E7EB]'}`} />
                            <div className="min-w-0 flex-1">
                              <p className={`text-[12px] truncate whitespace-nowrap ${theme.textPrimary}`} style={{ fontWeight: 500 }}>
                                {emp.name}
                              </p>
                              <p className={`text-[10px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                                {empWeekHours}h this week
                              </p>
                            </div>
                            <AnimatePresence>
                              {isHovered ? (
                                <motion.button
                                  initial={{ opacity: 0, scale: 0.9 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  exit={{ opacity: 0, scale: 0.9 }}
                                  transition={{ duration: 0.15 }}
                                  onClick={() => removeEmployee(emp.id)}
                                  className="p-1 rounded-md hover:bg-red-50 border border-red-200/60 transition-colors shrink-0"
                                  title="Remove from scheduler"
                                  type="button"
                                >
                                  <UserMinus size={11} className="text-red-500" />
                                </motion.button>
                              ) : null}
                            </AnimatePresence>
                          </div>

                          {/* Day cells */}
                          {DAYS.map((_day, dayIdx) => {
                            const cellShifts = getShiftsForCell(emp.id, dayIdx);
                            const isMulti = cellShifts.length > 1;
                            const isDragCopyTarget =
                              dragCopyPreview?.employeeId === emp.id &&
                              dragCopyPreview.days.includes(dayIdx);
                            return (
                              <DroppableCell
                                key={dayIdx}
                                employeeId={emp.id}
                                day={dayIdx}
                                onDrop={handleShiftDrop}
                                onClickEmpty={() =>
                                  setCreatingAt({
                                    day: dayIdx,
                                    roleId: roleEntry.id,
                                    roleName: roleEntry.name,
                                    employeeId: emp.id,
                                    employeeName: emp.name,
                                  })
                                }
                                isToday={isToday(weekDates[dayIdx])}
                                isDragCopyTarget={isDragCopyTarget}
                                dragCopyColor={dragCopyPreview?.color}
                                dark={isDark}
                              >
                                {cellShifts.length > 0 ? (
                                  cellShifts.map(shift => (
                                    <DraggableShiftChip key={shift.id} shift={shift} isMulti={isMulti}
                                      dark={isDark}
                                      draggable
                                      onEdit={() => setEditingShift(shift)}
                                      onDelete={() => deleteShift(shift.id)}
                                      onDuplicate={() => duplicateShift(shift)}
                                      onDragCopy={(targetDays) => dragCopyShift(shift, targetDays)}
                                      onDragCopyPreview={(days) =>
                                        setDragCopyPreview(
                                          days
                                            ? { employeeId: emp.id, days, color: shift.color }
                                            : null,
                                        )
                                      }
                                    />
                                  ))
                                ) : null}
                              </DroppableCell>
                            );
                          })}
                        </motion.div>
                      );
                    })}
                    {!isCollapsed ? (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className={`flex border-b ${theme.cellBorderClass}`}
                      >
                        <div className={`${EMP_COL} shrink-0 px-4 py-2`}>
                          <button
                            onClick={() => {
                              openAddEmployeeModal(roleEntry.id, roleEntry.name);
                            }}
                            className={`flex items-center gap-1.5 text-[11px] transition-colors ${theme.textSecondary} ${isDark ? 'hover:text-white' : 'hover:text-[#635BFF]'} group/add`}
                            style={{ fontWeight: 460 }}
                            type="button"
                          >
                            <div className={`p-0.5 rounded-md border border-dashed ${isDark ? 'border-white/[0.08] group-hover/add:border-[#635BFF]/40 group-hover/add:bg-white/[0.04]' : 'border-[#E5E7EB] group-hover/add:border-[#635BFF]/30 group-hover/add:bg-[#635BFF]/[0.02]'} transition-all`}>
                              <UserPlus size={11} />
                            </div>
                            <span>Add employee</span>
                          </button>
                        </div>
                        {DAYS.map((day, i) => (
                          <div key={day} className={`flex-1 border-l ${theme.cellBorderClass} ${isToday(weekDates[i]) ? theme.todayRoleBandClass : ''}`} />
                        ))}
                      </motion.div>
                    ) : null}
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

            {filteredRoles.map((roleEntry) => {
              const roleEmps = activeEmployees.filter((employee) => employee.role === roleEntry.name);
              const roleAccent = roleColorById.get(roleEntry.id) ?? roleColor(roleEntry.name);

              return (
                <div key={roleEntry.id} className="mb-4">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-2 h-2 rounded-full" style={{ background: roleAccent }} />
                    <span className={`text-[11px] uppercase tracking-[0.03em] whitespace-nowrap ${theme.textPrimary}`} style={{ fontWeight: 580 }}>{roleEntry.name}</span>
                    <span className={`text-[10px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>{roleEmps.length}</span>
                  </div>

                  <div className="space-y-1.5">
                    {roleEmps.map(emp => {
                      const cellShifts = getShiftsForCell(emp.id, mobileDay);
                      const empWeekHours = getEmployeeWeekHours(emp.id);
                      const isSwiped = swipedEmployeeId === emp.id;

                      return (
                        <MobileEmployeeCard
                          key={emp.id}
                          dark={isDark}
                          employee={emp}
                          empWeekHours={empWeekHours}
                          cellShifts={cellShifts}
                          isSwiped={isSwiped}
                          onSwipe={(id) => setSwipedEmployeeId(id === swipedEmployeeId ? null : id || null)}
                          onRemove={() => removeEmployee(emp.id)}
                          onEditShift={(shift) => setEditingShift(shift)}
                          onCreateShift={() =>
                            setCreatingAt({
                              day: mobileDay,
                              roleId: roleEntry.id,
                              roleName: roleEntry.name,
                              employeeId: emp.id,
                              employeeName: emp.name,
                            })
                          }
                        />
                      );
                    })}
                    <button
                      onClick={() => {
                        openAddEmployeeModal(roleEntry.id, roleEntry.name);
                      }}
                      className={`w-full flex items-center justify-center gap-1.5 p-2.5 rounded-xl border border-dashed text-[11px] transition-colors ${
                        isDark
                          ? 'border-white/[0.08] text-[#C1CED8] hover:text-white hover:border-[#635BFF]/40'
                          : 'border-[#E5E7EB] text-[#8898AA] hover:text-[#635BFF] hover:border-[#635BFF]/30'
                      }`}
                      style={{ fontWeight: 460 }}
                      type="button"
                    >
                      <UserPlus size={12} />
                      Add employee
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        </>
        )}

        {/* ─── Quick Create Modal ─── */}
        <AnimatePresence>
          {creatingAt && (
            <QuickCreateModal
              dark={isDark}
              employeeName={creatingAt.employeeName ?? "Open Shift"}
              dayLabel={`${FULL_DAYS[creatingAt.day]}, ${weekDates[creatingAt.day]?.toLocaleString('default', { month: 'short' })} ${weekDates[creatingAt.day]?.getDate()}`}
              shiftDefaults={shiftDefaults}
              role={creatingAt.roleName}
              onClose={() => setCreatingAt(null)}
              onCreate={(start, end) => {
                const targetDate = weekDates[creatingAt.day];
                if (!targetDate) {
                  return;
                }
                void (async () => {
                  try {
                    const createdShift = await createWorkspaceShift(
                      location.business_id,
                      buildShiftPayload(
                        location,
                        creatingAt.roleId,
                        formatDateKey(targetDate),
                        start,
                        end,
                      ),
                    );
                    if (creatingAt.employeeId) {
                      await assignWorkspaceShift(location.business_id, createdShift.id, {
                        employee_id: creatingAt.employeeId,
                        source: 'scheduler_ui',
                        expected_assignment_id: null,
                      });
                    }
                    await refreshSchedulerData();
                    setCreatingAt(null);
                    setSchedulerNotice({
                      tone: 'success',
                      title: creatingAt.employeeId ? 'Shift created' : 'Open shift created',
                      detail: creatingAt.employeeId
                        ? `${creatingAt.roleName} shift added for ${creatingAt.employeeName ?? 'this employee'}.`
                        : `${creatingAt.roleName} shift is open and ready for reassignment.`,
                    });
                  } catch (error) {
                    setSchedulerNotice({
                      tone: 'error',
                      title: 'Could not create shift',
                      detail: error instanceof Error ? error.message : 'Please try again.',
                    });
                  }
                })();
              }}
            />
          )}
        </AnimatePresence>

        {/* ─── Edit Shift Modal ─── */}
        <AnimatePresence>
          {editingShift && (
            <EditShiftModal
              dark={isDark}
              shiftDefaults={shiftDefaults}
              shift={editingShift}
              employeeName={
                editingShift.employeeId
                  ? schedulerEmployees.find((employee) => employee.id === editingShift.employeeId)?.name || 'Assigned Employee'
                  : editingShift.displayEmployeeName
                    ? `${editingShift.displayEmployeeName} · Needs Reassignment`
                    : 'Needs Reassignment'
              }
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
              employeesCount={new Set(shifts.map((s) => s.employeeId).filter(Boolean)).size}
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
              shifts={assignedShiftsForPublishing}
              employees={activeEmployees}
              onClose={() => setShowPublishModal(false)}
              onComplete={() => {
                setShowPublishModal(false);
                setSchedulerNotice({
                  tone: 'success',
                  title: 'Schedule published',
                });
              }}
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {removingEmployee ? (
            <RemoveEmployeeModal
              dark={isDark}
              employeeName={removingEmployee.name}
              hasShifts={removingEmployee.hasShifts}
              shiftCount={shifts.filter((shift) => shift.employeeId === removingEmployee.id).length}
              isLoading={isRemovingEmployee}
              onClose={() => setRemovingEmployee(null)}
              onConfirm={confirmRemoveEmployee}
            />
          ) : null}
        </AnimatePresence>

        <AnimatePresence>
          {addEmployeeContext ? (
            <AddEmployeeModal
              activeTab={addEmployeeTab}
              businessEmployees={businessEmployees}
              businessId={location.business_id}
              businessLocations={businessLocations}
              businessRoles={businessRoles}
              dark={isDark}
              loadingBusinessEmployees={loadingSchedulerData}
              locationId={location.location_id}
              locationName={locationDisplayName}
              roleId={addEmployeeContext?.roleId ?? ''}
              roleName={addEmployeeContext?.roleName ?? ''}
              activeEmployeeIds={locationEmployeeIds}
              onActiveTabChange={setAddEmployeeTab}
              onAttach={addEmployeeToLocation}
              onClose={() => {
                setAddEmployeeTab('existing');
                setAddEmployeeContext(null);
              }}
              onAdd={addEmployeeToLocation}
            />
          ) : null}
        </AnimatePresence>

        {/* ─── Toasts ─── */}
        <AnimatePresence>
          {schedulerNotice && (
            <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 30 }}
              className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-5 py-3.5 rounded-2xl shadow-2xl ${theme.toastClass}`}>
              <div className={`w-7 h-7 rounded-full flex items-center justify-center ${
                schedulerNotice.tone === 'success'
                  ? 'bg-[#00B893]/20'
                  : schedulerNotice.tone === 'error'
                    ? 'bg-[#E5484D]/20'
                    : 'bg-[#635BFF]/20'
              }`}>
                {schedulerNotice.tone === 'success' ? (
                  <Check size={14} className="text-[#00B893]" />
                ) : schedulerNotice.tone === 'error' ? (
                  <AlertTriangle size={14} className="text-[#E5484D]" />
                ) : (
                  <Info size={14} className="text-[#635BFF]" />
                )}
              </div>
              <div>
                <p className="text-[12px] text-white" style={{ fontWeight: 520 }}>{schedulerNotice.title}</p>
                {schedulerNotice.detail ? (
                  <p className={`text-[10px] mt-0.5 ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                    {schedulerNotice.detail}
                  </p>
                ) : null}
              </div>
              <button onClick={() => setSchedulerNotice(null)} className="p-1 rounded-lg hover:bg-white/10 transition-colors ml-2">
                <X size={12} className={theme.textSecondary} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
        {editorLocation ? (
            <LocationRoleEditor
              dark={isDark}
              location={editorLocation}
              employees={editorEmployees}
              assignments={editorAssignments}
              shiftDefaults={editorShiftDefaults}
              staffCount={editorStaffCount}
              loading={editorLoading}
              saving={isSavingEditor}
              feedback={editorFeedback}
              deleteState={{
                ...effectiveDeleteState,
                deleting: deletingLocationId === editorLocation.id,
              }}
              onClose={closeLocationEditor}
              onDelete={() => {
                void handleDeleteLocation();
              }}
              onSave={handleSaveEditor}
            />
          ) : null}
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

function MobileEmployeeCard({
  dark = false,
  employee,
  empWeekHours,
  cellShifts,
  isSwiped,
  onSwipe,
  onRemove,
  onEditShift,
  onCreateShift,
}: {
  dark?: boolean;
  employee: Employee;
  empWeekHours: number;
  cellShifts: Shift[];
  isSwiped: boolean;
  onSwipe: (id: string) => void;
  onRemove: () => void;
  onEditShift: (shift: Shift) => void;
  onCreateShift: () => void;
}) {
  const [touchStart, setTouchStart] = useState<number | null>(null);
  const [touchEnd, setTouchEnd] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const minSwipeDistance = 50;

  const onTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    setTouchEnd(null);
    setTouchStart(event.targetTouches[0].clientX);
    setIsDragging(false);
  };

  const onTouchMove = (event: TouchEvent<HTMLDivElement>) => {
    setTouchEnd(event.targetTouches[0].clientX);
    setIsDragging(true);
  };

  const onTouchEnd = () => {
    if (touchStart === null || touchEnd === null) {
      return;
    }

    const distance = touchStart - touchEnd;
    if (distance > minSwipeDistance) {
      onSwipe(employee.id);
    } else if (distance < -minSwipeDistance) {
      onSwipe('');
    } else if (!isSwiped) {
      onSwipe('');
    }

    setIsDragging(false);
  };

  return (
    <div className="relative overflow-hidden rounded-xl">
      <div className="absolute inset-y-0 right-0 w-20 bg-red-500 flex items-center justify-center rounded-xl">
        <UserMinus size={18} className="text-white" />
      </div>

      <motion.div
        className={`flex items-center gap-3 p-2.5 rounded-xl border relative touch-pan-y ${dark ? 'border-white/[0.08] bg-[#0F2E4C]' : 'border-[#E5E7EB] bg-white'}`}
        animate={{ x: isSwiped ? -80 : 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        <img src={employee.avatar} alt={employee.name}
          className={`w-8 h-8 rounded-full object-cover shrink-0 ring-1 ${dark ? 'ring-white/[0.08]' : 'ring-[#E5E7EB]'}`} />
        <div className="flex-1 min-w-0">
          <p className={`text-[12px] truncate ${dark ? 'text-white' : 'text-[#0A2540]'}`} style={{ fontWeight: 500 }}>{employee.name}</p>
          <p className={`text-[10px] ${dark ? 'text-[#C1CED8]' : 'text-[#8898AA]'}`} style={{ fontWeight: 420 }}>{empWeekHours}h this week</p>
        </div>
        {cellShifts.length > 0 ? (
          <div className="flex flex-col gap-1">
            {cellShifts.map((shift) => {
              const desc = getShiftDescriptor(shift.startHour, shift.endHour);
              const DescIcon = shift.presetKey ? getShiftDefaultIcon(shift.presetKey) : desc.icon;
              const shiftLabel = shift.presetLabel?.trim() || desc.label;
              const dur = shiftDuration(shift);
              return (
                <button
                  key={shift.id}
                  onClick={() => {
                    if (!isDragging) {
                      onEditShift(shift);
                    }
                  }}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-all"
                  style={{ background: `${shift.color}10` }}
                  type="button"
                >
                  <DescIcon size={10} style={{ color: shift.color }} />
                  <span className="text-[10px]" style={{ fontWeight: 520, color: shift.color }}>{shiftLabel}</span>
                  <span className={`text-[9px] ${dark ? 'text-[#C1CED8]' : 'text-[#8898AA]'}`} style={{ fontWeight: 400 }}>{dur}h</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className={`p-1.5 rounded-lg transition-colors border border-dashed ${dark ? 'border-white/[0.08]' : 'border-[#E5E7EB]'}`}>
            <Plus size={14} className="text-[#C1CED8]/40" />
          </div>
        )}
      </motion.div>

      <AnimatePresence>
        {isSwiped ? (
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onRemove}
            className="absolute inset-y-0 right-0 w-20 bg-red-500 flex items-center justify-center active:bg-red-600 rounded-xl"
            type="button"
          >
            <UserMinus size={18} className="text-white" />
          </motion.button>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function RemoveEmployeeModal({
  dark = false,
  employeeName,
  hasShifts,
  shiftCount,
  isLoading = false,
  onClose,
  onConfirm,
}: {
  dark?: boolean;
  employeeName: string;
  hasShifts: boolean;
  shiftCount: number;
  isLoading?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const borderClass = dark ? 'border-white/[0.08]' : 'border-[#E5E7EB]';
  const panelClass = dark ? 'bg-[#0F2E4C] border-white/[0.08]' : 'bg-white border-[#E5E7EB]';
  const textPrimary = dark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]';

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90vw] max-w-[420px] rounded-2xl shadow-2xl border overflow-hidden ${panelClass}`}>
        <div className={`px-6 py-5 border-b flex items-start justify-between ${borderClass}`}>
          <div className="flex items-start gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${hasShifts ? 'bg-orange-50' : 'bg-red-50'}`}>
              {hasShifts ? (
                <AlertTriangle size={18} className="text-orange-500" />
              ) : (
                <UserMinus size={18} className="text-red-500" />
              )}
            </div>
            <div>
              <h3 className={`text-[16px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                Remove {employeeName}?
              </h3>
              <p className={`text-[12px] mt-1 ${dark ? 'text-[#8898AA]' : 'text-[#8898AA]'}`} style={{ fontWeight: 420 }}>
                {hasShifts
                  ? `This person has ${shiftCount} scheduled shift${shiftCount !== 1 ? 's' : ''}`
                  : 'Remove this person from the scheduler'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className={`p-1.5 rounded-lg ${dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]'} transition-colors`} type="button">
            <X size={16} className="text-[#8898AA]" />
          </button>
        </div>

        <div className="px-6 py-5">
          {hasShifts ? (
            <div className="space-y-3">
              <p className={`text-[13px] ${textSecondary} leading-[1.6]`}>
                <span className={`font-medium ${textPrimary}`}>{employeeName}</span> still has assigned shifts.
              </p>
              <ul className="space-y-2 ml-4">
                <li className={`text-[12px] ${textSecondary} flex items-start gap-2`}>
                  <span className="text-orange-500 mt-0.5">•</span>
                  <span>Assigned shifts cannot be removed from this real-data scheduler yet</span>
                </li>
                <li className={`text-[12px] ${textSecondary} flex items-start gap-2`}>
                  <span className="text-orange-500 mt-0.5">•</span>
                  <span>Clear or reassign those shifts before removing them from this location</span>
                </li>
              </ul>
            </div>
          ) : (
            <p className={`text-[13px] ${textSecondary} leading-[1.6]`}>
              <span className={`font-medium ${textPrimary}`}>{employeeName}</span> will be removed from this location&apos;s scheduler. You can add them back anytime.
            </p>
          )}
        </div>

        <div className={`px-6 py-4 border-t flex gap-2.5 ${borderClass}`}>
          <button onClick={onClose}
            className={`flex-1 py-2.5 rounded-xl border text-[12px] transition-colors ${dark ? 'border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]' : 'border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]'}`}
            style={{ fontWeight: 500 }}
            disabled={isLoading}
            type="button">
            Cancel
          </button>
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={onConfirm}
            className={`flex-1 py-2.5 rounded-xl text-[12px] text-white transition-all flex items-center justify-center gap-2 ${
              hasShifts ? 'bg-orange-500 hover:bg-orange-600' : 'bg-red-500 hover:bg-red-600'
            }`}
            style={{ fontWeight: 540 }}
            disabled={isLoading}
            type="button">
            <UserMinus size={13} />
            {isLoading ? 'Removing...' : hasShifts ? 'Understood' : 'Remove'}
          </motion.button>
        </div>
      </motion.div>
    </>
  );
}

function AddEmployeeModal({
  activeTab,
  businessEmployees,
  businessId,
  businessLocations,
  businessRoles,
  dark = false,
  loadingBusinessEmployees,
  locationId,
  locationName,
  roleId,
  roleName,
  activeEmployeeIds,
  onActiveTabChange,
  onAttach,
  onClose,
  onAdd,
}: {
  activeTab: 'existing' | 'new';
  businessEmployees: EmployeeSummary[];
  businessId: string;
  businessLocations: BusinessLocation[];
  businessRoles: BusinessRole[];
  dark?: boolean;
  loadingBusinessEmployees: boolean;
  locationId: string;
  locationName: string;
  roleId: string;
  roleName: string;
  activeEmployeeIds: Set<string>;
  onActiveTabChange: (tab: 'existing' | 'new') => void;
  onAttach: (employee: EmployeeSummary) => void;
  onClose: () => void;
  onAdd: (employee: EmployeeSummary) => void;
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const searchableEmployees = useMemo(
    () =>
      businessEmployees.filter((employee) => !activeEmployeeIds.has(employee.id)),
    [activeEmployeeIds, businessEmployees],
  );
  const scopedEmployees = useMemo(
    () =>
      searchableEmployees.filter(
        (employee) =>
          employee.role_ids.includes(roleId) || employee.role_ids.length === 0,
      ),
    [roleId, searchableEmployees],
  );
  const filteredEmployees = useMemo(
    () =>
      scopedEmployees.filter((employee) => {
        const normalizedQuery = searchQuery.trim().toLowerCase();
        if (!normalizedQuery) {
          return true;
        }
        return (
          employee.full_name.toLowerCase().includes(normalizedQuery) ||
          employee.role_names.some((role) => role.toLowerCase().includes(normalizedQuery))
        );
      }),
    [scopedEmployees, searchQuery],
  );
  const availableReadyEmployees = useMemo(
    () => filteredEmployees.filter((employee) => employee.role_ids.includes(roleId)),
    [filteredEmployees, roleId],
  );
  const availableUnavailableEmployees = useMemo(
    () => filteredEmployees.filter((employee) => employee.role_names.length === 0),
    [filteredEmployees],
  );
  const canOpenNewTab =
    !loadingBusinessEmployees &&
    businessLocations.length > 0 &&
    businessRoles.some((role) => role.id === roleId);
  const borderClass = dark ? 'border-white/[0.08]' : 'border-[#E5E7EB]';
  const panelClass = dark ? 'bg-[#0F2E4C] border-white/[0.08]' : 'bg-white border-[#E5E7EB]';
  const textPrimary = dark ? 'text-white' : 'text-[#0A2540]';
  const textSecondary = dark ? 'text-[#C1CED8]' : 'text-[#8898AA]';

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 0.3 }} exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black z-40" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2 }}
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[90vw] max-w-[480px] rounded-2xl shadow-2xl border overflow-hidden ${panelClass}`}>
        <div className={`px-6 py-5 border-b flex items-center justify-between ${borderClass}`}>
          <div>
            <h3 className={`text-[17px] ${textPrimary}`} style={{ fontWeight: 600 }}>Add Employee</h3>
            <p className={`text-[11px] mt-1 ${textSecondary}`} style={{ fontWeight: 440 }}>
              Add someone to {roleName} at {locationName}
            </p>
          </div>
          <button onClick={onClose} className={`p-1.5 rounded-lg ${dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]'} transition-colors`} type="button">
            <X size={18} className="text-[#8898AA]" />
          </button>
        </div>

        <div className={`px-6 py-4 border-b ${borderClass}`}>
          <div className={`flex items-center gap-1 rounded-lg p-0.5 ${dark ? 'bg-white/[0.04]' : 'bg-[#F0F0F5]'}`}>
            {[
              { value: 'existing', label: 'Existing' },
              { value: 'new', label: 'New Employee' },
            ].map((tab) => {
              const selected = activeTab === tab.value;
              const disabled = tab.value === 'new' ? !canOpenNewTab : false;
              return (
                <button
                  key={tab.value}
                  onClick={() => {
                    if (!disabled) {
                      onActiveTabChange(tab.value as 'existing' | 'new');
                    }
                  }}
                  className={`flex-1 rounded-md py-2 text-[12px] transition-all duration-200 ${
                    selected
                      ? dark
                        ? 'bg-white/[0.08] text-white shadow-[0_1px_3px_rgba(0,0,0,0.25)]'
                        : 'bg-white text-[#0A2540] shadow-sm'
                      : `${textSecondary} ${disabled ? 'opacity-50' : dark ? 'hover:text-white' : 'hover:text-[#0A2540]'}`
                  }`}
                  disabled={disabled}
                  style={{ fontWeight: selected ? 520 : 440 }}
                  type="button"
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>

        {activeTab === 'existing' ? (
          <div className="px-6 py-4 max-h-[420px] overflow-y-auto">
            {scopedEmployees.length > 0 ? (
              <div className="pb-3">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search by name or role..."
                  className={`w-full px-3.5 py-2.5 border rounded-xl text-[13px] placeholder:text-[#8898AA] focus:border-[#635BFF]/40 focus:outline-none focus:ring-2 focus:ring-[#635BFF]/10 transition-all ${
                    dark
                      ? 'border-white/[0.08] bg-white/[0.04] text-white'
                      : 'border-[#E5E7EB] bg-white text-[#0A2540]'
                  }`}
                  style={{ fontWeight: 440 }}
                />
              </div>
            ) : null}

            {loadingBusinessEmployees ? (
              <div className="py-8 text-center">
                <p className={`text-[13px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                  Loading business employees...
                </p>
              </div>
            ) : scopedEmployees.length === 0 ? (
              <div className="py-8 text-center">
                <div className={`w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3 ${dark ? 'bg-white/[0.04]' : 'bg-[#F7F8FA]'}`}>
                  <UserPlus size={20} className="text-[#8898AA]" />
                </div>
                <p className={`text-[13px] ${dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'}`} style={{ fontWeight: 480 }}>
                  {businessEmployees.length === 0
                    ? 'No employees found yet'
                    : `All ${roleName} employees are already added`}
                </p>
                {businessEmployees.length === 0 ? (
                  <p className={`mt-1 text-[11px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                    Use New Employee to add someone to this scheduler.
                  </p>
                ) : null}
              </div>
            ) : filteredEmployees.length === 0 ? (
              <div className="py-8 text-center">
                <p className="text-[13px] text-[#8898AA]" style={{ fontWeight: 440 }}>
                  No employees match &quot;{searchQuery}&quot;
                </p>
              </div>
            ) : (
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h4 className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 500 }}>
                    Available {roleName}
                  </h4>
                  <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                    {availableReadyEmployees.length} of {filteredEmployees.length}
                  </span>
                </div>
                {availableReadyEmployees.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {availableReadyEmployees.map((employee) => (
                      <button
                        key={employee.id}
                        onClick={() => onAdd(employee)}
                        className={`group flex items-center gap-2 rounded-lg border px-3 py-1.5 transition-all duration-200 ${
                          dark
                            ? 'bg-white/[0.03] border-white/[0.08] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]'
                            : 'bg-[#F7F8FA] border-[#E5E7EB] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]'
                        }`}
                        type="button"
                      >
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#635BFF]/10 text-[10px] text-[#635BFF]">
                          {employeeInitials(employee.full_name)}
                        </span>
                        <span
                          className={`text-[12px] transition-colors ${
                            dark
                              ? 'text-[#C1CED8] group-hover:text-white'
                              : 'text-[#5E6D7A] group-hover:text-[#0A2540]'
                          }`}
                          style={{ fontWeight: 440 }}
                        >
                          {employee.full_name}
                        </span>
                        <Plus
                          size={11}
                          className="ml-0.5 text-[#8898AA] transition-colors group-hover:text-[#635BFF]"
                        />
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className={`py-2 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                    All employees with the {roleName} role are already added to this scheduler.
                  </p>
                )}

                {availableUnavailableEmployees.length > 0 ? (
                  <div className="mt-5">
                    <div className="mb-2.5">
                      <h4 className={`text-[11px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 500 }}>
                        Needs role assignment
                      </h4>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {availableUnavailableEmployees.map((employee) => (
                        <div
                          key={employee.id}
                          className={`group relative z-0 flex items-center gap-2 rounded-lg border px-3 py-1.5 text-left transition-all duration-200 hover:z-20 ${
                            dark
                              ? 'border-[#FFB800]/25 bg-[#FFB800]/[0.1] hover:bg-[#FFB800]/[0.14]'
                              : 'border-[#FFB800]/20 bg-[#FFB800]/[0.06] hover:bg-[#FFB800]/[0.1]'
                          }`}
                        >
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#FFB800]/10 text-[10px] text-[#FFB800]">
                            {employeeInitials(employee.full_name)}
                          </span>
                          <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                            {employee.full_name}
                          </span>
                          <div className="relative ml-0.5">
                            <Info size={12} className="cursor-default text-[#FFB800]" />
                            <div
                              className={`pointer-events-none absolute bottom-full right-0 z-30 mb-2 w-56 rounded-lg px-3 py-2 text-[11px] opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 ${
                                dark
                                  ? 'border border-white/[0.08] bg-[#102B46] text-[#C1CED8]'
                                  : 'border border-[#E5E7EB] bg-white text-[#5E6D7A]'
                              }`}
                              style={{ fontWeight: 440 }}
                            >
                              Assign at least one role before adding this employee to the scheduler.
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ) : (
          <div className="px-6 py-6">
            <div className={`rounded-2xl border px-4 py-4 ${
              dark
                ? 'border-white/[0.08] bg-white/[0.03]'
                : 'border-[#E5E7EB] bg-[#FAFBFC]'
            }`}>
              <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                Open the employee enrollment flow
              </p>
              <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                This employee will be created directly inside {locationName} with the {roleName} role already assigned.
              </p>
              {!canOpenNewTab ? (
                <p className={`mt-3 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Loading live roles and locations for this business...
                </p>
              ) : null}
            </div>
          </div>
        )}
      </motion.div>

      <AnimatePresence>
        {activeTab === 'new' && canOpenNewTab ? (
          <SchedulerEmployeeEnrollmentModal
            businessId={businessId}
            businessLocations={businessLocations}
            dark={dark}
            locationId={locationId}
            locationName={locationName}
            roleId={roleId}
            roleName={roleName}
            onClose={() => onActiveTabChange('existing')}
            onCreated={(employee) => {
              onAttach(employee);
              onClose();
            }}
            roles={businessRoles}
          />
        ) : null}
      </AnimatePresence>
    </>
  );
}

/* ─── Quick Create Modal ─── */
function QuickCreateModal({ employeeName, dayLabel, role, shiftDefaults, onClose, onCreate, dark = false }: {
  employeeName: string; dayLabel: string; role: string; shiftDefaults: ShiftDefault[];
  onClose: () => void;
  onCreate: (start: number, end: number, presetKey: ShiftDefaultKey, presetLabel: string) => void;
  dark?: boolean;
}) {
  const normalizedDefaults = useMemo(
    () => normalizeShiftDefaults(shiftDefaults),
    [shiftDefaults],
  );
  const initialPreset = normalizedDefaults[0] ?? SHIFT_DEFAULT_FALLBACKS[0];
  const [selectedPresetKey, setSelectedPresetKey] = useState<ShiftDefaultKey>(initialPreset.key);
  const [startHour, setStartHour] = useState(initialPreset.start_hour);
  const [endHour, setEndHour] = useState(initialPreset.end_hour);
  const accentColor = roleColor(role);
  const hourOptions = TIME_VALUES.map(h => ({ label: formatHour(h), value: String(h) }));
  const theme = getSchedulerTheme(dark);

  useEffect(() => {
    const selectedPreset =
      normalizedDefaults.find((preset) => preset.key === selectedPresetKey) ??
      normalizedDefaults[0];
    if (!selectedPreset) {
      return;
    }
    setSelectedPresetKey(selectedPreset.key);
    setStartHour(selectedPreset.start_hour);
    setEndHour(selectedPreset.end_hour);
  }, [normalizedDefaults, selectedPresetKey]);

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
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg w-fit" style={{ background: `${accentColor}10` }}>
            <div className="w-2 h-2 rounded-full" style={{ background: accentColor }} />
            <span className="text-[11px]" style={{ fontWeight: 520, color: accentColor }}>{role}</span>
          </div>
        </div>
        <div className="px-5 pt-3 pb-2">
          <p className={`text-[10px] uppercase tracking-[0.05em] mb-2 ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Quick Fill</p>
          <div className="grid grid-cols-4 gap-2">
            {normalizedDefaults.map((preset) => {
              const Icon = getShiftDefaultIcon(preset.key);
              const accent = getShiftDefaultColor(preset.key);
              const isActive = selectedPresetKey === preset.key;
              return (
                <button key={preset.key}
                  onClick={() => {
                    setSelectedPresetKey(preset.key);
                    setStartHour(preset.start_hour);
                    setEndHour(preset.end_hour);
                  }}
                  className={`flex flex-col items-center gap-1 py-2 rounded-xl border transition-all ${
                    isActive
                      ? 'border-[#635BFF]/30 bg-[#635BFF]/[0.08]'
                      : dark
                        ? 'border-white/[0.08] hover:border-[#635BFF]/20 hover:bg-[#635BFF]/[0.04]'
                        : 'border-[#E5E7EB] hover:border-[#635BFF]/20 hover:bg-[#635BFF]/[0.02]'
                  }`}>
                  <Icon size={13} style={{ color: isActive ? '#635BFF' : accent }} />
                  <span className={`text-[10px] ${isActive ? 'text-[#635BFF]' : dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'}`} style={{ fontWeight: isActive ? 540 : 480 }}>{preset.label}</span>
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
            onClick={() =>
              onCreate(
                startHour,
                endHour,
                selectedPresetKey,
                resolveShiftLabel(normalizedDefaults, selectedPresetKey, startHour, endHour),
              )
            }
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
function EditShiftModal({ shift, employeeName, shiftDefaults, onClose, onSave, onDelete, dark = false }: {
  shift: Shift; employeeName: string; shiftDefaults: ShiftDefault[]; onClose: () => void; onSave: (s: Shift) => void; onDelete: () => void; dark?: boolean;
}) {
  const normalizedDefaults = useMemo(
    () => normalizeShiftDefaults(shiftDefaults),
    [shiftDefaults],
  );
  const matchedPreset = normalizedDefaults.find(
    (preset) =>
      preset.key === shift.presetKey ||
      (preset.start_hour === shift.startHour && preset.end_hour === shift.endHour),
  );
  const [selectedPresetKey, setSelectedPresetKey] = useState<ShiftDefaultKey | null>(
    matchedPreset?.key ?? shift.presetKey ?? null,
  );
  const [startHour, setStartHour] = useState(shift.startHour);
  const [endHour, setEndHour] = useState(shift.endHour);
  const accentColor = shift.color || roleColor(shift.role);
  const descriptor = getShiftDescriptor(startHour, endHour);
  const hourOptions = TIME_VALUES.map(h => ({ label: formatHour(h), value: String(h) }));
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
              <div className="w-3 h-3 rounded-full" style={{ background: accentColor }} />
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
          {selectedPresetKey ? (
            (() => {
              const Icon = getShiftDefaultIcon(selectedPresetKey);
              const shiftLabel = resolveShiftLabel(normalizedDefaults, selectedPresetKey, startHour, endHour) || descriptor.label;
              return (
                <>
                  <Icon size={14} style={{ color: accentColor }} />
                  <span className="text-[12px]" style={{ fontWeight: 520, color: accentColor }}>{shiftLabel} Shift</span>
                </>
              );
            })()
          ) : (
            <>
              <descriptor.icon size={14} style={{ color: accentColor }} />
              <span className="text-[12px]" style={{ fontWeight: 520, color: accentColor }}>{descriptor.label} Shift</span>
            </>
          )}
          <span className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
            · {endHour > startHour ? endHour - startHour : 24 - startHour + endHour}h
          </span>
        </div>
        <div className="px-5 pt-3 pb-2">
          <div className="grid grid-cols-4 gap-2">
            {normalizedDefaults.map((preset) => {
              const Icon = getShiftDefaultIcon(preset.key);
              const isActive =
                selectedPresetKey === preset.key ||
                (selectedPresetKey === null &&
                  startHour === preset.start_hour &&
                  endHour === preset.end_hour);
              return (
                <button key={preset.key}
                  onClick={() => {
                    setSelectedPresetKey(preset.key);
                    setStartHour(preset.start_hour);
                    setEndHour(preset.end_hour);
                  }}
                  className={`flex flex-col items-center gap-1 py-2 rounded-xl border transition-all ${
                    isActive
                      ? 'border-[#635BFF]/30 bg-[#635BFF]/[0.08]'
                      : dark
                        ? 'border-white/[0.08] hover:border-[#635BFF]/20 hover:bg-[#635BFF]/[0.04]'
                        : 'border-[#E5E7EB] hover:border-[#635BFF]/20 hover:bg-[#635BFF]/[0.02]'
                  }`}>
                  <Icon size={13} className={isActive ? 'text-[#635BFF]' : dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'} />
                  <span className={`text-[10px] ${isActive ? 'text-[#635BFF]' : dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]'}`} style={{ fontWeight: isActive ? 540 : 480 }}>{preset.label}</span>
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
              onClick={() =>
                onSave({
                  ...shift,
                  startHour,
                  endHour,
                  presetKey: selectedPresetKey,
                  presetLabel:
                    resolveShiftLabel(
                      normalizedDefaults,
                      selectedPresetKey,
                      startHour,
                      endHour,
                    ) || shift.presetLabel || descriptor.label,
                })
              }
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
