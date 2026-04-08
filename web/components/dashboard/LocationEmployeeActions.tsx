"use client";

import { useMemo, useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Download, Plus, Tag, Upload, UserPlus, X } from "lucide-react";

import type { BusinessRole } from "@/lib/api/businesses";
import { enrollEmployeeAtLocation } from "@/lib/api/workspace";

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

const rosterTemplateHref = "/backfill-employee-roster-template.xlsx";

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

type EnrollmentResponse = Awaited<ReturnType<typeof enrollEmployeeAtLocation>>;

export function LocationEmployeeEnrollmentModal({
  businessId,
  dark,
  locationId,
  locationName,
  onClose,
  onCreated,
  roles,
}: {
  businessId: string;
  dark: boolean;
  locationId: string;
  locationName: string;
  onClose(): void;
  onCreated(result: EnrollmentResponse): Promise<void> | void;
  roles: BusinessRole[];
}) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
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

  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";
  const inputClass = dark
    ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8898AA]"
    : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#8898AA]";

  const canSubmit = Boolean(fullName.trim()) && selectedRoleIds.length > 0;

  const toggleRole = (roleId: string) => {
    setSelectedRoleIds((current) =>
      current.includes(roleId)
        ? current.filter((item) => item !== roleId)
        : [...current, roleId],
    );
  };

  const handleSubmit = () => {
    if (!canSubmit || isPending) {
      return;
    }

    startTransition(async () => {
      try {
        setFeedback(null);
        const result = await enrollEmployeeAtLocation(businessId, {
          full_name: fullName.trim(),
          email: normalizeOptional(email),
          phone_e164: normalizeOptional(phone),
          location_id: locationId,
          role_ids: selectedRoleIds,
        });
        await onCreated(result);
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
                  Create the employee and add them to {locationName}.
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
                Assigned Location
              </h3>
            </div>
            <div
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 ${dark ? "border-[#635BFF]/25 bg-[#635BFF]/[0.12]" : "border-[#635BFF]/15 bg-[#635BFF]/[0.06]"}`}
            >
              <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                {locationName}
              </span>
            </div>
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
                  Assign at least one role before this employee can be scheduled.
                </p>
              ) : null}
            </div>

            {availableRoles.length > 0 ? (
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
                      {role.name}
                    </span>
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
  dark,
  onClose,
}: {
  dark: boolean;
  onClose(): void;
}) {
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const borderClass = dark ? "border-white/[0.08]" : "border-[#E5E7EB]";

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
        className={`mx-4 w-full max-w-lg overflow-hidden rounded-[28px] border ${dark ? "border-white/[0.08] bg-[#0F2E4C]" : "border-[#E5E7EB] bg-white"}`}
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
                  Prep roster data while the import contract is finalized.
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

        <div className="px-6 py-6">
          <div
            className={`flex items-start gap-3 rounded-2xl border px-4 py-4 ${dark ? "border-white/[0.08] bg-white/[0.04]" : "border-[#E5E7EB] bg-[#F7F8FA]"}`}
          >
            <Upload className="mt-0.5 text-[#635BFF]" size={16} />
            <div>
              <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>
                Bulk import is not wired yet on this screen.
              </p>
              <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 420 }}>
                Download the employee roster template now, then return here once the import flow lands.
              </p>
            </div>
          </div>
        </div>

        <div className={`flex items-center justify-end gap-3 border-t px-6 py-4 ${borderClass}`}>
          <a
            className={`inline-flex items-center gap-1.5 rounded-full border px-4 py-2.5 text-[13px] text-[#635BFF] ${dark ? "border-white/[0.08] bg-white/[0.04] hover:bg-white/[0.06]" : "border-[#E5E7EB] bg-white hover:bg-[#F7F8FA]"}`}
            download
            href={rosterTemplateHref}
            style={{ fontWeight: 520 }}
          >
            <Download size={13} /> Download Template
          </a>
          <button
            className={`rounded-full border px-4 py-2.5 text-[13px] ${dark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.06]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-[#F7F8FA]"}`}
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
