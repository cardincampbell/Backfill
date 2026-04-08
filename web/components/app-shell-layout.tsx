"use client";

import { AppSessionGate } from "@/components/app-session-gate";
import { AppWorkspaceProvider } from "@/components/app-workspace";
import DashboardShell from "@/components/dashboard/DashboardShell";
import type { AppShellSidebarTab } from "@/lib/app-shell-prefs";
import type { Workspace } from "@/lib/api/workspace";
import { usePathname } from "next/navigation";

type AppShellLayoutProps = {
  children: React.ReactNode;
  initialSidebarTab: AppShellSidebarTab;
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
  initialWorkspace,
}: AppShellLayoutProps) {
  const pathname = usePathname();
  const activeNav = resolveActiveNav(pathname);

  return (
    <AppSessionGate>
      <AppWorkspaceProvider initialWorkspace={initialWorkspace}>
        <DashboardShell
          activeNav={activeNav}
          initialSidebarTab={initialSidebarTab}
        >
          {children}
        </DashboardShell>
      </AppWorkspaceProvider>
    </AppSessionGate>
  );
}
