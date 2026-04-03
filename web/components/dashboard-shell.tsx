"use client";

import { useEffect, useState } from "react";

import {
  DashboardRailHomeLink,
  DashboardRailNav,
  DashboardRailProfile,
  DashboardRailThemeToggle,
  type DashboardTheme,
} from "@/components/dashboard-rail-nav";

type DashboardShellProps = {
  children: React.ReactNode;
  fallbackBasePath: string;
  profileDisplayName: string;
  subjectPhone: string | null;
  subjectEmail: string | null;
  signOutRedirectTo?: string;
};

const STORAGE_KEY = "backfill-dashboard-theme";

function resolveInitialTheme(): DashboardTheme {
  if (typeof window === "undefined") {
    return "light";
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function DashboardShell({
  children,
  fallbackBasePath,
  profileDisplayName,
  subjectPhone,
  subjectEmail,
  signOutRedirectTo = "/login",
}: DashboardShellProps) {
  const [theme, setTheme] = useState<DashboardTheme>("light");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setTheme(resolveInitialTheme());
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [ready, theme]);

  return (
    <div
      className="dashboard-app-shell"
      data-dashboard-theme={theme}
      suppressHydrationWarning
    >
      <aside className="dashboard-rail">
        <div className="dashboard-rail-top">
          <DashboardRailHomeLink fallbackBasePath={fallbackBasePath} />
          <DashboardRailThemeToggle
            theme={theme}
            onChange={setTheme}
          />
        </div>

        <DashboardRailNav fallbackBasePath={fallbackBasePath} />

        <DashboardRailProfile
          displayName={profileDisplayName}
          signOutRedirectTo={signOutRedirectTo}
          subjectEmail={subjectEmail}
          subjectPhone={subjectPhone}
        />
      </aside>

      <div className="dashboard-stage">
        <div className="dashboard-stage-content">{children}</div>
      </div>
    </div>
  );
}
