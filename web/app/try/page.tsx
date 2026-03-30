"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { requestAccess } from "@/lib/api/auth";
import {
  isPreviewAuthBypassEnabled,
  storePreviewPhone,
} from "@/lib/auth/preview";

export default function TryPage() {
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [consented, setConsented] = useState(false);
  const [step, setStep] = useState<"form" | "sent">("form");
  const [destination, setDestination] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const previewBypassEnabled = isPreviewAuthBypassEnabled();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim() || !consented || loading) return;
    setError("");
    setLoading(true);
    try {
      if (previewBypassEnabled) {
        storePreviewPhone(phone.trim());
        router.push("/onboarding");
        return;
      }
      const result = await requestAccess(phone.trim());
      setDestination(result.destination);
      setStep("sent");
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
                  : "Drop your number and we’ll text you a link to get into Backfill — no passwords, no friction. Just the product."}
              </p>
              <form onSubmit={handleSubmit} className="lp-signup-form">
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
                      : "By checking this box, you agree to receive text messages from Backfill Technologies, Inc. at the number provided above, including marketing and account messages. Message and data rates may apply. Reply STOP at any time to unsubscribe. View our "}
                    <a href="/privacy" className="lp-signup-text-link">Privacy Policy</a>.
                  </span>
                </label>

                {error && <p className="lp-signup-error">{error}</p>}

                <button
                  type="submit"
                  className="lp-signup-submit"
                  disabled={!phone.trim() || !consented || loading}
                >
                  {loading ? (previewBypassEnabled ? "Continuing..." : "Sending...") : (previewBypassEnabled ? "Continue" : "Get access")}
                </button>
              </form>

              <p className="lp-signup-footer-note">
                {previewBypassEnabled
                  ? "We’ll carry this number into your setup so you don’t have to enter it again."
                  : "We’ll text you a one-time link. Standard messaging rates may apply. No spam — ever."}
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
              <h1 className="lp-signup-headline">You&rsquo;re in.</h1>
              <p className="lp-signup-sub">
                Check your phone &mdash; we just sent a link to <strong>{destination}</strong>
                to get started with Backfill. See you on the inside.
              </p>
              <p className="lp-signup-resend">
                Didn&rsquo;t get it?{" "}
                <button
                  onClick={() => { setStep("form"); setError(""); }}
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
