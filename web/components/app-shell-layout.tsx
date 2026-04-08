"use client";

import { AppSessionGate } from "@/components/app-session-gate";
import { AppWorkspaceProvider } from "@/components/app-workspace";
import DashboardShell from "@/components/dashboard/DashboardShell";
import { LocationEntryProvider } from "@/components/location-entry-provider";
import type { AppShellSidebarTab } from "@/lib/app-shell-prefs";
import type { Workspace } from "@/lib/api/workspace";
import type { AuthMeResponse } from "@/lib/api/auth";
import { usePathname } from "next/navigation";

type AppShellLayoutProps = {
  children: React.ReactNode;
  initialSidebarTab: AppShellSidebarTab;
  initialSession: AuthMeResponse | null;
  initialWorkspace: Workspace | null;
};

function resolveActiveNav(pathname: string): string {
  if (pathname === "/team") {
    return "Team";
  }
  if (pathname === "/activity") {
    return "Activity";
  }
  if (pathname === "/settings" || pathname.startsWith("/settings/")) {
    return "Settings";
  }
  if (pathname.startsWith("/location/") || pathname.startsWith("/scheduler/")) {
    return "";
  }
  return "Overview";
}

export function AppShellLayout({
  children,
  initialSidebarTab,
  initialSession,
  initialWorkspace,
}: AppShellLayoutProps) {
  const pathname = usePathname();
  const activeNav = resolveActiveNav(pathname);

  return (
    <AppSessionGate initialSession={initialSession}>
      <AppWorkspaceProvider initialWorkspace={initialWorkspace}>
        <LocationEntryProvider>
          <DashboardShell
            activeNav={activeNav}
            initialSidebarTab={initialSidebarTab}
          >
            {children}
          </DashboardShell>
        </LocationEntryProvider>
      </AppWorkspaceProvider>
    </AppSessionGate>
  );
}
