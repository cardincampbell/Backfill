"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { PlaceAutocomplete } from "@/components/place-autocomplete";
import type { PlaceSuggestion } from "@/lib/api/places";
import {
  bootstrapOwnerWorkspace,
  completeOnboardingProfile,
  getAuthMe,
  getManagerInvitePreview,
  requestManagerInviteChallenge,
  type AuthMeResponse,
  type ManagerInvitePreview,
  verifyChallenge,
} from "@/lib/api/auth";
import { useOtpCooldown } from "@/lib/auth/use-otp-cooldown";
import { buildLocationPayloadFromPlace } from "@/lib/place-location";
import { inferOrganizationName } from "@/lib/place-location";

type InviteStep = "identity" | "code" | "profile";
type OwnerStep = "name" | "email" | "location";

const OWNER_STEPS: OwnerStep[] = ["name", "email", "location"];

function inThirtySeconds(): string {
  return new Date(Date.now() + 30_000).toISOString();
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function OnboardingBody() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get("invite")?.trim() || null;
  const isInviteFlow = Boolean(inviteToken);

  const [checkingSession, setCheckingSession] = useState(true);
  const [session, setSession] = useState<AuthMeResponse | null>(null);
  const [invitePreview, setInvitePreview] = useState<ManagerInvitePreview | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [inviteStep, setInviteStep] = useState<InviteStep>("identity");
  const [ownerStep, setOwnerStep] = useState<OwnerStep>("name");
  const [selectedPlace, setSelectedPlace] = useState<PlaceSuggestion | null>(null);
  const [locationQuery, setLocationQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { canResend, secondsLeft, startCooldown } = useOtpCooldown();

  useEffect(() => {
    let cancelled = false;

    async function resolveSession() {
      const authMe = await getAuthMe();
      if (cancelled) return;
      setSession(authMe);
      if (!inviteToken && authMe && !authMe.onboarding_required) {
        router.replace("/dashboard");
        return;
      }
      if (!inviteToken && authMe?.user.full_name) {
        setName((current) => current || authMe.user.full_name || "");
      }
      if (inviteToken && authMe?.user.full_name) {
        setName((current) => current || authMe.user.full_name || "");
      }
      if (!inviteToken && authMe?.user.email) {
        setEmail((current) => current || authMe.user.email || "");
      }
      setCheckingSession(false);
    }

    void resolveSession();
    return () => {
      cancelled = true;
    };
  }, [inviteToken, router]);

  useEffect(() => {
    if (!inviteToken) {
      setInvitePreview(null);
      setInviteError("");
      return;
    }

    let cancelled = false;
    setInviteLoading(true);
    setInviteError("");

    void getManagerInvitePreview(inviteToken)
      .then((preview) => {
        if (cancelled) return;
        setInvitePreview(preview);
        setEmail((current) => current || preview.invite_email);
        setName((current) => current || preview.manager_name || "");
      })
      .catch((err) => {
        if (cancelled) return;
        setInviteError(err instanceof Error ? err.message : "Could not load this invite.");
      })
      .finally(() => {
        if (!cancelled) setInviteLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [inviteToken]);

  const ownerCanSubmit =
    Boolean(session) &&
    Boolean(name.trim()) &&
    isValidEmail(email) &&
    Boolean(selectedPlace) &&
    !loading;

  const ownerStepIndex = OWNER_STEPS.indexOf(ownerStep);
  const ownerStepNumber = ownerStepIndex + 1;
  const ownerProgressPercent = (ownerStepNumber / OWNER_STEPS.length) * 100;
  const ownerIsLastStep = ownerStep === "location";
  const inviteNeedsName = !name.trim();
  const inviteNeedsEmail = !isValidEmail(email);

  const inviteLocationLabel = useMemo(() => {
    if (!invitePreview) return "";
    return `${invitePreview.business_name} · ${invitePreview.location_name}`;
  }, [invitePreview]);

  async function submitOwnerWorkspace() {
    if (!session || !selectedPlace || loading) return;
    setLoading(true);
    setError("");
    try {
      const organizationName = inferOrganizationName(selectedPlace);
      const response = await bootstrapOwnerWorkspace({
        profile: {
          full_name: name.trim(),
          email: email.trim(),
        },
        business: {
          legal_name: organizationName,
          brand_name: organizationName,
          primary_email: email.trim(),
          vertical: selectedPlace.primary_type ?? undefined,
          timezone: "America/Los_Angeles",
          place_metadata: {
            provider: selectedPlace.provider,
            place_id: selectedPlace.place_id,
            name: selectedPlace.name,
            brand_name: selectedPlace.brand_name ?? null,
            formatted_address: selectedPlace.formatted_address ?? null,
            types: selectedPlace.types ?? [],
          },
        },
        location: buildLocationPayloadFromPlace(selectedPlace),
      });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish onboarding.");
    } finally {
      setLoading(false);
    }
  }

  function ownerStepCanContinue(): boolean {
    if (loading) {
      return false;
    }
    if (ownerStep === "name") {
      return Boolean(name.trim());
    }
    if (ownerStep === "email") {
      return isValidEmail(email);
    }
    return ownerCanSubmit;
  }

  function goToPreviousOwnerStep() {
    if (ownerStepIndex <= 0 || loading) {
      return;
    }
    setError("");
    setOwnerStep(OWNER_STEPS[ownerStepIndex - 1]);
  }

  async function handleOwnerStepSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!ownerStepCanContinue()) {
      return;
    }
    setError("");
    if (ownerIsLastStep) {
      await submitOwnerWorkspace();
      return;
    }
    setOwnerStep(OWNER_STEPS[ownerStepIndex + 1]);
  }

  async function handleInviteIdentitySubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!inviteToken || !phone.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await requestManagerInviteChallenge({
        inviteToken,
        phone_e164: phone.trim(),
        manager_name: name.trim() || undefined,
      });
      setChallengeId(response.challenge.id);
      setInviteStep("code");
      setCode("");
      startCooldown(inThirtySeconds());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send your verification code.");
    } finally {
      setLoading(false);
    }
  }

  async function handleInviteCodeSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!challengeId || !phone.trim() || !code.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await verifyChallenge({
        challenge_id: challengeId,
        phone_e164: phone.trim(),
        code: code.trim(),
      });
      const authMe = await getAuthMe();
      setSession(authMe);
      setName((current) => current || authMe?.user.full_name || "");
      setEmail((current) => current || authMe?.user.email || invitePreview?.invite_email || "");
      if (!response.onboarding_required) {
        router.replace("/dashboard");
        return;
      }
      setInviteStep("profile");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not verify your code.");
    } finally {
      setLoading(false);
    }
  }

  async function handleInviteProfileSubmit(event: React.FormEvent) {
    event.preventDefault();
    if ((inviteNeedsName && !name.trim()) || (inviteNeedsEmail && !isValidEmail(email)) || loading) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      await completeOnboardingProfile({
        full_name: name.trim(),
        email: email.trim(),
      });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish your profile.");
    } finally {
      setLoading(false);
    }
  }

  async function handleInviteResend() {
    if (!inviteToken || !canResend || !phone.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await requestManagerInviteChallenge({
        inviteToken,
        phone_e164: phone.trim(),
        manager_name: name.trim(),
      });
      setChallengeId(response.challenge.id);
      startCooldown(inThirtySeconds());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend your code.");
    } finally {
      setLoading(false);
    }
  }

  if (checkingSession || inviteLoading) {
    return (
      <main className="lp-signup">
        <div style={{ minHeight: "100svh", display: "grid", placeItems: "center" }}>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, letterSpacing: "-0.04em" }}>
            Backfill
          </div>
        </div>
      </main>
    );
  }

  if (!isInviteFlow && !session) {
    return (
      <main className="section">
        <div className="page-head">
          <span className="eyebrow">Onboarding</span>
          <h1>Verification required</h1>
          <p className="muted">
            Start with phone verification so we can create your session first.
          </p>
        </div>
        <EmptyState
          title="No session"
          body="Start setup first, then come back here to bootstrap the owner workspace."
        />
        <div style={{ display: "flex", gap: 12, paddingTop: 20 }}>
          <Link href="/try" className="button">Start setup</Link>
          <Link href="/login" className="button-secondary">Sign in</Link>
        </div>
      </main>
    );
  }

  if (isInviteFlow && inviteError) {
    return (
      <main className="section">
        <div className="page-head">
          <span className="eyebrow">Manager invite</span>
          <h1>Invite unavailable</h1>
          <p className="muted">{inviteError}</p>
        </div>
      </main>
    );
  }

  if (isInviteFlow) {
    return (
      <main className="lp-signup">
        <div className="lp-signup-card">
          <div className="lp-signup-header">
            <Link href="/" className="lp-signup-logo">Backfill</Link>
          </div>
          <div className="lp-signup-body">
            <p className="lp-eyebrow" style={{ marginBottom: 12 }}>MANAGER INVITE</p>
            <h1 className="lp-signup-headline">
              {inviteStep === "profile" ? "Finish your Backfill profile." : "Accept your invitation."}
            </h1>
            <p className="lp-signup-sub">
              {inviteLocationLabel}
              {invitePreview?.location_address ? ` · ${invitePreview.location_address}` : ""}
            </p>
            {inviteStep === "identity" ? (
              <form onSubmit={handleInviteIdentitySubmit} className="lp-signup-form">
                <div className="lp-signup-field">
                  <label htmlFor="phone">Phone number</label>
                  <input
                    id="phone"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    placeholder="(555) 123-4567"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    autoFocus
                  />
                </div>
                <div className="lp-signup-field">
                  <label htmlFor="email">Invite email</label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    disabled
                  />
                </div>
                {invitePreview?.manager_name ? (
                  <p className="lp-signup-sub" style={{ marginTop: -4, marginBottom: 0 }}>
                    You&apos;re being invited as {invitePreview.manager_name}.
                  </p>
                ) : null}
                {error ? <p className="lp-signup-error">{error}</p> : null}
                <button
                  type="submit"
                  className="lp-signup-submit"
                  disabled={!phone.trim() || loading}
                >
                  {loading ? "Sending..." : "Send code"}
                </button>
              </form>
            ) : null}

            {inviteStep === "code" ? (
              <>
                <form onSubmit={handleInviteCodeSubmit} className="lp-signup-form">
                  <div className="lp-signup-field">
                    <label htmlFor="code">Verification code</label>
                    <input
                      id="code"
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="123456"
                      value={code}
                      onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 10))}
                      autoFocus
                    />
                  </div>
                  {error ? <p className="lp-signup-error">{error}</p> : null}
                  <button
                    type="submit"
                    className="lp-signup-submit"
                    disabled={!code.trim() || loading}
                  >
                    {loading ? "Verifying..." : "Verify code"}
                  </button>
                </form>
                <p className="lp-signup-resend">
                  Didn&apos;t get it?{" "}
                  <button
                    type="button"
                    className="lp-signup-text-link"
                    disabled={!canResend || loading}
                    onClick={() => {
                      void handleInviteResend();
                    }}
                  >
                    {canResend ? "Resend code" : `Resend in ${secondsLeft}s`}
                  </button>
                </p>
              </>
            ) : null}

            {inviteStep === "profile" ? (
              <form onSubmit={handleInviteProfileSubmit} className="lp-signup-form">
                {inviteNeedsName ? (
                  <div className="lp-signup-field">
                    <label htmlFor="profile-name">Full name</label>
                    <input
                      id="profile-name"
                      type="text"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      autoFocus
                    />
                  </div>
                ) : null}
                {inviteNeedsEmail ? (
                  <div className="lp-signup-field">
                    <label htmlFor="profile-email">Email</label>
                    <input
                      id="profile-email"
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      autoFocus={!inviteNeedsName}
                    />
                  </div>
                ) : null}
                {error ? <p className="lp-signup-error">{error}</p> : null}
                <button
                  type="submit"
                  className="lp-signup-submit"
                  disabled={
                    (inviteNeedsName && !name.trim()) ||
                    (inviteNeedsEmail && !isValidEmail(email)) ||
                    loading
                  }
                >
                  {loading ? "Saving..." : "Finish setup"}
                </button>
              </form>
            ) : null}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="lp-onboarding">
      <div className="ob-card">
        <div className="ob-header">
          <Link href="/" className="ob-logo">Backfill</Link>
          <span className="ob-step-label">Owner setup · {ownerStepNumber} of {OWNER_STEPS.length}</span>
        </div>
        <div className="ob-progress-bar">
          <div className="ob-progress-fill" style={{ width: `${ownerProgressPercent}%` }} />
        </div>
        <form onSubmit={handleOwnerStepSubmit}>
          <div className="ob-body">
            {ownerStep === "name" ? (
              <div className="ob-step-pane" key="owner-name">
                <h1 className="ob-question">What should we call the first workspace owner?</h1>
                <p className="ob-sub">
                  This becomes the default operator profile for your first Backfill workspace.
                </p>
                <input
                  id="name"
                  className="ob-input ob-input-underline"
                  type="text"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Cardin Campbell"
                  autoFocus
                />
              </div>
            ) : null}

            {ownerStep === "email" ? (
              <div className="ob-step-pane" key="owner-email">
                <h1 className="ob-question">Where should workspace alerts and invites go?</h1>
                <p className="ob-sub">
                  We&apos;ll use this email for admin access and important workspace updates.
                </p>
                <input
                  id="email"
                  className="ob-input ob-input-underline"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  autoFocus
                />
              </div>
            ) : null}

            {ownerStep === "location" ? (
              <div className="ob-step-pane" key="owner-location">
                <h1 className="ob-question">Which location should we start with?</h1>
                <p className="ob-sub">
                  Search the real place so Backfill can prefill the address and business details.
                </p>
                <div className="lp-signup-field">
                  <label htmlFor="location-search">Location</label>
                  <PlaceAutocomplete
                    value={locationQuery}
                    selectedPlace={selectedPlace}
                    onInputChange={(value) => {
                      setLocationQuery(value);
                      if (selectedPlace && value !== selectedPlace.label) {
                        setSelectedPlace(null);
                      }
                    }}
                    onSelect={(place) => {
                      setSelectedPlace(place);
                      setLocationQuery(place.label);
                    }}
                    placeholder="Search for your location"
                    autoFocus
                  />
                </div>
              </div>
            ) : null}

            {error ? <p className="ob-error">{error}</p> : null}
          </div>
          <div className="ob-footer">
            <button
              type="button"
              className="ob-btn-back"
              onClick={goToPreviousOwnerStep}
              disabled={ownerStepIndex === 0 || loading}
            >
              Back
            </button>
            <button
              type="submit"
              className="ob-btn-next"
              disabled={!ownerStepCanContinue()}
            >
              {ownerIsLastStep ? (loading ? "Creating workspace..." : "Create workspace") : "Continue"}
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={<main className="lp-signup" />}>
      <OnboardingBody />
    </Suspense>
  );
}
