"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check } from "lucide-react";

import {
  getBusinessCompliancePolicyVersions,
  getLocationCompliancePolicyVersions,
  applySimulatedBusinessCompliancePolicy,
  applySimulatedLocationCompliancePolicy,
  replayLocationCompliancePolicyVersion,
  simulateBusinessCompliancePolicy,
  simulateLocationCompliancePolicy,
  type BusinessCompliancePolicySimulation,
  type CompliancePolicyVersion,
  type CompliancePolicySettingsSnapshot,
  type LocationComplianceWeekReplay,
  type LocationCompliancePolicySimulation,
  restoreBusinessCompliancePolicyVersion,
  restoreLocationCompliancePolicyVersion,
} from "@/lib/api/finance";

type PolicyScope = "business" | "location";

type DraftState = {
  minimumRestHours: string;
  maxDailyMinutes: string;
  maxWeeklyMinutes: string;
  requireStructuredBreakPlans: boolean;
  blockUnresolvedPremiums: boolean;
  disableWrittenConsent: boolean;
  disableMealWaivers: boolean;
  schoolDayWeekdays: string[];
  schoolDatesText: string;
  nonSchoolDatesText: string;
};

const WEEKDAY_OPTIONS = [
  { value: "monday", label: "Mon" },
  { value: "tuesday", label: "Tue" },
  { value: "wednesday", label: "Wed" },
  { value: "thursday", label: "Thu" },
  { value: "friday", label: "Fri" },
  { value: "saturday", label: "Sat" },
  { value: "sunday", label: "Sun" },
] as const;
const WEEKDAY_ORDER = WEEKDAY_OPTIONS.reduce<Record<string, number>>((accumulator, weekday, index) => {
  accumulator[weekday.value] = index;
  return accumulator;
}, {});

function normalizeDateList(values: string[] | null | undefined) {
  return [...new Set((values ?? [])
    .map((value) => value.trim())
    .filter(Boolean))]
    .sort();
}

function normalizeWeekdayList(values: string[] | null | undefined) {
  return [...new Set((values ?? [])
    .map((value) => value.trim().toLowerCase())
    .filter((value) => value in WEEKDAY_ORDER))]
    .sort((left, right) => WEEKDAY_ORDER[left] - WEEKDAY_ORDER[right]);
}

function parseDateListText(value: string) {
  return normalizeDateList(
    value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

function buildDraftState(
  currentPolicy: CompliancePolicySettingsSnapshot | null | undefined,
): DraftState {
  return {
    minimumRestHours:
      currentPolicy?.minimum_rest_hours != null
        ? String(currentPolicy.minimum_rest_hours)
        : "",
    maxDailyMinutes:
      currentPolicy?.max_daily_minutes != null
        ? String(currentPolicy.max_daily_minutes)
        : "",
    maxWeeklyMinutes:
      currentPolicy?.max_weekly_minutes != null
        ? String(currentPolicy.max_weekly_minutes)
        : "",
    requireStructuredBreakPlans: Boolean(
      currentPolicy?.require_structured_break_plans,
    ),
    blockUnresolvedPremiums: Boolean(
      currentPolicy?.block_unresolved_premiums,
    ),
    disableWrittenConsent: currentPolicy?.written_consent_allowed === false,
    disableMealWaivers:
      currentPolicy?.first_meal_waiver_allowed === false
      || currentPolicy?.second_meal_waiver_allowed === false,
    schoolDayWeekdays: normalizeWeekdayList(currentPolicy?.school_day_weekdays),
    schoolDatesText: normalizeDateList(currentPolicy?.school_dates).join(", "),
    nonSchoolDatesText: normalizeDateList(currentPolicy?.non_school_dates).join(", "),
  };
}

function draftToPolicyPayload(draft: DraftState): Record<string, unknown> {
  return {
    minimum_rest_hours: draft.minimumRestHours.trim()
      ? Number(draft.minimumRestHours)
      : null,
    max_daily_minutes: draft.maxDailyMinutes.trim()
      ? Number(draft.maxDailyMinutes)
      : null,
    max_weekly_minutes: draft.maxWeeklyMinutes.trim()
      ? Number(draft.maxWeeklyMinutes)
      : null,
    require_structured_break_plans: draft.requireStructuredBreakPlans,
    block_unresolved_premiums: draft.blockUnresolvedPremiums,
    written_consent_allowed: draft.disableWrittenConsent ? false : null,
    first_meal_waiver_allowed: draft.disableMealWaivers ? false : null,
    second_meal_waiver_allowed: draft.disableMealWaivers ? false : null,
    school_day_weekdays: normalizeWeekdayList(draft.schoolDayWeekdays),
    school_dates: parseDateListText(draft.schoolDatesText),
    non_school_dates: parseDateListText(draft.nonSchoolDatesText),
  };
}

function currentPolicyToPayload(
  currentPolicy: CompliancePolicySettingsSnapshot | null | undefined,
): Record<string, unknown> {
  return {
    minimum_rest_hours: currentPolicy?.minimum_rest_hours ?? null,
    max_daily_minutes: currentPolicy?.max_daily_minutes ?? null,
    max_weekly_minutes: currentPolicy?.max_weekly_minutes ?? null,
    require_structured_break_plans: Boolean(
      currentPolicy?.require_structured_break_plans,
    ),
    block_unresolved_premiums: Boolean(
      currentPolicy?.block_unresolved_premiums,
    ),
    written_consent_allowed: currentPolicy?.written_consent_allowed ?? null,
    first_meal_waiver_allowed: currentPolicy?.first_meal_waiver_allowed ?? null,
    second_meal_waiver_allowed: currentPolicy?.second_meal_waiver_allowed ?? null,
    school_day_weekdays: normalizeWeekdayList(currentPolicy?.school_day_weekdays),
    school_dates: normalizeDateList(currentPolicy?.school_dates),
    non_school_dates: normalizeDateList(currentPolicy?.non_school_dates),
  };
}

function payloadToSnapshot(
  payload: Record<string, unknown>,
): CompliancePolicySettingsSnapshot {
  return {
    minimum_rest_hours:
      typeof payload.minimum_rest_hours === "number"
        ? payload.minimum_rest_hours
        : null,
    written_consent_allowed:
      typeof payload.written_consent_allowed === "boolean"
        ? payload.written_consent_allowed
        : null,
    first_meal_waiver_allowed:
      typeof payload.first_meal_waiver_allowed === "boolean"
        ? payload.first_meal_waiver_allowed
        : null,
    second_meal_waiver_allowed:
      typeof payload.second_meal_waiver_allowed === "boolean"
        ? payload.second_meal_waiver_allowed
        : null,
    require_structured_break_plans: Boolean(
      payload.require_structured_break_plans,
    ),
    block_unresolved_premiums: Boolean(payload.block_unresolved_premiums),
    max_daily_minutes:
      typeof payload.max_daily_minutes === "number"
        ? payload.max_daily_minutes
        : null,
    max_weekly_minutes:
      typeof payload.max_weekly_minutes === "number"
        ? payload.max_weekly_minutes
        : null,
    school_day_weekdays: Array.isArray(payload.school_day_weekdays)
      ? normalizeWeekdayList(
          payload.school_day_weekdays.filter(
            (value): value is string => typeof value === "string",
          ),
        )
      : [],
    school_dates: Array.isArray(payload.school_dates)
      ? normalizeDateList(
          payload.school_dates.filter(
            (value): value is string => typeof value === "string",
          ),
        )
      : [],
    non_school_dates: Array.isArray(payload.non_school_dates)
      ? normalizeDateList(
          payload.non_school_dates.filter(
            (value): value is string => typeof value === "string",
          ),
        )
      : [],
  };
}

function toWeekStartDate(weekStartDay: string | null | undefined): string {
  const normalized = (weekStartDay ?? "monday").trim().toLowerCase();
  const dayIndex = {
    sunday: 0,
    monday: 1,
    tuesday: 2,
    wednesday: 3,
    thursday: 4,
    friday: 5,
    saturday: 6,
  }[normalized] ?? 1;
  const now = new Date();
  const localDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const offset = (localDate.getDay() - dayIndex + 7) % 7;
  localDate.setDate(localDate.getDate() - offset);
  const year = localDate.getFullYear();
  const month = String(localDate.getMonth() + 1).padStart(2, "0");
  const day = String(localDate.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatMoney(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

function formatSignedMoney(cents: number) {
  const prefix = cents > 0 ? "+" : cents < 0 ? "-" : "";
  return `${prefix}${formatMoney(Math.abs(cents))}`;
}

function formatSignedCount(value: number) {
  return value > 0 ? `+${value}` : String(value);
}

function summarizePolicy(policy: CompliancePolicySettingsSnapshot) {
  return [
    policy.minimum_rest_hours != null
      ? `Minimum rest hours: ${policy.minimum_rest_hours}`
      : null,
    policy.max_daily_minutes != null
      ? `Max daily minutes: ${policy.max_daily_minutes}`
      : null,
    policy.max_weekly_minutes != null
      ? `Max weekly minutes: ${policy.max_weekly_minutes}`
      : null,
    policy.require_structured_break_plans
      ? "Structured break plans required"
      : null,
    policy.block_unresolved_premiums
      ? "Unresolved premiums blocked"
      : null,
    policy.written_consent_allowed === false
      ? "Written consent disabled"
      : null,
    policy.first_meal_waiver_allowed === false
      || policy.second_meal_waiver_allowed === false
      ? "Meal waivers disabled"
      : null,
    policy.school_day_weekdays?.length
      ? `School weekdays: ${policy.school_day_weekdays.join(", ")}`
      : null,
    policy.school_dates?.length
      ? `Extra school dates: ${policy.school_dates.join(", ")}`
      : null,
    policy.non_school_dates?.length
      ? `Closed school dates: ${policy.non_school_dates.join(", ")}`
      : null,
  ].filter(Boolean) as string[];
}

function formatPolicyEffectiveAt(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function normalizeScheduledEffectiveAt(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) {
    return undefined;
  }
  return parsed.toISOString();
}

export function readCompliancePolicySnapshot(
  value: unknown,
): CompliancePolicySettingsSnapshot {
  const raw = value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
  return {
    minimum_rest_hours:
      typeof raw.minimum_rest_hours === "number"
        ? raw.minimum_rest_hours
        : null,
    written_consent_allowed:
      typeof raw.written_consent_allowed === "boolean"
        ? raw.written_consent_allowed
        : null,
    first_meal_waiver_allowed:
      typeof raw.first_meal_waiver_allowed === "boolean"
        ? raw.first_meal_waiver_allowed
        : null,
    second_meal_waiver_allowed:
      typeof raw.second_meal_waiver_allowed === "boolean"
        ? raw.second_meal_waiver_allowed
        : null,
    require_structured_break_plans: Boolean(raw.require_structured_break_plans),
    block_unresolved_premiums: Boolean(raw.block_unresolved_premiums),
    max_daily_minutes:
      typeof raw.max_daily_minutes === "number"
        ? raw.max_daily_minutes
        : null,
    max_weekly_minutes:
      typeof raw.max_weekly_minutes === "number"
        ? raw.max_weekly_minutes
        : null,
    school_day_weekdays: Array.isArray(raw.school_day_weekdays)
      ? normalizeWeekdayList(
          raw.school_day_weekdays.filter(
            (value): value is string => typeof value === "string",
          ),
        )
      : [],
    school_dates: Array.isArray(raw.school_dates)
      ? normalizeDateList(
          raw.school_dates.filter(
            (value): value is string => typeof value === "string",
          ),
        )
      : [],
    non_school_dates: Array.isArray(raw.non_school_dates)
      ? normalizeDateList(
          raw.non_school_dates.filter(
            (value): value is string => typeof value === "string",
          ),
        )
      : [],
  };
}

export default function CompliancePolicySettingsEditor({
  dark,
  businessId,
  scope,
  currentPolicy,
  weekStartDay,
  locationId,
  title,
  description,
  onApplied,
}: {
  dark: boolean;
  businessId: string;
  scope: PolicyScope;
  currentPolicy: CompliancePolicySettingsSnapshot;
  weekStartDay: string | null | undefined;
  locationId?: string;
  title: string;
  description: string;
  onApplied(nextPolicy: CompliancePolicySettingsSnapshot): void;
}) {
  const [draft, setDraft] = useState<DraftState>(() => buildDraftState(currentPolicy));
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [applying, setApplying] = useState(false);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [policyVersions, setPolicyVersions] = useState<CompliancePolicyVersion[]>([]);
  const [restoringVersionId, setRestoringVersionId] = useState<string | null>(null);
  const [replayingVersionId, setReplayingVersionId] = useState<string | null>(null);
  const [activationAtLocal, setActivationAtLocal] = useState("");
  const [weekReplay, setWeekReplay] = useState<{
    versionId: string;
    replay: LocationComplianceWeekReplay;
  } | null>(null);
  const [locationSimulation, setLocationSimulation] = useState<LocationCompliancePolicySimulation | null>(null);
  const [businessSimulation, setBusinessSimulation] = useState<BusinessCompliancePolicySimulation | null>(null);
  const [stalePolicy, setStalePolicy] = useState<{
    hash: string;
    settings: CompliancePolicySettingsSnapshot;
  } | null>(null);

  useEffect(() => {
    setDraft(buildDraftState(currentPolicy));
    setLocationSimulation(null);
    setBusinessSimulation(null);
    setStalePolicy(null);
    setWeekReplay(null);
    setActivationAtLocal("");
    setMessage((current) => (current?.tone === "success" ? current : null));
  }, [currentPolicy]);

  const desiredPayload = useMemo(() => draftToPolicyPayload(draft), [draft]);
  const baselinePayload = useMemo(
    () => currentPolicyToPayload(currentPolicy),
    [currentPolicy],
  );
  const hasChanges =
    JSON.stringify(desiredPayload) !== JSON.stringify(baselinePayload);
  const effectiveWeekStartDate = useMemo(
    () => toWeekStartDate(weekStartDay),
    [weekStartDay],
  );
  const currentChips = summarizePolicy(currentPolicy);
  const activeSimulation = scope === "business" ? businessSimulation : locationSimulation;
  const scheduledEffectiveAt = useMemo(
    () => normalizeScheduledEffectiveAt(activationAtLocal),
    [activationAtLocal],
  );
  const isScheduledActivation = useMemo(
    () => scheduledEffectiveAt != null && new Date(scheduledEffectiveAt).getTime() > Date.now(),
    [scheduledEffectiveAt],
  );
  const currentPolicyHash = useMemo(
    () => policyVersions.find((version) => version.is_effective)?.policy_hash
      ?? policyVersions[0]?.policy_hash
      ?? null,
    [policyVersions],
  );

  const cardSurface = dark
    ? "bg-white/[0.03] border border-white/[0.08]"
    : "bg-[#F7F8FA] border border-[#E5E7EB]";
  const innerSurface = dark ? "bg-white/[0.04]" : "bg-white";
  const textPrimary = dark ? "text-white" : "text-[#0A2540]";
  const textSecondary = dark ? "text-[#C1CED8]" : "text-[#5E6D7A]";

  useEffect(() => {
    if (hasChanges && message?.tone === "success") {
      setMessage(null);
    }
  }, [hasChanges, message]);

  async function loadPolicyVersions() {
    setLoadingVersions(true);
    try {
      if (scope === "business") {
        setPolicyVersions(await getBusinessCompliancePolicyVersions(businessId, 6));
        return;
      }
      if (!locationId) {
        setPolicyVersions([]);
        return;
      }
      setPolicyVersions(
        await getLocationCompliancePolicyVersions(businessId, locationId, 6),
      );
    } finally {
      setLoadingVersions(false);
    }
  }

  useEffect(() => {
    void loadPolicyVersions();
  }, [businessId, locationId, scope]);

  async function handlePreview() {
    if (!hasChanges) {
      return;
    }
    setLoadingPreview(true);
    setMessage(null);
    setStalePolicy(null);
    try {
      if (scope === "business") {
        const payload = await simulateBusinessCompliancePolicy(
          businessId,
          effectiveWeekStartDate,
          {
            week_count: 6,
            compliance: desiredPayload,
          },
        );
        if (!payload) {
          setMessage({
            tone: "error",
            text: "Backfill could not preview this business compliance policy right now.",
          });
          return;
        }
        setBusinessSimulation(payload);
        setLocationSimulation(null);
      } else {
        if (!locationId) {
          setMessage({ tone: "error", text: "Location policy preview requires a location." });
          return;
        }
        const payload = await simulateLocationCompliancePolicy(
          businessId,
          locationId,
          effectiveWeekStartDate,
          {
            week_count: 6,
            compliance: desiredPayload,
          },
        );
        if (!payload) {
          setMessage({
            tone: "error",
            text: "Backfill could not preview this location compliance policy right now.",
          });
          return;
        }
        setLocationSimulation(payload);
        setBusinessSimulation(null);
      }
    } finally {
      setLoadingPreview(false);
    }
  }

  async function handleApply() {
    if (!activeSimulation) {
      return;
    }
    setApplying(true);
    setMessage(null);
    setStalePolicy(null);
    try {
      if (scope === "business") {
        const simulation = activeSimulation as BusinessCompliancePolicySimulation;
        const result = await applySimulatedBusinessCompliancePolicy(
          businessId,
          {
            expected_compliance_policy_hash:
              simulation.baseline_business_compliance_policy_hash,
            compliance: simulation.proposed_business_compliance_settings,
            effective_at: scheduledEffectiveAt,
          },
        );
        if (!result.ok) {
          if (result.reason === "stale_preview") {
            setStalePolicy({
              hash: result.current_compliance_policy_hash,
              settings: result.current_compliance_settings,
            });
            setMessage({
              tone: "error",
              text: "Business preview is stale. Rerun the preview before applying.",
            });
            return;
          }
          setMessage({ tone: "error", text: result.message });
          return;
        }
        if (!isScheduledActivation) {
          const nextPolicy = payloadToSnapshot(
            simulation.proposed_business_compliance_settings as Record<string, unknown>,
          );
          onApplied(nextPolicy);
        }
        await loadPolicyVersions();
        setActivationAtLocal("");
        setMessage({
          tone: "success",
          text: isScheduledActivation
            ? "Business compliance policy scheduled."
            : "Business compliance policy updated.",
        });
        return;
      }

      if (!locationId) {
        setMessage({ tone: "error", text: "Location policy apply requires a location." });
        return;
      }
      const simulation = activeSimulation as LocationCompliancePolicySimulation;
      const result = await applySimulatedLocationCompliancePolicy(
        businessId,
        locationId,
        {
          expected_compliance_policy_hash:
            simulation.baseline_location_compliance_policy_hash,
          compliance: simulation.proposed_location_compliance_settings,
          effective_at: scheduledEffectiveAt,
        },
      );
      if (!result.ok) {
        if (result.reason === "stale_preview") {
          setStalePolicy({
            hash: result.current_compliance_policy_hash,
            settings: result.current_compliance_settings,
          });
          setMessage({
            tone: "error",
            text: "Location preview is stale. Rerun the preview before applying.",
          });
          return;
        }
        setMessage({ tone: "error", text: result.message });
        return;
      }
      if (!isScheduledActivation) {
        const nextPolicy = payloadToSnapshot(
          simulation.proposed_location_compliance_settings as Record<string, unknown>,
        );
        onApplied(nextPolicy);
      }
      await loadPolicyVersions();
      setActivationAtLocal("");
      setMessage({
        tone: "success",
        text: isScheduledActivation
          ? "Location compliance policy scheduled."
          : "Location compliance policy updated.",
      });
    } finally {
      setApplying(false);
    }
  }

  function resetDraft() {
    setDraft(buildDraftState(currentPolicy));
    setLocationSimulation(null);
    setBusinessSimulation(null);
    setStalePolicy(null);
    setWeekReplay(null);
    setMessage(null);
  }

  async function handleRestoreVersion(version: CompliancePolicyVersion) {
    if (version.is_effective) {
      return;
    }
    setRestoringVersionId(version.id);
    setMessage(null);
    setStalePolicy(null);
    try {
      const result = scope === "business"
        ? await restoreBusinessCompliancePolicyVersion(
            businessId,
            version.id,
            {
              expected_current_policy_hash: currentPolicyHash ?? undefined,
              effective_at: scheduledEffectiveAt,
            },
          )
        : locationId
          ? await restoreLocationCompliancePolicyVersion(
              businessId,
              locationId,
              version.id,
              {
                expected_current_policy_hash: currentPolicyHash ?? undefined,
                effective_at: scheduledEffectiveAt,
              },
            )
          : {
              ok: false as const,
              reason: "request_failed" as const,
              message: "Location restore requires a location.",
            };
      if (!result.ok) {
        if (result.reason === "stale_preview") {
          setStalePolicy({
            hash: result.current_compliance_policy_hash,
            settings: result.current_compliance_settings,
          });
          setMessage({
            tone: "error",
            text: "Policy history is stale. Refresh and try the restore again.",
          });
          return;
        }
        setMessage({ tone: "error", text: result.message });
        return;
      }
      if (!isScheduledActivation) {
        onApplied(result.version.settings);
        setDraft(buildDraftState(result.version.settings));
      }
      setLocationSimulation(null);
      setBusinessSimulation(null);
      setWeekReplay(null);
      await loadPolicyVersions();
      setActivationAtLocal("");
      setMessage({
        tone: "success",
        text: isScheduledActivation
          ? scope === "business"
            ? "Business compliance policy restore scheduled."
            : "Location compliance policy restore scheduled."
          : scope === "business"
            ? "Business compliance policy restored."
            : "Location compliance policy restored.",
      });
    } finally {
      setRestoringVersionId(null);
    }
  }

  async function handleReplayVersion(version: CompliancePolicyVersion) {
    if (scope !== "location" || !locationId) {
      return;
    }
    setReplayingVersionId(version.id);
    setMessage(null);
    try {
      const replay = await replayLocationCompliancePolicyVersion(
        businessId,
        locationId,
        effectiveWeekStartDate,
        version.id,
      );
      if (!replay) {
        setMessage({
          tone: "error",
          text: "Backfill could not replay this policy against the selected week.",
        });
        return;
      }
      setWeekReplay({ versionId: version.id, replay });
    } finally {
      setReplayingVersionId(null);
    }
  }

  return (
    <div className={`rounded-2xl px-4 py-4 ${cardSurface}`}>
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 580 }}>
            {title}
          </p>
          <p className={`mt-1 text-[11px] ${textSecondary}`} style={{ fontWeight: 430 }}>
            {description}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={resetDraft}
            className={`rounded-xl border px-3 py-2 text-[11px] transition-colors ${dark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]" : "border-[#E5E7EB] text-[#5E6D7A] hover:bg-white"}`}
            style={{ fontWeight: 500 }}
          >
            Reset
          </button>
          <button
            type="button"
            disabled={!hasChanges || loadingPreview}
            onClick={() => {
              void handlePreview();
            }}
            className={`rounded-xl px-3 py-2 text-[11px] text-white transition-all ${hasChanges ? "" : "opacity-50"} ${dark ? "bg-[#635BFF] hover:bg-[#726BFF]" : "bg-[#0A2540] hover:bg-[#163A5B]"}`}
            style={{ fontWeight: 540 }}
          >
            {loadingPreview ? "Running Preview" : "Run Preview"}
          </button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {currentChips.length ? currentChips.map((chip) => (
          <span
            key={chip}
            className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.08] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"}`}
            style={{ fontWeight: 500 }}
          >
            {chip}
          </span>
        )) : (
          <span
            className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.08] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"}`}
            style={{ fontWeight: 500 }}
          >
            No stricter-than-law policy overlay is set.
          </span>
        )}
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <label className="space-y-1">
          <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
            Minimum Rest Hours
          </span>
          <input
            type="number"
            min={0}
            step="0.5"
            value={draft.minimumRestHours}
            onChange={(event) =>
              setDraft((current) => ({ ...current, minimumRestHours: event.target.value }))
            }
            className={`w-full rounded-xl border px-3 py-2 text-[12px] outline-none ${dark ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8FA3B5]" : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#9CA3AF]"}`}
            placeholder="e.g. 12"
          />
        </label>
        <label className="space-y-1">
          <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
            Max Daily Minutes
          </span>
          <input
            type="number"
            min={0}
            step="1"
            value={draft.maxDailyMinutes}
            onChange={(event) =>
              setDraft((current) => ({ ...current, maxDailyMinutes: event.target.value }))
            }
            className={`w-full rounded-xl border px-3 py-2 text-[12px] outline-none ${dark ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8FA3B5]" : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#9CA3AF]"}`}
            placeholder="e.g. 480"
          />
        </label>
        <label className="space-y-1">
          <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
            Max Weekly Minutes
          </span>
          <input
            type="number"
            min={0}
            step="1"
            value={draft.maxWeeklyMinutes}
            onChange={(event) =>
              setDraft((current) => ({ ...current, maxWeeklyMinutes: event.target.value }))
            }
            className={`w-full rounded-xl border px-3 py-2 text-[12px] outline-none ${dark ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8FA3B5]" : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#9CA3AF]"}`}
            placeholder="e.g. 2400"
          />
        </label>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <div className="space-y-2">
          <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
            School Day Weekdays
          </span>
          <div className="grid grid-cols-4 gap-2">
            {WEEKDAY_OPTIONS.map((weekday) => {
              const checked = draft.schoolDayWeekdays.includes(weekday.value);
              return (
                <label
                  key={weekday.value}
                  className={`flex items-center justify-center gap-2 rounded-xl px-3 py-2 ${innerSurface}`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        schoolDayWeekdays: event.target.checked
                          ? [...current.schoolDayWeekdays, weekday.value]
                          : current.schoolDayWeekdays.filter((value) => value !== weekday.value),
                      }))
                    }
                  />
                  <span className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 500 }}>
                    {weekday.label}
                  </span>
                </label>
              );
            })}
          </div>
          <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
            Used for school-day minor limits when an employee is marked in session.
          </p>
        </div>

        <div className="grid gap-3">
          <label className="space-y-1">
            <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
              Extra School Dates
            </span>
            <input
              type="text"
              value={draft.schoolDatesText}
              onChange={(event) =>
                setDraft((current) => ({ ...current, schoolDatesText: event.target.value }))
              }
              className={`w-full rounded-xl border px-3 py-2 text-[12px] outline-none ${dark ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8FA3B5]" : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#9CA3AF]"}`}
              placeholder="YYYY-MM-DD, YYYY-MM-DD"
            />
          </label>
          <label className="space-y-1">
            <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
              Non-School Dates
            </span>
            <input
              type="text"
              value={draft.nonSchoolDatesText}
              onChange={(event) =>
                setDraft((current) => ({ ...current, nonSchoolDatesText: event.target.value }))
              }
              className={`w-full rounded-xl border px-3 py-2 text-[12px] outline-none ${dark ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8FA3B5]" : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#9CA3AF]"}`}
              placeholder="YYYY-MM-DD, YYYY-MM-DD"
            />
          </label>
        </div>
      </div>

      <label className="mt-4 block space-y-1">
        <span className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
          Activation Time
        </span>
        <input
          type="datetime-local"
          value={activationAtLocal}
          onChange={(event) => setActivationAtLocal(event.target.value)}
          className={`w-full rounded-xl border px-3 py-2 text-[12px] outline-none ${dark ? "border-white/[0.08] bg-white/[0.04] text-white placeholder:text-[#8FA3B5]" : "border-[#E5E7EB] bg-white text-[#0A2540] placeholder:text-[#9CA3AF]"}`}
        />
        <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
          Leave blank to activate immediately. Set a future time to schedule a promotion or restore.
        </p>
      </label>

      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {[
          {
            key: "requireStructuredBreakPlans",
            label: "Require Structured Break Plans",
          },
          {
            key: "blockUnresolvedPremiums",
            label: "Block Unresolved Premiums",
          },
          {
            key: "disableWrittenConsent",
            label: "Disable Written Consent",
          },
          {
            key: "disableMealWaivers",
            label: "Disable Meal Waivers",
          },
        ].map((item) => (
          <label
            key={item.key}
            className={`flex items-center gap-2 rounded-xl px-3 py-2 ${innerSurface}`}
          >
            <input
              type="checkbox"
              checked={Boolean(draft[item.key as keyof DraftState])}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  [item.key]: event.target.checked,
                }))
              }
            />
            <span className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 500 }}>
              {item.label}
            </span>
          </label>
        ))}
      </div>

      {message ? (
        <div
          className="mt-4 rounded-xl px-3 py-3 text-[11px]"
          style={{
            background:
              message.tone === "success"
                ? "rgba(0, 184, 147, 0.08)"
                : "rgba(229, 72, 77, 0.08)",
            color: message.tone === "success" ? "#067A64" : "#C13535",
            fontWeight: 500,
          }}
        >
          {message.text}
        </div>
      ) : null}

      {stalePolicy ? (
        <div className={`mt-4 rounded-xl border px-3 py-3 ${dark ? "border-[#F59E0B]/30 bg-[#F59E0B]/10" : "border-[#FDE68A] bg-[#FFFBEB]"}`}>
          <div className="flex items-start gap-2">
            <AlertTriangle size={14} className="mt-0.5 text-[#F59E0B]" />
            <div>
              <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                Persisted policy changed after preview
              </p>
              <p className={`mt-1 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                Current policy hash: {stalePolicy.hash.slice(0, 10)}
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {summarizePolicy(stalePolicy.settings).map((chip) => (
              <span
                key={chip}
                className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.08] text-[#C1CED8]" : "bg-white text-[#5E6D7A]"}`}
                style={{ fontWeight: 500 }}
              >
                {chip}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className={`mt-4 rounded-xl px-3 py-3 ${innerSurface}`}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
              Policy Version History
            </p>
            <p className={`mt-1 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
              Promote or roll back a previously reviewed policy version.
            </p>
          </div>
          {loadingVersions ? (
            <span className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 500 }}>
              Loading
            </span>
          ) : null}
        </div>
        <div className="mt-3 space-y-2">
          {policyVersions.length ? policyVersions.map((version) => {
            const chips = summarizePolicy(version.settings);
            const statusLabel = version.is_effective
              ? "Effective"
              : version.is_scheduled
                ? "Scheduled"
                : "Historical";
            return (
              <div
                key={version.id}
                className={`rounded-xl border px-3 py-3 ${dark ? "border-white/[0.08] bg-white/[0.03]" : "border-[#E5E7EB] bg-white"}`}
              >
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                        {statusLabel}
                      </p>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[9px] ${version.is_effective ? "bg-[#00B893]/10 text-[#067A64]" : version.is_scheduled ? "bg-[#F59E0B]/10 text-[#B45309]" : dark ? "bg-white/[0.08] text-[#C1CED8]" : "bg-[#EEF2F7] text-[#5E6D7A]"}`}
                        style={{ fontWeight: 600 }}
                      >
                        {version.policy_hash.slice(0, 8)}
                      </span>
                    </div>
                    <p className={`mt-1 text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                      Effective {formatPolicyEffectiveAt(version.effective_at)}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {chips.length ? chips.map((chip) => (
                        <span
                          key={`${version.id}-${chip}`}
                          className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.08] text-[#C1CED8]" : "bg-[#F7F8FA] text-[#5E6D7A]"}`}
                          style={{ fontWeight: 500 }}
                        >
                          {chip}
                        </span>
                      )) : (
                        <span
                          className={`rounded-full px-2.5 py-1 text-[10px] ${dark ? "bg-white/[0.08] text-[#C1CED8]" : "bg-[#F7F8FA] text-[#5E6D7A]"}`}
                          style={{ fontWeight: 500 }}
                        >
                          Clears stricter-than-law policy overlay
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center justify-end">
                    <button
                      type="button"
                      disabled={version.is_effective || restoringVersionId === version.id}
                      onClick={() => {
                        void handleRestoreVersion(version);
                      }}
                      className={`rounded-xl border px-3 py-2 text-[10px] transition-colors ${version.is_effective ? "opacity-50" : ""} ${dark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]" : "border-[#D0D7DE] text-[#0A2540] hover:bg-[#F7F8FA]"}`}
                      style={{ fontWeight: 560 }}
                    >
                      {restoringVersionId === version.id ? "Restoring" : "Restore Now"}
                    </button>
                    {scope === "location" ? (
                      <button
                        type="button"
                        disabled={replayingVersionId === version.id}
                        onClick={() => {
                          void handleReplayVersion(version);
                        }}
                        className={`ml-2 rounded-xl border px-3 py-2 text-[10px] transition-colors ${dark ? "border-white/[0.08] text-[#C1CED8] hover:bg-white/[0.04]" : "border-[#D0D7DE] text-[#0A2540] hover:bg-[#F7F8FA]"}`}
                        style={{ fontWeight: 560 }}
                      >
                        {replayingVersionId === version.id ? "Replaying" : "Replay Week"}
                      </button>
                    ) : null}
                  </div>
                </div>
                {weekReplay?.versionId === version.id ? (
                  <div className={`mt-3 rounded-xl px-3 py-3 ${dark ? "bg-white/[0.04]" : "bg-[#F7F8FA]"}`}>
                    <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                      Week Replay for {effectiveWeekStartDate}
                    </p>
                    <div className="mt-3 grid gap-3 md:grid-cols-4">
                      <div>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Premium Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${weekReplay.replay.delta.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedMoney(weekReplay.replay.delta.premium_total_cents_delta)}
                        </p>
                      </div>
                      <div>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Block Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${weekReplay.replay.delta.blocked_assignment_count_delta > 0 ? "text-[#EF4444]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(weekReplay.replay.delta.blocked_assignment_count_delta)}
                        </p>
                      </div>
                      <div>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Warning Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(weekReplay.replay.delta.warning_assignment_count_delta)}
                        </p>
                      </div>
                      <div>
                        <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                          Unresolved Delta
                        </p>
                        <p className={`mt-1 text-[14px] ${weekReplay.replay.delta.unresolved_premium_assignment_count_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                          {formatSignedCount(weekReplay.replay.delta.unresolved_premium_assignment_count_delta)}
                        </p>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          }) : (
            <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
              No compliance policy history is available yet.
            </p>
          )}
        </div>
      </div>

      {activeSimulation ? (
        <div className="mt-4 space-y-3">
          <div className="grid gap-3 md:grid-cols-4">
            <div className={`rounded-xl px-3 py-3 ${innerSurface}`}>
              <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                Premium Delta
              </p>
              <p className={`mt-1 text-[15px] ${activeSimulation.delta.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                {formatSignedMoney(activeSimulation.delta.premium_total_cents_delta)}
              </p>
            </div>
            <div className={`rounded-xl px-3 py-3 ${innerSurface}`}>
              <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                Block Delta
              </p>
              <p className={`mt-1 text-[15px] ${activeSimulation.delta.blocked_assignment_count_delta > 0 ? "text-[#EF4444]" : textPrimary}`} style={{ fontWeight: 620 }}>
                {formatSignedCount(activeSimulation.delta.blocked_assignment_count_delta)}
              </p>
            </div>
            <div className={`rounded-xl px-3 py-3 ${innerSurface}`}>
              <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                Unresolved Delta
              </p>
              <p className={`mt-1 text-[15px] ${activeSimulation.delta.unresolved_premium_assignment_count_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                {formatSignedCount(activeSimulation.delta.unresolved_premium_assignment_count_delta)}
              </p>
            </div>
            <div className={`rounded-xl px-3 py-3 ${innerSurface}`}>
              <p className={`text-[10px] uppercase tracking-[0.04em] ${textSecondary}`} style={{ fontWeight: 520 }}>
                Override Delta
              </p>
              <p className={`mt-1 text-[15px] ${activeSimulation.delta.override_applied_count_delta < 0 ? "text-[#EF4444]" : textPrimary}`} style={{ fontWeight: 620 }}>
                {formatSignedCount(activeSimulation.delta.override_applied_count_delta)}
              </p>
            </div>
          </div>

          {"location_count" in activeSimulation ? (
            <div className={`rounded-xl px-3 py-3 ${innerSurface}`}>
              <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                Location Impact
              </p>
              <div className="mt-3 space-y-2">
                {activeSimulation.location_deltas.length ? activeSimulation.location_deltas.map((row) => (
                  <div key={row.location_id} className="flex items-center justify-between gap-3">
                    <div>
                      <p className={`text-[10px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                        {row.location_name}
                      </p>
                      <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                        {formatSignedCount(row.blocked_assignment_count_delta)} blocks · {formatSignedCount(row.unresolved_premium_assignment_count_delta)} unresolved
                      </p>
                    </div>
                    <p className={`text-[11px] ${row.premium_total_cents_delta > 0 ? "text-[#F59E0B]" : textPrimary}`} style={{ fontWeight: 620 }}>
                      {formatSignedMoney(row.premium_total_cents_delta)}
                    </p>
                  </div>
                )) : (
                  <p className={`text-[10px] ${textSecondary}`} style={{ fontWeight: 430 }}>
                    No active locations are materially affected by this change.
                  </p>
                )}
              </div>
            </div>
          ) : (
            <div className={`rounded-xl px-3 py-3 ${innerSurface}`}>
              <div className="flex items-center gap-2">
                <Check size={14} className="text-[#00B893]" />
                <p className={`text-[11px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                  Preview Hash: {(activeSimulation as LocationCompliancePolicySimulation).baseline_location_compliance_policy_hash.slice(0, 10)}
                </p>
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="button"
              disabled={applying}
              onClick={() => {
                void handleApply();
              }}
              className={`rounded-xl px-3 py-2 text-[11px] text-white transition-all ${dark ? "bg-[#635BFF] hover:bg-[#726BFF]" : "bg-[#0A2540] hover:bg-[#163A5B]"}`}
              style={{ fontWeight: 540 }}
            >
              {applying
                ? "Applying Policy"
                : scope === "business"
                  ? "Apply As Business Default"
                  : "Apply To Location Policy"}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
