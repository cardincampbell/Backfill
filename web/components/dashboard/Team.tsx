"use client";

import { useState, useRef, useCallback, useEffect, useMemo, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { usePathname, useRouter, useSelectedLayoutSegments } from 'next/navigation';
import {
  Plus,
  Upload,
  Search,
  Check,
  ChevronDown,
  X,
  CheckCircle2,
  AlertCircle,
  FileSpreadsheet,
  UserPlus,
  UserMinus,
  ArrowUpDown,
  Download,
  Eye,
  MapPin,
  Activity,
  Tag,
  Shield as ShieldCheck,
  Info,
} from 'lucide-react';
import { useResolvedAppAppearance } from '@/components/app-session-gate';
import { useAppWorkspace, useAppWorkspaceReady } from '@/components/app-workspace';
import { FloatingDropdown } from '@/components/floating-dropdown';
import {
  listBusinessLocations,
  listBusinessRoles,
  type BusinessLocation,
  type BusinessRole,
} from '@/lib/api/businesses';
import {
  createEmployee,
  deleteEmployee,
  downloadEmployeeImportTemplate,
  getEmployeeDeleteReadiness,
  importEmployees,
  listEmployees,
  updateEmployee,
  type EmployeeBulkImportResponse,
  type EmployeeProfile,
  type EmployeeSummary,
} from '@/lib/api/workforce';
import { buildTeamEmployeeEditPath } from '@/lib/dashboard-paths';
import { resolvePreferredWorkspaceBusiness } from '@/lib/workspace-business';
import DashboardShell from './DashboardShell';
import { EmployeeEditorDrawer, type EmployeeEditorSeed } from './EmployeeEditorDrawer';
import {
  EmployeeBulkUploadModal,
  EmployeeEnrollmentModal,
} from './LocationEmployeeActions';
import { formatLocationMeta, getLocationReference } from './location-role-reference';

/* ─── Types ─── */
interface EmployeeLocation {
  id?: string;
  name: string;
  emoji: string;
  meta?: string;
  primary: boolean;
}

interface Employee {
  id: string;
  name: string;
  email: string;
  phone: string;
  roles: string[];
  locations: EmployeeLocation[];
  status: 'active' | 'on_leave' | 'inactive' | 'needs_attention';
  statusReason?: string;
  reliability: number;
  avatar: string;
}

function TeamLoadingSkeleton({ dark }: { dark: boolean }) {
  return (
    <div
      className={`overflow-hidden rounded-2xl border ${
        dark ? 'border-white/[0.06] bg-[#0F2E4C]' : 'border-[#E5E7EB] bg-white'
      }`}
    >
      <div
        className={`border-b px-5 py-4 ${
          dark ? 'border-white/[0.08] bg-white/[0.03]' : 'border-[#F0F0F5] bg-[#FAFBFC]'
        }`}
      >
        <div className="flex items-center gap-3">
          <div className="skeleton" style={{ width: 18, height: 18, borderRadius: 6 }} />
          <div className="skeleton skeleton-text" style={{ width: 132, marginBottom: 0 }} />
        </div>
      </div>
      <div className="px-5 py-5">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="skeleton skeleton-card" />
          <div className="skeleton skeleton-card" />
          <div className="skeleton skeleton-card" />
        </div>
        <div className="mt-5 space-y-3">
          <div className="skeleton" style={{ width: '100%', height: 44, borderRadius: 14 }} />
          <div className="skeleton" style={{ width: '100%', height: 44, borderRadius: 14 }} />
          <div className="skeleton" style={{ width: '100%', height: 44, borderRadius: 14 }} />
          <div className="skeleton" style={{ width: '100%', height: 44, borderRadius: 14 }} />
          <div className="skeleton skeleton-table" />
        </div>
      </div>
    </div>
  );
}

type AddEmployeeFormState = {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  roleId: string;
  locationId: string;
};

type TeamLocationLike = Pick<
  BusinessLocation,
  | 'id'
  | 'name'
  | 'display_name'
  | 'slug'
  | 'address_line_1'
  | 'locality'
  | 'region'
  | 'postal_code'
  | 'timezone'
>;

const seededEmployeeNames = [
  'Sarah Martinez',
  'James Chen',
  'Aisha Patel',
  'Emily Ross',
  'David Kim',
  'Carlos Rivera',
  'Mia Johnson',
  'Marcus Thompson',
  'Priya Sharma',
  'Alex Morgan',
  'Jordan Lee',
  'Nina Patel',
];

/* ─── Mock Data ─── */
const employees: Employee[] = [
  { id: '1', name: 'Sarah Martinez', email: 'sarah.m@backfill.io', phone: '(415) 555-0142', roles: ['RN'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }, { name: 'Bay Area Staffing Co.', emoji: '\u{1F3E2}', primary: false }], status: 'active', reliability: 98, avatar: 'SM' },
  { id: '2', name: 'James Chen', email: 'james.c@backfill.io', phone: '(415) 555-0198', roles: ['LPN'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }], status: 'active', reliability: 96, avatar: 'JC' },
  { id: '3', name: 'Aisha Patel', email: 'aisha.p@backfill.io', phone: '(415) 555-0176', roles: ['CNA'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }], status: 'active', reliability: 94, avatar: 'AP' },
  { id: '4', name: 'Emily Ross', email: 'emily.r@backfill.io', phone: '(510) 555-0234', roles: ['Caregiver'], locations: [{ name: 'Sunrise Senior Living', emoji: '\u{1F305}', primary: true }], status: 'active', reliability: 99, avatar: 'ER' },
  { id: '5', name: 'David Kim', email: 'david.k@backfill.io', phone: '(510) 555-0187', roles: ['CNA'], locations: [{ name: 'Sunrise Senior Living', emoji: '\u{1F305}', primary: true }], status: 'on_leave', reliability: 91, avatar: 'DK' },
  { id: '6', name: 'Carlos Rivera', email: 'carlos.r@backfill.io', phone: '(408) 555-0165', roles: ['RN', 'EMT'], locations: [{ name: 'Bay Area Staffing Co.', emoji: '\u{1F3E2}', primary: true }, { name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: false }], status: 'active', reliability: 97, avatar: 'CR' },
  { id: '7', name: 'Mia Johnson', email: 'mia.j@backfill.io', phone: '(831) 555-0119', roles: ['Server Lead'], locations: [{ name: 'Coastal Hospitality Group', emoji: '\u{1F3E8}', primary: true }], status: 'active', reliability: 99, avatar: 'MJ' },
  { id: '8', name: 'Marcus Thompson', email: 'marcus.t@backfill.io', phone: '(415) 555-0203', roles: ['RN'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }], status: 'inactive', reliability: 85, avatar: 'MT' },
  { id: '9', name: 'Priya Sharma', email: 'priya.s@backfill.io', phone: '(408) 555-0291', roles: ['LPN', 'Phlebotomist'], locations: [{ name: 'Bay Area Staffing Co.', emoji: '\u{1F3E2}', primary: true }], status: 'active', reliability: 95, avatar: 'PS' },
  { id: '10', name: 'Alex Morgan', email: 'alex.m@backfill.io', phone: '(510) 555-0148', roles: ['Caregiver'], locations: [{ name: 'Sunrise Senior Living', emoji: '\u{1F305}', primary: true }], status: 'inactive', reliability: 96, avatar: 'AM' },
  { id: '11', name: 'Jordan Lee', email: 'jordan.l@backfill.io', phone: '(415) 555-0177', roles: ['CNA'], locations: [{ name: 'Downtown Medical Center', emoji: '\u{1F3E5}', primary: true }], status: 'active', reliability: 92, avatar: 'JL' },
  { id: '12', name: 'Nina Patel', email: 'nina.p@backfill.io', phone: '(831) 555-0205', roles: ['Bartender', 'Host'], locations: [{ name: 'Coastal Hospitality Group', emoji: '\u{1F3E8}', primary: true }], status: 'active', reliability: 94, avatar: 'NP' },
];

const roleColors: Record<string, string> = {
  'RN': '#635BFF', 'LPN': '#3B82F6', 'CNA': '#00B893', 'Caregiver': '#8B5CF6',
  'Temp RN': '#F59E0B', 'Temp LPN': '#F59E0B', 'Server Lead': '#FF6B35', 'Bartender': '#E5484D',
};

const statusConfig = {
  active: { label: 'Active', color: '#00B893', bg: '#00B893', description: 'Included in normal scheduling and outreach.' },
  on_leave: { label: 'On Leave', color: '#635BFF', bg: '#635BFF', description: 'Temporarily unavailable until they return.' },
  inactive: { label: 'Inactive', color: '#8898AA', bg: '#8898AA', description: 'Excluded from active scheduling.' },
  needs_attention: { label: 'Needs Attention', color: '#F59E0B', bg: '#F59E0B', description: 'Resolve missing assignments to make this employee schedulable.' },
};

function employeeInitials(name: string) {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('') || 'BF';
}

function emailFromName(name: string) {
  return `${name.toLowerCase().replace(/[^a-z0-9]+/g, '.').replace(/(^\.|\.$)/g, '')}@backfill.io`;
}

function normalizeOptional(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function locationDisplayName(location: TeamLocationLike) {
  return location.display_name || location.name;
}

function toEmployeeLocation(location: TeamLocationLike, primary = false): EmployeeLocation {
  const reference = getLocationReference({
    name: locationDisplayName(location),
    slug: location.slug,
  });
  return {
    id: location.id,
    name: locationDisplayName(location),
    emoji: reference.logo,
    meta: formatLocationMeta(location) || location.timezone,
    primary,
  };
}

function buildReferenceEmployees(
  roles: BusinessRole[],
  locations: BusinessLocation[],
): Employee[] {
  if (!roles.length || !locations.length) {
    return employees;
  }

  const statuses: Employee['status'][] = [
    'active',
    'active',
    'active',
    'inactive',
    'active',
    'on_leave',
  ];

  return seededEmployeeNames.map((name, index) => {
    const primaryRole = roles[index % roles.length];
    const secondaryRole =
      roles.length > 1 && index % 4 === 0 ? roles[(index + 1) % roles.length] : null;
    const primaryLocation = locations[index % locations.length];
    const secondaryLocation =
      locations.length > 1 && index % 5 === 0
        ? locations[(index + 1) % locations.length]
        : null;

    return {
      id: `seed-${index + 1}`,
      name,
      email: emailFromName(name),
      phone: `(415) 555-${String(1200 + index * 17).slice(-4)}`,
      roles: [primaryRole.name, secondaryRole?.name].filter(Boolean) as string[],
      locations: [
        toEmployeeLocation(primaryLocation, true),
        ...(secondaryLocation ? [toEmployeeLocation(secondaryLocation)] : []),
      ],
      status: statuses[index % statuses.length],
      reliability: 88 + ((index * 3) % 12),
      avatar: employeeInitials(name),
    };
  });
}

function buildAddEmployeeFormState(): AddEmployeeFormState {
  return {
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    roleId: '',
    locationId: '',
  };
}

function displayNameFromSummary(employee: EmployeeSummary | EmployeeProfile) {
  return employee.preferred_name?.trim() || employee.full_name;
}

function uniqueOrdered(values: Array<string | null | undefined>) {
  const seen = new Set<string>();
  const ordered: string[] = [];
  values.forEach((value) => {
    const normalized = value?.trim();
    if (!normalized || seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    ordered.push(normalized);
  });
  return ordered;
}

function intersectAll(values: string[][]) {
  if (!values.length) {
    return [];
  }
  return values.reduce<string[]>((shared, current) => {
    const currentSet = new Set(current);
    return shared.filter((value) => currentSet.has(value));
  }, uniqueOrdered(values[0]));
}

function mapEmployeeStatus(status: string): Employee['status'] {
  if (status === 'on_leave') {
    return 'on_leave';
  }
  if (status === 'inactive') {
    return 'inactive';
  }
  return 'active';
}

function buildLiveEmployee(
  employee: EmployeeSummary | EmployeeProfile,
  locations: BusinessLocation[],
): Employee {
  const locationById = new Map(locations.map((location) => [location.id, location]));
  const selectedLocations = employee.location_ids.length
    ? employee.location_ids
        .map((id) => {
          const location = locationById.get(id);
          if (location) {
            return toEmployeeLocation(location, id === employee.primary_location_id);
          }
          const nameIndex = employee.location_ids.indexOf(id);
          const name = employee.location_names[nameIndex] ?? 'Unknown Location';
          return {
            id,
            name,
            emoji: getLocationReference({ name }).logo,
            primary: id === employee.primary_location_id,
          };
        })
    : uniqueOrdered(employee.location_names).map((name, index) => ({
        name,
        emoji: getLocationReference({ name }).logo,
        primary: index === 0,
      }));

  const roleNames = uniqueOrdered(employee.role_names);
  const missingRole = roleNames.length === 0;
  const missingLocation = selectedLocations.length === 0;
  const statusReason = missingRole && missingLocation
    ? 'Missing role and location assignments'
    : missingRole
      ? 'Missing role assignment'
      : missingLocation
        ? 'Missing location assignment'
        : undefined;

  return {
    id: employee.id,
    name: displayNameFromSummary(employee),
    email: employee.email ?? '',
    phone: employee.phone_e164 ?? '',
    roles: roleNames,
    locations: selectedLocations,
    status: statusReason ? 'needs_attention' : mapEmployeeStatus(employee.status),
    statusReason,
    reliability: Math.round((employee.reliability_score ?? 0.7) * 100),
    avatar: employeeInitials(displayNameFromSummary(employee)),
  };
}

function buildEmployeeEditorSeed(
  employee: Employee,
  roles: BusinessRole[],
  locations: BusinessLocation[],
): EmployeeEditorSeed {
  const primaryRole = roles.find((role) => role.name === employee.roles[0]) ?? null;
  const primaryLocation =
    locations.find((location) =>
      employee.locations.some(
        (item) =>
          item.primary &&
          (item.id === location.id ||
            item.name === locationDisplayName(location) ||
            item.name === location.name),
      ),
    ) ?? null;

  return {
    id: employee.id,
    full_name: employee.name,
    preferred_name: null,
    email: employee.email,
    phone_e164: employee.phone,
    primary_location_id: primaryLocation?.id ?? employee.locations.find((item) => item.primary)?.id ?? null,
    primary_role_id: primaryRole?.id ?? null,
    role_ids: roles
      .filter((role) => employee.roles.includes(role.name))
      .map((role) => role.id),
    role_names: employee.roles,
    location_ids: locations
      .filter((location) =>
        employee.locations.some(
          (item) =>
            item.id === location.id ||
            item.name === locationDisplayName(location) ||
            item.name === location.name,
        ),
      )
      .map((location) => location.id),
    location_names: employee.locations.map((location) => location.name),
    reliability_score: employee.reliability / 100,
    status: employee.status,
  };
}

/* ─── Status Info Tooltip ─── */
function StatusWithInfo({
  status,
  dark = false,
  descriptionOverride,
}: {
  status: keyof typeof statusConfig;
  dark?: boolean;
  descriptionOverride?: string;
}) {
  const [showTooltip, setShowTooltip] = useState(false);
  const cfg = statusConfig[status];
  const description = descriptionOverride ?? cfg.description;
  return (
    <div className="flex items-center gap-1.5 relative">
      <div className="w-1.5 h-1.5 rounded-full" style={{ background: cfg.color }} />
      <span className="text-[12px]" style={{ fontWeight: 460, color: cfg.color }}>{cfg.label}</span>
      <div className="relative"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}>
        <Info size={12} className={`cursor-default transition-colors ${dark ? 'text-[#5E6D7A] hover:text-[#C1CED8]' : 'text-[#C1CED8] hover:text-[#8898AA]'}`} />
        <AnimatePresence>
          {showTooltip && (
            dark ? (
              <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
                className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 w-48 px-3 py-2 rounded-lg bg-[#0A2540] shadow-xl pointer-events-none">
                <p className="text-[11px] text-white text-center" style={{ fontWeight: 440 }}>{description}</p>
                <div className="absolute top-full left-1/2 -translate-x-1/2 w-2 h-2 bg-[#0A2540] rotate-45 -mt-1" />
              </motion.div>
            ) : (
              <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
                className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 w-48 px-3 py-2.5 rounded-xl bg-white border border-[#E5E7EB] shadow-[0_4px_16px_rgba(0,0,0,0.08),0_1px_3px_rgba(0,0,0,0.04)] pointer-events-none">
                <p className="text-[11px] text-[#3E4C59] text-center" style={{ fontWeight: 440 }}>{description}</p>
              </motion.div>
            )
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function RolesTooltip({
  dark = false,
  roles,
  roleColors: rc,
}: {
  dark?: boolean;
  roles: string[];
  roleColors: Record<string, string>;
}) {
  const [show, setShow] = useState(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span
        className={`cursor-default rounded-full px-1.5 py-0.5 text-[10px] transition-colors ${
          dark ? 'bg-white/[0.06] text-[#C1CED8] hover:bg-white/[0.1]' : 'bg-[#F7F8FA] text-[#8898AA] hover:bg-[#F0F0F5]'
        }`}
        style={{ fontWeight: 440 }}
      >
        +{roles.length}
      </span>
      <AnimatePresence>
        {show && (
          dark ? (
            <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
              className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-[#0A2540] px-3 py-2 shadow-xl pointer-events-none">
              <div className="flex flex-col gap-1.5">
                {roles.map((role) => {
                  const color = rc[role] || '#635BFF';
                  return (
                    <div key={role} className="flex items-center gap-2">
                      <div className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: color }} />
                      <span className="text-[11px] text-white" style={{ fontWeight: 460 }}>{role}</span>
                    </div>
                  );
                })}
              </div>
              <div className="absolute top-full left-1/2 -translate-x-1/2 h-2 w-2 -mt-1 rotate-45 bg-[#0A2540]" />
            </motion.div>
          ) : (
            <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 4 }}
              className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 px-3 py-2.5 rounded-xl bg-white border border-[#E5E7EB] shadow-[0_4px_16px_rgba(0,0,0,0.08),0_1px_3px_rgba(0,0,0,0.04)] pointer-events-none whitespace-nowrap">
              <div className="flex flex-col gap-1.5">
                {roles.map((role) => {
                  const color = rc[role] || '#635BFF';
                  return (
                    <div key={role} className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
                      <span className="text-[11px] text-[#3E4C59]" style={{ fontWeight: 460 }}>{role}</span>
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )
        )}
      </AnimatePresence>
    </div>
  );
}

function LocationsTooltip({
  dark = false,
  locations,
}: {
  dark?: boolean;
  locations: EmployeeLocation[];
}) {
  const [show, setShow] = useState(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span
        className={`cursor-default rounded-full px-1.5 py-0.5 text-[10px] transition-colors ${
          dark
            ? 'bg-white/[0.06] text-[#C1CED8] hover:bg-white/[0.1]'
            : 'bg-[#F7F8FA] text-[#8898AA] hover:bg-[#F0F0F5]'
        }`}
        style={{ fontWeight: 440 }}
      >
        +{locations.length}
      </span>
      <AnimatePresence>
        {show && (
          dark ? (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-[#0A2540] px-3 py-2 shadow-xl pointer-events-none"
            >
              <div className="flex flex-col gap-1.5">
                {locations.map((location) => (
                  <div key={location.id ?? location.name} className="flex items-center gap-2">
                    <span className="text-[12px]">{location.emoji}</span>
                    <span className="text-[11px] text-white" style={{ fontWeight: 460 }}>
                      {location.name}
                    </span>
                  </div>
                ))}
              </div>
              <div className="absolute top-full left-1/2 -translate-x-1/2 h-2 w-2 -mt-1 rotate-45 bg-[#0A2540]" />
            </motion.div>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              className="absolute z-50 bottom-full mb-2 left-1/2 -translate-x-1/2 px-3 py-2.5 rounded-xl bg-white border border-[#E5E7EB] shadow-[0_4px_16px_rgba(0,0,0,0.08),0_1px_3px_rgba(0,0,0,0.04)] pointer-events-none whitespace-nowrap"
            >
              <div className="flex flex-col gap-1.5">
                {locations.map((location) => (
                  <div key={location.id ?? location.name} className="flex items-center gap-2">
                    <span className="text-[12px]">{location.emoji}</span>
                    <span className="text-[11px] text-[#3E4C59]" style={{ fontWeight: 460 }}>
                      {location.name}
                    </span>
                  </div>
                ))}
              </div>
            </motion.div>
          )
        )}
      </AnimatePresence>
    </div>
  );
}

const statusOptions = [
  'All Status',
  statusConfig.needs_attention.label,
  statusConfig.active.label,
  statusConfig.on_leave.label,
  statusConfig.inactive.label,
];

function getPrimaryLocation(emp: Employee) {
  return emp.locations.find((l) => l.primary) || emp.locations[0];
}

function getReliabilityColor(r: number) {
  if (r >= 95) return '#00B893';
  if (r >= 85) return '#F59E0B';
  return '#E5484D';
}

function getTeamTheme(dark: boolean) {
  return {
    textPrimary: dark ? 'text-white' : 'text-[#0A2540]',
    textSecondary: dark ? 'text-[#C1CED8]' : 'text-[#8898AA]',
    textTertiary: dark ? 'text-[#C1CED8]' : 'text-[#5E6D7A]',
    rowText: dark ? 'text-[#C1CED8]' : 'text-[#3E4C59]',
    panelClass: dark
      ? 'bg-[#0F2E4C] border-white/[0.06] shadow-[0_18px_48px_rgba(0,0,0,0.28)]'
      : 'bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]',
    overlayPanelClass: dark ? 'bg-[#0F2E4C] border-white/[0.08]' : 'bg-white border-[#E5E7EB]',
    borderClass: dark ? 'border-white/[0.06]' : 'border-[#F0F0F5]',
    subtleBorderClass: dark ? 'border-white/[0.08]' : 'border-[#E5E7EB]',
    subtleSurfaceClass: dark ? 'bg-white/[0.04]' : 'bg-[#F7F8FA]',
    softSurfaceClass: dark ? 'bg-white/[0.03]' : 'bg-[#FAFBFC]',
    rowHoverClass: dark ? 'hover:bg-white/[0.03]' : 'hover:bg-[#FAFBFC]',
    rowBorderClass: dark ? 'border-white/[0.06]' : 'border-[#F7F8FA]',
    dropdownClass: dark
      ? 'bg-[#0F2E4C] border-white/[0.08] shadow-[0_24px_60px_rgba(0,0,0,0.35)]'
      : 'bg-white border-[#E5E7EB] shadow-xl',
    inputClass: dark
      ? 'border-white/[0.08] bg-white/[0.04] text-white placeholder-[#8898AA]/60'
      : 'border-[#E5E7EB] bg-white text-[#0A2540] placeholder-[#8898AA]/50',
    filterButtonClass: dark
      ? 'bg-white/[0.04] border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]'
      : 'bg-white border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]',
    secondaryButtonClass: dark
      ? 'border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]'
      : 'border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]',
    closeButtonClass: dark ? 'hover:bg-white/[0.06]' : 'hover:bg-[#F7F8FA]',
    pillClass: dark ? 'bg-white/[0.06] text-[#C1CED8]' : 'bg-[#F7F8FA] text-[#8898AA]',
    emptyIconClass: dark ? 'text-white/[0.16]' : 'text-[#E5E7EB]',
  };
}

function AssignmentPill({
  dark,
  label,
  leading,
  primary,
  onSetPrimary,
  onRemove,
}: {
  dark: boolean;
  label: string;
  leading: ReactNode;
  primary: boolean;
  onSetPrimary(): void;
  onRemove(): void;
}) {
  return (
    <motion.div
      layout
      animate={{ opacity: 1, scale: 1 }}
      className={`flex items-center gap-1.5 rounded-lg border py-1.5 pl-2.5 pr-2 ${
        dark
          ? 'border-[#635BFF]/25 bg-[#635BFF]/[0.12]'
          : 'border-[#635BFF]/15 bg-[#635BFF]/[0.06]'
      }`}
      exit={{ opacity: 0, scale: 0.9 }}
      initial={{ opacity: 0, scale: 0.9 }}
    >
      <span className="shrink-0">{leading}</span>
      <span className={`${dark ? 'text-white' : 'text-[#0A2540]'} text-[12px]`} style={{ fontWeight: 480 }}>
        {label}
      </span>
      <button
        className={`ml-1 rounded-full px-2 py-0.5 text-[10px] transition-colors ${
          primary
            ? 'bg-[#635BFF] text-white'
            : dark
              ? 'bg-white/[0.06] text-[#C1CED8] hover:bg-white/[0.1]'
              : 'bg-white text-[#635BFF] hover:bg-[#635BFF]/10'
        }`}
        onClick={onSetPrimary}
        style={{ fontWeight: primary ? 560 : 500 }}
        type="button"
      >
        {primary ? 'Primary' : 'Set Primary'}
      </button>
      <button
        className="ml-0.5 rounded p-0.5 transition-colors hover:bg-[#635BFF]/10"
        onClick={onRemove}
        type="button"
      >
        <X className="text-[#8898AA] hover:text-[#E5484D]" size={12} />
      </button>
    </motion.div>
  );
}

function AvailableAssignmentButton({
  dark,
  label,
  leading,
  onClick,
}: {
  dark: boolean;
  label: string;
  leading: ReactNode;
  onClick(): void;
}) {
  return (
    <button
      className={`group flex items-center gap-1.5 rounded-lg border px-3 py-1.5 transition-all duration-200 ${
        dark
          ? 'border-white/[0.08] bg-white/[0.03] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]'
          : 'border-[#E5E7EB] bg-[#F7F8FA] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]'
      }`}
      onClick={onClick}
      type="button"
    >
      <span className="shrink-0">{leading}</span>
      <span
        className={`text-[12px] transition-colors ${
          dark ? 'text-[#C1CED8] group-hover:text-white' : 'text-[#5E6D7A] group-hover:text-[#0A2540]'
        }`}
        style={{ fontWeight: 440 }}
      >
        {label}
      </span>
      <Plus className="ml-0.5 text-[#8898AA] transition-colors group-hover:text-[#635BFF]" size={11} />
    </button>
  );
}

function RoleAssignmentPicker({
  dark,
  loading,
  roles,
  selectedRoleIds,
  primaryRoleId,
  onToggleRole,
  onSetPrimaryRole,
}: {
  dark: boolean;
  loading: boolean;
  roles: BusinessRole[];
  selectedRoleIds: string[];
  primaryRoleId: string;
  onToggleRole(roleId: string): void;
  onSetPrimaryRole(roleId: string): void;
}) {
  const selectedRoles = roles.filter((role) => selectedRoleIds.includes(role.id));
  const availableRoles = roles.filter((role) => !selectedRoleIds.includes(role.id));

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
          Roles
        </h3>
        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>
          {selectedRoles.length} selected
        </span>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <AnimatePresence>
          {selectedRoles.map((role) => (
            <AssignmentPill
              dark={dark}
              key={role.id}
              label={role.name}
              leading={<Tag className="text-[#635BFF]" size={11} />}
              onRemove={() => onToggleRole(role.id)}
              onSetPrimary={() => onSetPrimaryRole(role.id)}
              primary={primaryRoleId === role.id}
            />
          ))}
        </AnimatePresence>
        {!selectedRoles.length ? (
          <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
            {loading ? 'Loading business roles...' : 'No roles selected yet. Add from the business role catalog below.'}
          </p>
        ) : null}
      </div>

      {!loading && !roles.length ? (
        <div className={`rounded-xl border px-4 py-3 text-[12px] ${dark ? 'border-white/[0.08] bg-white/[0.03] text-[#C1CED8]' : 'border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]'}`}>
          Create business roles first. Employee role assignment should only use the business role catalog.
        </div>
      ) : null}

      {availableRoles.length ? (
        <div>
          <div className="mb-2.5 flex items-center justify-between">
            <h4 className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
              Available Roles
            </h4>
            {availableRoles.length > 1 ? (
              <button
                className="text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9]"
                onClick={() => availableRoles.forEach((role) => onToggleRole(role.id))}
                style={{ fontWeight: 520 }}
                type="button"
              >
                + Add All
              </button>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {availableRoles.map((role) => (
              <AvailableAssignmentButton
                dark={dark}
                key={role.id}
                label={role.name}
                leading={<Tag className="text-[#635BFF]" size={11} />}
                onClick={() => onToggleRole(role.id)}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function LocationAssignmentPicker({
  dark,
  loading,
  locations,
  selectedLocationIds,
  primaryLocationId,
  onToggleLocation,
  onSetPrimaryLocation,
}: {
  dark: boolean;
  loading: boolean;
  locations: BusinessLocation[];
  selectedLocationIds: string[];
  primaryLocationId: string;
  onToggleLocation(locationId: string): void;
  onSetPrimaryLocation(locationId: string): void;
}) {
  const selectedLocations = locations.filter((location) => selectedLocationIds.includes(location.id));
  const availableLocations = locations.filter((location) => !selectedLocationIds.includes(location.id));

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
          Locations
        </h3>
        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>
          {selectedLocations.length} selected
        </span>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <AnimatePresence>
          {selectedLocations.map((location) => {
            const reference = getLocationReference({
              name: locationDisplayName(location),
              slug: location.slug,
            });
            return (
              <AssignmentPill
                dark={dark}
                key={location.id}
                label={locationDisplayName(location)}
                leading={<span className="text-[13px]">{reference.logo}</span>}
                onRemove={() => onToggleLocation(location.id)}
                onSetPrimary={() => onSetPrimaryLocation(location.id)}
                primary={primaryLocationId === location.id}
              />
            );
          })}
        </AnimatePresence>
        {!selectedLocations.length ? (
          <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
            {loading ? 'Loading business locations...' : 'No locations selected yet. Add locations from this business below.'}
          </p>
        ) : null}
      </div>

      {!loading && !locations.length ? (
        <div className={`rounded-xl border px-4 py-3 text-[12px] ${dark ? 'border-white/[0.08] bg-white/[0.03] text-[#C1CED8]' : 'border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]'}`}>
          Add at least one business location first. Employee location assignment should only use locations from this business.
        </div>
      ) : null}

      {availableLocations.length ? (
        <div>
          <div className="mb-2.5 flex items-center justify-between">
            <h4 className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
              Available Locations
            </h4>
            {availableLocations.length > 1 ? (
              <button
                className="text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9]"
                onClick={() => availableLocations.forEach((location) => onToggleLocation(location.id))}
                style={{ fontWeight: 520 }}
                type="button"
              >
                + Add All
              </button>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {availableLocations.map((location) => {
              const reference = getLocationReference({
                name: locationDisplayName(location),
                slug: location.slug,
              });
              return (
                <AvailableAssignmentButton
                  dark={dark}
                  key={location.id}
                  label={locationDisplayName(location)}
                  leading={<span className="text-[13px]">{reference.logo}</span>}
                  onClick={() => onToggleLocation(location.id)}
                />
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ─── Add Employee Modal ─── */
function AddEmployeeModal({
  businessId,
  dark,
  locations,
  onClose,
  onCreated,
  roles,
}: {
  businessId: string;
  dark: boolean;
  locations: BusinessLocation[];
  onClose: () => void;
  onCreated(employee: EmployeeSummary): Promise<void>;
  roles: BusinessRole[];
}) {
  const theme = getTeamTheme(dark);
  const [formData, setFormData] = useState<AddEmployeeFormState>(buildAddEmployeeFormState());
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);
  const canSubmit =
    Boolean(formData.firstName.trim()) &&
    Boolean(formData.lastName.trim()) &&
    Boolean(formData.roleId) &&
    Boolean(formData.locationId);

  const handleCreate = async () => {
    if (!canSubmit || isPending) {
      return;
    }
    try {
      setIsPending(true);
      setFeedback(null);
      const fullName = `${formData.firstName.trim()} ${formData.lastName.trim()}`.trim();
      const created = await createEmployee(businessId, {
        full_name: fullName,
        email: normalizeOptional(formData.email),
        phone_e164: normalizeOptional(formData.phone),
        primary_location_id: formData.locationId,
        employee_metadata: { source: 'team_ui' },
      });
      const updated = await updateEmployee(businessId, created.id, {
        roles: [{ role_id: formData.roleId, is_primary: true }],
        locations: [{ location_id: formData.locationId, is_primary: true }],
      });
      await onCreated(updated);
      onClose();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Could not add this employee.');
    } finally {
      setIsPending(false);
    }
  };

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      exit={{ opacity: 0 }}
      initial={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className={`mx-4 w-full max-w-3xl overflow-hidden rounded-2xl border ${theme.overlayPanelClass}`}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        onClick={(event) => event.stopPropagation()}
        transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        <div className={`flex items-center justify-between border-b px-4 py-5 sm:px-6 ${theme.borderClass}`}>
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#635BFF]/10">
              <UserPlus className="text-[#635BFF]" size={18} />
            </div>
            <div>
              <h2 className={`text-[16px] ${theme.textPrimary}`} style={{ fontWeight: 600 }}>
                Add Employee
              </h2>
              <p className={`text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                Add a new team member using this business&apos;s live roles and locations.
              </p>
            </div>
          </div>
          <button className={`rounded-lg p-2 transition-colors ${theme.closeButtonClass}`} onClick={onClose} type="button">
            <X className="text-[#8898AA]" size={18} />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-5 overflow-y-auto px-4 py-5 sm:px-6">
          {feedback ? (
            <div
              className="rounded-xl px-4 py-3 text-[13px]"
              role="status"
              style={{ background: 'rgba(229, 72, 77, 0.08)', color: '#C13535', fontWeight: 500 }}
            >
              {feedback}
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
                First Name
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${theme.inputClass}`}
                onChange={(event) => setFormData((current) => ({ ...current, firstName: event.target.value }))}
                placeholder="Sarah"
                style={{ fontWeight: 440 }}
                type="text"
                value={formData.firstName}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
                Last Name
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${theme.inputClass}`}
                onChange={(event) => setFormData((current) => ({ ...current, lastName: event.target.value }))}
                placeholder="Martinez"
                style={{ fontWeight: 440 }}
                type="text"
                value={formData.lastName}
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
                Email
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${theme.inputClass}`}
                onChange={(event) => setFormData((current) => ({ ...current, email: event.target.value }))}
                placeholder="sarah.m@company.com"
                style={{ fontWeight: 440 }}
                type="email"
                value={formData.email}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
                Phone
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${theme.inputClass}`}
                onChange={(event) => setFormData((current) => ({ ...current, phone: event.target.value }))}
                placeholder="(415) 555-0142"
                style={{ fontWeight: 440 }}
                type="tel"
                value={formData.phone}
              />
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
              Role
            </label>
            <select
              className={`w-full appearance-none rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${theme.inputClass}`}
              onChange={(event) => setFormData((current) => ({ ...current, roleId: event.target.value }))}
              style={{ fontWeight: 440 }}
              value={formData.roleId}
            >
              <option value="">Select role</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>{role.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
              Location
            </label>
            <select
              className={`w-full appearance-none rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${theme.inputClass}`}
              onChange={(event) => setFormData((current) => ({ ...current, locationId: event.target.value }))}
              style={{ fontWeight: 440 }}
              value={formData.locationId}
            >
              <option value="">Select location</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>{locationDisplayName(location)}</option>
              ))}
            </select>
          </div>
        </div>

        <div className={`flex items-center justify-end gap-3 border-t px-4 py-4 sm:px-6 ${theme.borderClass} ${theme.softSurfaceClass}`}>
          <button
            className={`rounded-lg border px-4 py-2.5 text-[13px] transition-all ${theme.secondaryButtonClass}`}
            onClick={onClose}
            style={{ fontWeight: 480 }}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-lg px-5 py-2.5 text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_20px_rgba(99,91,255,0.25)] disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canSubmit || isPending}
            onClick={() => {
              void handleCreate();
            }}
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}
            type="button"
          >
            {isPending ? 'Adding...' : 'Add Employee'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Bulk Upload Modal ─── */
function BulkUploadModal({
  businessId,
  dark,
  onClose,
  onImported,
}: {
  businessId: string;
  dark: boolean;
  onClose: () => void;
  onImported(result: EmployeeBulkImportResponse): Promise<void>;
}) {
  const theme = getTeamTheme(dark);
  const fileRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);
  const [isDownloadingTemplate, setIsDownloadingTemplate] = useState(false);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) simulateUpload(file);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) simulateUpload(file);
  };

  const simulateUpload = (file: File) => {
    setUploadedFile(file);
    setUploadProgress(0);
    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 100) { clearInterval(interval); return 100; }
        return prev + 15;
      });
    }, 200);
  };

  const handleTemplateDownload = async () => {
    try {
      setFeedback(null);
      setIsDownloadingTemplate(true);
      await downloadEmployeeImportTemplate(businessId);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Could not download the template.');
    } finally {
      setIsDownloadingTemplate(false);
    }
  };

  const handleImport = async () => {
    if (!uploadedFile || uploadProgress < 100 || isPending) {
      return;
    }
    try {
      setIsPending(true);
      setFeedback(null);
      const result = await importEmployees(businessId, uploadedFile);
      await onImported(result);
      if (!result.errors.length) {
        onClose();
        return;
      }
      setFeedback(`Imported ${result.created_count} employee${result.created_count === 1 ? '' : 's'} with ${result.errors.length} row issue${result.errors.length === 1 ? '' : 's'}.`);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Could not import these employees.');
    } finally {
      setIsPending(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
        className={`w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden border ${theme.overlayPanelClass}`}
        onClick={(e) => e.stopPropagation()}>
        <div className={`flex items-center justify-between px-6 py-5 border-b ${theme.borderClass}`}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#00B893]/10 flex items-center justify-center">
              <Upload size={18} className="text-[#00B893]" />
            </div>
            <div>
              <h2 className={`text-[16px] ${theme.textPrimary}`} style={{ fontWeight: 600 }}>Import Employees</h2>
              <p className={`text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Import employees from a CSV or Excel file</p>
            </div>
          </div>
          <button onClick={onClose} className={`p-2 rounded-lg transition-colors ${theme.closeButtonClass}`}>
            <X size={18} className="text-[#8898AA]" />
          </button>
        </div>

        <div className="px-6 py-6">
          {feedback ? (
            <div
              className="mb-4 rounded-xl px-4 py-3 text-[13px]"
              role="status"
              style={{ background: 'rgba(229, 72, 77, 0.08)', color: '#C13535', fontWeight: 500 }}
            >
              {feedback}
            </div>
          ) : null}
          <div className={`mb-5 flex items-center gap-3 p-3.5 rounded-xl border ${
            dark
              ? 'bg-[#635BFF]/[0.08] border-[#635BFF]/20'
              : 'bg-[#635BFF]/[0.04] border-[#635BFF]/10'
          }`}>
            <FileSpreadsheet size={18} className="text-[#635BFF] shrink-0" />
            <div className="flex-1">
              <p className={`text-[12px] ${theme.textPrimary}`} style={{ fontWeight: 500 }}>Need a template?</p>
              <p className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Download our CSV template with the required columns.</p>
            </div>
            <button className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[11px] text-[#635BFF] transition-all ${dark ? 'bg-white/[0.04] border-white/[0.08] hover:bg-white/[0.06]' : 'bg-white border-[#E5E7EB] hover:bg-[#F7F8FA]'}`}
              onClick={() => {
                void handleTemplateDownload();
              }}
              style={{ fontWeight: 500 }}
              type="button">
              <Download size={12} /> {isDownloadingTemplate ? 'Downloading...' : 'Template'}
            </button>
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            className={`relative cursor-pointer rounded-xl border-2 border-dashed transition-all duration-300 p-8 text-center ${
              isDragging ? 'border-[#635BFF] bg-[#635BFF]/[0.08]' :
              uploadedFile ? 'border-[#00B893]/40 bg-[#00B893]/[0.06]' :
              dark ? 'border-white/[0.08] hover:border-[#635BFF]/30 hover:bg-white/[0.04]' :
              'border-[#E5E7EB] hover:border-[#635BFF]/30 hover:bg-[#F7F8FA]'
            }`}>
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleFileSelect} className="hidden" />
            
            {uploadedFile ? (
              <div>
                <div className="w-12 h-12 rounded-full bg-[#00B893]/10 flex items-center justify-center mx-auto mb-3">
                  {uploadProgress >= 100 ? (
                    <CheckCircle2 size={24} className="text-[#00B893]" />
                  ) : (
                    <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
                      <Activity size={20} className="text-[#00B893]" />
                    </motion.div>
                  )}
                </div>
                <p className={`mb-1 text-[13px] ${theme.textPrimary}`} style={{ fontWeight: 520 }}>{uploadedFile.name}</p>
                {uploadProgress < 100 ? (
                  <div className="w-48 mx-auto">
                    <div className={`mt-2 h-1.5 rounded-full overflow-hidden ${dark ? 'bg-white/[0.08]' : 'bg-[#F0F0F5]'}`}>
                      <motion.div className="h-full rounded-full bg-gradient-to-r from-[#00B893] to-[#00D4AA]"
                        initial={{ width: 0 }} animate={{ width: `${Math.min(uploadProgress, 100)}%` }} />
                    </div>
                  <p className={`mt-1.5 text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Processing...</p>
                </div>
              ) : (
                  <p className="text-[12px] text-[#00B893]" style={{ fontWeight: 480 }}>Ready to import this file</p>
              )}
              </div>
            ) : (
              <div>
                <div className={`w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3 ${theme.subtleSurfaceClass}`}>
                  <Upload size={20} className="text-[#8898AA]" />
                </div>
                <p className={`mb-1 text-[13px] ${theme.textPrimary}`} style={{ fontWeight: 520 }}>Drop your file here, or click to browse</p>
                <p className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Supports CSV, XLS, XLSX {'\u2022'} Max 5MB</p>
              </div>
            )}
          </div>

          {uploadedFile && uploadProgress >= 100 && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.1 }}
              className={`mt-4 p-4 rounded-xl border ${theme.subtleBorderClass} ${theme.subtleSurfaceClass}`}>
              <p className={`mb-3 text-[11px] uppercase tracking-[0.04em] ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Column Mapping Preview</p>
              <div className="space-y-2">
                {[
                  { csv: 'full_name', mapped: 'Employee Name', icon: '\u2713' },
                  { csv: 'email_address', mapped: 'Email', icon: '\u2713' },
                  { csv: 'phone', mapped: 'Phone Number', icon: '\u2713' },
                  { csv: 'job_title', mapped: 'Role', icon: '\u2713' },
                  { csv: 'work_location', mapped: 'Location', icon: '\u2713' },
                ].map((col) => (
                  <div key={col.csv} className="flex items-center gap-3 text-[12px]">
                    <span className="text-[#00B893]">{col.icon}</span>
                    <span className={`w-28 truncate ${theme.textSecondary}`} style={{ fontWeight: 420 }}>{col.csv}</span>
                    <span className={theme.textSecondary}>{'\u2192'}</span>
                    <span className={theme.textPrimary} style={{ fontWeight: 480 }}>{col.mapped}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </div>

        <div className={`flex items-center justify-end gap-3 px-6 py-4 border-t ${theme.borderClass} ${theme.softSurfaceClass}`}>
          <button onClick={onClose}
            className={`px-4 py-2.5 rounded-lg text-[13px] border transition-all ${theme.secondaryButtonClass}`}
            style={{ fontWeight: 480 }}>
            Cancel
          </button>
          <button
            className={`px-5 py-2.5 rounded-lg text-[13px] text-white transition-all duration-300 ${
              uploadedFile && uploadProgress >= 100 ? 'hover:shadow-[0_0_20px_rgba(0,184,147,0.25)]' : 'opacity-40 cursor-not-allowed'
            }`}
            style={{ fontWeight: 540, background: 'linear-gradient(135deg, #00B893, #00D4AA)' }}
            disabled={!uploadedFile || uploadProgress < 100 || isPending}
            onClick={() => {
              void handleImport();
            }}
            type="button">
            {isPending ? 'Importing...' : 'Import Employees'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Employee Detail Slide-over ─── */
function EmployeeDetail({
  businessId,
  dark,
  employee,
  locations,
  onClose,
  onDelete,
  onSave,
  onRoleCreated,
  roles,
}: {
  businessId: string;
  dark: boolean;
  employee: Employee;
  locations: BusinessLocation[];
  onClose: () => void;
  onDelete(employeeId: string): Promise<void> | void;
  onSave(employee: EmployeeProfile): Promise<void>;
  onRoleCreated(role: BusinessRole): void;
  roles: BusinessRole[];
}) {
  const seed = useMemo(
    () => buildEmployeeEditorSeed(employee, roles, locations),
    [employee, locations, roles],
  );

  return (
    <EmployeeEditorDrawer
      businessId={businessId}
      dark={dark}
      employee={seed}
      locations={locations}
      onClose={onClose}
      onDeleted={onDelete}
      onRoleCreated={onRoleCreated}
      onSaved={onSave}
      roles={roles}
    />
  );
}

function SelectedAssignmentTag({
  dark,
  label,
  leading,
  onRemove,
}: {
  dark: boolean;
  label: string;
  leading: ReactNode;
  onRemove(): void;
}) {
  return (
    <motion.div
      layout
      animate={{ opacity: 1, scale: 1 }}
      className={`flex items-center gap-1.5 rounded-lg border py-1.5 pl-2.5 pr-2 ${
        dark
          ? 'border-[#635BFF]/25 bg-[#635BFF]/[0.12]'
          : 'border-[#635BFF]/15 bg-[#635BFF]/[0.06]'
      }`}
      exit={{ opacity: 0, scale: 0.9 }}
      initial={{ opacity: 0, scale: 0.9 }}
    >
      <span className="shrink-0">{leading}</span>
      <span className={`${dark ? 'text-white' : 'text-[#0A2540]'} text-[12px]`} style={{ fontWeight: 480 }}>
        {label}
      </span>
      <button
        className="ml-0.5 rounded p-0.5 transition-colors hover:bg-[#635BFF]/10"
        onClick={onRemove}
        type="button"
      >
        <X className="text-[#8898AA] hover:text-[#E5484D]" size={12} />
      </button>
    </motion.div>
  );
}

function BulkActionModalShell({
  dark,
  title,
  subtitle,
  children,
  footerNote,
  confirmLabel,
  confirmDisabled = false,
  onClose,
  onConfirm,
}: {
  dark: boolean;
  title: string;
  subtitle: string;
  children: ReactNode;
  footerNote: string;
  confirmLabel: string;
  confirmDisabled?: boolean;
  onClose(): void;
  onConfirm(): void | Promise<void>;
}) {
  const theme = getTeamTheme(dark);

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      exit={{ opacity: 0 }}
      initial={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className={`mx-4 w-full max-w-3xl overflow-hidden rounded-[28px] border ${theme.overlayPanelClass}`}
        exit={{ opacity: 0, scale: 0.96, y: 16 }}
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        onClick={(event) => event.stopPropagation()}
        transition={{ duration: 0.22 }}
      >
        <div className={`border-b px-6 py-5 ${theme.borderClass}`}>
          <div className="flex items-center justify-between">
            <div>
              <h2 className={`text-[18px] ${theme.textPrimary}`} style={{ fontWeight: 600 }}>
                {title}
              </h2>
              <p className={`mt-1 text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
                {subtitle}
              </p>
            </div>
            <button
              className={`rounded-full p-2 ${theme.closeButtonClass}`}
              onClick={onClose}
              type="button"
            >
              <X className="text-[#8898AA]" size={16} />
            </button>
          </div>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">
          {children}
        </div>

        <div className={`flex items-center justify-between gap-3 border-t px-6 py-4 ${theme.borderClass}`}>
          <p className={`max-w-[420px] text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
            {footerNote}
          </p>
          <div className="flex items-center gap-3">
            <button
              className={`rounded-full border px-4 py-2.5 text-[13px] ${theme.secondaryButtonClass}`}
              onClick={onClose}
              type="button"
            >
              Cancel
            </button>
            <button
              className="rounded-full px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-50"
              disabled={confirmDisabled}
              onClick={() => {
                void onConfirm();
              }}
              style={{
                fontWeight: 540,
                background: 'linear-gradient(135deg, #635BFF, #8B5CF6)',
              }}
              type="button"
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function BulkAssignLocationsModal({
  count,
  dark,
  initialSelectedLocationIds = [],
  locations,
  onClose,
  onConfirm,
}: {
  count: number;
  dark: boolean;
  initialSelectedLocationIds?: string[];
  locations: BusinessLocation[];
  onClose(): void;
  onConfirm(locationIds: string[]): Promise<void>;
}) {
  const [selectedLocationIds, setSelectedLocationIds] = useState<string[]>(initialSelectedLocationIds);
  const selectedLocations = locations.filter((location) => selectedLocationIds.includes(location.id));
  const availableLocations = locations.filter((location) => !selectedLocationIds.includes(location.id));
  const hasLocationChanges = useMemo(() => {
    const initial = [...initialSelectedLocationIds].sort();
    const current = [...selectedLocationIds].sort();
    return initial.length !== current.length || initial.some((value, index) => value !== current[index]);
  }, [initialSelectedLocationIds, selectedLocationIds]);

  const toggleLocation = (locationId: string) => {
    setSelectedLocationIds((current) =>
      current.includes(locationId)
        ? current.filter((item) => item !== locationId)
        : [...current, locationId],
    );
  };

  return (
    <BulkActionModalShell
      dark={dark}
      title="Assign Locations"
      subtitle={`Update the shared location assignments for ${count} selected employee${count === 1 ? '' : 's'}.`}
      footerNote="Shared locations can be added or removed here. Employee-specific locations stay intact."
      confirmLabel="Update Locations"
      confirmDisabled={!hasLocationChanges}
      onClose={onClose}
      onConfirm={() => onConfirm(selectedLocationIds)}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
          Locations
        </h3>
        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>
          {selectedLocations.length} selected
        </span>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <AnimatePresence>
          {selectedLocations.map((location) => {
            const reference = getLocationReference({
              name: locationDisplayName(location),
              slug: location.slug,
            });
            return (
              <SelectedAssignmentTag
                dark={dark}
                key={location.id}
                label={locationDisplayName(location)}
                leading={<span className="text-[13px]">{reference.logo}</span>}
                onRemove={() => toggleLocation(location.id)}
              />
            );
          })}
        </AnimatePresence>
        {!selectedLocations.length ? (
          <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
            No locations selected yet. Add from the business catalog below.
          </p>
        ) : null}
      </div>

      {availableLocations.length ? (
        <div>
          <div className="mb-2.5 flex items-center justify-between">
            <h4 className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
              Available Locations
            </h4>
            {availableLocations.length > 1 ? (
              <button
                className="text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9]"
                onClick={() => setSelectedLocationIds(availableLocations.map((location) => location.id))}
                style={{ fontWeight: 520 }}
                type="button"
              >
                + Add All
              </button>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {availableLocations.map((location) => {
              const reference = getLocationReference({
                name: locationDisplayName(location),
                slug: location.slug,
              });
              return (
                <AvailableAssignmentButton
                  dark={dark}
                  key={location.id}
                  label={locationDisplayName(location)}
                  leading={<span className="text-[13px]">{reference.logo}</span>}
                  onClick={() => toggleLocation(location.id)}
                />
              );
            })}
          </div>
        </div>
      ) : null}
    </BulkActionModalShell>
  );
}

function BulkAssignRolesModal({
  count,
  dark,
  initialSelectedRoleIds = [],
  roles,
  onClose,
  onConfirm,
}: {
  count: number;
  dark: boolean;
  initialSelectedRoleIds?: string[];
  roles: BusinessRole[];
  onClose(): void;
  onConfirm(roleIds: string[]): Promise<void>;
}) {
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>(initialSelectedRoleIds);
  const selectedRoles = roles.filter((role) => selectedRoleIds.includes(role.id));
  const availableRoles = roles.filter((role) => !selectedRoleIds.includes(role.id));

  const toggleRole = (roleId: string) => {
    setSelectedRoleIds((current) =>
      current.includes(roleId)
        ? current.filter((item) => item !== roleId)
        : [...current, roleId],
    );
  };

  return (
    <BulkActionModalShell
      dark={dark}
      title="Assign Roles"
      subtitle={`Update the shared role assignments for ${count} selected employee${count === 1 ? '' : 's'}.`}
      footerNote="Shared roles can be added or removed here. Employee-specific roles stay intact."
      confirmLabel="Update Roles"
      confirmDisabled={selectedRoleIds.length === 0 && initialSelectedRoleIds.length === 0}
      onClose={onClose}
      onConfirm={() => onConfirm(selectedRoleIds)}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
          Roles
        </h3>
        <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>
          {selectedRoles.length} selected
        </span>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        <AnimatePresence>
          {selectedRoles.map((role) => (
            <SelectedAssignmentTag
              dark={dark}
              key={role.id}
              label={role.name}
              leading={<Tag className="text-[#635BFF]" size={11} />}
              onRemove={() => toggleRole(role.id)}
            />
          ))}
        </AnimatePresence>
        {!selectedRoles.length ? (
          <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
            No roles selected yet. Add from the business role catalog below.
          </p>
        ) : null}
      </div>

      {availableRoles.length ? (
        <div>
          <div className="mb-2.5 flex items-center justify-between">
            <h4 className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
              Available Roles
            </h4>
            {availableRoles.length > 1 ? (
              <button
                className="text-[11px] text-[#635BFF] transition-colors hover:text-[#4B3FD9]"
                onClick={() => setSelectedRoleIds(availableRoles.map((role) => role.id))}
                style={{ fontWeight: 520 }}
                type="button"
              >
                + Add All
              </button>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {availableRoles.map((role) => (
              <AvailableAssignmentButton
                dark={dark}
                key={role.id}
                label={role.name}
                leading={<Tag className="text-[#635BFF]" size={11} />}
                onClick={() => toggleRole(role.id)}
              />
            ))}
          </div>
        </div>
      ) : null}
    </BulkActionModalShell>
  );
}

function BulkExportModal({
  count,
  dark,
  onClose,
  onConfirm,
}: {
  count: number;
  dark: boolean;
  onClose(): void;
  onConfirm(): void;
}) {
  return (
    <BulkActionModalShell
      dark={dark}
      title="Export Employees"
      subtitle={`Download a CSV export for ${count} selected employee${count === 1 ? '' : 's'}.`}
      footerNote="The export includes employee name, contact info, roles, locations, status, and reliability."
      confirmLabel="Export CSV"
      onClose={onClose}
      onConfirm={onConfirm}
    >
      <div className={`rounded-2xl border px-4 py-4 ${dark ? 'border-white/[0.08] bg-white/[0.03]' : 'border-[#E5E7EB] bg-[#F7F8FA]'}`}>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#635BFF]/10">
            <Download className="text-[#635BFF]" size={18} />
          </div>
          <div>
            <p className={`${dark ? 'text-white' : 'text-[#0A2540]'} text-[13px]`} style={{ fontWeight: 520 }}>
              Ready to export
            </p>
            <p className="text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
              {count} selected employee{count === 1 ? '' : 's'}
            </p>
          </div>
        </div>
      </div>
    </BulkActionModalShell>
  );
}

function BulkRemoveModal({
  count,
  dark,
  onClose,
  onConfirm,
}: {
  count: number;
  dark: boolean;
  onClose(): void;
  onConfirm(): Promise<void>;
}) {
  return (
    <BulkActionModalShell
      dark={dark}
      title="Remove Employees"
      subtitle={`Remove ${count} selected employee${count === 1 ? '' : 's'} from this business.`}
      footerNote="Backfill will respect existing scheduling constraints and skip any employee who cannot be deleted."
      confirmLabel="Remove Selected"
      onClose={onClose}
      onConfirm={onConfirm}
    >
      <div className={`rounded-2xl border px-4 py-4 ${dark ? 'border-[#E5484D]/30 bg-[#E5484D]/10' : 'border-red-200 bg-red-50'}`}>
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#E5484D]/10">
            <UserMinus className="text-[#E5484D]" size={18} />
          </div>
          <div>
            <p className={`${dark ? 'text-white' : 'text-[#0A2540]'} text-[13px]`} style={{ fontWeight: 520 }}>
              This action removes roster records
            </p>
            <p className="mt-1 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
              Employees that are tied to published scheduling data will be skipped automatically.
            </p>
          </div>
        </div>
      </div>
    </BulkActionModalShell>
  );
}

/* ─── Main Team Page ─── */
export default function Team({
  embeddedInShell = false,
  editingEmployeeId = null,
}: {
  embeddedInShell?: boolean;
  editingEmployeeId?: string | null;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const routeSegments = useSelectedLayoutSegments();
  const workspace = useAppWorkspace();
  const workspaceReady = useAppWorkspaceReady();
  const isDark = useResolvedAppAppearance() === 'dark';
  const theme = getTeamTheme(isDark);
  const activeBusiness = useMemo(
    () => resolvePreferredWorkspaceBusiness(workspace, pathname),
    [pathname, workspace],
  );
  const businessId = activeBusiness?.business_id ?? null;
  const [businessRoles, setBusinessRoles] = useState<BusinessRole[]>([]);
  const [businessLocations, setBusinessLocations] = useState<BusinessLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<{ tone: 'success' | 'error'; message: string } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [locationFilters, setLocationFilters] = useState<Set<string>>(new Set());
  const [statusFilters, setStatusFilters] = useState<Set<string>>(new Set());
  const [roleFilters, setRoleFilters] = useState<Set<string>>(new Set());
  const [showAddModal, setShowAddModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [showBulkAssignLocation, setShowBulkAssignLocation] = useState(false);
  const [showBulkAssignRole, setShowBulkAssignRole] = useState(false);
  const [showBulkExport, setShowBulkExport] = useState(false);
  const [showBulkRemove, setShowBulkRemove] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null);
  const [selectedEmployees, setSelectedEmployees] = useState<Set<string>>(new Set());
  const [employeesData, setEmployeesData] = useState<Employee[]>([]);
  const [sortField, setSortField] = useState<'name' | 'reliability'>('name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [isTableHovered, setIsTableHovered] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [showLocationDropdown, setShowLocationDropdown] = useState(false);
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  const locationFilterRef = useRef<HTMLButtonElement>(null);
  const statusFilterRef = useRef<HTMLButtonElement>(null);
  const roleFilterRef = useRef<HTMLButtonElement>(null);
  const activeEditingEmployeeId =
    editingEmployeeId ?? (routeSegments[0] === 'employee' ? routeSegments[1] ?? null : null);
  const defaultBusinessLocation =
    businessLocations.length === 1 ? businessLocations[0] : null;

  useEffect(() => {
    let cancelled = false;

    async function loadCatalog() {
      if (!workspaceReady) {
        setLoading(true);
        return;
      }

      if (!businessId) {
        setBusinessRoles([]);
        setBusinessLocations([]);
        setEmployeesData([]);
        setLoading(false);
        return;
      }

      setLoading(true);

      try {
        setFeedback(null);
        const [nextLocations, nextRoles, nextEmployees] = await Promise.all([
          listBusinessLocations(businessId),
          listBusinessRoles(businessId),
          listEmployees(businessId),
        ]);
        if (cancelled) {
          return;
        }
        const activeLocations = nextLocations.filter((location) => location.is_active);
        setBusinessLocations(activeLocations);
        setBusinessRoles(nextRoles);
        setEmployeesData(nextEmployees.map((employee) => buildLiveEmployee(employee, activeLocations)));
        setSelectedEmployee(null);
      } catch {
        if (cancelled) {
          return;
        }
        setFeedback({
          tone: 'error',
          message: 'Could not load the team roster.',
        });
        setBusinessLocations([]);
        setBusinessRoles([]);
        setEmployeesData([]);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadCatalog();

    return () => {
      cancelled = true;
    };
  }, [businessId, workspaceReady]);

  const locationOptions = useMemo(
    () => ['All Locations', ...businessLocations.map((location) => locationDisplayName(location))],
    [businessLocations],
  );
  const roleOptions = useMemo(
    () => ['All Roles', ...uniqueOrdered([...businessRoles.map((role) => role.name), ...employeesData.flatMap((employee) => employee.roles)])],
    [businessRoles, employeesData],
  );

  const closeEmployeeEditor = useCallback(() => {
    setSelectedEmployee(null);
    router.replace('/team', { scroll: false });
  }, [router]);

  useEffect(() => {
    setLocationFilters((current) => {
      const next = new Set(
        Array.from(current).filter((location) => locationOptions.includes(location)),
      );
      return next.size === current.size ? current : next;
    });
  }, [locationOptions]);

  useEffect(() => {
    setRoleFilters((current) => {
      const next = new Set(
        Array.from(current).filter((role) => roleOptions.includes(role)),
      );
      return next.size === current.size ? current : next;
    });
  }, [roleOptions]);

  useEffect(() => {
    if (!activeEditingEmployeeId) {
      setSelectedEmployee(null);
      return;
    }

    const nextEmployee =
      employeesData.find((employee) => employee.id === activeEditingEmployeeId) ?? null;

    if (nextEmployee) {
      setSelectedEmployee((current) =>
        current?.id === nextEmployee.id ? current : nextEmployee,
      );
      return;
    }

    if (!loading) {
      setSelectedEmployee(null);
      router.replace('/team', { scroll: false });
    }
  }, [activeEditingEmployeeId, employeesData, loading, router]);

  const openEmployeeEditor = useCallback(
    (employee: Employee) => {
      router.push(buildTeamEmployeeEditPath(employee.id), { scroll: false });
    },
    [router],
  );

  const filtered = employeesData
    .filter((e) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch = !q || e.name.toLowerCase().includes(q) || e.roles.some((r) => r.toLowerCase().includes(q)) || e.email.toLowerCase().includes(q);
      const matchesLocation = locationFilters.size === 0 || e.locations.some((l) => locationFilters.has(l.name));
      const matchesStatus = statusFilters.size === 0 || statusFilters.has(statusConfig[e.status].label);
      const matchesRole = roleFilters.size === 0 || e.roles.some((role) => roleFilters.has(role));
      return matchesSearch && matchesLocation && matchesStatus && matchesRole;
    })
    .sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1;
      if (sortField === 'name') return a.name.localeCompare(b.name) * dir;
      return (a.reliability - b.reliability) * dir;
    });

  const toggleSort = (field: 'name' | 'reliability') => {
    if (sortField === field) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
  };

  const toggleLocationFilter = (locationName: string) => {
    setLocationFilters((current) => {
      const next = new Set(current);
      if (next.has(locationName)) next.delete(locationName);
      else next.add(locationName);
      return next;
    });
  };

  const toggleStatusFilter = (statusLabel: string) => {
    setStatusFilters((current) => {
      const next = new Set(current);
      if (next.has(statusLabel)) next.delete(statusLabel);
      else next.add(statusLabel);
      return next;
    });
  };

  const toggleRoleFilter = (roleName: string) => {
    setRoleFilters((current) => {
      const next = new Set(current);
      if (next.has(roleName)) next.delete(roleName);
      else next.add(roleName);
      return next;
    });
  };

  const toggleEmployee = useCallback((employeeId: string) => {
    setSelectedEmployees((current) => {
      const next = new Set(current);
      if (next.has(employeeId)) next.delete(employeeId);
      else next.add(employeeId);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    const filteredIds = filtered.map((employee) => employee.id);
    setSelectedEmployees((current) => {
      const allVisibleSelected =
        filteredIds.length > 0 && filteredIds.every((employeeId) => current.has(employeeId));
      if (allVisibleSelected) {
        const next = new Set(current);
        filteredIds.forEach((employeeId) => next.delete(employeeId));
        return next;
      }
      return new Set(filteredIds);
    });
  }, [filtered]);

  const clearSelection = useCallback(() => {
    setSelectedEmployees(new Set());
  }, []);

  useEffect(() => {
    setSelectedEmployees((current) => {
      const validIds = new Set(employeesData.map((employee) => employee.id));
      const next = new Set(Array.from(current).filter((employeeId) => validIds.has(employeeId)));
      return next.size === current.size ? current : next;
    });
  }, [employeesData]);

  const handleAddEmployee = useCallback(async (employee: EmployeeSummary) => {
    const nextEmployee = buildLiveEmployee(employee, businessLocations);
    setEmployeesData((current) => [nextEmployee, ...current.filter((item) => item.id !== nextEmployee.id)]);
    setFeedback({
      tone: 'success',
      message: `${nextEmployee.name} added to the roster.`,
    });
  }, [businessLocations]);

  const handleSaveEmployee = useCallback(async (employee: EmployeeProfile) => {
    const nextEmployee = buildLiveEmployee(employee, businessLocations);
    setEmployeesData((current) =>
      current.map((item) => (item.id === nextEmployee.id ? nextEmployee : item)),
    );
    setSelectedEmployee(nextEmployee);
    setFeedback({
      tone: 'success',
      message: `${nextEmployee.name} updated.`,
    });
  }, [businessLocations]);

  const handleDeleteEmployee = useCallback(async (employeeId: string) => {
    setEmployeesData((current) => current.filter((item) => item.id !== employeeId));
    closeEmployeeEditor();
    setFeedback({
      tone: 'success',
      message: 'Employee removed from the roster.',
    });
  }, [closeEmployeeEditor]);

  const handleBulkImported = useCallback(async (result: EmployeeBulkImportResponse) => {
    if (!businessId) {
      return;
    }
    const refreshed = await listEmployees(businessId);
    setEmployeesData(refreshed.map((employee) => buildLiveEmployee(employee, businessLocations)));
    setFeedback({
      tone: 'success',
      message: `Imported ${result.created_count} employee${result.created_count === 1 ? '' : 's'}${result.skipped_count ? `, skipped ${result.skipped_count}` : ''}.`,
    });
  }, [businessId, businessLocations]);

  const selectedEmployeeRecords = useMemo(
    () => employeesData.filter((employee) => selectedEmployees.has(employee.id)),
    [employeesData, selectedEmployees],
  );

  const sharedSelectedLocationIds = useMemo(
    () =>
      intersectAll(
        selectedEmployeeRecords.map((employee) =>
          buildEmployeeEditorSeed(employee, businessRoles, businessLocations).location_ids,
        ),
      ),
    [businessLocations, businessRoles, selectedEmployeeRecords],
  );

  const sharedSelectedRoleIds = useMemo(
    () =>
      intersectAll(
        selectedEmployeeRecords.map((employee) =>
          buildEmployeeEditorSeed(employee, businessRoles, businessLocations).role_ids,
        ),
      ),
    [businessLocations, businessRoles, selectedEmployeeRecords],
  );

  const handleBulkAction = useCallback((action: 'assign-location' | 'assign-role' | 'export' | 'remove') => {
    switch (action) {
      case 'assign-location':
        setShowBulkAssignLocation(true);
        break;
      case 'assign-role':
        setShowBulkAssignRole(true);
        break;
      case 'export':
        setShowBulkExport(true);
        break;
      case 'remove':
        setShowBulkRemove(true);
        break;
    }
  }, []);

  const handleBulkAssignLocations = useCallback(async (locationIds: string[]) => {
    if (!businessId || !locationIds.length || !selectedEmployeeRecords.length) {
      if (!businessId || !selectedEmployeeRecords.length) {
        return;
      }
    }

    const initialSharedLocationIds = intersectAll(
      selectedEmployeeRecords.map((employee) =>
        buildEmployeeEditorSeed(employee, businessRoles, businessLocations).location_ids,
      ),
    );

    const updatedEmployees = await Promise.all(
      selectedEmployeeRecords.map(async (employee) => {
        const seed = buildEmployeeEditorSeed(employee, businessRoles, businessLocations);
        const preservedLocationIds = seed.location_ids.filter(
          (locationId) => !initialSharedLocationIds.includes(locationId),
        );
        const nextLocationIds = uniqueOrdered([...preservedLocationIds, ...locationIds]);
        const primaryLocationId =
          seed.primary_location_id && nextLocationIds.includes(seed.primary_location_id)
            ? seed.primary_location_id
            : nextLocationIds[0] ?? null;
        return updateEmployee(businessId, employee.id, {
          locations: nextLocationIds.map((locationId) => ({
            location_id: locationId,
            is_primary: locationId === primaryLocationId,
          })),
        });
      }),
    );

    const updatedById = new Map(
      updatedEmployees.map((employee) => [employee.id, buildLiveEmployee(employee, businessLocations)]),
    );
    setEmployeesData((current) =>
      current.map((employee) => updatedById.get(employee.id) ?? employee),
    );
    clearSelection();
    setFeedback({
      tone: 'success',
      message: `Updated locations for ${updatedEmployees.length} employee${updatedEmployees.length === 1 ? '' : 's'}.`,
    });
  }, [businessId, businessLocations, businessRoles, clearSelection, selectedEmployeeRecords]);

  const handleBulkAssignRoles = useCallback(async (roleIds: string[]) => {
    if (!businessId || !roleIds.length || !selectedEmployeeRecords.length) {
      if (!businessId || !selectedEmployeeRecords.length) {
        return;
      }
    }

    const initialSharedRoleIds = intersectAll(
      selectedEmployeeRecords.map((employee) =>
        buildEmployeeEditorSeed(employee, businessRoles, businessLocations).role_ids,
      ),
    );

    const updatedEmployees = await Promise.all(
      selectedEmployeeRecords.map(async (employee) => {
        const seed = buildEmployeeEditorSeed(employee, businessRoles, businessLocations);
        const preservedRoleIds = seed.role_ids.filter(
          (roleId) => !initialSharedRoleIds.includes(roleId),
        );
        const nextRoleIds = uniqueOrdered([...preservedRoleIds, ...roleIds]);
        const primaryRoleId =
          seed.primary_role_id && nextRoleIds.includes(seed.primary_role_id)
            ? seed.primary_role_id
            : nextRoleIds[0] ?? null;
        return updateEmployee(businessId, employee.id, {
          roles: nextRoleIds.map((roleId) => ({
            role_id: roleId,
            is_primary: roleId === primaryRoleId,
          })),
        });
      }),
    );

    const updatedById = new Map(
      updatedEmployees.map((employee) => [employee.id, buildLiveEmployee(employee, businessLocations)]),
    );
    setEmployeesData((current) =>
      current.map((employee) => updatedById.get(employee.id) ?? employee),
    );
    clearSelection();
    setFeedback({
      tone: 'success',
      message: `Updated roles for ${updatedEmployees.length} employee${updatedEmployees.length === 1 ? '' : 's'}.`,
    });
  }, [businessId, businessLocations, businessRoles, clearSelection, selectedEmployeeRecords]);

  const handleBulkExport = useCallback(() => {
    if (!selectedEmployeeRecords.length) {
      return;
    }

    const header = ['Full Name', 'Email', 'Phone', 'Roles', 'Locations', 'Status', 'Reliability'];
    const rows = selectedEmployeeRecords.map((employee) => [
      employee.name,
      employee.email,
      employee.phone,
      employee.roles.join('; '),
      employee.locations.map((location) => location.name).join('; '),
      statusConfig[employee.status].label,
      `${employee.reliability}%`,
    ]);
    const csv = [header, ...rows]
      .map((row) =>
        row
          .map((value) => `"${String(value ?? '').replace(/"/g, '""')}"`)
          .join(','),
      )
      .join('\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `backfill-team-export-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    setShowBulkExport(false);
    clearSelection();
    setFeedback({
      tone: 'success',
      message: `Exported ${selectedEmployeeRecords.length} employee${selectedEmployeeRecords.length === 1 ? '' : 's'}.`,
    });
  }, [clearSelection, selectedEmployeeRecords]);

  const handleBulkRemove = useCallback(async () => {
    if (!businessId || !selectedEmployeeRecords.length) {
      return;
    }

    const readiness = await Promise.all(
      selectedEmployeeRecords.map(async (employee) => ({
        employee,
        state: await getEmployeeDeleteReadiness(businessId, employee.id),
      })),
    );

    const removable = readiness.filter(({ state }) => state.can_delete);
    const blocked = readiness.filter(({ state }) => !state.can_delete);

    if (removable.length) {
      await Promise.all(removable.map(({ employee }) => deleteEmployee(businessId, employee.id)));
      const removableIds = new Set(removable.map(({ employee }) => employee.id));
      setEmployeesData((current) =>
        current.filter((employee) => !removableIds.has(employee.id)),
      );
    }

    clearSelection();
    setShowBulkRemove(false);
    setFeedback({
      tone: blocked.length ? 'error' : 'success',
      message: blocked.length
        ? `Removed ${removable.length} employee${removable.length === 1 ? '' : 's'}, skipped ${blocked.length} due to active scheduling constraints.`
        : `Removed ${removable.length} employee${removable.length === 1 ? '' : 's'}.`,
    });
  }, [businessId, clearSelection, selectedEmployeeRecords]);

  const showBlockingLoader = loading && employeesData.length === 0;
  const allVisibleSelected =
    filtered.length > 0 && filtered.every((employee) => selectedEmployees.has(employee.id));
  const selectedCount = selectedEmployees.size;

  const content = (
    <>
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
        <div className="flex items-end justify-between mb-6">
          <div>
            <h1 className={`text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] mb-1 ${theme.textPrimary}`} style={{ fontWeight: 620 }}>
              Team
            </h1>
            <p className={`text-[13px] sm:text-[15px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>
              Manage your employees across all locations.
            </p>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <button onClick={() => setShowBulkModal(true)}
              className={`flex items-center gap-2 px-3 sm:px-4 py-2.5 rounded-lg text-[12px] sm:text-[13px] border transition-all disabled:opacity-40 disabled:cursor-not-allowed ${theme.secondaryButtonClass}`}
              disabled={!businessId || loading}
              style={{ fontWeight: 480 }}>
              <Upload size={15} /> <span className="hidden sm:inline">Import Employees</span><span className="sm:hidden">Import</span>
            </button>
            <button onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 px-3 sm:px-5 py-2.5 rounded-full text-[12px] sm:text-[13px] text-white transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)] disabled:opacity-40 disabled:cursor-not-allowed"
              disabled={!businessId || loading}
              style={{ fontWeight: 540, background: 'linear-gradient(135deg, #635BFF, #8B5CF6)' }}>
              <Plus size={15} /> <span className="hidden sm:inline">Add Employee</span><span className="sm:hidden">Add</span>
            </button>
          </div>
        </div>

        {feedback ? (
          <div
            className="mb-4 rounded-xl px-4 py-3 text-[13px]"
            role="status"
            style={{
              background: feedback.tone === 'success' ? 'rgba(0, 184, 147, 0.08)' : 'rgba(229, 72, 77, 0.08)',
              color: feedback.tone === 'success' ? '#067A64' : '#C13535',
              fontWeight: 500,
            }}
          >
            {feedback.message}
          </div>
        ) : null}

        {/* Filters + Search */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-4">
          <motion.div
            animate={{ width: searchFocused || searchQuery ? '100%' : '140px' }}
            transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="relative w-full sm:w-auto sm:max-w-sm"
          >
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8898AA]" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setSearchFocused(false)}
              placeholder="Search..."
              className={`w-full rounded-lg border py-2.5 pl-9 pr-3 text-[16px] transition-all focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] focus:outline-none sm:text-[12px] ${theme.inputClass}`}
              style={{ fontWeight: 420 }}
            />
          </motion.div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Role filter */}
            <div className="relative">
              <button onClick={() => { setShowRoleDropdown(!showRoleDropdown); setShowLocationDropdown(false); setShowStatusDropdown(false); }}
                ref={roleFilterRef}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-[12px] transition-all ${
                  roleFilters.size > 0 ? 'border-[#635BFF]/40 text-[#635BFF]' : theme.filterButtonClass
                }`}
                style={{ fontWeight: 440 }}>
                <Tag size={13} />
                <span>Role</span>
                {roleFilters.size > 0 && (
                  <span className="px-1.5 py-0.5 rounded-full bg-[#635BFF] text-white text-[10px]" style={{ fontWeight: 540 }}>
                    {roleFilters.size}
                  </span>
                )}
                <ChevronDown size={13} />
              </button>
              <AnimatePresence>
                {showRoleDropdown && (
                  <FloatingDropdown
                    open={showRoleDropdown}
                    anchorRef={roleFilterRef}
                    className={`rounded-xl border overflow-hidden ${theme.dropdownClass}`}
                    onClose={() => setShowRoleDropdown(false)}
                    width={224}
                    zIndex={10010}
                  >
                    {roleOptions.slice(1).map((opt) => (
                      <button key={opt} onClick={() => toggleRoleFilter(opt)}
                        className={`w-full flex items-center gap-2.5 px-4 py-2.5 text-[12px] transition-colors text-left ${
                          roleFilters.has(opt)
                            ? 'bg-[#635BFF]/[0.08] text-[#635BFF]'
                            : `${theme.rowText} ${isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]'}`
                        }`}
                        style={{ fontWeight: roleFilters.has(opt) ? 500 : 420 }}>
                        <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-all shrink-0 ${
                          roleFilters.has(opt) ? 'bg-[#635BFF] border-[#635BFF]' : 'border-[#D1D5DB]'
                        }`}>
                          {roleFilters.has(opt) ? <Check size={10} className="text-white" strokeWidth={3} /> : null}
                        </div>
                        <span>{opt}</span>
                      </button>
                    ))}
                  </FloatingDropdown>
                )}
              </AnimatePresence>
            </div>

            {/* Location filter */}
            <div className="relative">
              <button onClick={() => { setShowLocationDropdown(!showLocationDropdown); setShowStatusDropdown(false); setShowRoleDropdown(false); }}
                ref={locationFilterRef}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-[12px] transition-all ${
                  locationFilters.size > 0 ? 'border-[#635BFF]/40 text-[#635BFF]' : theme.filterButtonClass
                }`}
                style={{ fontWeight: 440 }}>
                <MapPin size={13} />
                <span>Location</span>
                {locationFilters.size > 0 && (
                  <span className="px-1.5 py-0.5 rounded-full bg-[#635BFF] text-white text-[10px]" style={{ fontWeight: 540 }}>
                    {locationFilters.size}
                  </span>
                )}
                <ChevronDown size={13} />
              </button>
              <AnimatePresence>
                {showLocationDropdown && (
                  <FloatingDropdown
                    open={showLocationDropdown}
                    anchorRef={locationFilterRef}
                    className={`rounded-xl border overflow-hidden ${theme.dropdownClass}`}
                    onClose={() => setShowLocationDropdown(false)}
                    width={256}
                    zIndex={10010}
                  >
                    {locationOptions.slice(1).map((opt) => (
                      <button key={opt} onClick={() => toggleLocationFilter(opt)}
                        className={`w-full flex items-center gap-2.5 px-4 py-2.5 text-[12px] transition-colors text-left ${
                          locationFilters.has(opt)
                            ? 'bg-[#635BFF]/[0.08] text-[#635BFF]'
                            : `${theme.rowText} ${isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]'}`
                        }`}
                        style={{ fontWeight: locationFilters.has(opt) ? 500 : 420 }}>
                        <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-all shrink-0 ${
                          locationFilters.has(opt) ? 'bg-[#635BFF] border-[#635BFF]' : 'border-[#D1D5DB]'
                        }`}>
                          {locationFilters.has(opt) ? <Check size={10} className="text-white" strokeWidth={3} /> : null}
                        </div>
                        <span>{opt}</span>
                      </button>
                    ))}
                  </FloatingDropdown>
                )}
              </AnimatePresence>
            </div>

            {/* Status filter */}
            <div className="relative">
              <button onClick={() => { setShowStatusDropdown(!showStatusDropdown); setShowLocationDropdown(false); setShowRoleDropdown(false); }}
                ref={statusFilterRef}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-[12px] transition-all ${
                  statusFilters.size > 0 ? 'border-[#635BFF]/40 text-[#635BFF]' : theme.filterButtonClass
                }`}
                style={{ fontWeight: 440 }}>
                <Activity size={13} />
                <span>Status</span>
                {statusFilters.size > 0 && (
                  <span className="px-1.5 py-0.5 rounded-full bg-[#635BFF] text-white text-[10px]" style={{ fontWeight: 540 }}>
                    {statusFilters.size}
                  </span>
                )}
                <ChevronDown size={13} />
              </button>
              <AnimatePresence>
                {showStatusDropdown && (
                  <FloatingDropdown
                    open={showStatusDropdown}
                    anchorRef={statusFilterRef}
                    className={`rounded-xl border overflow-hidden ${theme.dropdownClass}`}
                    onClose={() => setShowStatusDropdown(false)}
                    width={192}
                    zIndex={10010}
                  >
                    {statusOptions.slice(1).map((opt) => (
                      <button key={opt} onClick={() => toggleStatusFilter(opt)}
                        className={`w-full flex items-center gap-2.5 px-4 py-2.5 text-[12px] transition-colors text-left ${
                          statusFilters.has(opt)
                            ? 'bg-[#635BFF]/[0.08] text-[#635BFF]'
                            : `${theme.rowText} ${isDark ? 'hover:bg-white/[0.04]' : 'hover:bg-[#F7F8FA]'}`
                        }`}
                        style={{ fontWeight: statusFilters.has(opt) ? 500 : 420 }}>
                        <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-all shrink-0 ${
                          statusFilters.has(opt) ? 'bg-[#635BFF] border-[#635BFF]' : 'border-[#D1D5DB]'
                        }`}>
                          {statusFilters.has(opt) ? <Check size={10} className="text-white" strokeWidth={3} /> : null}
                        </div>
                        <span>{opt}</span>
                      </button>
                    ))}
                  </FloatingDropdown>
                )}
              </AnimatePresence>
            </div>
          </div>

          <span className={`text-[12px] ml-auto ${theme.textSecondary}`} style={{ fontWeight: 420 }}>{filtered.length} employee{filtered.length !== 1 ? 's' : ''}</span>
        </div>
      </motion.div>

      {!workspaceReady ? null : !businessId ? (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}
          className={`rounded-2xl border px-8 py-16 text-center ${theme.panelClass}`}>
          <AlertCircle size={32} className={`mx-auto mb-3 ${theme.emptyIconClass}`} />
          <p className={`text-[14px] ${theme.textPrimary}`} style={{ fontWeight: 540 }}>No workspace business yet</p>
          <p className={`mt-1 text-[12px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>Create a business before managing employees.</p>
        </motion.div>
      ) : showBlockingLoader ? (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <TeamLoadingSkeleton dark={isDark} />
        </motion.div>
      ) : (
      /* Employee Table */
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}
        className={`rounded-2xl border overflow-hidden ${theme.panelClass}`}
        onMouseEnter={() => setIsTableHovered(true)}
        onMouseLeave={() => setIsTableHovered(false)}>
        {/* Desktop header / bulk actions */}
        <AnimatePresence mode="wait">
          {selectedCount > 0 ? (
            <motion.div
              key="bulk-header"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className={`hidden md:flex items-center justify-between px-5 py-3 border-b ${theme.borderClass} ${isDark ? 'bg-[#635BFF]/[0.12]' : 'bg-[#635BFF]/[0.04]'}`}>
              <div className="flex items-center gap-4">
                <button onClick={clearSelection} className={`p-1 rounded-lg transition-colors ${theme.closeButtonClass}`}>
                  <X size={14} className={theme.textTertiary} />
                </button>
                <span className={`text-[13px] ${theme.textPrimary}`} style={{ fontWeight: 520 }}>
                  {selectedCount} selected
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleBulkAction('assign-location')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[12px] transition-all ${theme.secondaryButtonClass}`}
                  style={{ fontWeight: 480 }}>
                  <MapPin size={12} />
                  Assign Location
                </button>
                <button
                  onClick={() => handleBulkAction('assign-role')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[12px] transition-all ${theme.secondaryButtonClass}`}
                  style={{ fontWeight: 480 }}>
                  <Tag size={12} />
                  Assign Role
                </button>
                <button
                  onClick={() => handleBulkAction('export')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[12px] transition-all ${theme.secondaryButtonClass}`}
                  style={{ fontWeight: 480 }}>
                  <Download size={12} />
                  Export
                </button>
                <div className={`h-5 w-px ${isDark ? 'bg-white/[0.08]' : 'bg-[#E5E7EB]'}`} />
                <button
                  onClick={() => handleBulkAction('remove')}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-red-200 hover:bg-red-50 transition-all text-[12px] text-red-500"
                  style={{ fontWeight: 480 }}>
                  <UserMinus size={12} />
                  Remove
                </button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="table-header"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              style={{
                gridTemplateColumns:
                  isTableHovered || selectedCount > 0
                    ? '44px 2fr 1fr 1fr 1fr 0.8fr 44px'
                    : '0px 2fr 1fr 1fr 1fr 0.8fr 44px',
              }}
              className={`hidden md:grid gap-4 px-5 py-3 border-b transition-all duration-200 ${theme.borderClass} ${theme.softSurfaceClass}`}>
              <motion.div
                animate={{ opacity: isTableHovered || selectedCount > 0 ? 1 : 0 }}
                transition={{ duration: 0.2 }}
                className="flex items-center justify-center overflow-hidden">
                <button
                  onClick={toggleAll}
                  className="w-4 h-4 rounded border-2 flex items-center justify-center transition-all border-[#D1D5DB] hover:border-[#635BFF]/40"
                >
                  {allVisibleSelected ? <Check size={10} className="text-[#635BFF]" strokeWidth={3} /> : null}
                </button>
              </motion.div>
              <button onClick={() => toggleSort('name')} className={`flex items-center gap-1.5 text-[11px] uppercase tracking-[0.04em] transition-colors ${theme.textSecondary} ${isDark ? 'hover:text-white' : 'hover:text-[#5E6D7A]'}`} style={{ fontWeight: 500 }}>
                Employee <ArrowUpDown size={11} />
              </button>
              <span className={`text-[11px] uppercase tracking-[0.04em] ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Roles</span>
              <span className={`text-[11px] uppercase tracking-[0.04em] ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Location</span>
              <span className={`text-[11px] uppercase tracking-[0.04em] ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Status</span>
              <button onClick={() => toggleSort('reliability')} className={`flex items-center gap-1.5 text-[11px] uppercase tracking-[0.04em] transition-colors ${theme.textSecondary} ${isDark ? 'hover:text-white' : 'hover:text-[#5E6D7A]'}`} style={{ fontWeight: 500 }}>
                Reliability <ArrowUpDown size={11} />
              </button>
              <span />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Mobile sort bar / bulk actions */}
        <AnimatePresence mode="wait">
          {selectedCount > 0 ? (
            <motion.div
              key="mobile-bulk"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className={`md:hidden px-4 py-3 border-b ${theme.borderClass} ${isDark ? 'bg-[#635BFF]/[0.12]' : 'bg-[#635BFF]/[0.04]'}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <button onClick={clearSelection} className={`p-1 rounded-lg transition-colors ${theme.closeButtonClass}`}>
                    <X size={14} className={theme.textTertiary} />
                  </button>
                  <span className={`text-[12px] ${theme.textPrimary}`} style={{ fontWeight: 520 }}>
                    {selectedCount} selected
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
                <button
                  onClick={() => handleBulkAction('assign-location')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[11px] whitespace-nowrap transition-all ${theme.secondaryButtonClass}`}
                  style={{ fontWeight: 480 }}>
                  <MapPin size={11} />
                  Location
                </button>
                <button
                  onClick={() => handleBulkAction('assign-role')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[11px] whitespace-nowrap transition-all ${theme.secondaryButtonClass}`}
                  style={{ fontWeight: 480 }}>
                  <Tag size={11} />
                  Role
                </button>
                <button
                  onClick={() => handleBulkAction('export')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[11px] whitespace-nowrap transition-all ${theme.secondaryButtonClass}`}
                  style={{ fontWeight: 480 }}>
                  <Download size={11} />
                  Export
                </button>
                <button
                  onClick={() => handleBulkAction('remove')}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-red-200 text-[11px] text-red-500 whitespace-nowrap"
                  style={{ fontWeight: 480 }}>
                  <UserMinus size={11} />
                  Remove
                </button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="mobile-sort"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className={`md:hidden flex items-center gap-2 px-4 py-3 border-b overflow-x-auto ${theme.borderClass} ${theme.softSurfaceClass}`}>
              <button onClick={toggleAll} className="shrink-0">
                <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-all ${
                  allVisibleSelected ? 'bg-[#635BFF] border-[#635BFF]' : 'border-[#D1D5DB]'
                }`}>
                  {allVisibleSelected ? <Check size={10} className="text-white" strokeWidth={3} /> : null}
                </div>
              </button>
              <div className={`h-4 w-px ${isDark ? 'bg-white/[0.08]' : 'bg-[#E5E7EB]'}`} />
              <span className={`text-[10px] uppercase tracking-[0.04em] shrink-0 ${theme.textSecondary}`} style={{ fontWeight: 500 }}>Sort:</span>
              {(['name', 'reliability'] as const).map((field) => (
                <button key={field} onClick={() => toggleSort(field)}
                  className={`shrink-0 px-2.5 py-1 rounded-full text-[11px] transition-colors ${
                    sortField === field ? 'bg-[#635BFF]/10 text-[#635BFF]' : `${theme.textSecondary} ${theme.subtleSurfaceClass}`
                  }`}
                  style={{ fontWeight: sortField === field ? 520 : 420 }}>
                  {field.charAt(0).toUpperCase() + field.slice(1)} {sortField === field && (sortDir === 'asc' ? '\u2191' : '\u2193')}
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Rows - Desktop Table */}
        <div className="hidden md:block">
          {filtered.map((emp, i) => {
            const primaryRole = emp.roles[0] || 'Unassigned';
            const color = roleColors[primaryRole] || '#635BFF';
            const primaryLoc = getPrimaryLocation(emp);
            const reliabilityColor = getReliabilityColor(emp.reliability);
            return (
              <motion.div
                key={emp.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.25, delay: i * 0.02 }}
                style={{
                  gridTemplateColumns:
                    isTableHovered || selectedCount > 0
                      ? '44px 2fr 1fr 1fr 1fr 0.8fr 44px'
                      : '0px 2fr 1fr 1fr 1fr 0.8fr 44px',
                }}
                className={`grid gap-4 px-5 py-3.5 border-b last:border-0 transition-all duration-200 group ${
                  selectedEmployees.has(emp.id) ? 'bg-[#635BFF]/[0.02]' : ''
                } ${theme.rowBorderClass} ${theme.rowHoverClass}`}
              >
                <motion.div
                  animate={{ opacity: isTableHovered || selectedCount > 0 ? 1 : 0 }}
                  transition={{ duration: 0.2 }}
                  className="flex items-center justify-center overflow-hidden"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleEmployee(emp.id);
                  }}
                >
                  <button
                    className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-all ${
                      selectedEmployees.has(emp.id)
                        ? 'bg-[#635BFF] border-[#635BFF]'
                        : 'border-[#D1D5DB] hover:border-[#635BFF]/40'
                    }`}
                  >
                    {selectedEmployees.has(emp.id) ? <Check size={10} className="text-white" strokeWidth={3} /> : null}
                  </button>
                </motion.div>
                <div className="flex items-center gap-3 min-w-0 cursor-pointer" onClick={() => openEmployeeEditor(emp)}>
                  <div className="w-9 h-9 rounded-full flex items-center justify-center text-[11px] text-white shrink-0"
                    style={{ fontWeight: 600, background: `linear-gradient(135deg, ${color}, ${color}CC)` }}>
                    {emp.avatar}
                  </div>
                  <div className="min-w-0">
                    <p className={`text-[13px] truncate ${theme.textPrimary}`} style={{ fontWeight: 520 }}>{emp.name}</p>
                    <p className={`text-[11px] truncate ${theme.textSecondary}`} style={{ fontWeight: 400 }}>{emp.email}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap cursor-pointer" onClick={() => openEmployeeEditor(emp)}>
                  <span className="text-[11px] px-2.5 py-1 rounded-full" style={{ fontWeight: 500, color, background: `${color}10` }}>{primaryRole}</span>
                  {emp.roles.length > 1 ? (
                    <RolesTooltip dark={isDark} roleColors={roleColors} roles={emp.roles.slice(1)} />
                  ) : null}
                </div>
                <div className="flex items-center gap-1.5 min-w-0 cursor-pointer" onClick={() => openEmployeeEditor(emp)}>
                  {primaryLoc ? (
                    <>
                      <span className="text-[13px]">{primaryLoc.emoji}</span>
                      <span className={`text-[12px] truncate ${theme.textTertiary}`} style={{ fontWeight: 440 }}>{primaryLoc.name.split(' ')[0]}</span>
                      {emp.locations.length > 1 ? (
                        <LocationsTooltip dark={isDark} locations={emp.locations.slice(1)} />
                      ) : null}
                    </>
                  ) : null}
                </div>
                <div className="flex items-center cursor-pointer" onClick={() => openEmployeeEditor(emp)}>
                  <StatusWithInfo dark={isDark} descriptionOverride={emp.statusReason} status={emp.status} />
                </div>
                <div className="flex items-center gap-1.5 cursor-pointer" onClick={() => openEmployeeEditor(emp)}>
                  <ShieldCheck size={13} style={{ color: reliabilityColor }} />
                  <span className="text-[13px] tabular-nums" style={{ fontWeight: 520, color: reliabilityColor }}>{emp.reliability}%</span>
                </div>
                <div className="flex items-center justify-center">
                  <button onClick={(e) => { e.stopPropagation(); openEmployeeEditor(emp); }}
                    className={`p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-all ${theme.closeButtonClass}`}>
                    <Eye size={14} className="text-[#8898AA]" />
                  </button>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Rows - Mobile Cards */}
        <div className={`md:hidden divide-y ${isDark ? 'divide-white/[0.06]' : 'divide-[#F7F8FA]'}`}>
          {filtered.map((emp, i) => {
            const primaryRole = emp.roles[0] || 'Unassigned';
            const color = roleColors[primaryRole] || '#635BFF';
            const primaryLoc = getPrimaryLocation(emp);
            const reliabilityColor = getReliabilityColor(emp.reliability);
            return (
              <motion.div key={emp.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, delay: i * 0.02 }}
                className={`px-4 py-3.5 transition-colors ${selectedEmployees.has(emp.id) ? 'bg-[#635BFF]/[0.02]' : ''} ${isDark ? 'active:bg-white/[0.03]' : 'active:bg-[#FAFBFC]'}`}>
                <div className="flex items-center gap-3">
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleEmployee(emp.id); }}
                    className={`shrink-0 w-4 h-4 rounded border-2 flex items-center justify-center transition-all ${
                      selectedEmployees.has(emp.id) ? 'bg-[#635BFF] border-[#635BFF]' : 'border-[#D1D5DB]'
                    }`}
                  >
                    {selectedEmployees.has(emp.id) ? <Check size={10} className="text-white" strokeWidth={3} /> : null}
                  </button>
                  <div
                    onClick={() => (selectedCount > 0 ? toggleEmployee(emp.id) : openEmployeeEditor(emp))}
                    className="flex items-center gap-3 flex-1 min-w-0 cursor-pointer"
                  >
                    <div className="w-10 h-10 rounded-full flex items-center justify-center text-[12px] text-white shrink-0"
                      style={{ fontWeight: 600, background: `linear-gradient(135deg, ${color}, ${color}CC)` }}>
                      {emp.avatar}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p className={`text-[14px] truncate ${theme.textPrimary}`} style={{ fontWeight: 520 }}>{emp.name}</p>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <ShieldCheck size={12} style={{ color: reliabilityColor }} />
                          <span className="text-[11px] tabular-nums" style={{ fontWeight: 520, color: reliabilityColor }}>{emp.reliability}%</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ fontWeight: 500, color, background: `${color}10` }}>{primaryRole}</span>
                        {primaryLoc ? <span className={`text-[11px] ${theme.textSecondary}`} style={{ fontWeight: 420 }}>{primaryLoc.emoji} {primaryLoc.name.split(' ')[0]}</span> : null}
                        <div className="flex items-center gap-1.5 ml-auto shrink-0">
                          <div className="w-1.5 h-1.5 rounded-full" style={{ background: statusConfig[emp.status].color }} />
                          <span className="text-[11px]" style={{ fontWeight: 460, color: statusConfig[emp.status].color }}>{statusConfig[emp.status].label}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

        {filtered.length === 0 && (
          <div className="px-8 py-16 text-center">
            <AlertCircle size={32} className={`mx-auto mb-3 ${theme.emptyIconClass}`} />
            <p className={`text-[14px] ${theme.textSecondary}`} style={{ fontWeight: 480 }}>No employees match your filters</p>
            <p className={`mt-1 text-[12px] ${isDark ? 'text-[#8898AA]' : 'text-[#C1CED8]'}`} style={{ fontWeight: 420 }}>Try adjusting your search or filter criteria</p>
          </div>
        )}
      </motion.div>
      )}

      {/* Modals */}
      <AnimatePresence>
        {showAddModal && businessId && (
          <EmployeeEnrollmentModal
            businessId={businessId}
            businessLocations={businessLocations}
            defaultLocationId={defaultBusinessLocation?.id ?? null}
            defaultLocationName={defaultBusinessLocation ? locationDisplayName(defaultBusinessLocation) : null}
            dark={isDark}
            onClose={() => setShowAddModal(false)}
            onCreated={handleAddEmployee}
            roles={businessRoles}
          />
        )}
        {showBulkModal && businessId && (
          <EmployeeBulkUploadModal
            businessId={businessId}
            defaultLocationId={defaultBusinessLocation?.id ?? null}
            defaultLocationName={defaultBusinessLocation ? locationDisplayName(defaultBusinessLocation) : null}
            dark={isDark}
            onClose={() => setShowBulkModal(false)}
            onImported={async (result) => {
              await handleBulkImported(result);
            }}
          />
        )}
        {showBulkAssignLocation && businessId ? (
          <BulkAssignLocationsModal
            count={selectedCount}
            dark={isDark}
            initialSelectedLocationIds={sharedSelectedLocationIds}
            locations={businessLocations}
            onClose={() => setShowBulkAssignLocation(false)}
            onConfirm={async (locationIds) => {
              await handleBulkAssignLocations(locationIds);
              setShowBulkAssignLocation(false);
            }}
          />
        ) : null}
        {showBulkAssignRole && businessId ? (
          <BulkAssignRolesModal
            count={selectedCount}
            dark={isDark}
            initialSelectedRoleIds={sharedSelectedRoleIds}
            roles={businessRoles}
            onClose={() => setShowBulkAssignRole(false)}
            onConfirm={async (roleIds) => {
              await handleBulkAssignRoles(roleIds);
              setShowBulkAssignRole(false);
            }}
          />
        ) : null}
        {showBulkExport ? (
          <BulkExportModal
            count={selectedCount}
            dark={isDark}
            onClose={() => setShowBulkExport(false)}
            onConfirm={handleBulkExport}
          />
        ) : null}
        {showBulkRemove ? (
          <BulkRemoveModal
            count={selectedCount}
            dark={isDark}
            onClose={() => setShowBulkRemove(false)}
            onConfirm={async () => {
              await handleBulkRemove();
            }}
          />
        ) : null}
        {selectedEmployee && businessId && (
          <EmployeeDetail
            businessId={businessId}
            dark={isDark}
            employee={selectedEmployee}
            locations={businessLocations}
            onClose={closeEmployeeEditor}
            onDelete={handleDeleteEmployee}
            onSave={handleSaveEmployee}
            onRoleCreated={(role) => {
              setBusinessRoles((current) =>
                current.some((item) => item.id === role.id) ? current : [...current, role],
              );
            }}
            roles={businessRoles}
          />
        )}
      </AnimatePresence>
    </>
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav="Team">{content}</DashboardShell>;
}
