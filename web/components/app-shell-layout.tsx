"use client";

import { AppSessionGate } from "@/components/app-session-gate";
import DashboardShell from "@/components/source-dashboard/DashboardShell";
import type { AppShellSidebarTab } from "@/lib/app-shell-prefs";
import { usePathname } from "next/navigation";

type AppShellLayoutProps = {
  children: React.ReactNode;
  initialSidebarTab: AppShellSidebarTab;
};

function resolveActiveNav(pathname: string): string {
  if (pathname === "/team") {
    return "Team";
  }
  if (pathname === "/settings" || pathname.startsWith("/settings/")) {
    return "Settings";
  }
  return "Overview";
}

export function AppShellLayout({
  children,
  initialSidebarTab,
}: AppShellLayoutProps) {
  const pathname = usePathname();
  const activeNav = resolveActiveNav(pathname);

  return (
    <AppSessionGate>
      <DashboardShell
        activeNav={activeNav}
        initialSidebarTab={initialSidebarTab}
      >
        {children}
      </DashboardShell>
    </AppSessionGate>
  );
}
