"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import {
  AlertCircle,
  ArrowUpDown,
  Check,
  Download,
  Eye,
  Info,
  MapPin,
  Plus,
  Search,
  Shield,
  Upload,
  UserPlus,
  X,
} from "lucide-react";

import {
  useAppWorkspace,
  useAppWorkspaceReady,
} from "@/components/app-workspace";
import { useResolvedAppAppearance } from "@/components/app-session-gate";
import {
  listBusinessLocations,
  listBusinessRoles,
  type BusinessLocation,
  type BusinessRole,
} from "@/lib/api/businesses";
import {
  createEmployee,
  downloadEmployeeImportTemplate,
  getEmployeeProfile,
  importEmployees,
  listEmployees,
  updateEmployee,
  type EmployeeBulkImportResponse,
  type EmployeeProfile,
  type EmployeeSummary,
} from "@/lib/api/workforce";
import { resolvePreferredWorkspaceBusiness } from "@/lib/workspace-business";

import { BrandedSelect } from "./BrandedSelect";
import DashboardShell from "./DashboardShell";

/* ─── Types ─── */

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

type EmployeeFormState = {
  fullName: string;
  preferredName: string;
  email: string;
  phone: string;
  employmentType: string;
  status: string;
  notes: string;
  selectedRoleIds: string[];
  primaryRoleId: string;
  selectedLocationIds: string[];
  primaryLocationId: string;
};

type EmployeeFormControls = {
  state: EmployeeFormState;
  setState(next: EmployeeFormState): void;
  setField(field: keyof EmployeeFormState, value: string): void;
  toggleRole(roleId: string): void;
  setPrimaryRole(roleId: string): void;
  toggleLocation(locationId: string): void;
  setPrimaryLocation(locationId: string): void;
};

type TooltipListItem = {
  key: string;
  label: string;
  accent?: string;
  icon?: ReactNode;
};

/* ─── Constants ─── */

const statusOptions = [
  { value: "all", label: "All Status" },
  { value: "active", label: "Active" },
  { value: "on_leave", label: "On Leave" },
  { value: "inactive", label: "Inactive" },
];

const statusConfig: Record<
  string,
  { label: string; color: string; bg: string; description: string }
> = {
  active: {
    label: "Active",
    color: "#00D4AA",
    bg: "rgba(0, 212, 170, 0.10)",
    description: "Included in normal scheduling and outreach.",
  },
  on_leave: {
    label: "On Leave",
    color: "#F59E0B",
    bg: "rgba(245, 158, 11, 0.10)",
    description: "Temporarily unavailable until management reactivates them.",
  },
  inactive: {
    label: "Inactive",
    color: "#8898AA",
    bg: "rgba(136, 152, 170, 0.12)",
    description: "Kept in the roster but excluded from active scheduling.",
  },
};

const roleTonePalette = [
  "#635BFF",
  "#3B82F6",
  "#00D4AA",
  "#F59E0B",
  "#E5484D",
  "#8B5CF6",
];

/* ─── Utilities ─── */

function emptyEmployeeForm(defaultLocationId?: string): EmployeeFormState {
  return {
    fullName: "",
    preferredName: "",
    email: "",
    phone: "",
    employmentType: "",
    status: "active",
    notes: "",
    selectedRoleIds: [],
    primaryRoleId: "",
    selectedLocationIds: defaultLocationId ? [defaultLocationId] : [],
    primaryLocationId: defaultLocationId ?? "",
  };
}

function buildEmployeeForm(profile: EmployeeProfile): EmployeeFormState {
  const selectedRoleIds = profile.roles.map((role) => role.role_id);
  const selectedLocationIds = profile.locations.map((loc) => loc.location_id);
  return {
    fullName: profile.full_name,
    preferredName: profile.preferred_name ?? "",
    email: profile.email ?? "",
    phone: profile.phone_e164 ?? "",
    employmentType: profile.employment_type ?? "",
    status: profile.status,
    notes: profile.notes ?? "",
    selectedRoleIds,
    primaryRoleId:
      profile.roles.find((r) => r.is_primary)?.role_id ?? selectedRoleIds[0] ?? "",
    selectedLocationIds,
    primaryLocationId:
      profile.locations.find((l) => l.is_primary)?.location_id ??
      selectedLocationIds[0] ??
      "",
  };
}

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function displayName(employee: EmployeeSummary): string {
  return employee.preferred_name?.trim() || employee.full_name;
}

function employeeInitials(name: string): string {
  return (
    name
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "BF"
  );
}

function formatLocationMeta(location: BusinessLocation): string {
  return [location.address_line_1, location.locality, location.region]
    .filter((v): v is string => Boolean(v))
    .join(", ");
}

function roleTone(roleName?: string | null): string {
  if (!roleName) return "#635BFF";
  const hash = Array.from(roleName).reduce((t, c) => t + c.charCodeAt(0), 0);
  return roleTonePalette[hash % roleTonePalette.length] ?? "#635BFF";
}

function uniqueOrdered(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const value of values) {
    const n = value?.trim();
    if (!n || seen.has(n)) continue;
    seen.add(n);
    ordered.push(n);
  }
  return ordered;
}

function extraRoleNames(employee: EmployeeSummary): string[] {
  return uniqueOrdered(
    employee.role_names.filter((r) => r !== employee.primary_role_name),
  );
}

function extraLocationNames(employee: EmployeeSummary): string[] {
  return uniqueOrdered(
    employee.location_names.filter((l) => l !== employee.primary_location_name),
  );
}

function employeeNeedsAssignment(employee: EmployeeSummary): boolean {
  return employee.role_ids.length === 0 || employee.location_ids.length === 0;
}

function sortEmployees(
  employees: EmployeeSummary[],
  field: "name" | "role" | "location",
  direction: "asc" | "desc",
): EmployeeSummary[] {
  const factor = direction === "asc" ? 1 : -1;
  return [...employees].sort((l, r) => {
    if (field === "role")
      return (l.primary_role_name ?? "").localeCompare(r.primary_role_name ?? "") * factor;
    if (field === "location")
      return (
        (l.primary_location_name ?? "").localeCompare(r.primary_location_name ?? "") * factor
      );
    return displayName(l).localeCompare(displayName(r)) * factor;
  });
}

/* ─── Hooks ─── */

function useEmployeeForm(initialState: EmployeeFormState): EmployeeFormControls {
  const [state, setState] = useState<EmployeeFormState>(initialState);

  const setField = (field: keyof EmployeeFormState, value: string) => {
    setState((c) => ({ ...c, [field]: value }));
  };

  const toggleRole = (roleId: string) => {
    setState((c) => {
      const selectedRoleIds = c.selectedRoleIds.includes(roleId)
        ? c.selectedRoleIds.filter((id) => id !== roleId)
        : [...c.selectedRoleIds, roleId];
      const primaryRoleId = selectedRoleIds.includes(c.primaryRoleId)
        ? c.primaryRoleId
        : selectedRoleIds[0] ?? "";
      return { ...c, selectedRoleIds, primaryRoleId };
    });
  };

  const setPrimaryRole = (roleId: string) => {
    setState((c) => ({ ...c, primaryRoleId: roleId }));
  };

  const toggleLocation = (locationId: string) => {
    setState((c) => {
      const selectedLocationIds = c.selectedLocationIds.includes(locationId)
        ? c.selectedLocationIds.filter((id) => id !== locationId)
        : [...c.selectedLocationIds, locationId];
      const primaryLocationId = selectedLocationIds.includes(c.primaryLocationId)
        ? c.primaryLocationId
        : selectedLocationIds[0] ?? "";
      return { ...c, selectedLocationIds, primaryLocationId };
    });
  };

  const setPrimaryLocation = (locationId: string) => {
    setState((c) => ({ ...c, primaryLocationId: locationId }));
  };

  return { state, setState, setField, toggleRole, setPrimaryRole, toggleLocation, setPrimaryLocation };
}

/* ─── Shared UI primitives ─── */

function TextInput({
  dark,
  multiline = false,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  dark: boolean;
  multiline?: boolean;
  value: string;
  onChange(value: string): void;
  placeholder: string;
  type?: string;
}) {
  const base = `w-full rounded-2xl border px-3.5 py-2.5 text-[13px] placeholder-[#8898AA]/50 transition-all focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.12)] ${
    dark
      ? "border-white/[0.06] bg-white/[0.04] text-white focus:border-[#635BFF]/40"
      : "border-[#E5E7EB] bg-white text-[#0A2540] focus:border-[#635BFF]/40"
  }`;

  if (multiline)
    return (
      <textarea
        className={`${base} min-h-[96px] resize-none`}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        value={value}
      />
    );

  return (
    <input
      className={base}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      type={type}
      value={value}
    />
  );
}

function SectionLabel({ label, muted }: { label: string; muted: string }) {
  return (
    <p className={`mb-2 text-[11px] uppercase tracking-[0.04em] ${muted}`} style={{ fontWeight: 500 }}>
      {label}
    </p>
  );
}

function SelectionGrid({
  dark,
  items,
  selectedIds,
  onToggle,
}: {
  dark: boolean;
  items: Array<{ id: string; label: string; meta: string }>;
  selectedIds: string[];
  onToggle(id: string): void;
}) {
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {items.map((item) => {
        const selected = selectedSet.has(item.id);
        return (
          <button
            key={item.id}
            className={`flex items-start gap-3 rounded-2xl border px-3.5 py-3 text-left transition-all ${
              selected
                ? "border-[#635BFF]/30 bg-[#635BFF]/[0.08]"
                : dark
                  ? "border-white/[0.06] bg-white/[0.03] hover:bg-white/[0.05]"
                  : "border-[#E5E7EB] bg-[#F7F8FA] hover:bg-[#F0F0F5]"
            }`}
            onClick={() => onToggle(item.id)}
            type="button"
          >
            <div
              className={`mt-0.5 flex h-5 w-5 items-center justify-center rounded-md border ${
                selected
                  ? "border-[#635BFF] bg-[#635BFF] text-white"
                  : dark
                    ? "border-white/[0.14]"
                    : "border-[#D1D5DB]"
              }`}
            >
              {selected ? <Check size={12} /> : null}
            </div>
            <div className="min-w-0 flex-1">
              <p
                className={`truncate text-[13px] ${dark ? "text-white" : "text-[#0A2540]"}`}
                style={{ fontWeight: 520 }}
              >
                {item.label}
              </p>
              <p className="mt-1 truncate text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                {item.meta}
              </p>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function TooltipPanel({
  dark,
  children,
  widthClass = "w-52",
}: {
  dark: boolean;
  children: ReactNode;
  widthClass?: string;
}) {
  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      className={`absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 rounded-xl border px-3 py-2.5 shadow-[0_12px_36px_rgba(0,0,0,0.22)] ${widthClass} ${
        dark
          ? "border-white/[0.08] bg-[#0A2540] text-[#E6EDF5]"
          : "border-[#E5E7EB] bg-white text-[#3E4C59]"
      }`}
      exit={{ opacity: 0, y: 4 }}
      initial={{ opacity: 0, y: 4 }}
    >
      {children}
    </motion.div>
  );
}

function StatusWithInfo({ dark, status }: { dark: boolean; status: string }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const config = statusConfig[status] ?? statusConfig.inactive;

  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-1.5 rounded-full" style={{ background: config.color }} />
      <span className="text-[12px]" style={{ color: config.color, fontWeight: 480 }}>
        {config.label}
      </span>
      <div
        className="relative"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <button className="rounded-full p-0.5 text-[#C1CED8]/60 transition-colors hover:text-[#8898AA]" type="button">
          <Info size={12} />
        </button>
        <AnimatePresence>
          {showTooltip ? (
            <TooltipPanel dark={dark} widthClass="w-48">
              <p className="text-center text-[11px]" style={{ fontWeight: 440 }}>
                {config.description}
              </p>
            </TooltipPanel>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}

function OverflowPill({ dark, items }: { dark: boolean; items: TooltipListItem[] }) {
  const [showTooltip, setShowTooltip] = useState(false);

  if (!items.length) return null;

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span
        className={`cursor-default rounded-full px-1.5 py-0.5 text-[10px] transition-colors ${
          dark
            ? "bg-white/[0.06] text-[#C1CED8] hover:bg-white/[0.10]"
            : "bg-[#F7F8FA] text-[#8898AA] hover:bg-[#F0F0F5]"
        }`}
        style={{ fontWeight: 440 }}
      >
        +{items.length}
      </span>
      <AnimatePresence>
        {showTooltip ? (
          <TooltipPanel dark={dark} widthClass="min-w-[10rem] max-w-[16rem]">
            <div className="flex flex-col gap-1.5">
              {items.map((item) => (
                <div key={item.key} className="flex items-center gap-2">
                  {item.icon ? (
                    <span className="shrink-0 text-[#8898AA]">{item.icon}</span>
                  ) : (
                    <div
                      className="h-1.5 w-1.5 shrink-0 rounded-full"
                      style={{ background: item.accent ?? "#635BFF" }}
                    />
                  )}
                  <span className="text-[11px]" style={{ fontWeight: 460 }}>
                    {item.label}
                  </span>
                </div>
              ))}
            </div>
          </TooltipPanel>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function EmployeeRoleCell({ dark, employee }: { dark: boolean; employee: EmployeeSummary }) {
  const primaryRole = employee.primary_role_name ?? "Unassigned";
  const accent = employee.primary_role_name ? roleTone(employee.primary_role_name) : "#8898AA";
  const extras = extraRoleNames(employee).map((r) => ({ key: r, label: r, accent: roleTone(r) }));

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span
        className="rounded-full px-2.5 py-1 text-[11px]"
        style={{
          fontWeight: 520,
          color: accent,
          background: employee.primary_role_name ? `${accent}12` : "rgba(136,152,170,0.10)",
        }}
      >
        {primaryRole}
      </span>
      <OverflowPill dark={dark} items={extras} />
    </div>
  );
}

function EmployeeLocationCell({
  dark,
  employee,
  textSecondary,
}: {
  dark: boolean;
  employee: EmployeeSummary;
  textSecondary: string;
}) {
  const primaryLocation = employee.primary_location_name ?? "Unassigned";
  const extras = extraLocationNames(employee).map((l) => ({
    key: l,
    label: l,
    icon: <MapPin size={11} />,
  }));

  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <MapPin className="text-[#8898AA] shrink-0" size={13} />
      <span className={`truncate text-[12px] ${textSecondary}`} style={{ fontWeight: 440 }}>
        {primaryLocation}
      </span>
      <OverflowPill dark={dark} items={extras} />
    </div>
  );
}

function EmployeeAssignmentFields({
  controls,
  dark,
  includeStatus,
  locations,
  roles,
}: {
  controls: EmployeeFormControls;
  dark: boolean;
  includeStatus: boolean;
  locations: BusinessLocation[];
  roles: BusinessRole[];
}) {
  const { state, setField, toggleRole, setPrimaryRole, toggleLocation, setPrimaryLocation } = controls;
  const muted = "text-[#8898AA]";
  const noDataClass = `rounded-2xl border px-4 py-3 text-[12px] ${
    dark
      ? "border-white/[0.06] bg-white/[0.03] text-[#C1CED8]"
      : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
  }`;

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <SectionLabel label="Full Name" muted={muted} />
          <TextInput dark={dark} onChange={(v) => setField("fullName", v)} placeholder="Taylor Smith" value={state.fullName} />
        </div>
        <div>
          <SectionLabel label="Preferred Name" muted={muted} />
          <TextInput dark={dark} onChange={(v) => setField("preferredName", v)} placeholder="Taylor" value={state.preferredName} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <SectionLabel label="Email" muted={muted} />
          <TextInput dark={dark} onChange={(v) => setField("email", v)} placeholder="taylor@company.com" type="email" value={state.email} />
        </div>
        <div>
          <SectionLabel label="Phone" muted={muted} />
          <TextInput dark={dark} onChange={(v) => setField("phone", v)} placeholder="+15555550123" type="tel" value={state.phone} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <SectionLabel label="Employment Type" muted={muted} />
          <TextInput dark={dark} onChange={(v) => setField("employmentType", v)} placeholder="full_time, part_time, seasonal" value={state.employmentType} />
        </div>
        {includeStatus ? (
          <div>
            <SectionLabel label="Status" muted={muted} />
            <BrandedSelect
              dark={dark}
              onChange={(e: { target: { value: string } }) => setField("status", e.target.value)}
              value={state.status}
            >
              <option value="active">Active</option>
              <option value="on_leave">On Leave</option>
              <option value="inactive">Inactive</option>
            </BrandedSelect>
          </div>
        ) : null}
      </div>

      <div>
        <SectionLabel label="Roles" muted={muted} />
        {roles.length ? (
          <SelectionGrid dark={dark} items={roles.map((r) => ({ id: r.id, label: r.name, meta: r.code }))} onToggle={toggleRole} selectedIds={state.selectedRoleIds} />
        ) : (
          <div className={noDataClass}>No business roles yet. You can still create the employee now and assign roles later.</div>
        )}
      </div>

      <div>
        <SectionLabel label="Primary Role" muted={muted} />
        <BrandedSelect dark={dark} disabled={!state.selectedRoleIds.length} onChange={(e: { target: { value: string } }) => setPrimaryRole(e.target.value)} value={state.primaryRoleId}>
          <option value="">Select primary role</option>
          {roles.filter((r) => state.selectedRoleIds.includes(r.id)).map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </BrandedSelect>
      </div>

      <div>
        <SectionLabel label="Locations" muted={muted} />
        {locations.length ? (
          <SelectionGrid dark={dark} items={locations.map((l) => ({ id: l.id, label: l.name, meta: formatLocationMeta(l) || l.timezone }))} onToggle={toggleLocation} selectedIds={state.selectedLocationIds} />
        ) : (
          <div className={noDataClass}>No active locations yet. Add locations first or leave this employee unassigned for now.</div>
        )}
      </div>

      <div>
        <SectionLabel label="Primary Location" muted={muted} />
        <BrandedSelect dark={dark} disabled={!state.selectedLocationIds.length} onChange={(e: { target: { value: string } }) => setPrimaryLocation(e.target.value)} value={state.primaryLocationId}>
          <option value="">Select primary location</option>
          {locations.filter((l) => state.selectedLocationIds.includes(l.id)).map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </BrandedSelect>
      </div>

      <div>
        <SectionLabel label="Notes" muted={muted} />
        <TextInput dark={dark} multiline onChange={(v) => setField("notes", v)} placeholder="Operational notes for managers" value={state.notes} />
      </div>

      {!state.selectedRoleIds.length || !state.selectedLocationIds.length ? (
        <div className={noDataClass}>
          Employees remain in <span style={{ fontWeight: 520 }}>Needs Assignment</span> until they have at least one role and one location.
        </div>
      ) : null}
    </div>
  );
}

/* ─── Add Employee Modal ─── */

function AddEmployeeModal({
  businessId,
  businessName,
  dark,
  locations,
  onClose,
  onCreated,
  roles,
}: {
  businessId: string;
  businessName: string;
  dark: boolean;
  locations: BusinessLocation[];
  onClose(): void;
  onCreated(nextEmployee: EmployeeSummary): Promise<void>;
  roles: BusinessRole[];
}) {
  const defaultLocationId = locations.length === 1 ? locations[0]?.id : undefined;
  const controls = useEmployeeForm(emptyEmployeeForm(defaultLocationId));
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.06]" : "border-[#E5E7EB]";
  const singleLocationName = locations.length === 1 ? locations[0]?.name ?? null : null;

  const canSubmit =
    Boolean(controls.state.fullName.trim()) &&
    Boolean(controls.state.email.trim()) &&
    Boolean(controls.state.phone.trim()) &&
    Boolean(controls.state.selectedRoleIds.length) &&
    Boolean(controls.state.primaryRoleId) &&
    Boolean(controls.state.selectedLocationIds.length) &&
    Boolean(controls.state.primaryLocationId);

  const handleSubmit = () => {
    if (!canSubmit || isPending) return;
    startTransition(async () => {
      try {
        setFeedback(null);
        const desiredLocations = controls.state.selectedLocationIds.map((id) => ({
          location_id: id,
          is_primary: id === controls.state.primaryLocationId,
        }));
        const desiredRoles = controls.state.selectedRoleIds.map((id) => ({
          role_id: id,
          is_primary: id === controls.state.primaryRoleId,
        }));

        const created = await createEmployee(businessId, {
          full_name: controls.state.fullName.trim(),
          preferred_name: normalizeOptional(controls.state.preferredName),
          email: normalizeOptional(controls.state.email),
          phone_e164: normalizeOptional(controls.state.phone),
          employment_type: normalizeOptional(controls.state.employmentType),
          notes: normalizeOptional(controls.state.notes),
          primary_location_id: normalizeOptional(controls.state.primaryLocationId),
          employee_metadata: { source: "team_ui" },
        });

        let nextEmployee: EmployeeSummary = created;
        if (desiredRoles.length || desiredLocations.length) {
          nextEmployee = await updateEmployee(businessId, created.id, {
            roles: desiredRoles,
            locations: desiredLocations,
          });
        }

        await onCreated(nextEmployee);
        onClose();
      } catch (error) {
        setFeedback({
          tone: "error",
          message: error instanceof Error ? error.message : "Could not add this employee.",
        });
      }
    });
  };

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      exit={{ opacity: 0 }}
      initial={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className={`mx-4 w-full max-w-3xl overflow-hidden rounded-[28px] border ${
          dark ? "border-white/[0.06] bg-[#0A2540]" : "border-[#E5E7EB] bg-white"
        }`}
        exit={{ opacity: 0, scale: 0.96, y: 16 }}
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        onClick={(e) => e.stopPropagation()}
        transition={{ duration: 0.22 }}
        style={dark ? { boxShadow: "0 32px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(99,91,255,0.08)" } : undefined}
      >
        {/* Header */}
        <div className={`border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#635BFF]/10">
                <UserPlus className="text-[#635BFF]" size={18} />
              </div>
              <div>
                <h2 className={`text-[18px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  Add Employee
                </h2>
                <p className={`mt-0.5 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Add a new employee to {businessName}.
                </p>
              </div>
            </div>
            <button
              className={`rounded-full p-2 transition-colors ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`}
              onClick={onClose}
              type="button"
            >
              <X className="text-[#8898AA]" size={16} />
            </button>
          </div>
          {singleLocationName ? (
            <div
              className={`mt-4 rounded-2xl border px-4 py-3 text-[12px] ${
                dark ? "border-white/[0.06] bg-white/[0.03] text-[#C1CED8]" : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
              }`}
            >
              Only one active location exists — new employees default to{" "}
              <span style={{ fontWeight: 520 }}>{singleLocationName}</span>.
            </div>
          ) : null}
        </div>

        {/* Body */}
        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">
          {feedback ? (
            <div
              className="mb-4 rounded-2xl px-4 py-3 text-[13px]"
              role="status"
              style={{ background: "rgba(229,72,77,0.08)", color: "#C13535", fontWeight: 500 }}
            >
              {feedback.message}
            </div>
          ) : null}
          {!canSubmit ? (
            <div
              className={`mb-4 rounded-2xl border px-4 py-3 text-[12px] ${
                dark ? "border-white/[0.06] bg-white/[0.03] text-[#C1CED8]" : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
              }`}
            >
              Name, phone, email, at least one role, and at least one location are required.
            </div>
          ) : null}
          <EmployeeAssignmentFields
            controls={controls}
            dark={dark}
            includeStatus={false}
            locations={locations}
            roles={roles}
          />
        </div>

        {/* Footer */}
        <div className={`flex items-center justify-end gap-3 border-t px-6 py-4 ${borderClass}`}>
          <button
            className={`rounded-full border px-4 py-2.5 text-[13px] transition-colors ${
              dark ? "border-white/[0.06] text-[#C1CED8] hover:bg-white/[0.06]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
            }`}
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-full px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-40 transition-all"
            disabled={!canSubmit || isPending}
            onClick={handleSubmit}
            style={{ fontWeight: 540, background: "linear-gradient(135deg, #635BFF, #8B5CF6)" }}
            type="button"
          >
            {isPending ? "Adding..." : "Add Employee"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Bulk Upload Modal ─── */

function BulkUploadModal({
  businessId,
  businessName,
  dark,
  locations,
  onClose,
  onImported,
}: {
  businessId: string;
  businessName: string;
  dark: boolean;
  locations: BusinessLocation[];
  onClose(): void;
  onImported(result: EmployeeBulkImportResponse): Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [importResult, setImportResult] = useState<EmployeeBulkImportResponse | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isPending, startTransition] = useTransition();
  const [isDownloadingTemplate, setIsDownloadingTemplate] = useState(false);
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.06]" : "border-[#E5E7EB]";
  const singleLocationName = locations.length === 1 ? locations[0]?.name ?? null : null;

  const handleTemplateDownload = async () => {
    try {
      setFeedback(null);
      setIsDownloadingTemplate(true);
      await downloadEmployeeImportTemplate(businessId);
    } catch (error) {
      setFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : "Could not download the template.",
      });
    } finally {
      setIsDownloadingTemplate(false);
    }
  };

  const handleImport = () => {
    if (!selectedFile || isPending) return;
    startTransition(async () => {
      try {
        setFeedback(null);
        const result = await importEmployees(businessId, selectedFile);
        setImportResult(result);
        await onImported(result);
        if (!result.errors.length) onClose();
      } catch (error) {
        setFeedback({
          tone: "error",
          message: error instanceof Error ? error.message : "Could not import these employees.",
        });
      }
    });
  };

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      exit={{ opacity: 0 }}
      initial={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className={`mx-4 w-full max-w-2xl overflow-hidden rounded-[28px] border ${
          dark ? "border-white/[0.06] bg-[#0A2540]" : "border-[#E5E7EB] bg-white"
        }`}
        exit={{ opacity: 0, scale: 0.96, y: 16 }}
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        onClick={(e) => e.stopPropagation()}
        transition={{ duration: 0.22 }}
        style={dark ? { boxShadow: "0 32px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(99,91,255,0.08)" } : undefined}
      >
        {/* Header */}
        <div className={`border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#635BFF]/10">
                <Upload className="text-[#635BFF]" size={18} />
              </div>
              <div>
                <h2 className={`text-[18px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  Bulk Upload
                </h2>
                <p className={`mt-0.5 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Import employee profiles for {businessName}.
                </p>
              </div>
            </div>
            <button
              className={`rounded-full p-2 transition-colors ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`}
              onClick={onClose}
              type="button"
            >
              <X className="text-[#8898AA]" size={16} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="space-y-5 px-6 py-5">
          {feedback ? (
            <div
              className="rounded-2xl px-4 py-3 text-[13px]"
              role="status"
              style={{ background: "rgba(229,72,77,0.08)", color: "#C13535", fontWeight: 500 }}
            >
              {feedback.message}
            </div>
          ) : null}

          <div
            className={`rounded-2xl border px-4 py-4 ${
              dark ? "border-white/[0.06] bg-white/[0.03] text-[#C1CED8]" : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
            }`}
          >
            <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 520 }}>
              Supported columns
            </p>
            <p className="mt-1 text-[12px]" style={{ fontWeight: 420 }}>
              Required: full_name, email, phone_e164. Optional: preferred_name, employee_number,
              external_ref, employment_type, hire_date, notes
            </p>
            {singleLocationName ? (
              <p className="mt-3 text-[12px]" style={{ fontWeight: 420 }}>
                Imported employees will default to{" "}
                <span style={{ fontWeight: 520 }}>{singleLocationName}</span>.
              </p>
            ) : (
              <p className="mt-3 text-[12px]" style={{ fontWeight: 420 }}>
                Imported employees will remain unassigned until you add locations.
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-4 py-2.5 text-[13px] transition-colors ${
                dark ? "border-white/[0.06] text-[#C1CED8] hover:bg-white/[0.06]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
              }`}
              disabled={isDownloadingTemplate}
              onClick={handleTemplateDownload}
              type="button"
            >
              <Download size={14} />
              {isDownloadingTemplate ? "Downloading..." : "Download Template"}
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-4 py-2.5 text-[13px] transition-colors ${
                dark ? "border-white/[0.06] text-[#C1CED8] hover:bg-white/[0.06]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
              }`}
              onClick={() => inputRef.current?.click()}
              type="button"
            >
              <Upload size={14} />
              Choose File
            </button>
            {selectedFile ? (
              <span className="text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                {selectedFile.name}
              </span>
            ) : null}
          </div>

          <input
            accept=".csv,.xlsx"
            className="hidden"
            onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            ref={inputRef}
            type="file"
          />

          <button
            className={`w-full rounded-[24px] border border-dashed px-6 py-8 text-center transition-all duration-300 ${
              isDragging
                ? "border-[#635BFF] bg-[#635BFF]/[0.06]"
                : dark
                  ? "border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.04] hover:border-white/[0.14]"
                  : "border-[#D7DBE3] bg-[#FAFBFC] hover:bg-[#F7F8FA]"
            }`}
            onClick={() => inputRef.current?.click()}
            onDragEnter={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              const file = e.dataTransfer.files?.[0];
              if (file) setSelectedFile(file);
            }}
            type="button"
          >
            <Upload className="mx-auto mb-3 text-[#635BFF]" size={24} />
            <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
              Drag a CSV or XLSX file here
            </p>
            <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
              Only employee profile information is imported from the file.
            </p>
          </button>

          {importResult?.errors.length ? (
            <div
              className={`rounded-2xl border px-4 py-4 ${
                dark ? "border-white/[0.06] bg-white/[0.03]" : "border-[#E5E7EB] bg-[#FAFBFC]"
              }`}
            >
              <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                Import completed with row issues
              </p>
              <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                {importResult.created_count} created, {importResult.skipped_count} skipped.
              </p>
              <div className="mt-3 space-y-2">
                {importResult.errors.map((err, i) => (
                  <div
                    key={`${err.row_number ?? "general"}-${i}`}
                    className={`rounded-xl px-3 py-2 text-[12px] ${dark ? "bg-white/[0.04] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"}`}
                    style={{ fontWeight: 420 }}
                  >
                    Row {err.row_number ?? "?"}: {err.message}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className={`flex items-center justify-end gap-3 border-t px-6 py-4 ${borderClass}`}>
          <button
            className={`rounded-full border px-4 py-2.5 text-[13px] transition-colors ${
              dark ? "border-white/[0.06] text-[#C1CED8] hover:bg-white/[0.06]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
            }`}
            onClick={onClose}
            type="button"
          >
            Close
          </button>
          <button
            className="rounded-full px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-40 transition-all"
            disabled={!selectedFile || isPending}
            onClick={handleImport}
            style={{ fontWeight: 540, background: "linear-gradient(135deg, #635BFF, #8B5CF6)" }}
            type="button"
          >
            {isPending ? "Uploading..." : "Import Employees"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Employee Editor Drawer ─── */

function EmployeeEditorDrawer({
  businessId,
  dark,
  employee,
  locations,
  onClose,
  onSaved,
  roles,
}: {
  businessId: string;
  dark: boolean;
  employee: EmployeeSummary;
  locations: BusinessLocation[];
  onClose(): void;
  onSaved(nextEmployee: EmployeeProfile): Promise<void>;
  roles: BusinessRole[];
}) {
  const controls = useEmployeeForm(emptyEmployeeForm());
  const [profile, setProfile] = useState<EmployeeProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.06]" : "border-[#E5E7EB]";
  const panelSurface = dark ? "bg-white/[0.03]" : "bg-[#F7F8FA]";

  useEffect(() => {
    let cancelled = false;
    async function loadProfile() {
      try {
        setLoading(true);
        setFeedback(null);
        const p = await getEmployeeProfile(businessId, employee.id);
        if (cancelled) return;
        setProfile(p);
        controls.setState(buildEmployeeForm(p));
      } catch (error) {
        if (!cancelled)
          setFeedback({
            tone: "error",
            message: error instanceof Error ? error.message : "Could not load this employee.",
          });
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadProfile();
    return () => { cancelled = true; };
  }, [businessId, employee.id]);

  const canSave = Boolean(controls.state.fullName.trim());

  const handleSave = () => {
    if (!canSave || isPending) return;
    startTransition(async () => {
      try {
        setFeedback(null);
        const next = await updateEmployee(businessId, employee.id, {
          full_name: controls.state.fullName.trim(),
          preferred_name: normalizeOptional(controls.state.preferredName),
          email: normalizeOptional(controls.state.email),
          phone_e164: normalizeOptional(controls.state.phone),
          employment_type: normalizeOptional(controls.state.employmentType),
          status: controls.state.status,
          notes: normalizeOptional(controls.state.notes),
          roles: controls.state.selectedRoleIds.map((id) => ({
            role_id: id,
            is_primary: id === controls.state.primaryRoleId,
          })),
          locations: controls.state.selectedLocationIds.map((id) => ({
            location_id: id,
            is_primary: id === controls.state.primaryLocationId,
          })),
        });
        setProfile(next);
        controls.setState(buildEmployeeForm(next));
        await onSaved(next);
        setFeedback({ tone: "success", message: "Employee updated." });
      } catch (error) {
        setFeedback({
          tone: "error",
          message: error instanceof Error ? error.message : "Could not update this employee.",
        });
      }
    });
  };

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-sm"
      exit={{ opacity: 0 }}
      initial={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        animate={{ x: 0 }}
        className={`flex h-full w-full max-w-[520px] flex-col border-l ${
          dark ? "border-white/[0.06] bg-[#0A2540]" : "border-[#E5E7EB] bg-white"
        }`}
        exit={{ x: 520 }}
        initial={{ x: 520 }}
        onClick={(e) => e.stopPropagation()}
        transition={{ duration: 0.28, ease: [0.25, 0.46, 0.45, 0.94] }}
        style={dark ? { boxShadow: "-24px 0 80px rgba(0,0,0,0.4)" } : undefined}
      >
        {/* Header */}
        <div className={`border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className="flex h-12 w-12 items-center justify-center rounded-2xl text-[14px] text-white"
                style={{
                  fontWeight: 600,
                  background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
                }}
              >
                {employeeInitials(displayName(employee))}
              </div>
              <div>
                <h2 className={`text-[18px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  {displayName(employee)}
                </h2>
                <p className={`mt-0.5 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Edit profile, roles, and location assignments.
                </p>
              </div>
            </div>
            <button
              className={`rounded-full p-2 transition-colors ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`}
              onClick={onClose}
              type="button"
            >
              <X className="text-[#8898AA]" size={16} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {feedback ? (
            <div
              className="mb-4 rounded-2xl px-4 py-3 text-[13px]"
              role="status"
              style={{
                background: feedback.tone === "success" ? "rgba(0,212,170,0.08)" : "rgba(229,72,77,0.08)",
                color: feedback.tone === "success" ? "#00A88A" : "#C13535",
                fontWeight: 500,
              }}
            >
              {feedback.message}
            </div>
          ) : null}

          {loading ? (
            <div className={`py-12 text-[13px] ${textSecondary}`}>Loading employee profile...</div>
          ) : profile ? (
            <>
              <div className={`mb-5 rounded-2xl border px-4 py-4 ${dark ? "border-white/[0.06]" : "border-[#E5E7EB]"} ${panelSurface}`}>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
                      Primary Role
                    </p>
                    <p className={`mt-1 text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                      {profile.primary_role_name ?? "Not set"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]" style={{ fontWeight: 500 }}>
                      Primary Location
                    </p>
                    <p className={`mt-1 text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                      {profile.primary_location_name ?? "Not set"}
                    </p>
                  </div>
                </div>
              </div>
              <EmployeeAssignmentFields
                controls={controls}
                dark={dark}
                includeStatus
                locations={locations}
                roles={roles}
              />
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className={`flex items-center justify-end gap-3 border-t px-6 py-4 ${borderClass}`}>
          <button
            className={`rounded-full border px-4 py-2.5 text-[13px] transition-colors ${
              dark ? "border-white/[0.06] text-[#C1CED8] hover:bg-white/[0.06]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
            }`}
            onClick={onClose}
            type="button"
          >
            Close
          </button>
          <button
            className="rounded-full px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-40 transition-all"
            disabled={!canSave || isPending || loading}
            onClick={handleSave}
            style={{ fontWeight: 540, background: "linear-gradient(135deg, #635BFF, #8B5CF6)" }}
            type="button"
          >
            {isPending ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ─── Team Roster Section ─── */

function TeamRosterSection({
  dark,
  description,
  employees,
  emptyDescription,
  emptyTitle,
  onSelectEmployee,
  onToggleSort,
  sortField,
  title,
  accentColor = "#635BFF",
}: {
  dark: boolean;
  description: string;
  employees: EmployeeSummary[];
  emptyDescription: string;
  emptyTitle: string;
  onSelectEmployee(employee: EmployeeSummary): void;
  onToggleSort(field: "name" | "role" | "location"): void;
  sortField: "name" | "role" | "location";
  title: string;
  accentColor?: string;
}) {
  const [hovered, setHovered] = useState(false);
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const textMuted = "text-[#8898AA]";

  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-2xl border transition-all duration-500"
      initial={{ opacity: 0, y: 16 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        borderColor: dark ? "rgba(255,255,255,0.06)" : "#E5E7EB",
        background: dark ? "rgba(255,255,255,0.02)" : "white",
        boxShadow: dark
          ? hovered
            ? `0 20px 60px -12px ${accentColor}18, 0 1px 3px rgba(0,0,0,0.2)`
            : "0 1px 3px rgba(0,0,0,0.15)"
          : hovered
            ? "0 8px 32px rgba(0,0,0,0.08)"
            : "0 1px 3px rgba(0,0,0,0.04)",
      }}
      transition={{ duration: 0.35 }}
    >
      {/* Top accent line */}
      <div
        className="h-[2px] w-full transition-all duration-500"
        style={{
          background: hovered
            ? `linear-gradient(90deg, transparent, ${accentColor}, transparent)`
            : `linear-gradient(90deg, transparent, ${accentColor}30, transparent)`,
        }}
      />

      {/* Section header */}
      <div
        className="border-b px-5 py-4"
        style={{ borderColor: dark ? "rgba(255,255,255,0.05)" : "#F0F0F5", background: dark ? "rgba(255,255,255,0.01)" : "#FAFBFC" }}
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className={`text-[15px] ${textPrimary}`} style={{ fontWeight: 600 }}>
              {title}
            </h2>
            <p className={`mt-0.5 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
              {description}
            </p>
          </div>
          <span
            className="rounded-full px-2.5 py-0.5 text-[12px]"
            style={{
              fontWeight: 520,
              color: accentColor,
              background: `${accentColor}12`,
            }}
          >
            {employees.length}
          </span>
        </div>
      </div>

      {/* Column headers — desktop */}
      <div
        className="hidden grid-cols-[2fr_1fr_1fr_1fr_44px] gap-4 border-b px-5 py-3 md:grid"
        style={{ borderColor: dark ? "rgba(255,255,255,0.05)" : "#F0F0F5", background: dark ? "rgba(255,255,255,0.01)" : "#FAFBFC" }}
      >
        {[
          { label: "Employee", field: "name" as const },
          { label: "Roles", field: "role" as const },
          { label: "Location", field: "location" as const },
        ].map((col) => (
          <button
            key={col.field}
            className={`flex items-center gap-1.5 text-[11px] uppercase tracking-[0.04em] ${textMuted} transition-colors hover:text-[#C1CED8]`}
            onClick={() => onToggleSort(col.field)}
            type="button"
            style={{ fontWeight: 500 }}
          >
            {col.label}
            <ArrowUpDown size={11} style={{ opacity: sortField === col.field ? 1 : 0.45 }} />
          </button>
        ))}
        <span className={`text-[11px] uppercase tracking-[0.04em] ${textMuted}`} style={{ fontWeight: 500 }}>
          Status
        </span>
        <span />
      </div>

      {employees.length ? (
        <>
          {/* Desktop rows */}
          <div className="hidden md:block">
            {employees.map((employee, index) => (
              <motion.div
                key={employee.id}
                animate={{ opacity: 1 }}
                className="grid cursor-pointer grid-cols-[2fr_1fr_1fr_1fr_44px] gap-4 border-b px-5 py-3.5 last:border-0 transition-colors duration-150"
                initial={{ opacity: 0 }}
                onClick={() => onSelectEmployee(employee)}
                transition={{ delay: index * 0.015, duration: 0.18 }}
                style={{
                  borderColor: dark ? "rgba(255,255,255,0.05)" : "#F7F8FA",
                }}
                onMouseEnter={(e) => {
                  if (dark) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.025)";
                  else (e.currentTarget as HTMLElement).style.background = "#FAFBFC";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background = "transparent";
                }}
              >
                {/* Name + contact */}
                <div className="min-w-0 flex items-center gap-3">
                  <div
                    className="flex h-9 w-9 items-center justify-center rounded-full text-[11px] text-white shrink-0"
                    style={{
                      fontWeight: 600,
                      background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
                    }}
                  >
                    {employeeInitials(displayName(employee))}
                  </div>
                  <div className="min-w-0">
                    <p className={`truncate text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                      {displayName(employee)}
                    </p>
                    <p className={`truncate text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                      {employee.email ?? employee.phone_e164 ?? "No contact info"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center">
                  <EmployeeRoleCell dark={dark} employee={employee} />
                </div>

                <div className="flex items-center">
                  <EmployeeLocationCell dark={dark} employee={employee} textSecondary={textSecondary} />
                </div>

                <div className="flex items-center">
                  <StatusWithInfo dark={dark} status={employee.status} />
                </div>

                <div className="flex items-center justify-center">
                  <button
                    className={`rounded-full p-2 transition-colors ${dark ? "hover:bg-white/[0.08]" : "hover:bg-[#F0F0F5]"}`}
                    onClick={(e) => { e.stopPropagation(); onSelectEmployee(employee); }}
                    type="button"
                  >
                    <Eye className="text-[#8898AA]" size={14} />
                  </button>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Mobile rows */}
          <div className={`divide-y md:hidden ${dark ? "divide-white/[0.05]" : "divide-[#F7F8FA]"}`}>
            {employees.map((employee) => {
              const status = statusConfig[employee.status] ?? statusConfig.inactive;
              const extraRoles = extraRoleNames(employee);
              const extraLocations = extraLocationNames(employee);
              return (
                <button
                  key={employee.id}
                  className={`w-full px-4 py-3.5 text-left transition-colors ${dark ? "hover:bg-white/[0.03]" : "hover:bg-[#FAFBFC]"}`}
                  onClick={() => onSelectEmployee(employee)}
                  type="button"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className="flex h-10 w-10 items-center justify-center rounded-full text-[12px] text-white shrink-0"
                      style={{ fontWeight: 600, background: "linear-gradient(135deg, #635BFF, #8B5CF6)" }}
                    >
                      {employeeInitials(displayName(employee))}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className={`truncate text-[14px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                          {displayName(employee)}
                        </p>
                        <span
                          className="rounded-full px-2 py-0.5 text-[10px] shrink-0"
                          style={{ fontWeight: 520, color: status.color, background: status.bg }}
                        >
                          {status.label}
                        </span>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-[#8898AA]">
                        <span style={{ fontWeight: 440 }}>{employee.primary_role_name ?? "Unassigned"}</span>
                        {extraRoles.length ? (
                          <span style={{ fontWeight: 420 }}>+{extraRoles.length} more</span>
                        ) : null}
                        <span>·</span>
                        <span style={{ fontWeight: 440 }}>{employee.primary_location_name ?? "Unassigned"}</span>
                        {extraLocations.length ? (
                          <span style={{ fontWeight: 420 }}>+{extraLocations.length} more</span>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <div className="px-8 py-14 text-center">
          <div
            className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl"
            style={{ background: dark ? "rgba(255,255,255,0.04)" : "#F7F8FA" }}
          >
            <Shield className="text-[#8898AA]" size={22} />
          </div>
          <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 540 }}>
            {emptyTitle}
          </p>
          <p className={`mt-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
            {emptyDescription}
          </p>
        </div>
      )}
    </motion.div>
  );
}

/* ─── Main Team Component ─── */

export default function Team({ embeddedInShell = false }: { embeddedInShell?: boolean }) {
  const pathname = usePathname();
  const workspace = useAppWorkspace();
  const workspaceReady = useAppWorkspaceReady();
  const isDark = useResolvedAppAppearance() === "dark";
  const preferredBusiness = useMemo(
    () => resolvePreferredWorkspaceBusiness(workspace, pathname),
    [pathname, workspace],
  );
  const businessId = preferredBusiness?.business_id ?? null;
  const businessName =
    preferredBusiness?.business_display_name ?? preferredBusiness?.business_name ?? "Backfill";

  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);
  const [locations, setLocations] = useState<BusinessLocation[]>([]);
  const [roles, setRoles] = useState<BusinessRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [locationFilter, setLocationFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortField, setSortField] = useState<"name" | "role" | "location">("name");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [showAddModal, setShowAddModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeSummary | null>(null);

  const refreshEmployees = useCallback(async () => {
    if (!businessId) { setEmployees([]); return; }
    const next = await listEmployees(businessId);
    setEmployees(next);
  }, [businessId]);

  useEffect(() => {
    let cancelled = false;
    async function loadTeamData() {
      if (!workspaceReady) { setLoading(true); return; }
      if (!businessId) {
        setEmployees([]); setLocations([]); setRoles([]); setLoading(false); return;
      }
      try {
        setLoading(true);
        setFeedback(null);
        const [nextEmployees, nextLocations, nextRoles] = await Promise.all([
          listEmployees(businessId),
          listBusinessLocations(businessId),
          listBusinessRoles(businessId),
        ]);
        if (cancelled) return;
        setEmployees(nextEmployees);
        setLocations(nextLocations.filter((l) => l.is_active));
        setRoles(nextRoles);
      } catch (error) {
        if (!cancelled)
          setFeedback({
            tone: "error",
            message: error instanceof Error ? error.message : "Could not load the team roster.",
          });
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadTeamData();
    return () => { cancelled = true; };
  }, [businessId, workspaceReady]);

  const handleToggleSort = (field: "name" | "role" | "location") => {
    if (sortField === field) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDirection("asc");
  };

  const handleEmployeeCreated = async (nextEmployee: EmployeeSummary) => {
    setEmployees((cur) => [nextEmployee, ...cur.filter((e) => e.id !== nextEmployee.id)]);
    setFeedback({ tone: "success", message: `${displayName(nextEmployee)} added to the roster.` });
  };

  const handleBulkImported = async (result: EmployeeBulkImportResponse) => {
    await refreshEmployees();
    setFeedback({
      tone: "success",
      message: `Imported ${result.created_count} employee${result.created_count === 1 ? "" : "s"}${result.skipped_count ? `, skipped ${result.skipped_count}` : ""}.`,
    });
  };

  const handleEmployeeSaved = async (nextEmployee: EmployeeProfile) => {
    setEmployees((cur) => {
      const replacement: EmployeeSummary = nextEmployee;
      return cur.map((e) => (e.id === replacement.id ? replacement : e));
    });
    setSelectedEmployee(nextEmployee);
  };

  const filteredEmployees = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const filtered = employees.filter((e) => {
      const matchesSearch =
        !query ||
        displayName(e).toLowerCase().includes(query) ||
        (e.email ?? "").toLowerCase().includes(query) ||
        e.role_names.some((r) => r.toLowerCase().includes(query)) ||
        e.location_names.some((l) => l.toLowerCase().includes(query));
      const matchesLocation = locationFilter === "all" || e.location_ids.includes(locationFilter);
      const matchesStatus = statusFilter === "all" || e.status === statusFilter;
      return matchesSearch && matchesLocation && matchesStatus;
    });
    return sortEmployees(filtered, sortField, sortDirection);
  }, [employees, locationFilter, searchQuery, sortDirection, sortField, statusFilter]);

  const needsAssignmentEmployees = useMemo(
    () => filteredEmployees.filter(employeeNeedsAssignment),
    [filteredEmployees],
  );
  const scheduleReadyEmployees = useMemo(
    () => filteredEmployees.filter((e) => !employeeNeedsAssignment(e)),
    [filteredEmployees],
  );

  /* ── Derived style tokens ── */
  const textPrimary = isDark ? "text-white" : "text-[#0A2540]";
  const textSecondary = isDark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const textMuted = "text-[#8898AA]";
  const inputClass = isDark
    ? "border-white/[0.06] bg-white/[0.04] text-white placeholder-[#8898AA]/50 focus:border-[#635BFF]/40"
    : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder-[#8898AA]/60 focus:border-[#635BFF]/40";

  const content = (
    <>
      {/* ── Page header ── */}
      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
        initial={{ opacity: 0, y: 12 }}
        transition={{ duration: 0.45 }}
      >
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <h1
              className={`text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] ${textPrimary}`}
              style={{ fontWeight: 640 }}
            >
              Team
            </h1>
            <p className={`mt-1 text-[13px] sm:text-[15px] ${textSecondary}`} style={{ fontWeight: 420 }}>
              Manage employees, assignments, and roster readiness for {businessName}.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              className={`hidden items-center gap-2 rounded-full border px-4 py-2.5 text-[13px] transition-colors sm:flex ${
                isDark
                  ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.05]"
                  : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
              }`}
              disabled={!businessId}
              onClick={() => setShowBulkModal(true)}
              style={{ fontWeight: 480 }}
              type="button"
            >
              <Upload size={14} />
              Bulk Upload
            </button>
            <button
              className="flex items-center gap-2 backfill-ui-radius px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-40 transition-all hover:shadow-[0_0_24px_rgba(99,91,255,0.3)]"
              disabled={!businessId}
              onClick={() => setShowAddModal(true)}
              style={{
                fontWeight: 540,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
              type="button"
            >
              <Plus size={14} />
              Add Employee
            </button>
          </div>
        </div>

        {/* ── Feedback banner ── */}
        {feedback ? (
          <div
            className="mb-4 rounded-2xl px-4 py-3 text-[13px]"
            role="status"
            style={{
              background: feedback.tone === "success" ? "rgba(0,212,170,0.08)" : "rgba(229,72,77,0.08)",
              color: feedback.tone === "success" ? "#00A88A" : "#C13535",
              fontWeight: 500,
            }}
          >
            {feedback.message}
          </div>
        ) : null}

        {/* ── Search + filters ── */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative max-w-sm flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8898AA]" size={14} />
            <input
              className={`w-full rounded-full border py-2.5 pl-10 pr-4 text-[12px] transition-all focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.10)] ${inputClass}`}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, role, location, or email"
              type="text"
              value={searchQuery}
              style={{ fontWeight: 420 }}
            />
          </div>
          <div className="flex items-center gap-2">
            <BrandedSelect
              dark={isDark}
              onChange={(e: { target: { value: string } }) => setLocationFilter(e.target.value)}
              value={locationFilter}
            >
              <option value="all">All Locations</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </BrandedSelect>
            <BrandedSelect
              dark={isDark}
              onChange={(e: { target: { value: string } }) => setStatusFilter(e.target.value)}
              value={statusFilter}
            >
              {statusOptions.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </BrandedSelect>
          </div>
          <span className={`ml-auto text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
            {filteredEmployees.length} employee{filteredEmployees.length === 1 ? "" : "s"}
          </span>
        </div>
      </motion.div>

      {/* ── Roster ── */}
      {loading ? (
        <div
          className="overflow-hidden rounded-2xl border px-8 py-16 text-center"
          style={{
            borderColor: isDark ? "rgba(255,255,255,0.06)" : "#E5E7EB",
            background: isDark ? "rgba(255,255,255,0.02)" : "white",
          }}
        >
          <p className={`text-[14px] ${textSecondary}`} style={{ fontWeight: 420 }}>
            Loading team roster…
          </p>
        </div>
      ) : !workspaceReady ? (
        <div />
      ) : !businessId ? (
        <div
          className="overflow-hidden rounded-2xl border px-8 py-16 text-center"
          style={{
            borderColor: isDark ? "rgba(255,255,255,0.06)" : "#E5E7EB",
            background: isDark ? "rgba(255,255,255,0.02)" : "white",
          }}
        >
          <div
            className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl"
            style={{ background: isDark ? "rgba(255,255,255,0.04)" : "#F7F8FA" }}
          >
            <AlertCircle className="text-[#8898AA]" size={22} />
          </div>
          <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 540 }}>
            No workspace business yet
          </p>
          <p className={`mt-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
            Create a business before managing employees.
          </p>
        </div>
      ) : (
        <div className="space-y-5">
          {needsAssignmentEmployees.length > 0 && (
            <TeamRosterSection
              accentColor="#F59E0B"
              dark={isDark}
              description="Employees missing at least one role or one location. Finish their assignment here before they are schedule-ready."
              employees={needsAssignmentEmployees}
              emptyDescription=""
              emptyTitle=""
              onSelectEmployee={setSelectedEmployee}
              onToggleSort={handleToggleSort}
              sortField={sortField}
              title="Needs Assignment"
            />
          )}
          {scheduleReadyEmployees.length > 0 && (
            <TeamRosterSection
              accentColor="#635BFF"
              dark={isDark}
              description="Employees with at least one role and one location, ready to appear in normal scheduling flows."
              employees={scheduleReadyEmployees}
              emptyDescription=""
              emptyTitle=""
              onSelectEmployee={setSelectedEmployee}
              onToggleSort={handleToggleSort}
              sortField={sortField}
              title="Schedule Ready"
            />
          )}
        </div>
      )}

      {/* ── Modals / Drawer ── */}
      <AnimatePresence>
        {showAddModal && businessId ? (
          <AddEmployeeModal
            businessId={businessId}
            businessName={businessName}
            dark={isDark}
            locations={locations}
            onClose={() => setShowAddModal(false)}
            onCreated={handleEmployeeCreated}
            roles={roles}
          />
        ) : null}

        {showBulkModal && businessId ? (
          <BulkUploadModal
            businessId={businessId}
            businessName={businessName}
            dark={isDark}
            locations={locations}
            onClose={() => setShowBulkModal(false)}
            onImported={handleBulkImported}
          />
        ) : null}

        {selectedEmployee && businessId ? (
          <EmployeeEditorDrawer
            businessId={businessId}
            dark={isDark}
            employee={selectedEmployee}
            locations={locations}
            onClose={() => setSelectedEmployee(null)}
            onSaved={handleEmployeeSaved}
            roles={roles}
          />
        ) : null}
      </AnimatePresence>
    </>
  );

  if (embeddedInShell) return content;

  return <DashboardShell activeNav="Team">{content}</DashboardShell>;
}
