"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { exchangeToken } from "@/lib/api/auth";
import { SESSION_COOKIE } from "@/lib/auth/constants";

function VerifyContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setError("Missing access token. Please request a new link.");
      return;
    }

    let cancelled = false;

    async function verify() {
      try {
        const result = await exchangeToken(token!);
        if (cancelled) return;

        if (!result.session_token) {
          setError("No session returned. Please try again.");
          return;
        }

        // Store session token as a cookie (secure, same-site, 30-day expiry)
        const maxAge = 30 * 24 * 60 * 60;
        const secure = window.location.protocol === "https:" ? "; Secure" : "";
        document.cookie = `${SESSION_COOKIE}=${result.session_token}; path=/; max-age=${maxAge}; SameSite=Lax${secure}`;

        router.replace("/dashboard");
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Verification failed");
      }
    }

    verify();
    return () => { cancelled = true; };
  }, [searchParams, router]);

  return (
    <div className="settings-card">
      <div className="settings-card-header">
        {error ? "Link expired" : "Signing in..."}
      </div>
      <div className="settings-card-body">
        {error ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 14, textAlign: "center" }}>
            <p style={{ fontSize: "0.8rem", color: "var(--foreground)", lineHeight: 1.6 }}>
              {error}
            </p>
            <a href="/login" className="button" style={{ textDecoration: "none", textAlign: "center" }}>
              Back to sign in
            </a>
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "8px 0" }}>
            <p style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
              Verifying your access link...
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <section style={{ maxWidth: 400, margin: "120px auto 0", padding: "0 20px" }}>
      <div style={{ textAlign: "center", marginBottom: 32 }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600, letterSpacing: "-0.025em" }}>
          Backfill
        </h1>
      </div>
      <Suspense
        fallback={
          <div className="settings-card">
            <div className="settings-card-header">Signing in...</div>
            <div className="settings-card-body">
              <div style={{ textAlign: "center", padding: "8px 0" }}>
                <p style={{ fontSize: "0.8rem", color: "var(--muted)" }}>Loading...</p>
              </div>
            </div>
          </div>
        }
      >
        <VerifyContent />
      </Suspense>
    </section>
  );
}
