"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
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
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  function handleSignOut() {
    startSignOutTransition(async () => {
      await signOutClientSession("/login");
    });
  }

  return (
    <div className="dashboard-rail-profile" ref={menuRef}>
      <button
        className="dashboard-rail-profile-trigger"
        onClick={() => setMenuOpen((current) => !current)}
        type="button"
      >
        <div className="dashboard-rail-profile-avatar">{getInitials(displayName)}</div>
        <div className="dashboard-rail-profile-copy">
          <strong>{displayName}</strong>
          <span>{maskedPhone ?? `${locationCount} ${locationCount === 1 ? "location" : "locations"}`}</span>
        </div>
        <span className="dashboard-rail-profile-caret" aria-hidden="true">
          {menuOpen ? "▴" : "▾"}
        </span>
      </button>

      {menuOpen ? (
        <div className="dashboard-rail-profile-menu">
          <Link
            className="dashboard-rail-profile-item"
            data-active={pathname === "/dashboard/ops"}
            href="/dashboard/ops"
            onClick={() => setMenuOpen(false)}
          >
            Locations
          </Link>
          <Link
            className="dashboard-rail-profile-item"
            data-active={currentTab === "settings" && pathname !== "/dashboard/ops"}
            href={settingsHref}
            onClick={() => setMenuOpen(false)}
          >
            Settings
          </Link>
          <button
            className="dashboard-rail-profile-item dashboard-rail-profile-signout"
            disabled={signingOut}
            onClick={handleSignOut}
            type="button"
          >
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
      ) : null}
      <div className="dashboard-rail-profile-meta">
        {locationCount} {locationCount === 1 ? "location" : "locations"}
      </div>
    </div>
  );
}
