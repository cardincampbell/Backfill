"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { requestAccess, verifyAccessCode } from "@/lib/api/auth";
import {
  clearStoredPreviewWorkspace,
  isPreviewAuthBypassEnabled,
  storePreviewPhone,
} from "@/lib/auth/preview";
import { useOtpCooldown } from "@/lib/auth/use-otp-cooldown";

export default function TryPage() {
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [consented, setConsented] = useState(false);
  const [step, setStep] = useState<"form" | "code">("form");
  const [requestId, setRequestId] = useState<number | null>(null);
  const [code, setCode] = useState("");
  const [destination, setDestination] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const previewBypassEnabled = isPreviewAuthBypassEnabled();
  const { canResend, secondsLeft, startCooldown } = useOtpCooldown();

  async function handlePhoneSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim() || !consented || loading) return;
    setError("");
    setLoading(true);
    try {
      if (previewBypassEnabled) {
        clearStoredPreviewWorkspace();
        storePreviewPhone(phone.trim());
        router.push("/onboarding");
        return;
      }
      const result = await requestAccess(phone.trim());
      setRequestId(result.request_id);
      setDestination(result.destination);
      startCooldown(result.resend_available_at);
      setCode("");
      setStep("code");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCodeSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!requestId || !code.trim() || loading) return;
    setError("");
    setLoading(true);
    try {
      const result = await verifyAccessCode(requestId, code.trim());
      clearStoredPreviewWorkspace();
      router.replace(result.onboarding_required ? "/onboarding" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResendCode() {
    if (!canResend || !phone.trim() || loading) return;
    setError("");
    setLoading(true);
    try {
      const result = await requestAccess(phone.trim());
      setRequestId(result.request_id);
      setDestination(result.destination);
      startCooldown(result.resend_available_at);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="lp-signup">
      <div className="lp-signup-card">
        {step === "form" ? (
          <>
            <div className="lp-signup-header">
              <a href="/" className="lp-signup-logo">Backfill</a>
            </div>
            <div className="lp-signup-body">
              <p className="lp-eyebrow" style={{ marginBottom: 12 }}>GET EARLY ACCESS</p>
              <h1 className="lp-signup-headline">Your phone number is your login.</h1>
              <p className="lp-signup-sub">
                {previewBypassEnabled
                  ? "Drop your number and we’ll carry it into setup so you can get into Backfill without re-entering it."
                  : "Drop your number and we’ll text you a code to get into Backfill — no passwords, no friction. Just the product."}
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
                    onChange={(e) => setPhone(e.target.value)}
                    autoFocus
                  />
                </div>

                <label className="lp-signup-consent">
                  <input
                    type="checkbox"
                    checked={consented}
                    onChange={(e) => setConsented(e.target.checked)}
                  />
                  <span>
                    {previewBypassEnabled
                      ? "By checking this box, you agree that Backfill may use this number for your setup and future account communications. View our "
                      : "By checking this box, you agree to receive text messages from Backfill Works, Inc. at the number provided above, including marketing and account messages. Message and data rates may apply. Reply STOP at any time to unsubscribe. View our "}
                    <a href="/privacy" className="lp-signup-text-link">Privacy Policy</a>.
                  </span>
                </label>

                {error && <p className="lp-signup-error">{error}</p>}

                <button
                  type="submit"
                  className="lp-signup-submit"
                  disabled={!phone.trim() || !consented || loading}
                >
                  {loading ? (previewBypassEnabled ? "Continuing..." : "Sending...") : (previewBypassEnabled ? "Continue" : "Send code")}
                </button>
              </form>

              <p className="lp-signup-footer-note">
                {previewBypassEnabled
                  ? "We’ll carry this number into your setup so you don’t have to enter it again."
                  : "We’ll text you a one-time code. Standard messaging rates may apply. No spam — ever."}
              </p>
            </div>
          </>
        ) : (
          <>
            <div className="lp-signup-header">
              <a href="/" className="lp-signup-logo">Backfill</a>
            </div>
            <div className="lp-signup-body lp-signup-body-sent">
              <div className="lp-signup-check" aria-hidden="true">✓</div>
              <h1 className="lp-signup-headline">Enter your code.</h1>
              <p className="lp-signup-sub">
                We just texted a verification code to <strong>{destination}</strong>.
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
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 10))}
                    autoFocus
                  />
                </div>
                {error && <p className="lp-signup-error">{error}</p>}
                <button
                  type="submit"
                  className="lp-signup-submit"
                  disabled={!code.trim() || loading}
                >
                  {loading ? "Verifying..." : "Verify code"}
                </button>
              </form>
              <p className="lp-signup-resend">
                Didn&rsquo;t get it?{" "}
                <button
                  onClick={() => {
                    void handleResendCode();
                  }}
                  className="lp-signup-text-link"
                  disabled={!canResend || loading}
                  style={{ opacity: canResend ? 1 : 0.5 }}
                >
                  {canResend ? "Resend code" : `Resend in ${secondsLeft}s`}
                </button>
                {" · "}
                <button
                  onClick={() => {
                    setStep("form");
                    setRequestId(null);
                    setCode("");
                    setError("");
                  }}
                  className="lp-signup-text-link"
                >
                  Try again
                </button>
              </p>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
