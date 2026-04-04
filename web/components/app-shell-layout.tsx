"use client";

import { AppSessionGate } from "@/components/app-session-gate";
import DashboardShell from "@/components/source-dashboard/DashboardShell";
import { usePathname } from "next/navigation";

type AppShellLayoutProps = {
  children: React.ReactNode;
};

function resolveActiveNav(pathname: string): string {
  if (pathname === "/team") {
    return "Team";
  }
  if (pathname === "/settings") {
    return "Settings";
  }
  return "Overview";
}

export function AppShellLayout({ children }: AppShellLayoutProps) {
  const pathname = usePathname();
  const activeNav = resolveActiveNav(pathname);

  return (
    <AppSessionGate enforceRedirects={false}>
      <DashboardShell activeNav={activeNav}>{children}</DashboardShell>
    </AppSessionGate>
  );
}
