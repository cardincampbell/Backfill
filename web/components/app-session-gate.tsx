"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";

import type { AuthMeResponse } from "@/lib/api/auth";
import { getAuthMe } from "@/lib/api/auth";

type AppSessionGateProps = {
  children: ReactNode;
};

type SessionUserDisplay = {
  fullName: string;
  firstName: string;
  lastName: string;
  email: string | null;
  phone: string | null;
  initials: string;
};

export type AppearancePreference = "light" | "dark" | "system";
export type ResolvedAppAppearance = "light" | "dark";

type AppSessionContextValue = {
  session: AuthMeResponse | null;
  setSession: Dispatch<SetStateAction<AuthMeResponse | null>>;
  appearancePreference: AppearancePreference;
  setAppearancePreference: Dispatch<SetStateAction<AppearancePreference>>;
  resolvedAppearance: ResolvedAppAppearance;
};

const AppSessionContext = createContext<AppSessionContextValue | null>(null);
const DEFAULT_APPEARANCE_PREFERENCE: AppearancePreference = "system";

function normalizeAppearancePreference(value: unknown): AppearancePreference {
  return value === "light" || value === "dark" || value === "system"
    ? value
    : DEFAULT_APPEARANCE_PREFERENCE;
}

function resolveSystemAppearance(): ResolvedAppAppearance {
  if (typeof window === "undefined") {
    return "light";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

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
  return useContext(AppSessionContext)?.session ?? null;
}

export function useUpdateAppSession() {
  return useContext(AppSessionContext)?.setSession;
}

export function useAppAppearancePreference(): AppearancePreference {
  return (
    useContext(AppSessionContext)?.appearancePreference ??
    DEFAULT_APPEARANCE_PREFERENCE
  );
}

export function useUpdateAppAppearancePreference() {
  return useContext(AppSessionContext)?.setAppearancePreference;
}

export function useResolvedAppAppearance(): ResolvedAppAppearance {
  return useContext(AppSessionContext)?.resolvedAppearance ?? "light";
}

export function useSessionUserDisplay(): SessionUserDisplay {
  return buildSessionUserDisplay(useAppSession());
}

export function AppSessionGate({ children }: AppSessionGateProps) {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<AuthMeResponse | null>(null);
  const [appearancePreference, setAppearancePreference] =
    useState<AppearancePreference>(DEFAULT_APPEARANCE_PREFERENCE);
  const [resolvedAppearance, setResolvedAppearance] =
    useState<ResolvedAppAppearance>("light");

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
      const nextPreference = normalizeAppearancePreference(
        session.user.profile_metadata?.appearance_preference,
      );
      setAppearancePreference(nextPreference);
      setResolvedAppearance(
        nextPreference === "system"
          ? resolveSystemAppearance()
          : nextPreference,
      );
      setSession(session);
      setReady(true);
    }

    void resolveSession();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const nextPreference = normalizeAppearancePreference(
      session?.user.profile_metadata?.appearance_preference,
    );
    setAppearancePreference(nextPreference);
  }, [session]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (appearancePreference !== "system") {
      setResolvedAppearance(appearancePreference);
      return;
    }

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => {
      setResolvedAppearance(mediaQuery.matches ? "dark" : "light");
    };

    sync();
    if ("addEventListener" in mediaQuery) {
      mediaQuery.addEventListener("change", sync);
    } else {
      (mediaQuery as MediaQueryList & {
        addListener?(listener: (event: MediaQueryListEvent) => void): void;
      }).addListener?.(sync);
    }
    return () => {
      if ("removeEventListener" in mediaQuery) {
        mediaQuery.removeEventListener("change", sync);
      } else {
        (mediaQuery as MediaQueryList & {
          removeListener?(listener: (event: MediaQueryListEvent) => void): void;
        }).removeListener?.(sync);
      }
    };
  }, [appearancePreference]);

  useEffect(() => {
    if (!ready || typeof document === "undefined") {
      return;
    }
    document.documentElement.dataset.backfillAppearance = resolvedAppearance;
    document.documentElement.style.colorScheme = resolvedAppearance;
  }, [ready, resolvedAppearance]);

  if (!ready) {
    return (
      <main
        className="min-h-screen bg-[#F7F8FA]"
        style={{ fontFamily: "'Inter', system-ui, sans-serif" }}
      />
    );
  }

  return (
    <AppSessionContext.Provider
      value={{
        session,
        setSession,
        appearancePreference,
        setAppearancePreference,
        resolvedAppearance,
      }}
    >
      {children}
    </AppSessionContext.Provider>
  );
}
