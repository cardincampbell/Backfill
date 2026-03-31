"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useTransition } from "react";
import { signOutClientSession } from "@/lib/auth/client-signout";

type DashboardRailNavProps = {
  fallbackBasePath: string;
};

type DashboardRailProfileProps = DashboardRailNavProps & {
  displayName: string;
  subjectPhone: string | null;
  locationCount: number;
};

const RESERVED_SEGMENTS = new Set(["ops", "locations", "shifts"]);

const NAV_ITEMS = [
  { key: "schedule", label: "Schedule", icon: "▦" },
  { key: "coverage", label: "Coverage", icon: "◔" },
  { key: "actions", label: "Actions", icon: "◎" },
  { key: "roster", label: "Team", icon: "◉" },
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

function buildSettingsHref(basePath: string): string {
  return `${basePath}?tab=settings`;
}

function getInitials(label: string): string {
  const parts = label
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "B";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function formatPhone(phone: string | null): string | null {
  if (!phone) return null;
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 4) return phone;
  return `••• ${digits.slice(-4)}`;
}

export function DashboardRailHomeLink({
  fallbackBasePath,
}: DashboardRailNavProps) {
  const pathname = usePathname();
  const basePath = buildActiveBasePath(pathname, fallbackBasePath);
  const href = pathname === "/dashboard/ops" ? "/dashboard" : `${basePath}?tab=schedule`;

  return (
    <Link className="dashboard-rail-brand" href={href}>
      <span className="dashboard-rail-brand-mark">B</span>
      <span className="dashboard-rail-brand-copy">
        <strong>Backfill</strong>
      </span>
    </Link>
  );
}

export function DashboardRailNav({ fallbackBasePath }: DashboardRailNavProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const basePath = buildActiveBasePath(pathname, fallbackBasePath);
  const currentTab =
    pathname === "/dashboard/ops" ? "locations" : searchParams.get("tab") ?? "schedule";

  return (
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
  );
}

export function DashboardRailProfile({
  fallbackBasePath,
  displayName,
  subjectPhone,
  locationCount,
}: DashboardRailProfileProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const basePath = buildActiveBasePath(pathname, fallbackBasePath);
  const currentTab =
    pathname === "/dashboard/ops" ? "locations" : searchParams.get("tab") ?? "schedule";
  const settingsHref = buildSettingsHref(basePath);
  const maskedPhone = formatPhone(subjectPhone);
  const [signingOut, startSignOutTransition] = useTransition();

  function handleSignOut() {
    startSignOutTransition(async () => {
      await signOutClientSession("/login");
    });
  }

  return (
    <div className="dashboard-rail-profile">
      <div className="dashboard-rail-profile-header">
        <div className="dashboard-rail-profile-avatar">{getInitials(displayName)}</div>
        <div className="dashboard-rail-profile-copy">
          <strong>{displayName}</strong>
          <span>{maskedPhone ?? `${locationCount} ${locationCount === 1 ? "location" : "locations"}`}</span>
        </div>
      </div>

      <div className="dashboard-rail-profile-actions">
        <Link
          className="dashboard-rail-profile-link"
          data-active={pathname === "/dashboard/ops"}
          href="/dashboard/ops"
        >
          Locations
        </Link>
        <Link
          className="dashboard-rail-profile-link"
          data-active={currentTab === "settings" && pathname !== "/dashboard/ops"}
          href={settingsHref}
        >
          Settings
        </Link>
        <button
          className="dashboard-rail-profile-link dashboard-rail-profile-signout"
          disabled={signingOut}
          onClick={handleSignOut}
          type="button"
        >
          {signingOut ? "Signing out…" : "Sign out"}
        </button>
      </div>
    </div>
  );
}
