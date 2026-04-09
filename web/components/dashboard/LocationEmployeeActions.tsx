"use client";

import { useMemo, useRef, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Download, Plus, Tag, Upload, UserPlus, X } from "lucide-react";

import type { BusinessLocation, BusinessRole } from "@/lib/api/businesses";
import {
  createEmployee,
  downloadEmployeeImportTemplate,
  importEmployees,
  updateEmployee,
  type EmployeeBulkImportResponse,
  type EmployeeSummary,
} from "@/lib/api/workforce";

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function buildLocationAssignments(
  selectedLocationIds: string[],
  primaryLocationId: string,
) {
  const nextLocationIds = Array.from(new Set(selectedLocationIds));
  return nextLocationIds.map((locationId) => ({
    location_id: locationId,
    is_primary: locationId === primaryLocationId,
  }));
}

export function LocationEmployeeEnrollmentModal({
  businessId,
  businessLocations,
  dark,
  locationId,
  locationName,
  onClose,
  onCreated,
  roles,
}: {
  businessId: string;
  businessLocations: BusinessLocation[];
  dark: boolean;
  locationId: string;
  locationName: string;
  onClose(): void;
  onCreated(employee: EmployeeSummary): Promise<void> | void;
  roles: BusinessRole[];
}) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [selectedLocationIds, setSelectedLocationIds] = useState<string[]>([locationId]);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [isPending, startTransition] = useTransition();

  const selectedRoles = useMemo(
    () => roles.filter((role) => selectedRoleIds.includes(role.id)),
    [roles, selectedRoleIds],
  );
  const availableRoles = useMemo(
    () => roles.filter((role) => !selectedRoleIds.includes(role.id)),
    [roles, selectedRoleIds],
  );
  const selectedLocations = useMemo(
    () =>
      businessLocations.filter((location) => selectedLocationIds.includes(location.id)),
    [businessLocations, selectedLocationIds],
  );
  const availableLocations = useMemo(
    () =>
      businessLocations.filter((location) => !selectedLocationIds.includes(location.id)),
    [businessLocations, selectedLocationIds],
  );

  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const inputClass = dark
    ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8898AA]"
    : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#8898AA]";

  const hasRequiredLocation = selectedLocationIds.includes(locationId);
  const canSubmit =
    Boolean(fullName.trim()) &&
    Boolean(email.trim()) &&
    Boolean(phone.trim()) &&
    selectedRoleIds.length > 0 &&
    selectedLocationIds.length > 0 &&
    hasRequiredLocation;

  const toggleRole = (roleId: string) => {
    setSelectedRoleIds((current) =>
      current.includes(roleId)
        ? current.filter((item) => item !== roleId)
        : [...current, roleId],
    );
  };

  const toggleLocation = (locationIdToToggle: string) => {
    setSelectedLocationIds((current) =>
      current.includes(locationIdToToggle)
        ? current.filter((item) => item !== locationIdToToggle)
        : [...current, locationIdToToggle],
    );
  };

  const handleSubmit = () => {
    if (!canSubmit || isPending) {
      return;
    }

    startTransition(async () => {
      try {
        setFeedback(null);
        const createdEmployee = await createEmployee(businessId, {
          full_name: fullName.trim(),
          email: normalizeOptional(email),
          phone_e164: normalizeOptional(phone),
          primary_location_id: locationId,
          employee_metadata: {
            source: "location_ui",
            source_location_id: locationId,
          },
        });

        let nextEmployee: EmployeeSummary = createdEmployee;
        if (selectedRoleIds.length || selectedLocationIds.length) {
          nextEmployee = await updateEmployee(businessId, createdEmployee.id, {
            roles: selectedRoleIds.map((roleId) => ({
              role_id: roleId,
              is_primary: roleId === selectedRoleIds[0],
            })),
            locations: buildLocationAssignments(selectedLocationIds, locationId),
          });
        }

        await onCreated(nextEmployee);
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
                  This employee will be added to {locationName} automatically.
                </p>
              </div>
            </div>
            <button
              className={`rounded-full p-2 ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`}
              onClick={onClose}
              type="button"
            >
              <X className="text-[#8898AA]" size={16} />
            </button>
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
          {!canSubmit ? (
            <div
              className={`mb-4 rounded-2xl border px-4 py-3 text-[12px] ${
                dark
                  ? "border-white/[0.08] bg-white/[0.04] text-[#C1CED8]"
                  : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
              }`}
            >
              Name, phone, email, at least one role, and at least one location are required to add
              an employee from this form.
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label
                className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Full Name
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${inputClass}`}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Sarah Martinez"
                style={{ fontWeight: 440 }}
                type="text"
                value={fullName}
              />
            </div>
            <div>
              <label
                className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Email
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${inputClass}`}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="sarah.m@company.com"
                style={{ fontWeight: 440 }}
                type="email"
                value={email}
              />
            </div>
            <div>
              <label
                className="mb-1.5 block text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Phone
              </label>
              <input
                className={`w-full rounded-lg border px-3.5 py-2.5 text-[13px] transition-all focus:border-[#635BFF]/40 focus:outline-none focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] ${inputClass}`}
                onChange={(event) => setPhone(event.target.value)}
                placeholder="(415) 555-0142"
                style={{ fontWeight: 440 }}
                type="tel"
                value={phone}
              />
            </div>
          </div>

          <div className="mt-5">
            <div className="mb-3 flex items-center justify-between">
              <h3
                className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Assigned Locations
              </h3>
            </div>
            <div className="mb-4 flex flex-wrap gap-2">
              <AnimatePresence>
                {selectedLocations.map((location) => (
                  <motion.div
                    key={location.id}
                    layout
                    animate={{ opacity: 1, scale: 1 }}
                    className={`flex items-center gap-1.5 rounded-lg border py-1.5 pl-2.5 pr-2 ${dark ? "border-[#635BFF]/25 bg-[#635BFF]/[0.12]" : "border-[#635BFF]/15 bg-[#635BFF]/[0.06]"}`}
                    exit={{ opacity: 0, scale: 0.9 }}
                    initial={{ opacity: 0, scale: 0.9 }}
                  >
                    <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                      {location.name}
                    </span>
                    {location.id === locationId ? (
                      <span
                        className="text-[10px] text-[#635BFF]"
                        style={{ fontWeight: 520 }}
                      >
                        Primary
                      </span>
                    ) : null}
                    <button
                      className="ml-0.5 rounded p-0.5 transition-colors hover:bg-[#635BFF]/10"
                      onClick={() => toggleLocation(location.id)}
                      type="button"
                    >
                      <X className="text-[#8898AA] hover:text-[#E5484D]" size={12} />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
              {!selectedLocations.length ? (
                <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                  Select at least one location. This location must be included to continue.
                </p>
              ) : null}
            </div>

            {!hasRequiredLocation ? (
              <p className="mb-3 text-[12px] text-[#E5484D]" style={{ fontWeight: 460 }}>
                This location must stay selected to add an employee from this page.
              </p>
            ) : null}

            {availableLocations.length ? (
              <div className="flex flex-wrap gap-2">
                {availableLocations.map((location) => (
                  <button
                    className={`group flex items-center gap-1.5 rounded-lg border px-3 py-1.5 transition-all duration-200 ${
                      dark
                        ? "border-white/[0.08] bg-white/[0.03] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]"
                        : "border-[#E5E7EB] bg-[#F7F8FA] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]"
                    }`}
                    key={location.id}
                    onClick={() => toggleLocation(location.id)}
                    type="button"
                  >
                    <Plus
                      className="text-[#8898AA] transition-colors group-hover:text-[#635BFF]"
                      size={11}
                    />
                    <span
                      className={`text-[12px] transition-colors ${
                        dark
                          ? "text-[#C1CED8] group-hover:text-white"
                          : "text-[#5E6D7A] group-hover:text-[#0A2540]"
                      }`}
                      style={{ fontWeight: 440 }}
                    >
                      {location.name}
                    </span>
                    {location.id === locationId ? (
                      <span
                        className="text-[10px] text-[#635BFF]"
                        style={{ fontWeight: 520 }}
                      >
                        Current
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div className="mt-5">
            <div className="mb-3 flex items-center justify-between">
              <h3
                className="text-[11px] uppercase tracking-[0.04em] text-[#8898AA]"
                style={{ fontWeight: 500 }}
              >
                Roles
              </h3>
              <span className="text-[11px] text-[#8898AA]" style={{ fontWeight: 440 }}>
                {selectedRoles.length} selected
              </span>
            </div>
            <div className="mb-4 flex flex-wrap gap-2">
              <AnimatePresence>
                {selectedRoles.map((role) => (
                  <motion.div
                    key={role.id}
                    layout
                    animate={{ opacity: 1, scale: 1 }}
                    className={`flex items-center gap-1.5 rounded-lg border py-1.5 pl-2.5 pr-2 ${dark ? "border-[#635BFF]/25 bg-[#635BFF]/[0.12]" : "border-[#635BFF]/15 bg-[#635BFF]/[0.06]"}`}
                    exit={{ opacity: 0, scale: 0.9 }}
                    initial={{ opacity: 0, scale: 0.9 }}
                  >
                    <Tag className="text-[#635BFF]" size={11} />
                    <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                      {role.name}
                    </span>
                    <button
                      className="ml-0.5 rounded p-0.5 transition-colors hover:bg-[#635BFF]/10"
                      onClick={() => toggleRole(role.id)}
                      type="button"
                    >
                      <X className="text-[#8898AA] hover:text-[#E5484D]" size={12} />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
              {!selectedRoles.length ? (
                <p className="py-2 text-[12px] text-[#8898AA]" style={{ fontWeight: 420 }}>
                  Assign at least one role before you can add this employee from this screen.
                </p>
              ) : null}
            </div>

            {availableRoles.length ? (
              <div className="flex flex-wrap gap-2">
                {availableRoles.map((role) => (
                  <button
                    className={`group flex items-center gap-1.5 rounded-lg border px-3 py-1.5 transition-all duration-200 ${
                      dark
                        ? "border-white/[0.08] bg-white/[0.03] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.08]"
                        : "border-[#E5E7EB] bg-[#F7F8FA] hover:border-[#635BFF]/30 hover:bg-[#635BFF]/[0.03]"
                    }`}
                    key={role.id}
                    onClick={() => toggleRole(role.id)}
                    type="button"
                  >
                    <Tag className="text-[#635BFF]" size={11} />
                    <span
                      className={`text-[12px] transition-colors ${
                        dark
                          ? "text-[#C1CED8] group-hover:text-white"
                          : "text-[#5E6D7A] group-hover:text-[#0A2540]"
                      }`}
                      style={{ fontWeight: 440 }}
                    >
                      {role.name}
                    </span>
                    <Plus
                      className="ml-0.5 text-[#8898AA] transition-colors group-hover:text-[#635BFF]"
                      size={11}
                    />
                  </button>
                ))}
              </div>
            ) : null}
          </div>
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

export function LocationEmployeeBulkUploadModal({
  businessId,
  dark,
  locationId,
  locationName,
  onClose,
  onImported,
}: {
  businessId: string;
  dark: boolean;
  locationId: string;
  locationName: string;
  onClose(): void;
  onImported(
    employees: EmployeeSummary[],
    createdCount: number,
    skippedCount: number,
  ): Promise<void> | void;
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
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";

  const handleTemplateDownload = async () => {
    try {
      setFeedback(null);
      setIsDownloadingTemplate(true);
      await downloadEmployeeImportTemplate(businessId);
    } catch (error) {
      setFeedback({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Could not download the template.",
      });
    } finally {
      setIsDownloadingTemplate(false);
    }
  };

  const handleImport = () => {
    if (!selectedFile || isPending) {
      return;
    }

    startTransition(async () => {
      try {
        setFeedback(null);
        const result = await importEmployees(businessId, selectedFile);
        const updatedEmployees = await Promise.all(
          result.employees.map((employee) =>
            updateEmployee(businessId, employee.id, {
              locations: buildLocationAssignments([locationId], locationId),
            }),
          ),
        );
        setImportResult(result);
        await onImported(updatedEmployees, result.created_count, result.skipped_count);
        if (!result.errors.length) {
          onClose();
        }
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not import these employees.",
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
        className={`mx-4 w-full max-w-2xl overflow-hidden rounded-[28px] border ${dark ? "border-white/[0.08] bg-[#0F2E4C]" : "border-[#E5E7EB] bg-white"}`}
        exit={{ opacity: 0, scale: 0.96, y: 16 }}
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        onClick={(event) => event.stopPropagation()}
        transition={{ duration: 0.22 }}
      >
        <div className={`border-b px-6 py-5 ${borderClass}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#00B893]/10">
                <Upload className="text-[#00B893]" size={18} />
              </div>
              <div>
                <h2 className={`text-[18px] ${textPrimary}`} style={{ fontWeight: 600 }}>
                  Bulk Upload
                </h2>
                <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                  Imported employees will automatically be added to {locationName}.
                </p>
              </div>
            </div>
            <button
              className={`rounded-full p-2 ${dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"}`}
              onClick={onClose}
              type="button"
            >
              <X className="text-[#8898AA]" size={16} />
            </button>
          </div>
        </div>

        <div className="space-y-5 px-6 py-5">
          {feedback ? (
            <div
              className="rounded-2xl px-4 py-3 text-[13px]"
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

          <div
            className={`rounded-2xl border px-4 py-4 ${
              dark
                ? "border-white/[0.08] bg-white/[0.04] text-[#C1CED8]"
                : "border-[#E5E7EB] bg-[#F7F8FA] text-[#5E6D7A]"
            }`}
          >
            <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
              What gets imported
            </p>
            <p className="mt-1 text-[12px]" style={{ fontWeight: 420 }}>
              Required in the file: full_name, email, phone_e164. Roles still stay managed in the
              UI after import.
            </p>
            <p className="mt-3 text-[12px]" style={{ fontWeight: 420 }}>
              Everyone imported from this screen is assigned to{" "}
              <span style={{ fontWeight: 520 }}>{locationName}</span>.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-4 py-2.5 text-[13px] ${
                dark
                  ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]"
                  : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
              }`}
              disabled={isDownloadingTemplate}
              onClick={handleTemplateDownload}
              type="button"
            >
              <Download size={14} />
              {isDownloadingTemplate ? "Downloading..." : "Download Template"}
            </button>
            <button
              className={`inline-flex items-center gap-2 rounded-full border px-4 py-2.5 text-[13px] ${
                dark
                  ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]"
                  : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"
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
            onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            ref={inputRef}
            type="file"
          />

          <button
            className={`w-full rounded-[24px] border border-dashed px-6 py-8 text-center transition-all ${
              isDragging
                ? "border-[#635BFF] bg-[#635BFF]/[0.06]"
                : dark
                  ? "border-white/[0.1] bg-white/[0.03] hover:bg-white/[0.05]"
                  : "border-[#D7DBE3] bg-[#FAFBFC] hover:bg-[#F7F8FA]"
            }`}
            onClick={() => inputRef.current?.click()}
            onDragEnter={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              setIsDragging(false);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              const file = event.dataTransfer.files?.[0];
              if (file) {
                setSelectedFile(file);
              }
            }}
            type="button"
          >
            <Upload className="mx-auto mb-3 text-[#635BFF]" size={24} />
            <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
              Drag a CSV or XLSX file here
            </p>
            <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
              The import creates employee profiles, then assigns them to this location.
            </p>
          </button>

          {importResult?.errors.length ? (
            <div
              className={`rounded-2xl border px-4 py-4 ${
                dark
                  ? "border-white/[0.08] bg-white/[0.04]"
                  : "border-[#E5E7EB] bg-[#FAFBFC]"
              }`}
            >
              <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                Import completed with row issues
              </p>
              <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                {importResult.created_count} created, {importResult.skipped_count} skipped.
              </p>
              <div className="mt-3 space-y-2">
                {importResult.errors.map((error, index) => (
                  <div
                    key={`${error.row_number ?? "general"}-${index}`}
                    className={`rounded-xl px-3 py-2 text-[12px] ${
                      dark ? "bg-white/[0.04] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"
                    }`}
                    style={{ fontWeight: 420 }}
                  >
                    Row {error.row_number ?? "?"}: {error.message}
                  </div>
                ))}
              </div>
            </div>
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
            disabled={!selectedFile || isPending}
            onClick={handleImport}
            style={{
              fontWeight: 540,
              background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
            }}
            type="button"
          >
            {isPending ? "Uploading..." : "Import Employees"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
