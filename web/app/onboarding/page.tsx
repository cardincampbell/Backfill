"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE_URL, apiFetch } from "@/lib/api/client";
import {
  clearStoredPreviewPhone,
  getStoredPreviewPhone,
} from "@/lib/auth/preview";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";

// ── Types ───────────────────────────────────────────────────────────────────

type StepId = "name" | "business" | "role" | "locations" | "sites" | "staff" | "scheduler";

interface FormState {
  name: string;
  business: string;
  role: string;
  locationCount: number;
  locationNames: string[];
  staffBand: string;
  scheduler: string;
}

// ── Constants ───────────────────────────────────────────────────────────────

const STEPS: StepId[] = ["name", "business", "role", "locations", "sites", "staff", "scheduler"];

const ROLES = ["Owner", "General Manager", "Ops Manager", "HR", "Other"];

const STAFF_BANDS = ["Under 15", "15–30", "31–60", "61–100", "100+"];

const SCHEDULERS = ["7shifts", "Deputy", "When I Work", "Homebase", "We don't use one"];

const SCHEDULER_VALUES: Record<string, string> = {
  "7shifts": "7shifts",
  "Deputy": "deputy",
  "When I Work": "wheniwork",
  "Homebase": "homebase",
  "We don't use one": "backfill_native",
};

const STAFF_BAND_VALUES: Record<string, number> = {
  "Under 15": 10,
  "15–30": 22,
  "31–60": 45,
  "61–100": 80,
  "100+": 150,
};

// ── Main component ───────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter();
  const [stepIndex, setStepIndex] = useState(0);
  const [direction, setDirection] = useState<"forward" | "back">("forward");
  const [form, setForm] = useState<FormState>({
    name: "",
    business: "",
    role: "",
    locationCount: 1,
    locationNames: [""],
    staffBand: "",
    scheduler: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const currentStep = STEPS[stepIndex];
  const progress = ((stepIndex + 1) / STEPS.length) * 100;
  const isLast = stepIndex === STEPS.length - 1;

  function canAdvance(): boolean {
    switch (currentStep) {
      case "name": return form.name.trim().length > 0;
      case "business": return form.business.trim().length > 0;
      case "role": return form.role.length > 0;
      case "locations": return form.locationCount >= 1;
      case "sites": return form.locationNames.some((name) => name.trim().length > 0);
      case "staff": return form.staffBand.length > 0;
      case "scheduler": return form.scheduler.length > 0;
    }
  }

  function updateLocationCount(nextCount: number) {
    setForm((f) => {
      const normalizedCount = Math.max(1, nextCount);
      const nextNames = f.locationNames.slice(0, Math.max(1, normalizedCount));
      return {
        ...f,
        locationCount: normalizedCount,
        locationNames: nextNames.length ? nextNames : [""],
      };
    });
  }

  function updateLocationName(index: number, value: string) {
    setForm((f) => {
      const nextNames = [...f.locationNames];
      nextNames[index] = value;
      return { ...f, locationNames: nextNames };
    });
  }

  function addLocationField() {
    setForm((f) => {
      if (f.locationNames.length >= f.locationCount) {
        return f;
      }
      return { ...f, locationNames: [...f.locationNames, ""] };
    });
  }

  function removeLocationField(index: number) {
    setForm((f) => {
      if (f.locationNames.length <= 1) {
        return f;
      }
      const nextNames = f.locationNames.filter((_, i) => i !== index);
      return { ...f, locationNames: nextNames.length ? nextNames : [""] };
    });
  }

  function goForward() {
    if (!canAdvance() || submitting) return;
    if (isLast) {
      void submit();
    } else {
      setDirection("forward");
      setStepIndex((i) => i + 1);
      setError("");
    }
  }

  function goBack() {
    if (stepIndex === 0) return;
    setDirection("back");
    setStepIndex((i) => i - 1);
    setError("");
  }

  async function submit() {
    setSubmitting(true);
    setError("");
    try {
      const schedulerValue = SCHEDULER_VALUES[form.scheduler] ?? "backfill_native";
      const previewPhone = getStoredPreviewPhone();
      const namedLocations = form.locationNames
        .map((name) => name.trim())
        .filter(Boolean);

      if (namedLocations.length === 0) {
        throw new Error("Add at least one location to continue");
      }

      const primaryResponse = await apiFetch(`${API_BASE_URL}/api/locations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: namedLocations[0],
          organization_name: form.business.trim(),
          manager_name: form.name.trim(),
          manager_phone: previewPhone ?? undefined,
          employee_count: STAFF_BAND_VALUES[form.staffBand] ?? undefined,
          scheduling_platform: schedulerValue,
          operating_mode: schedulerValue === "backfill_native" ? "backfill_shifts" : "integration",
          backfill_shifts_enabled: true,
          backfill_shifts_launch_state: "enabled",
          onboarding_info: [
            `Role: ${form.role}`,
            `Locations: ${form.locationCount}`,
            `Named locations: ${namedLocations.length}`,
            `Staff band: ${form.staffBand}`,
            schedulerValue === "backfill_native" ? "Scheduler: none" : `Scheduler: ${form.scheduler}`,
          ].join(" · "),
        }),
      });

      if (!primaryResponse.ok) {
        const payload = await primaryResponse.json().catch(() => null);
        throw new Error(payload?.detail ?? "Could not finish onboarding");
      }

      const location = (await primaryResponse.json()) as {
        id: number;
        name: string;
        organization_id?: number | null;
        organization_name?: string | null;
      };

      const additionalLocations = namedLocations.slice(1);

      if (additionalLocations.length > 0) {
        await Promise.allSettled(
          additionalLocations.map((locationName) =>
            apiFetch(`${API_BASE_URL}/api/locations`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                name: locationName,
                organization_id: location.organization_id ?? undefined,
                organization_name: location.organization_id ? undefined : form.business.trim(),
                manager_name: form.name.trim(),
                manager_phone: previewPhone ?? undefined,
                employee_count: STAFF_BAND_VALUES[form.staffBand] ?? undefined,
                scheduling_platform: schedulerValue,
                operating_mode: schedulerValue === "backfill_native" ? "backfill_shifts" : "integration",
                backfill_shifts_enabled: true,
                backfill_shifts_launch_state: "enabled",
                onboarding_info: [
                  `Role: ${form.role}`,
                  `Locations: ${form.locationCount}`,
                  `Named locations: ${namedLocations.length}`,
                  `Staff band: ${form.staffBand}`,
                  schedulerValue === "backfill_native" ? "Scheduler: none" : `Scheduler: ${form.scheduler}`,
                ].join(" · "),
              }),
            }),
          ),
        );
      }

      clearStoredPreviewPhone();
      router.replace(
        buildDashboardLocationPath(location, { tab: "schedule" }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish onboarding");
      setSubmitting(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") goForward();
  }

  const slideClass = direction === "forward" ? "ob-slide" : "ob-slide-back";

  return (
    <main className="lp-onboarding">
      <div className="ob-card">
        {/* Header */}
        <div className="ob-header">
          <a href="/" className="ob-logo">Backfill</a>
          <span className="ob-step-label">Step {stepIndex + 1} of {STEPS.length}</span>
        </div>

        {/* Progress bar */}
        <div className="ob-progress-bar">
          <div className="ob-progress-fill" style={{ width: `${progress}%` }} />
        </div>

        {/* Step content */}
        <div className="ob-body" key={currentStep} style={{ animation: `${direction === "forward" ? "ob-slide-in" : "ob-slide-in-back"} 0.28s cubic-bezier(0.4,0,0.2,1)` }}>
          {currentStep === "name" && (
            <>
              <p className="ob-question">What&rsquo;s your name?</p>
              <input
                className="ob-input"
                type="text"
                placeholder="Your first and last name"
                autoFocus
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                onKeyDown={handleKey}
                autoComplete="name"
              />
            </>
          )}

          {currentStep === "business" && (
            <>
              <p className="ob-question">What&rsquo;s your restaurant or business called?</p>
              <input
                className="ob-input"
                type="text"
                placeholder="e.g. The Corner Café"
                autoFocus
                value={form.business}
                onChange={(e) => setForm((f) => ({ ...f, business: e.target.value }))}
                onKeyDown={handleKey}
                autoComplete="organization"
              />
            </>
          )}

          {currentStep === "role" && (
            <>
              <p className="ob-question">What&rsquo;s your role?</p>
              <p className="ob-sub">We&rsquo;ll tailor your experience to how you operate.</p>
              <div className="ob-chip-group">
                {ROLES.map((r) => (
                  <button
                    key={r}
                    className={`ob-chip${form.role === r ? " selected" : ""}`}
                    onClick={() => setForm((f) => ({ ...f, role: r }))}
                    type="button"
                  >
                    {r}
                  </button>
                ))}
              </div>
            </>
          )}

          {currentStep === "locations" && (
            <>
              <p className="ob-question">How many locations do you manage?</p>
              <p className="ob-sub">Include all sites where you&rsquo;d use Backfill.</p>
              <div className="ob-stepper">
                <button
                  className="ob-stepper-btn"
                  onClick={() => updateLocationCount(form.locationCount - 1)}
                  disabled={form.locationCount <= 1}
                  type="button"
                  aria-label="Decrease"
                >
                  −
                </button>
                <span className="ob-stepper-value">{form.locationCount}</span>
                <button
                  className="ob-stepper-btn"
                  onClick={() => updateLocationCount(form.locationCount + 1)}
                  type="button"
                  aria-label="Increase"
                >
                  +
                </button>
              </div>
            </>
          )}

          {currentStep === "sites" && (
            <>
              <p className="ob-question">What are your locations called?</p>
              <p className="ob-sub">
                Add at least one location now. You said you manage {form.locationCount} {form.locationCount === 1 ? "location" : "locations"}.
              </p>
              <div className="ob-locations">
                {form.locationNames.map((locationName, index) => (
                  <div key={index} className="ob-location-row">
                    <input
                      className="ob-input"
                      type="text"
                      placeholder={index === 0 ? "e.g. Mission District" : `Location ${index + 1}`}
                      autoFocus={index === 0}
                      value={locationName}
                      onChange={(e) => updateLocationName(index, e.target.value)}
                      onKeyDown={handleKey}
                    />
                    {form.locationNames.length > 1 ? (
                      <button
                        className="ob-location-remove"
                        type="button"
                        onClick={() => removeLocationField(index)}
                        aria-label={`Remove location ${index + 1}`}
                      >
                        ×
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
              <div className="ob-location-actions">
                <button
                  className="ob-location-add"
                  type="button"
                  onClick={addLocationField}
                  disabled={form.locationNames.length >= form.locationCount}
                >
                  + Add another location
                </button>
                <span className="ob-location-count">
                  {form.locationNames.filter((name) => name.trim().length > 0).length} of {form.locationCount} named
                </span>
              </div>
            </>
          )}

          {currentStep === "staff" && (
            <>
              <p className="ob-question">How many staff do you have per location?</p>
              <div className="ob-chip-group">
                {STAFF_BANDS.map((b) => (
                  <button
                    key={b}
                    className={`ob-chip${form.staffBand === b ? " selected" : ""}`}
                    onClick={() => setForm((f) => ({ ...f, staffBand: b }))}
                    type="button"
                  >
                    {b}
                  </button>
                ))}
              </div>
            </>
          )}

          {currentStep === "scheduler" && (
            <>
              <p className="ob-question">Which scheduling platform do you use?</p>
              <p className="ob-sub">Backfill connects directly to sync your shifts and roster.</p>
              <div className="ob-chip-group">
                {SCHEDULERS.map((s) => (
                  <button
                    key={s}
                    className={`ob-chip${form.scheduler === s ? " selected" : ""}`}
                    onClick={() => setForm((f) => ({ ...f, scheduler: s }))}
                    type="button"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </>
          )}

          {error && <p className="ob-error">{error}</p>}
        </div>

        {/* Footer */}
        <div className="ob-footer">
          {stepIndex > 0 ? (
            <button className="ob-btn-back" onClick={goBack} type="button">
              Back
            </button>
          ) : (
            <span />
          )}
          <button
            className="ob-btn-next"
            onClick={goForward}
            disabled={!canAdvance() || submitting}
            type="button"
          >
            {isLast ? (submitting ? "Starting..." : "Get started") : "Continue"}
          </button>
        </div>
      </div>
    </main>
  );
}
