"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  AlertCircle,
  ArrowUpDown,
  Check,
  Download,
  Eye,
  MapPin,
  Plus,
  Search,
  Shield,
  Upload,
  UserPlus,
  X,
} from "lucide-react";

import { useResolvedAppAppearance } from "@/components/app-session-gate";
import {
  listBusinessLocations,
  listBusinessRoles,
  type BusinessLocation,
  type BusinessRole,
} from "@/lib/api/businesses";
import {
  getEmployeeProfile,
  listEmployees,
  updateEmployee,
  type EmployeeProfile,
  type EmployeeSummary,
} from "@/lib/api/workforce";
import {
  enrollEmployeeAtLocation,
  getWorkspace,
  type Workspace,
} from "@/lib/api/workspace";

import { BrandedSelect } from "./BrandedSelect";
import DashboardShell from "./DashboardShell";

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

const rosterTemplateHref = "/backfill-employee-roster-template.xlsx";
const statusOptions = [
  { value: "all", label: "All Status" },
  { value: "active", label: "Active" },
  { value: "on_leave", label: "On Leave" },
  { value: "inactive", label: "Inactive" },
];

const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: "Active", color: "#00B893", bg: "rgba(0, 184, 147, 0.12)" },
  on_leave: { label: "On Leave", color: "#F59E0B", bg: "rgba(245, 158, 11, 0.12)" },
  inactive: { label: "Inactive", color: "#8898AA", bg: "rgba(136, 152, 170, 0.14)" },
};

function emptyEmployeeForm(): EmployeeFormState {
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
    selectedLocationIds: [],
    primaryLocationId: "",
  };
}

function buildEmployeeForm(profile: EmployeeProfile): EmployeeFormState {
  const selectedRoleIds = profile.roles.map((role) => role.role_id);
  const selectedLocationIds = profile.locations.map((location) => location.location_id);
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
      profile.roles.find((role) => role.is_primary)?.role_id ?? selectedRoleIds[0] ?? "",
    selectedLocationIds,
    primaryLocationId:
      profile.locations.find((location) => location.is_primary)?.location_id ??
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
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("") || "BF";
}

function formatLocationMeta(location: BusinessLocation): string {
  return [location.address_line_1, location.locality, location.region]
    .filter((value): value is string => Boolean(value))
    .join(", ");
}

function sortEmployees(
  employees: EmployeeSummary[],
  field: "name" | "role" | "location",
  direction: "asc" | "desc",
): EmployeeSummary[] {
  const factor = direction === "asc" ? 1 : -1;
  return [...employees].sort((left, right) => {
    if (field === "role") {
      return (left.primary_role_name ?? "").localeCompare(right.primary_role_name ?? "") * factor;
    }
    if (field === "location") {
      return (left.primary_location_name ?? "").localeCompare(right.primary_location_name ?? "") * factor;
    }
    return displayName(left).localeCompare(displayName(right)) * factor;
  });
}

function useEmployeeForm(initialState: EmployeeFormState): EmployeeFormControls {
  const [state, setState] = useState<EmployeeFormState>(initialState);

  const setField = (field: keyof EmployeeFormState, value: string) => {
    setState((current) => ({ ...current, [field]: value }));
  };

  const toggleRole = (roleId: string) => {
    setState((current) => {
      const selectedRoleIds = current.selectedRoleIds.includes(roleId)
        ? current.selectedRoleIds.filter((item) => item !== roleId)
        : [...current.selectedRoleIds, roleId];
      const primaryRoleId = selectedRoleIds.includes(current.primaryRoleId)
        ? current.primaryRoleId
        : selectedRoleIds[0] ?? "";
      return { ...current, selectedRoleIds, primaryRoleId };
    });
  };

  const setPrimaryRole = (roleId: string) => {
    setState((current) => ({ ...current, primaryRoleId: roleId }));
  };

  const toggleLocation = (locationId: string) => {
    setState((current) => {
      const selectedLocationIds = current.selectedLocationIds.includes(locationId)
        ? current.selectedLocationIds.filter((item) => item !== locationId)
        : [...current.selectedLocationIds, locationId];
      const primaryLocationId = selectedLocationIds.includes(current.primaryLocationId)
        ? current.primaryLocationId
        : selectedLocationIds[0] ?? "";
      return { ...current, selectedLocationIds, primaryLocationId };
    });
  };

  const setPrimaryLocation = (locationId: string) => {
    setState((current) => ({ ...current, primaryLocationId: locationId }));
  };

  return {
    state,
    setState,
    setField,
    toggleRole,
    setPrimaryRole,
    toggleLocation,
    setPrimaryLocation,
  };
}

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
  const className = `w-full rounded-2xl border px-3.5 py-2.5 text-[13px] placeholder-[#8898AA]/60 transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${
    dark
      ? "border-white/[0.08] bg-white/[0.04] text-white"
      : "border-[#E5E7EB] bg-white text-[#0A2540]"
  }`;

  if (multiline) {
    return (
      <textarea
        className={`${className} min-h-[96px] resize-none`}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    );
  }

  return (
    <input
      className={className}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      type={type}
      value={value}
    />
  );
}

function SectionLabel({
  label,
  muted,
}: {
  label: string;
  muted: string;
}) {
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
                  ? "border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.05]"
                  : "border-[#E5E7EB] bg-[#F7F8FA] hover:bg-[#F0F0F5]"
            }`}
            onClick={() => onToggle(item.id)}
            type="button"
          >
            <div className={`mt-0.5 flex h-5 w-5 items-center justify-center rounded-md border ${selected ? "border-[#635BFF] bg-[#635BFF] text-white" : dark ? "border-white/[0.14]" : "border-[#D1D5DB]"}`}>
              {selected ? <Check size={12} /> : null}
            </div>
            <div className="min-w-0 flex-1">
              <p className={`truncate text-[13px] ${dark ? "text-white" : "text-[#0A2540]"}`} style={{ fontWeight: 520 }}>
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
  const roleItems = roles.map((role) => ({
    id: role.id,
    label: role.name,
    meta: role.code,
  }));
  const locationItems = locations.map((location) => ({
    id: location.id,
    label: location.name,
    meta: formatLocationMeta(location) || location.timezone,
  }));

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <SectionLabel label="Full Name" muted={muted} />
          <TextInput
            dark={dark}
            onChange={(value) => setField("fullName", value)}
            placeholder="Taylor Smith"
            value={state.fullName}
          />
        </div>
        <div>
          <SectionLabel label="Preferred Name" muted={muted} />
          <TextInput
            dark={dark}
            onChange={(value) => setField("preferredName", value)}
            placeholder="Taylor"
            value={state.preferredName}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <SectionLabel label="Email" muted={muted} />
          <TextInput
            dark={dark}
            onChange={(value) => setField("email", value)}
            placeholder="taylor@company.com"
            type="email"
            value={state.email}
          />
        </div>
        <div>
          <SectionLabel label="Phone" muted={muted} />
          <TextInput
            dark={dark}
            onChange={(value) => setField("phone", value)}
            placeholder="+15555550123"
            type="tel"
            value={state.phone}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <SectionLabel label="Employment Type" muted={muted} />
          <TextInput
            dark={dark}
            onChange={(value) => setField("employmentType", value)}
            placeholder="full_time, part_time, seasonal"
            value={state.employmentType}
          />
        </div>
        {includeStatus ? (
          <div>
            <SectionLabel label="Status" muted={muted} />
            <BrandedSelect
              dark={dark}
              onChange={(event: { target: { value: string } }) => setField("status", event.target.value)}
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
          <SelectionGrid dark={dark} items={roleItems} onToggle={toggleRole} selectedIds={state.selectedRoleIds} />
        ) : (
          <div className={`rounded-2xl border px-4 py-3 text-[12px] ${dark ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8]" : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"}`}>
            Create the business role catalog first. Employee roles write to `employee_roles`.
          </div>
        )}
      </div>

      <div>
        <SectionLabel label="Primary Role" muted={muted} />
        <BrandedSelect
          dark={dark}
          disabled={!state.selectedRoleIds.length}
          onChange={(event: { target: { value: string } }) => setPrimaryRole(event.target.value)}
          value={state.primaryRoleId}
        >
          <option value="">Select primary role</option>
          {roles
            .filter((role) => state.selectedRoleIds.includes(role.id))
            .map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
              </option>
            ))}
        </BrandedSelect>
      </div>

      <div>
        <SectionLabel label="Locations" muted={muted} />
        {locations.length ? (
          <SelectionGrid dark={dark} items={locationItems} onToggle={toggleLocation} selectedIds={state.selectedLocationIds} />
        ) : (
          <div className={`rounded-2xl border px-4 py-3 text-[12px] ${dark ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8]" : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"}`}>
            Add at least one business location first. Employee locations write to `employee_locations`.
          </div>
        )}
      </div>

      <div>
        <SectionLabel label="Primary Location" muted={muted} />
        <BrandedSelect
          dark={dark}
          disabled={!state.selectedLocationIds.length}
          onChange={(event: { target: { value: string } }) => setPrimaryLocation(event.target.value)}
          value={state.primaryLocationId}
        >
          <option value="">Select primary location</option>
          {locations
            .filter((location) => state.selectedLocationIds.includes(location.id))
            .map((location) => (
              <option key={location.id} value={location.id}>
                {location.name}
              </option>
            ))}
        </BrandedSelect>
      </div>

      <div>
        <SectionLabel label="Notes" muted={muted} />
        <TextInput
          dark={dark}
          multiline
          onChange={(value) => setField("notes", value)}
          placeholder="Operational notes for managers"
          value={state.notes}
        />
      </div>

      {!state.selectedRoleIds.length || !state.selectedLocationIds.length ? (
        <div className={`rounded-2xl border px-4 py-3 text-[12px] ${dark ? "border-white/[0.08] bg-white/[0.03] text-[#C1CED8]" : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"}`}>
          Team editing requires at least one role and one location so we can persist the employee across `employee_roles` and `employee_locations` correctly.
        </div>
      ) : null}
    </div>
  );
}

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
  onClose(): void;
  onCreated(): Promise<void>;
  roles: BusinessRole[];
}) {
  const controls = useEmployeeForm(emptyEmployeeForm());
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";

  const canSubmit =
    Boolean(controls.state.fullName.trim()) &&
    Boolean(controls.state.selectedRoleIds.length) &&
    Boolean(controls.state.primaryRoleId) &&
    Boolean(controls.state.primaryLocationId);

  const handleSubmit = () => {
    if (!canSubmit || isPending) {
      return;
    }
    startTransition(async () => {
      try {
        setFeedback(null);
        const orderedRoleIds = [
          controls.state.primaryRoleId,
          ...controls.state.selectedRoleIds.filter(
            (roleId) => roleId !== controls.state.primaryRoleId,
          ),
        ];
        await enrollEmployeeAtLocation(businessId, {
          full_name: controls.state.fullName.trim(),
          preferred_name: normalizeOptional(controls.state.preferredName),
          email: normalizeOptional(controls.state.email),
          phone_e164: normalizeOptional(controls.state.phone),
          employment_type: normalizeOptional(controls.state.employmentType),
          notes: normalizeOptional(controls.state.notes),
          location_id: controls.state.primaryLocationId,
          role_ids: orderedRoleIds,
        });
        await onCreated();
        onClose();
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not add this employee.",
        });
      }
    });
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
        className={`mx-4 w-full max-w-3xl overflow-hidden rounded-[28px] border ${dark ? "border-white/[0.08] bg-[#0F2E4C]" : "border-[#E5E7EB] bg-white"}`}
        exit={{ opacity: 0, scale: 0.96, y: 16 }}
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        onClick={(event) => event.stopPropagation()}
        transition={{ duration: 0.22 }}
      >
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
                <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Create the employee and enroll them at their primary location.
                </p>
              </div>
            </div>
            <button className={`rounded-full p-2 ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`} onClick={onClose} type="button">
              <X className="text-[#8898AA]" size={16} />
            </button>
          </div>
          <div className={`mt-4 flex items-center gap-3 rounded-2xl border px-4 py-3 ${dark ? "border-white/[0.08] bg-white/[0.04]" : "border-[#E5E7EB] bg-[#F7F8FA]"}`}>
            <Upload className="text-[#635BFF]" size={16} />
            <div className="flex-1">
              <p className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                Bulk upload stays reference-only for now.
              </p>
              <p className="mt-1 text-[11px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                Download the roster template if you want to prep bulk data while we finalize the import contract.
              </p>
            </div>
            <a
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] text-[#635BFF] ${dark ? "border-white/[0.08] bg-white/[0.04] hover:bg-white/[0.06]" : "border-[#E5E7EB] bg-white hover:bg-[#F7F8FA]"}`}
              download
              href={rosterTemplateHref}
              style={{ fontWeight: 520 }}
            >
              <Download size={12} /> Template
            </a>
          </div>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">
          {feedback ? (
            <div
              className="mb-4 rounded-2xl px-4 py-3 text-[13px]"
              role="status"
              style={{
                background: "rgba(229, 72, 77, 0.08)",
                color: "#C13535",
                fontWeight: 500,
              }}
            >
              {feedback.message}
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

        <div className={`flex items-center justify-end gap-3 border-t px-6 py-4 ${borderClass}`}>
          <button
            className={`rounded-full border px-4 py-2.5 text-[13px] ${dark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"}`}
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-full px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canSubmit || isPending}
            onClick={handleSubmit}
            style={{
              fontWeight: 540,
              background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
            }}
            type="button"
          >
            {isPending ? "Adding..." : "Add Employee"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

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
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const panelSurface = dark ? "bg-white/[0.04]" : "bg-[#F7F8FA]";

  useEffect(() => {
    let cancelled = false;

    async function loadProfile() {
      try {
        setLoading(true);
        setFeedback(null);
        const nextProfile = await getEmployeeProfile(businessId, employee.id);
        if (cancelled) {
          return;
        }
        setProfile(nextProfile);
        controls.setState(buildEmployeeForm(nextProfile));
      } catch (error) {
        if (!cancelled) {
          setFeedback({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not load this employee.",
          });
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadProfile();

    return () => {
      cancelled = true;
    };
  }, [businessId, employee.id]);

  const canSave =
    Boolean(controls.state.fullName.trim()) &&
    Boolean(controls.state.selectedRoleIds.length) &&
    Boolean(controls.state.selectedLocationIds.length) &&
    Boolean(controls.state.primaryRoleId) &&
    Boolean(controls.state.primaryLocationId);

  const handleSave = () => {
    if (!canSave || isPending) {
      return;
    }
    startTransition(async () => {
      try {
        setFeedback(null);
        const nextProfile = await updateEmployee(businessId, employee.id, {
          full_name: controls.state.fullName.trim(),
          preferred_name: normalizeOptional(controls.state.preferredName),
          email: normalizeOptional(controls.state.email),
          phone_e164: normalizeOptional(controls.state.phone),
          employment_type: normalizeOptional(controls.state.employmentType),
          status: controls.state.status,
          notes: normalizeOptional(controls.state.notes),
          roles: controls.state.selectedRoleIds.map((roleId) => ({
            role_id: roleId,
            is_primary: roleId === controls.state.primaryRoleId,
          })),
          locations: controls.state.selectedLocationIds.map((locationId) => ({
            location_id: locationId,
            is_primary: locationId === controls.state.primaryLocationId,
          })),
        });
        setProfile(nextProfile);
        controls.setState(buildEmployeeForm(nextProfile));
        await onSaved(nextProfile);
        setFeedback({ tone: "success", message: "Employee updated." });
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not update this employee.",
        });
      }
    });
  };

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-sm"
      exit={{ opacity: 0 }}
      initial={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        animate={{ x: 0 }}
        className={`flex h-full w-full max-w-[520px] flex-col border-l ${dark ? "border-white/[0.08] bg-[#0F2E4C]" : "border-[#E5E7EB] bg-white"}`}
        exit={{ x: 520 }}
        initial={{ x: 520 }}
        onClick={(event) => event.stopPropagation()}
        transition={{ duration: 0.28, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        <div className={`border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#635BFF]/10 text-[14px] text-[#635BFF]" style={{ fontWeight: 600 }}>
                {employeeInitials(displayName(employee))}
              </div>
              <div>
                <h2 className={`text-[18px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  {displayName(employee)}
                </h2>
                <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Edit employee roles, locations, and core profile data.
                </p>
              </div>
            </div>
            <button className={`rounded-full p-2 ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`} onClick={onClose} type="button">
              <X className="text-[#8898AA]" size={16} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {feedback ? (
            <div
              className="mb-4 rounded-2xl px-4 py-3 text-[13px]"
              role="status"
              style={{
                background:
                  feedback.tone === "success"
                    ? "rgba(0, 184, 147, 0.08)"
                    : "rgba(229, 72, 77, 0.08)",
                color: feedback.tone === "success" ? "#067A64" : "#C13535",
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
              <div className={`mb-5 rounded-2xl px-4 py-4 ${panelSurface}`}>
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

        <div className={`flex items-center justify-end gap-3 border-t px-6 py-4 ${borderClass}`}>
          <button
            className={`rounded-full border px-4 py-2.5 text-[13px] ${dark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"}`}
            onClick={onClose}
            type="button"
          >
            Close
          </button>
          <button
            className="rounded-full px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canSave || isPending || loading}
            onClick={handleSave}
            style={{
              fontWeight: 540,
              background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
            }}
            type="button"
          >
            {isPending ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

export default function Team({
  embeddedInShell = false,
}: {
  embeddedInShell?: boolean;
}) {
  const isDark = useResolvedAppAppearance() === "dark";
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [businessId, setBusinessId] = useState<string | null>(null);
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
  const [showBulkInfo, setShowBulkInfo] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeSummary | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadTeamData() {
      try {
        setLoading(true);
        setFeedback(null);
        const nextWorkspace = await getWorkspace();
        if (cancelled) {
          return;
        }
        setWorkspace(nextWorkspace);
        const primaryBusinessId = nextWorkspace?.businesses[0]?.business_id ?? null;
        setBusinessId(primaryBusinessId);
        if (!primaryBusinessId) {
          setEmployees([]);
          setLocations([]);
          setRoles([]);
          return;
        }
        const [nextEmployees, nextLocations, nextRoles] = await Promise.all([
          listEmployees(primaryBusinessId),
          listBusinessLocations(primaryBusinessId),
          listBusinessRoles(primaryBusinessId),
        ]);
        if (cancelled) {
          return;
        }
        setEmployees(nextEmployees);
        setLocations(nextLocations.filter((location) => location.is_active));
        setRoles(nextRoles);
      } catch (error) {
        if (!cancelled) {
          setFeedback({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not load the team roster.",
          });
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadTeamData();

    return () => {
      cancelled = true;
    };
  }, []);

  const refreshEmployees = async () => {
    if (!businessId) {
      return;
    }
    const nextEmployees = await listEmployees(businessId);
    setEmployees(nextEmployees);
  };

  const handleEmployeeSaved = async (nextEmployee: EmployeeProfile) => {
    setEmployees((current) => {
      const replacement: EmployeeSummary = nextEmployee;
      return current.map((employee) =>
        employee.id === replacement.id ? replacement : employee,
      );
    });
    setSelectedEmployee(nextEmployee);
  };

  const filteredEmployees = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const filtered = employees.filter((employee) => {
      const matchesSearch =
        !query ||
        displayName(employee).toLowerCase().includes(query) ||
        (employee.email ?? "").toLowerCase().includes(query) ||
        (employee.primary_role_name ?? "").toLowerCase().includes(query);
      const matchesLocation =
        locationFilter === "all" || employee.primary_location_id === locationFilter;
      const matchesStatus = statusFilter === "all" || employee.status === statusFilter;
      return matchesSearch && matchesLocation && matchesStatus;
    });
    return sortEmployees(filtered, sortField, sortDirection);
  }, [employees, locationFilter, searchQuery, sortDirection, sortField, statusFilter]);

  const activeCount = employees.filter((employee) => employee.status === "active").length;
  const onLeaveCount = employees.filter((employee) => employee.status === "on_leave").length;
  const inactiveCount = employees.filter((employee) => employee.status === "inactive").length;
  const textPrimary = isDark ? "text-white" : "text-[#0A2540]";
  const textSecondary = isDark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const textMuted = "text-[#8898AA]";
  const cardClass = isDark
    ? "bg-[#0F2E4C] border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.25)]"
    : "bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]";
  const tableHeaderClass = isDark ? "bg-white/[0.03] border-white/[0.06]" : "bg-[#FAFBFC] border-[#F0F0F5]";
  const rowHover = isDark ? "hover:bg-white/[0.03]" : "hover:bg-[#FAFBFC]";
  const inputClass = isDark
    ? "border-white/[0.08] bg-white/[0.04] text-white"
    : "border-[#E5E7EB] bg-white text-[#0A2540]";
  const businessName =
    workspace?.businesses[0]?.business_display_name ??
    workspace?.businesses[0]?.business_name ??
    "Backfill";

  const content = (
    <>
      <motion.div animate={{ opacity: 1, y: 0 }} className="mb-8" initial={{ opacity: 0, y: 12 }} transition={{ duration: 0.45 }}>
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <h1 className={`text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] ${textPrimary}`} style={{ fontWeight: 620 }}>
              Team
            </h1>
            <p className={`mt-1 text-[13px] sm:text-[15px] ${textSecondary}`} style={{ fontWeight: 420 }}>
              Manage employees, roles, and location assignments for {businessName}.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              className={`hidden items-center gap-2 rounded-full border px-4 py-2.5 text-[13px] sm:flex ${isDark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"}`}
              onClick={() => setShowBulkInfo(true)}
              type="button"
            >
              <Upload size={14} /> Bulk Upload
            </button>
            <button
              className="flex items-center gap-2 rounded-full px-4 py-2.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!businessId || !locations.length || !roles.length}
              onClick={() => setShowAddModal(true)}
              style={{
                fontWeight: 540,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
              type="button"
            >
              <Plus size={14} /> Add Employee
            </button>
          </div>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Total Employees", value: employees.length, color: "#635BFF" },
            { label: "Active", value: activeCount, color: "#00B893" },
            { label: "On Leave", value: onLeaveCount, color: "#F59E0B" },
            { label: "Inactive", value: inactiveCount, color: "#8898AA" },
          ].map((stat, index) => (
            <motion.div
              key={stat.label}
              animate={{ opacity: 1, y: 0 }}
              className={`${cardClass} rounded-[24px] border px-4 py-4`}
              initial={{ opacity: 0, y: 8 }}
              transition={{ delay: index * 0.05, duration: 0.35 }}
            >
              <div className="mb-1 flex items-center justify-between">
                <span className={`text-[11px] uppercase tracking-[0.04em] ${textMuted}`} style={{ fontWeight: 480 }}>
                  {stat.label}
                </span>
                <div className="h-2 w-2 rounded-full" style={{ background: stat.color }} />
              </div>
              <span className={`text-[26px] tracking-[-0.02em] ${textPrimary}`} style={{ fontWeight: 660 }}>
                {stat.value}
              </span>
            </motion.div>
          ))}
        </div>

        {feedback ? (
          <div
            className="mb-4 rounded-2xl px-4 py-3 text-[13px]"
            role="status"
            style={{
              background:
                feedback.tone === "success"
                  ? "rgba(0, 184, 147, 0.08)"
                  : "rgba(229, 72, 77, 0.08)",
              color: feedback.tone === "success" ? "#067A64" : "#C13535",
              fontWeight: 500,
            }}
          >
            {feedback.message}
          </div>
        ) : null}

        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8898AA]" size={15} />
            <input
              className={`w-full rounded-full border py-2.5 pl-9 pr-4 text-[12px] placeholder-[#8898AA]/60 ${inputClass}`}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search by name, role, or email"
              type="text"
              value={searchQuery}
            />
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <BrandedSelect
                dark={isDark}
                onChange={(event: { target: { value: string } }) => setLocationFilter(event.target.value)}
                value={locationFilter}
              >
                <option value="all">All Locations</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </BrandedSelect>
            </div>
            <div className="relative">
              <BrandedSelect
                dark={isDark}
                onChange={(event: { target: { value: string } }) => setStatusFilter(event.target.value)}
                value={statusFilter}
              >
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </BrandedSelect>
            </div>
          </div>
          <span className={`ml-auto text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
            {filteredEmployees.length} employee{filteredEmployees.length === 1 ? "" : "s"}
          </span>
        </div>
      </motion.div>

      <motion.div
        animate={{ opacity: 1, y: 0 }}
        className={`${cardClass} overflow-hidden rounded-[28px] border`}
        initial={{ opacity: 0, y: 16 }}
        transition={{ duration: 0.45, delay: 0.1 }}
      >
        <div className={`hidden grid-cols-[2fr_1fr_1fr_0.9fr_44px] gap-4 border-b px-5 py-3 md:grid ${tableHeaderClass}`}>
          {[
            { label: "Employee", field: "name" as const },
            { label: "Primary Role", field: "role" as const },
            { label: "Primary Location", field: "location" as const },
          ].map((column) => (
            <button
              key={column.field}
              className={`flex items-center gap-1.5 text-[11px] uppercase tracking-[0.04em] ${textMuted}`}
              onClick={() => {
                if (sortField === column.field) {
                  setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
                } else {
                  setSortField(column.field);
                  setSortDirection("asc");
                }
              }}
              type="button"
            >
              {column.label} <ArrowUpDown size={11} />
            </button>
          ))}
          <span className={`text-[11px] uppercase tracking-[0.04em] ${textMuted}`} style={{ fontWeight: 500 }}>
            Status
          </span>
          <span />
        </div>

        {loading ? (
          <div className={`px-8 py-16 text-center text-[14px] ${textSecondary}`}>Loading team roster...</div>
        ) : !businessId ? (
          <div className="px-8 py-16 text-center">
            <AlertCircle className="mx-auto mb-3 text-[#8898AA]" size={28} />
            <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 520 }}>
              No workspace business yet
            </p>
            <p className={`mt-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
              Create a business before managing employees.
            </p>
          </div>
        ) : filteredEmployees.length ? (
          <>
            <div className="hidden md:block">
              {filteredEmployees.map((employee, index) => {
                const status = statusConfig[employee.status] ?? statusConfig.inactive;
                return (
                  <motion.div
                    key={employee.id}
                    animate={{ opacity: 1 }}
                    className={`grid cursor-pointer grid-cols-[2fr_1fr_1fr_0.9fr_44px] gap-4 border-b px-5 py-3.5 last:border-0 ${isDark ? "border-white/[0.06]" : "border-[#F7F8FA]"} ${rowHover}`}
                    initial={{ opacity: 0 }}
                    onClick={() => setSelectedEmployee(employee)}
                    transition={{ delay: index * 0.02, duration: 0.2 }}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] text-[12px] text-white" style={{ fontWeight: 600 }}>
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
                      <span className="rounded-full bg-[#635BFF]/10 px-2.5 py-1 text-[11px] text-[#635BFF]" style={{ fontWeight: 520 }}>
                        {employee.primary_role_name ?? "Unassigned"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 min-w-0">
                      <MapPin className="text-[#8898AA]" size={13} />
                      <span className={`truncate text-[12px] ${textSecondary}`} style={{ fontWeight: 440 }}>
                        {employee.primary_location_name ?? "Unassigned"}
                      </span>
                    </div>
                    <div className="flex items-center">
                      <span
                        className="rounded-full px-2.5 py-1 text-[11px]"
                        style={{
                          fontWeight: 520,
                          color: status.color,
                          background: status.bg,
                        }}
                      >
                        {status.label}
                      </span>
                    </div>
                    <div className="flex items-center justify-center">
                      <button
                        className={`rounded-full p-2 ${isDark ? "hover:bg-white/[0.06]" : "hover:bg-[#F0F0F5]"}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedEmployee(employee);
                        }}
                        type="button"
                      >
                        <Eye className="text-[#8898AA]" size={14} />
                      </button>
                    </div>
                  </motion.div>
                );
              })}
            </div>

            <div className={`divide-y md:hidden ${isDark ? "divide-white/[0.06]" : "divide-[#F7F8FA]"}`}>
              {filteredEmployees.map((employee) => {
                const status = statusConfig[employee.status] ?? statusConfig.inactive;
                return (
                  <button
                    key={employee.id}
                    className="w-full px-4 py-3.5 text-left"
                    onClick={() => setSelectedEmployee(employee)}
                    type="button"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] text-[12px] text-white" style={{ fontWeight: 600 }}>
                        {employeeInitials(displayName(employee))}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className={`truncate text-[14px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                            {displayName(employee)}
                          </p>
                          <span
                            className="rounded-full px-2 py-0.5 text-[10px]"
                            style={{
                              fontWeight: 520,
                              color: status.color,
                              background: status.bg,
                            }}
                          >
                            {status.label}
                          </span>
                        </div>
                        <p className={`mt-1 text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                          {employee.primary_role_name ?? "Unassigned"} · {employee.primary_location_name ?? "Unassigned"}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <div className="px-8 py-16 text-center">
            <Shield className="mx-auto mb-3 text-[#8898AA]" size={28} />
            <p className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 520 }}>
              No employees yet
            </p>
            <p className={`mt-1 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
              Add your first employee after the business has roles and locations configured.
            </p>
          </div>
        )}
      </motion.div>

      <AnimatePresence>
        {showBulkInfo ? (
          <motion.div
            animate={{ opacity: 1 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
            exit={{ opacity: 0 }}
            initial={{ opacity: 0 }}
            onClick={() => setShowBulkInfo(false)}
          >
            <motion.div
              animate={{ opacity: 1, scale: 1, y: 0 }}
              className={`mx-4 w-full max-w-lg rounded-[28px] border px-6 py-6 ${isDark ? "border-white/[0.08] bg-[#0F2E4C]" : "border-[#E5E7EB] bg-white"}`}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              onClick={(event) => event.stopPropagation()}
              transition={{ duration: 0.22 }}
            >
              <div className="mb-4 flex items-center justify-between">
                <h2 className={`text-[18px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  Bulk Upload
                </h2>
                <button className={`rounded-full p-2 ${isDark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`} onClick={() => setShowBulkInfo(false)} type="button">
                  <X className="text-[#8898AA]" size={16} />
                </button>
              </div>
              <p className={`text-[13px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                The bulk roster import UI is still reference-only. The live employee create and edit flows are wired, but the import contract is not finished yet.
              </p>
              <a
                className={`mt-4 inline-flex items-center gap-2 rounded-full border px-4 py-2.5 text-[13px] text-[#635BFF] ${isDark ? "border-white/[0.08] bg-white/[0.04] hover:bg-white/[0.06]" : "border-[#E5E7EB] bg-white hover:bg-[#F7F8FA]"}`}
                download
                href={rosterTemplateHref}
                style={{ fontWeight: 520 }}
              >
                <Download size={14} /> Download Template
              </a>
            </motion.div>
          </motion.div>
        ) : null}

        {showAddModal && businessId ? (
          <AddEmployeeModal
            businessId={businessId}
            dark={isDark}
            locations={locations}
            onClose={() => setShowAddModal(false)}
            onCreated={refreshEmployees}
            roles={roles}
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

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav="Team">{content}</DashboardShell>;
}
