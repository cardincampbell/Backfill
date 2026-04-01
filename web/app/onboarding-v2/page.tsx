"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { EmptyState } from "@/components/empty-state";
import { PlaceAutocomplete } from "@/components/place-autocomplete";
import type { PlaceSuggestion } from "@/lib/api/places";
import {
  bootstrapV2OwnerWorkspace,
  completeV2OnboardingProfile,
  getV2AuthMe,
  getV2ManagerInvitePreview,
  requestV2ManagerInviteChallenge,
  type V2AuthMeResponse,
  type V2ManagerInvitePreview,
  verifyV2Challenge,
} from "@/lib/api/v2-auth";
import { useOtpCooldown } from "@/lib/auth/use-otp-cooldown";
import { buildV2LocationPayloadFromPlace } from "@/lib/place-location-v2";
import { inferOrganizationName } from "@/lib/place-location";

type InviteStep = "identity" | "code" | "profile";

function inThirtySeconds(): string {
  return new Date(Date.now() + 30_000).toISOString();
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function OnboardingV2Body() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get("invite")?.trim() || null;
  const isInviteFlow = Boolean(inviteToken);

  const [checkingSession, setCheckingSession] = useState(true);
  const [session, setSession] = useState<V2AuthMeResponse | null>(null);
  const [invitePreview, setInvitePreview] = useState<V2ManagerInvitePreview | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [inviteStep, setInviteStep] = useState<InviteStep>("identity");
  const [selectedPlace, setSelectedPlace] = useState<PlaceSuggestion | null>(null);
  const [locationQuery, setLocationQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { canResend, secondsLeft, startCooldown } = useOtpCooldown();

  useEffect(() => {
    let cancelled = false;

    async function resolveSession() {
      const authMe = await getV2AuthMe();
      if (cancelled) return;
      setSession(authMe);
      if (!inviteToken && authMe && !authMe.onboarding_required) {
        router.replace("/dashboard");
        return;
      }
      if (!inviteToken && authMe?.user.full_name) {
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

    void getV2ManagerInvitePreview(inviteToken)
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

  const inviteLocationLabel = useMemo(() => {
    if (!invitePreview) return "";
    return `${invitePreview.business_name} · ${invitePreview.location_name}`;
  }, [invitePreview]);

  async function handleOwnerSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!session || !selectedPlace || loading) return;
    setLoading(true);
    setError("");
    try {
      const organizationName = inferOrganizationName(selectedPlace);
      const response = await bootstrapV2OwnerWorkspace({
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
        location: buildV2LocationPayloadFromPlace(selectedPlace),
      });
      router.replace(
        "/dashboard",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish onboarding.");
    } finally {
      setLoading(false);
    }
  }

  async function handleInviteIdentitySubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!inviteToken || !phone.trim() || !name.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await requestV2ManagerInviteChallenge({
        inviteToken,
        phone_e164: phone.trim(),
        manager_name: name.trim(),
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
      const response = await verifyV2Challenge({
        challenge_id: challengeId,
        phone_e164: phone.trim(),
        code: code.trim(),
      });
      const authMe = await getV2AuthMe();
      setSession(authMe);
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
    if (!name.trim() || !isValidEmail(email) || loading) return;
    setLoading(true);
    setError("");
    try {
      await completeV2OnboardingProfile({
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
      const response = await requestV2ManagerInviteChallenge({
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
                  <label htmlFor="name">Full name</label>
                  <input
                    id="name"
                    type="text"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    autoFocus
                  />
                </div>
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
                {error ? <p className="lp-signup-error">{error}</p> : null}
                <button
                  type="submit"
                  className="lp-signup-submit"
                  disabled={!name.trim() || !phone.trim() || loading}
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
                <div className="lp-signup-field">
                  <label htmlFor="profile-email">Email</label>
                  <input
                    id="profile-email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </div>
                {error ? <p className="lp-signup-error">{error}</p> : null}
                <button
                  type="submit"
                  className="lp-signup-submit"
                  disabled={!name.trim() || !isValidEmail(email) || loading}
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
    <main className="lp-signup">
      <div className="lp-signup-card">
        <div className="lp-signup-header">
          <Link href="/" className="lp-signup-logo">Backfill</Link>
        </div>
        <div className="lp-signup-body">
          <p className="lp-eyebrow" style={{ marginBottom: 12 }}>OWNER SETUP</p>
          <h1 className="lp-signup-headline">Set up your first business and location.</h1>
          <p className="lp-signup-sub">
            This creates your first live workspace in Backfill.
          </p>
          <form onSubmit={handleOwnerSubmit} className="lp-signup-form">
            <div className="lp-signup-field">
              <label htmlFor="name">Full name</label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoFocus
              />
            </div>
            <div className="lp-signup-field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
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
              />
            </div>
            {selectedPlace ? (
              <div className="place-selected-meta">
                <span className="place-selected-badge">
                  Business: {inferOrganizationName(selectedPlace)}
                </span>
                <span className="place-selected-address">
                  {selectedPlace.formatted_address ?? "Address unavailable"}
                </span>
              </div>
            ) : null}
            {error ? <p className="lp-signup-error">{error}</p> : null}
            <button
              type="submit"
              className="lp-signup-submit"
              disabled={!ownerCanSubmit}
            >
              {loading ? "Creating workspace..." : "Create workspace"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}

export default function OnboardingV2Page() {
  return (
    <Suspense fallback={<main className="lp-signup" />}>
      <OnboardingV2Body />
    </Suspense>
  );
}
