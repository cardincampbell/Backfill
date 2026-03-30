"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { requestAccess } from "@/lib/api/auth";

export default function LoginPage() {
  const router = useRouter();
  const [phone, setPhone] = useState("");
  const [step, setStep] = useState<"phone" | "sent">("phone");
  const [destination, setDestination] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim() || loading) return;
    setError("");
    setLoading(true);
    try {
      const result = await requestAccess(phone.trim());
      setDestination(result.destination);
      setStep("sent");
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
          {step === "phone" ? (
            <>
              <div className="settings-card-header">Sign in</div>
              <div className="settings-card-body">
                <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
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
                    {loading ? "Sending..." : "Send access link"}
                  </button>
                  <div style={{ fontSize: "0.7rem", color: "var(--muted)", textAlign: "center", lineHeight: 1.5 }}>
                    We'll text you a one-time link to sign in.
                  </div>
                </form>
              </div>
            </>
          ) : (
            <>
              <div className="settings-card-header">Check your phone</div>
              <div className="settings-card-body">
                <div style={{ display: "flex", flexDirection: "column", gap: 16, textAlign: "center" }}>
                  <p style={{ fontSize: "0.8rem", lineHeight: 1.6, color: "var(--foreground)" }}>
                    We sent an access link to <strong>{destination}</strong>.
                    <br />
                    Tap the link in the text to sign in.
                  </p>
                  <div style={{ fontSize: "0.7rem", color: "var(--muted)", lineHeight: 1.5 }}>
                    The link expires in a few minutes. Didn't get it?
                  </div>
                  <button
                    className="button"
                    onClick={() => {
                      setStep("phone");
                      setError("");
                    }}
                    style={{ background: "transparent", color: "var(--foreground)", border: "1px solid var(--line)" }}
                  >
                    Try again
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
