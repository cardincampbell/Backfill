"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { requestAccess, verifyAccessCode } from "@/lib/api/auth";
import { API_BASE_URL, apiFetch } from "@/lib/api/client";
import {
  clearStoredPreviewWorkspace,
  isPreviewAuthBypassEnabled,
  storePreviewPhone,
} from "@/lib/auth/preview";
import { useOtpCooldown } from "@/lib/auth/use-otp-cooldown";

export default function LoginPage() {
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [requestId, setRequestId] = useState<number | null>(null);
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [destination, setDestination] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const previewBypassEnabled = isPreviewAuthBypassEnabled();
  const { canResend, secondsLeft, startCooldown } = useOtpCooldown();

  useEffect(() => {
    let cancelled = false;

    async function resolveSession() {
      if (previewBypassEnabled) {
        setCheckingSession(false);
        return;
      }
      try {
        const response = await apiFetch(`${API_BASE_URL}/api/auth/me`, {
          method: "GET",
        });
        if (!response.ok) {
          if (!cancelled) setCheckingSession(false);
          return;
        }
        const payload = (await response.json()) as { onboarding_required?: boolean };
        if (cancelled) return;
        router.replace(payload.onboarding_required ? "/onboarding" : "/dashboard");
      } catch {
        if (!cancelled) setCheckingSession(false);
      }
    }

    void resolveSession();
    return () => {
      cancelled = true;
    };
  }, [previewBypassEnabled, router]);

  async function handlePhoneSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim() || loading) return;
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
      setError(err instanceof Error ? err.message : "Something went wrong");
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
      setError(err instanceof Error ? err.message : "Something went wrong");
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
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="lp-signup">
      <section style={{ maxWidth: 400, margin: "120px auto 0", padding: "0 20px", width: "100%" }}>
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 600, letterSpacing: "-0.025em" }}>
            Backfill
          </h1>
        </div>

        <div className="settings-card">
          {checkingSession ? (
            <>
              <div className="settings-card-header">Checking your session</div>
              <div className="settings-card-body">
                <div style={{ fontSize: "0.8rem", color: "var(--muted)", textAlign: "center" }}>
                  If you already signed in recently, we&rsquo;ll take you straight into Backfill.
                </div>
              </div>
            </>
          ) : step === "phone" ? (
            <>
              <div className="settings-card-header">Sign in</div>
              <div className="settings-card-body">
                <form onSubmit={handlePhoneSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div className="settings-field">
                    <label className="settings-toggle-label" htmlFor="phone">Phone number</label>
                    <input
                      id="phone"
                      type="tel"
                      inputMode="tel"
                      autoComplete="tel"
                      placeholder="(555) 123-4567"
                      className="settings-select"
                      style={{ width: "100%" }}
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      autoFocus
                    />
                  </div>
                  {error && (
                    <div style={{ fontSize: "0.75rem", color: "var(--danger, #d00)" }}>
                      {error}
                    </div>
                  )}
                  <button
                    type="submit"
                    className="button"
                    disabled={!phone.trim() || loading}
                    style={{ marginTop: 4 }}
                  >
                    {loading ? (previewBypassEnabled ? "Continuing..." : "Sending...") : (previewBypassEnabled ? "Continue to setup" : "Send code")}
                  </button>
                  <div style={{ fontSize: "0.7rem", color: "var(--muted)", textAlign: "center", lineHeight: 1.5 }}>
                    {previewBypassEnabled
                      ? "We’ll carry this number into setup for now instead of sending a text."
                      : "We’ll text you a one-time code to sign in."}
                  </div>
                </form>
              </div>
            </>
          ) : (
            <>
              <div className="settings-card-header">Enter your code</div>
              <div className="settings-card-body">
                <form onSubmit={handleCodeSubmit} style={{ display: "flex", flexDirection: "column", gap: 16, textAlign: "center" }}>
                  <p style={{ fontSize: "0.8rem", lineHeight: 1.6, color: "var(--foreground)" }}>
                    We sent a verification code to <strong>{destination}</strong>.
                  </p>
                  <div className="settings-field" style={{ textAlign: "left" }}>
                    <label className="settings-toggle-label" htmlFor="code">Verification code</label>
                    <input
                      id="code"
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="123456"
                      className="settings-select"
                      style={{ width: "100%", textAlign: "center", letterSpacing: "0.24em" }}
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 10))}
                      autoFocus
                    />
                  </div>
                  {error && (
                    <div style={{ fontSize: "0.75rem", color: "var(--danger, #d00)", textAlign: "left" }}>
                      {error}
                    </div>
                  )}
                  <button
                    type="submit"
                    className="button"
                    disabled={!code.trim() || loading}
                  >
                    {loading ? "Verifying..." : "Verify code"}
                  </button>
                  <div style={{ fontSize: "0.7rem", color: "var(--muted)", lineHeight: 1.5 }}>
                    Didn&apos;t get it?
                  </div>
                  <button
                    type="button"
                    className="button"
                    disabled={!canResend || loading}
                    onClick={() => {
                      void handleResendCode();
                    }}
                    style={{ background: "transparent", color: "var(--foreground)", border: "1px solid var(--line)" }}
                  >
                    {canResend ? "Resend code" : `Resend in ${secondsLeft}s`}
                  </button>
                  <button
                    type="button"
                    className="button"
                    onClick={() => {
                      setStep("phone");
                      setCode("");
                      setRequestId(null);
                      setError("");
                    }}
                    style={{ background: "transparent", color: "var(--foreground)", border: "1px solid var(--line)" }}
                  >
                    Use a different number
                  </button>
                </form>
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
