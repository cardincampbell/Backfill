"use client";

import { useState } from "react";
import { requestAccess } from "@/lib/api/auth";

export default function TryPage() {
  const [phone, setPhone] = useState("");
  const [consented, setConsented] = useState(false);
  const [step, setStep] = useState<"form" | "sent">("form");
  const [destination, setDestination] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim() || !consented || loading) return;
    setError("");
    setLoading(true);
    try {
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
              <h1 className="lp-signup-headline">Try Backfill Free</h1>
              <p className="lp-signup-sub">
                Enter your number and we&rsquo;ll text you a link to get started.
                Most operators are live within 24 hours.
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
                    By checking this box, you agree to receive text messages from Backfill
                    Technologies, Inc. at the number provided above, including marketing and
                    account messages. Message and data rates may apply. Reply STOP at any time
                    to unsubscribe. View our{" "}
                    <a href="/privacy" className="lp-signup-text-link">Privacy Policy</a>.
                  </span>
                </label>

                {error && <p className="lp-signup-error">{error}</p>}

                <button
                  type="submit"
                  className="lp-signup-submit"
                  disabled={!phone.trim() || !consented || loading}
                >
                  {loading ? "Sending..." : "Try Backfill Free"}
                </button>
              </form>

              <p className="lp-signup-footer-note">
                Already have an account?{" "}
                <a href="/login" className="lp-signup-text-link">Sign in</a>
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
              <h1 className="lp-signup-headline">Check your phone</h1>
              <p className="lp-signup-sub">
                We just texted a link to <strong>{destination}</strong>.
                Tap it to finish setting up your account.
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
