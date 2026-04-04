"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";

import type { AuthMeResponse } from "@/lib/api/auth";
import { getAuthMe } from "@/lib/api/auth";

type AppSessionGateProps = {
  children: React.ReactNode;
};

type SessionUserDisplay = {
  fullName: string;
  firstName: string;
  lastName: string;
  email: string | null;
  phone: string | null;
  initials: string;
};

const AppSessionContext = createContext<AuthMeResponse | null>(null);

function capitalizeSegment(value: string): string {
  if (!value) {
    return value;
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function deriveEmailName(email: string | null | undefined): string {
  if (!email) {
    return "";
  }
  const localPart = email.split("@")[0]?.trim() ?? "";
  if (!localPart) {
    return "";
  }
  return localPart
    .replace(/[._-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map(capitalizeSegment)
    .join(" ");
}

function deriveInitials(fullName: string): string {
  const parts = fullName
    .split(/\s+/)
    .filter((part) => /[A-Za-z0-9]/.test(part))
    .slice(0, 2);
  if (parts.length === 0) {
    return "BF";
  }
  const initials = parts
    .map((part) => part.charAt(0).toUpperCase())
    .join("")
    .slice(0, 2);
  return initials || "BF";
}

function buildSessionUserDisplay(
  session: AuthMeResponse | null,
): SessionUserDisplay {
  const user = session?.user;
  const email = user?.email?.trim() || null;
  const phone = user?.primary_phone_e164?.trim() || null;
  const fullName =
    user?.full_name?.trim() || deriveEmailName(email) || phone || "Backfill";
  const nameParts = fullName.split(/\s+/).filter(Boolean);
  const firstName = nameParts[0] || "Backfill";
  const lastName = nameParts.slice(1).join(" ");

  return {
    fullName,
    firstName,
    lastName,
    email,
    phone,
    initials: deriveInitials(fullName),
  };
}

export function useAppSession(): AuthMeResponse | null {
  return useContext(AppSessionContext);
}

export function useSessionUserDisplay(): SessionUserDisplay {
  return buildSessionUserDisplay(useAppSession());
}

export function AppSessionGate({ children }: AppSessionGateProps) {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<AuthMeResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function resolveSession() {
      const session = await getAuthMe();
      if (cancelled) {
        return;
      }
      if (!session) {
        window.location.replace("/login");
        return;
      }
      if (session.onboarding_required) {
        window.location.replace("/onboarding");
        return;
      }
      setSession(session);
      setReady(true);
    }

    void resolveSession();

    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) {
    return (
      <main
        className="min-h-screen bg-[#F7F8FA]"
        style={{ fontFamily: "'Inter', system-ui, sans-serif" }}
      />
    );
  }

  return (
    <AppSessionContext.Provider value={session}>
      {children}
    </AppSessionContext.Provider>
  );
}
