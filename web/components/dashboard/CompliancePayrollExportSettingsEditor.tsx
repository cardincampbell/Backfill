"use client";

import { useEffect, useMemo, useState } from "react";

import {
  type CompliancePayrollExportSettings,
  type CompliancePayrollProviderProfile,
  type CompliancePayrollExportSettingsUpdate,
  type CompliancePayrollIdentifierField,
  updateBusinessProfile,
} from "@/lib/api/workspace";

type RuleCodeField = {
  ruleCode: string;
  label: string;
  placeholder: string;
};

const RULE_CODE_FIELDS: RuleCodeField[] = [
  {
    ruleCode: "meal_break_first_window",
    label: "First meal premium code",
    placeholder: "MEALPREM",
  },
  {
    ruleCode: "meal_break_second_window",
    label: "Second meal premium code",
    placeholder: "MEALPREM",
  },
  {
    ruleCode: "paid_rest_break_quota",
    label: "Rest break premium code",
    placeholder: "RESTPREM",
  },
  {
    ruleCode: "split_shift_premium",
    label: "Split shift premium code",
    placeholder: "SPLITPREM",
  },
  {
    ruleCode: "spread_of_hours_premium",
    label: "Spread of hours premium code",
    placeholder: "SPREADPREM",
  },
];

const PROVIDER_PROFILES: Array<{
  value: CompliancePayrollProviderProfile;
  label: string;
  description: string;
}> = [
  {
    value: "generic_csv_v1",
    label: "Backfill generic CSV",
    description: "Full-fidelity export with Backfill’s canonical compliance payroll columns.",
  },
  {
    value: "gusto_csv_v1",
    label: "Gusto-aligned CSV",
    description: "Earnings-oriented CSV tuned for Gusto-style amount imports and audit notes.",
  },
  {
    value: "quickbooks_csv_v1",
    label: "QuickBooks-aligned CSV",
    description: "Payroll-item oriented CSV with employee identifiers and premium memo context.",
  },
  {
    value: "adp_csv_v1",
    label: "ADP-aligned CSV",
    description: "Associate/pay-code oriented CSV that preserves manual-review and source metadata.",
  },
];

type DraftState = {
  providerProfile: CompliancePayrollProviderProfile;
  preferredIdentifier: CompliancePayrollIdentifierField;
  useSecondaryIdentifier: boolean;
  allowInternalIdFallback: boolean;
  defaultEarningCode: string;
  defaultEarningLabel: string;
  earningCodes: Record<string, string>;
};

function normalizeProviderProfile(
  value: unknown,
): CompliancePayrollProviderProfile {
  const normalized = String(value ?? "").trim();
  const matched = PROVIDER_PROFILES.find((profile) => profile.value === normalized);
  return matched?.value ?? "generic_csv_v1";
}

function normalizePriority(
  priority: readonly CompliancePayrollIdentifierField[] | null | undefined,
): CompliancePayrollIdentifierField[] {
  const deduped: CompliancePayrollIdentifierField[] = [];
  for (const value of priority ?? []) {
    if (
      (value === "employee_number" || value === "external_ref")
      && !deduped.includes(value)
    ) {
      deduped.push(value);
    }
  }
  if (deduped.length === 0) {
    return ["employee_number", "external_ref"];
  }
  if (deduped.length === 1) {
    deduped.push(
      deduped[0] === "employee_number" ? "external_ref" : "employee_number",
    );
  }
  return deduped;
}

export function readCompliancePayrollExportSettingsSnapshot(
  value: unknown,
): CompliancePayrollExportSettings {
  const raw = value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
  const normalizedPriority = normalizePriority(
    Array.isArray(raw.employee_identifier_priority)
      ? (raw.employee_identifier_priority as CompliancePayrollIdentifierField[])
      : null,
  );
  const earningCodes: Record<string, { code: string; label?: string | null }> = {};
  const rawEarningCodes = raw.earning_codes;
  if (rawEarningCodes && typeof rawEarningCodes === "object") {
    for (const field of RULE_CODE_FIELDS) {
      const entry = (rawEarningCodes as Record<string, unknown>)[field.ruleCode];
      if (!entry || typeof entry !== "object") {
        continue;
      }
      const code = String((entry as Record<string, unknown>).code ?? "").trim();
      const label = String((entry as Record<string, unknown>).label ?? "").trim();
      if (!code) {
        continue;
      }
      earningCodes[field.ruleCode] = {
        code,
        label: label || null,
      };
    }
  }
  return {
    provider_profile: normalizeProviderProfile(raw.provider_profile),
    employee_identifier_priority: normalizedPriority,
    allow_internal_employee_id_fallback: Boolean(
      raw.allow_internal_employee_id_fallback,
    ),
    default_earning_code:
      String(raw.default_earning_code ?? "").trim() || "COMPLIANCE",
    default_earning_label:
      String(raw.default_earning_label ?? "").trim() || "Compliance Premium",
    earning_codes: earningCodes,
  };
}

function buildDraftState(
  currentSettings: CompliancePayrollExportSettings | null | undefined,
): DraftState {
  const normalized = readCompliancePayrollExportSettingsSnapshot(currentSettings);
  return {
    providerProfile: normalized.provider_profile,
    preferredIdentifier: normalized.employee_identifier_priority[0] ?? "employee_number",
    useSecondaryIdentifier:
      normalized.employee_identifier_priority.length > 1,
    allowInternalIdFallback:
      normalized.allow_internal_employee_id_fallback,
    defaultEarningCode: normalized.default_earning_code,
    defaultEarningLabel: normalized.default_earning_label,
    earningCodes: Object.fromEntries(
      RULE_CODE_FIELDS.map((field) => [
        field.ruleCode,
        normalized.earning_codes[field.ruleCode]?.code ?? "",
      ]),
    ),
  };
}

function draftToSettings(
  draft: DraftState,
): CompliancePayrollExportSettings {
  const priority: CompliancePayrollIdentifierField[] = [draft.preferredIdentifier];
  if (draft.useSecondaryIdentifier) {
    priority.push(
      draft.preferredIdentifier === "employee_number"
        ? "external_ref"
        : "employee_number",
    );
  }

  const earningCodes: CompliancePayrollExportSettings["earning_codes"] = {};
  for (const field of RULE_CODE_FIELDS) {
    const code = draft.earningCodes[field.ruleCode]?.trim() ?? "";
    if (!code) {
      continue;
    }
    earningCodes[field.ruleCode] = {
      code,
      label: field.label.replace(" code", ""),
    };
  }

  return {
    provider_profile: draft.providerProfile,
    employee_identifier_priority: priority,
    allow_internal_employee_id_fallback: draft.allowInternalIdFallback,
    default_earning_code: draft.defaultEarningCode.trim() || "COMPLIANCE",
    default_earning_label:
      draft.defaultEarningLabel.trim() || "Compliance Premium",
    earning_codes: earningCodes,
  };
}

function settingsToUpdatePayload(
  settings: CompliancePayrollExportSettings,
): CompliancePayrollExportSettingsUpdate {
  return {
    provider_profile: settings.provider_profile,
    employee_identifier_priority: settings.employee_identifier_priority,
    allow_internal_employee_id_fallback:
      settings.allow_internal_employee_id_fallback,
    default_earning_code: settings.default_earning_code,
    default_earning_label: settings.default_earning_label,
    earning_codes: Object.fromEntries(
      RULE_CODE_FIELDS.map((field) => [
        field.ruleCode,
        settings.earning_codes[field.ruleCode]
          ? {
              code: settings.earning_codes[field.ruleCode]?.code ?? "",
              label: settings.earning_codes[field.ruleCode]?.label ?? null,
            }
          : null,
      ]),
    ),
  };
}

export default function CompliancePayrollExportSettingsEditor({
  dark,
  businessId,
  businessDisplayName,
  businessTimezone,
  currentSettings,
  onApplied,
}: {
  dark: boolean;
  businessId: string;
  businessDisplayName: string;
  businessTimezone: string;
  currentSettings: CompliancePayrollExportSettings | null | undefined;
  onApplied(nextSettings: CompliancePayrollExportSettings): void;
}) {
  const [draft, setDraft] = useState<DraftState>(() => buildDraftState(currentSettings));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{
    tone: "success" | "error";
    text: string;
  } | null>(null);

  useEffect(() => {
    setDraft(buildDraftState(currentSettings));
    setMessage((current) => (current?.tone === "success" ? current : null));
  }, [currentSettings]);

  const nextSettings = useMemo(() => draftToSettings(draft), [draft]);
  const baselineSettings = useMemo(
    () => readCompliancePayrollExportSettingsSnapshot(currentSettings),
    [currentSettings],
  );
  const hasChanges =
    JSON.stringify(nextSettings) !== JSON.stringify(baselineSettings);

  const cardSurface = dark
    ? "border-white/10 bg-white/[0.04]"
    : "border-[#D6DEE8] bg-white";
  const textPrimary = dark ? "text-white" : "text-[#0F172A]";
  const textSecondary = dark ? "text-[#AFC2D3]" : "text-[#516072]";
  const inputSurface = dark
    ? "border-white/12 bg-[#08131F] text-white"
    : "border-[#D6DEE8] bg-white text-[#0F172A]";

  async function handleSave() {
    if (!hasChanges || saving) {
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const response = await updateBusinessProfile(businessId, {
        display_name: businessDisplayName,
        timezone: businessTimezone,
        compliance_payroll_export: settingsToUpdatePayload(nextSettings),
      });
      const savedSettings = readCompliancePayrollExportSettingsSnapshot(
        response.settings?.["compliance_payroll_export"],
      );
      onApplied(savedSettings);
      setMessage({
        tone: "success",
        text: "Compliance payroll export settings updated.",
      });
    } catch {
      setMessage({
        tone: "error",
        text: "Backfill could not save compliance payroll export settings right now.",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`rounded-2xl border p-4 ${cardSurface}`}>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 560 }}>
            Compliance Payroll Export
          </p>
          <p className={`mt-1 text-[12px] ${textSecondary}`} style={{ fontWeight: 430 }}>
            Define which employee identifier and earning codes Backfill uses when exporting compliance premiums and manual review rows for payroll.
          </p>
        </div>
        <button
          type="button"
          onClick={handleSave}
          disabled={!hasChanges || saving}
          className={`mt-3 rounded-full px-4 py-2 text-[12px] sm:mt-0 ${
            !hasChanges || saving
              ? dark
                ? "cursor-not-allowed border border-white/10 bg-white/5 text-white/45"
                : "cursor-not-allowed border border-[#D6DEE8] bg-[#F7F9FC] text-[#94A3B8]"
              : dark
                ? "border border-[#F97316]/40 bg-[#F97316]/15 text-white"
                : "border border-[#F97316]/25 bg-[#FFF4ED] text-[#9A3412]"
          }`}
          style={{ fontWeight: 560 }}
        >
          {saving ? "Saving…" : "Save Export Settings"}
        </button>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className={`rounded-2xl border p-3 ${cardSurface}`}>
          <p className={`text-[12px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 600 }}>
            Provider Profile
          </p>
          <label className={`mt-3 block text-[12px] ${textSecondary}`} style={{ fontWeight: 500 }}>
            Payroll export format
          </label>
          <select
            aria-label="Payroll export format"
            value={draft.providerProfile}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                providerProfile: event.target.value as CompliancePayrollProviderProfile,
              }))
            }
            className={`mt-1 w-full rounded-2xl border px-3 py-2 text-[13px] ${inputSurface}`}
          >
            {PROVIDER_PROFILES.map((profile) => (
              <option key={profile.value} value={profile.value}>
                {profile.label}
              </option>
            ))}
          </select>
          <p className={`mt-2 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
            {PROVIDER_PROFILES.find((profile) => profile.value === draft.providerProfile)?.description}
          </p>
        </div>

        <div className={`rounded-2xl border p-3 ${cardSurface}`}>
          <p className={`text-[12px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 600 }}>
            Employee Identifier
          </p>
          <label className={`mt-3 block text-[12px] ${textSecondary}`} style={{ fontWeight: 500 }}>
            Preferred identifier
          </label>
          <select
            aria-label="Preferred identifier"
            value={draft.preferredIdentifier}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                preferredIdentifier: event.target.value as CompliancePayrollIdentifierField,
              }))
            }
            className={`mt-1 w-full rounded-2xl border px-3 py-2 text-[13px] ${inputSurface}`}
          >
            <option value="employee_number">Employee number</option>
            <option value="external_ref">External reference</option>
          </select>

          <label className="mt-3 flex items-start gap-2 text-[12px]">
            <input
              checked={draft.useSecondaryIdentifier}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  useSecondaryIdentifier: event.target.checked,
                }))
              }
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-[#CBD5E1]"
            />
            <span className={textSecondary}>
              Use the secondary external identifier when the preferred one is missing.
            </span>
          </label>

          <label className="mt-2 flex items-start gap-2 text-[12px]">
            <input
              checked={draft.allowInternalIdFallback}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  allowInternalIdFallback: event.target.checked,
                }))
              }
              type="checkbox"
              className="mt-0.5 h-4 w-4 rounded border-[#CBD5E1]"
            />
            <span className={textSecondary}>
              Fall back to Backfill’s internal employee ID when no external identifier exists.
            </span>
          </label>
        </div>

        <div className={`rounded-2xl border p-3 ${cardSurface}`}>
          <p className={`text-[12px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 600 }}>
            Default Earning
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <label className={`block text-[12px] ${textSecondary}`} style={{ fontWeight: 500 }}>
                Default earning code
              </label>
              <input
                aria-label="Default earning code"
                value={draft.defaultEarningCode}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    defaultEarningCode: event.target.value.toUpperCase(),
                  }))
                }
                className={`mt-1 w-full rounded-2xl border px-3 py-2 text-[13px] ${inputSurface}`}
                placeholder="COMPLIANCE"
                type="text"
              />
            </div>
            <div>
              <label className={`block text-[12px] ${textSecondary}`} style={{ fontWeight: 500 }}>
                Default earning label
              </label>
              <input
                aria-label="Default earning label"
                value={draft.defaultEarningLabel}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    defaultEarningLabel: event.target.value,
                  }))
                }
                className={`mt-1 w-full rounded-2xl border px-3 py-2 text-[13px] ${inputSurface}`}
                placeholder="Compliance Premium"
                type="text"
              />
            </div>
          </div>
        </div>
      </div>

      <div className={`mt-4 rounded-2xl border p-3 ${cardSurface}`}>
        <p className={`text-[12px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 600 }}>
          Rule-Specific Earning Codes
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {RULE_CODE_FIELDS.map((field) => (
            <div key={field.ruleCode}>
              <label className={`block text-[12px] ${textSecondary}`} style={{ fontWeight: 500 }}>
                {field.label}
              </label>
              <input
                aria-label={field.label}
                value={draft.earningCodes[field.ruleCode] ?? ""}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    earningCodes: {
                      ...current.earningCodes,
                      [field.ruleCode]: event.target.value.toUpperCase(),
                    },
                  }))
                }
                className={`mt-1 w-full rounded-2xl border px-3 py-2 text-[13px] ${inputSurface}`}
                placeholder={field.placeholder}
                type="text"
              />
            </div>
          ))}
        </div>
        <p className={`mt-3 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
          Backfill emits one payroll consequence row per premium component or manual review item. These codes control how premium rows land in downstream payroll exports.
        </p>
      </div>

      {message ? (
        <div
          className={`mt-4 rounded-2xl border px-3 py-2 text-[12px] ${
            message.tone === "success"
              ? dark
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
                : "border-emerald-200 bg-emerald-50 text-emerald-700"
              : dark
                ? "border-red-500/30 bg-red-500/10 text-red-100"
                : "border-red-200 bg-red-50 text-red-700"
          }`}
          style={{ fontWeight: 520 }}
        >
          {message.text}
        </div>
      ) : null}
    </div>
  );
}
