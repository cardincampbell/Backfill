"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

type DashboardRailNavProps = {
  fallbackBasePath: string;
};

const RESERVED_SEGMENTS = new Set(["ops", "locations", "shifts"]);

const NAV_ITEMS = [
  { key: "schedule", label: "Schedule", icon: "▦" },
  { key: "coverage", label: "Coverage", icon: "◔" },
  { key: "actions", label: "Actions", icon: "◎" },
  { key: "exceptions", label: "Issues", icon: "!" },
  { key: "roster", label: "Team", icon: "◉" },
  { key: "imports", label: "Imports", icon: "↥" },
  { key: "overview", label: "Overview", icon: "◌" },
  { key: "settings", label: "Settings", icon: "⋯" },
] as const;

function buildActiveBasePath(pathname: string, fallbackBasePath: string): string {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length >= 3 && segments[0] === "dashboard") {
    const section = segments[1];
    if (!RESERVED_SEGMENTS.has(section)) {
      return `/dashboard/${segments[1]}/${segments[2]}`;
    }
  }
  return fallbackBasePath;
}

export function DashboardRailNav({ fallbackBasePath }: DashboardRailNavProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const basePath = buildActiveBasePath(pathname, fallbackBasePath);
  const currentTab = pathname === "/dashboard/ops" ? "ops" : searchParams.get("tab") ?? "schedule";

  return (
    <>
      <nav className="dashboard-rail-nav">
        {NAV_ITEMS.map((item) => {
          const params = new URLSearchParams();
          for (const key of ["week_start", "job_id", "row", "shift_id"]) {
            const value = searchParams.get(key);
            if (value) {
              params.set(key, value);
            }
          }
          if (item.key !== "schedule") {
            params.set("tab", item.key);
          }

          const href = params.toString() ? `${basePath}?${params.toString()}` : basePath;

          return (
            <Link
              key={item.key}
              className="dashboard-rail-link"
              data-active={currentTab === item.key}
              href={href}
            >
              <span className="dashboard-rail-link-icon">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="dashboard-rail-nav dashboard-rail-nav-secondary">
        <Link className="dashboard-rail-link" data-active={currentTab === "ops"} href="/dashboard/ops">
          <span className="dashboard-rail-link-icon">≡</span>
          <span>All locations</span>
        </Link>
      </div>
    </>
  );
}
