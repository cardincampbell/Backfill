"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  getV2AuthMe,
  requestV2Challenge,
  verifyV2Challenge,
} from "@/lib/api/v2-auth";
import { useOtpCooldown } from "@/lib/auth/use-otp-cooldown";

type Step = "phone" | "code";

function inThirtySeconds(): string {
  return new Date(Date.now() + 30_000).toISOString();
}

export default function LoginV2Page() {
  const router = useRouter();
  const [checkingSession, setCheckingSession] = useState(true);
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { canResend, secondsLeft, startCooldown } = useOtpCooldown();

  useEffect(() => {
    let cancelled = false;

    async function resolveSession() {
      const session = await getV2AuthMe();
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
    if (!phone.trim() || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await requestV2Challenge({
        phone_e164: phone.trim(),
        purpose: "sign_in",
      });
      setChallengeId(response.challenge.id);
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
      const response = await verifyV2Challenge({
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
      const response = await requestV2Challenge({
        phone_e164: phone.trim(),
        purpose: "sign_in",
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
            <p className="lp-eyebrow" style={{ marginBottom: 12 }}>SIGN IN</p>
            <h1 className="lp-signup-headline">Sign in with your phone.</h1>
            <p className="lp-signup-sub">
              If your session is still live, we&apos;ll skip this screen next time.
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
              {error ? <p className="lp-signup-error">{error}</p> : null}
              <button
                type="submit"
                className="lp-signup-submit"
                disabled={!phone.trim() || loading}
              >
                {loading ? "Sending..." : "Send code"}
              </button>
            </form>
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
              {" · "}
              <button
                type="button"
                className="lp-signup-text-link"
                onClick={() => {
                  setStep("phone");
                  setChallengeId(null);
                  setCode("");
                  setError("");
                }}
              >
                Use a different number
              </button>
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
