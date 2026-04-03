"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  getAuthMe,
  requestChallenge,
  requestChallengeAuto,
  verifyChallenge,
} from "@/lib/api/auth";
import { useOtpCooldown } from "@/lib/auth/use-otp-cooldown";

type Step = "phone" | "code";

function inThirtySeconds(): string {
  return new Date(Date.now() + 30_000).toISOString();
}

export default function TryPage() {
  const router = useRouter();
  const [checkingSession, setCheckingSession] = useState(true);
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [consented, setConsented] = useState(false);
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [requestedPurpose, setRequestedPurpose] = useState<"sign_in" | "sign_up">("sign_up");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { canResend, secondsLeft, startCooldown } = useOtpCooldown();

  useEffect(() => {
    let cancelled = false;

    async function resolveSession() {
      const session = await getAuthMe();
      if (cancelled) return;
      if (session) {
        router.replace(session.onboarding_required ? "/onboarding" : "/dashboard");
        return;
      }
      setCheckingSession(false);
    }

    void resolveSession();
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function handlePhoneSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!phone.trim() || !consented || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await requestChallengeAuto(phone.trim());
      setChallengeId(response.challenge.id);
      setRequestedPurpose(response.requestedPurpose);
      setStep("code");
      setCode("");
      startCooldown(inThirtySeconds());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send your code.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCodeSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!challengeId || !code.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await verifyChallenge({
        challenge_id: challengeId,
        phone_e164: phone.trim(),
        code: code.trim(),
      });
      router.replace(response.onboarding_required ? "/onboarding" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not verify your code.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    if (!canResend || !phone.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await requestChallenge({
        phone_e164: phone.trim(),
        purpose: requestedPurpose,
      });
      setChallengeId(response.challenge.id);
      startCooldown(inThirtySeconds());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend your code.");
    } finally {
      setLoading(false);
    }
  }

  if (checkingSession) {
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

  return (
    <main className="lp-signup">
      <div className="lp-signup-card">
        <div className="lp-signup-header">
          <Link href="/" className="lp-signup-logo">Backfill</Link>
        </div>
        {step === "phone" ? (
          <div className="lp-signup-body">
            <p className="lp-eyebrow" style={{ marginBottom: 12 }}>SET UP</p>
            <h1 className="lp-signup-headline">Use your phone to get into Backfill.</h1>
            <p className="lp-signup-sub">
              We&apos;ll text you a code and carry you straight into setup.
            </p>
            <form onSubmit={handlePhoneSubmit} className="lp-signup-form">
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
              <label className="lp-signup-consent">
                <input
                  type="checkbox"
                  checked={consented}
                  onChange={(event) => setConsented(event.target.checked)}
                />
                <span>
                  By checking this box, you agree to receive account texts from Backfill Works, Inc.
                  at the number above. View our{" "}
                  <Link href="/privacy" className="lp-signup-text-link">Privacy Policy</Link>.
                </span>
              </label>
              {error ? <p className="lp-signup-error">{error}</p> : null}
              <button
                type="submit"
                className="lp-signup-submit"
                disabled={!phone.trim() || !consented || loading}
              >
                {loading ? "Sending..." : "Send code"}
              </button>
            </form>
            <p className="lp-signup-footer-note">
              Already have access? <Link href="/login" className="lp-signup-text-link">Sign in</Link>
            </p>
          </div>
        ) : (
          <div className="lp-signup-body lp-signup-body-sent">
            <div className="lp-signup-check" aria-hidden="true">✓</div>
            <h1 className="lp-signup-headline">Enter your code.</h1>
            <p className="lp-signup-sub">
              We sent a verification code to <strong>{phone.trim()}</strong>.
            </p>
            <form onSubmit={handleCodeSubmit} className="lp-signup-form">
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
                  void handleResend();
                }}
              >
                {canResend ? "Resend code" : `Resend in ${secondsLeft}s`}
              </button>
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
