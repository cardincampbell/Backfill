"use client";

import {
  Building2,
  CalendarDays,
  Layers3,
  MoonStar,
  SunMedium,
  Users,
  Waves,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { signOutClientSession } from "@/lib/auth/client-signout";

type DashboardRailNavProps = {
  fallbackBasePath: string;
};

type DashboardRailProfileProps = {
  displayName: string;
  subjectPhone: string | null;
  subjectEmail: string | null;
  signOutRedirectTo?: string;
};

export type DashboardTheme = "light" | "dark";

type DashboardRailThemeToggleProps = {
  theme: DashboardTheme;
  onChange(theme: DashboardTheme): void;
};

const RESERVED_SEGMENTS = new Set(["account", "ops", "locations", "shifts"]);

const NAV_ITEMS = [
  { key: "schedule", label: "Schedule", icon: CalendarDays },
  { key: "coverage", label: "Coverage", icon: Waves },
  { key: "actions", label: "Actions", icon: Layers3 },
  { key: "roster", label: "Team", icon: Users },
  { key: "locations", label: "Locations", icon: Building2 },
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

function isLocationDashboardPath(pathname: string): boolean {
  const segments = pathname.split("/").filter(Boolean);
  return segments.length >= 3 && segments[0] === "dashboard" && !RESERVED_SEGMENTS.has(segments[1]);
}

function resolveCurrentRailView(
  pathname: string,
  searchParams: { get(key: string): string | null },
): string | null {
  if (pathname === "/dashboard/ops" || pathname === "/dashboard/locations") {
    return "locations";
  }
  if (pathname === "/dashboard/account") {
    return "account";
  }
  if (isLocationDashboardPath(pathname)) {
    const tab = searchParams.get("tab") ?? "schedule";
    return tab === "settings" ? "locations" : tab;
  }
  return null;
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
  fallbackBasePath: _fallbackBasePath,
}: DashboardRailNavProps) {
  return (
    <Link className="dashboard-rail-brand" href="/dashboard">
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
  const currentView = resolveCurrentRailView(pathname, searchParams);

  return (
    <nav className="dashboard-rail-nav">
      {NAV_ITEMS.map((item) => {
        const href =
          item.key === "locations"
            ? "/dashboard/locations"
            : (() => {
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
                return params.toString() ? `${basePath}?${params.toString()}` : basePath;
              })();

        return (
          <Link
            key={item.key}
            className="dashboard-rail-link"
            data-active={currentView === item.key}
            href={href}
          >
            <span className="dashboard-rail-link-icon">
              <item.icon size={17} strokeWidth={1.9} />
            </span>
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function DashboardRailThemeToggle({
  theme,
  onChange,
}: DashboardRailThemeToggleProps) {
  return (
    <div className="dashboard-rail-theme">
      <button
        aria-pressed={theme === "light"}
        className="dashboard-rail-theme-button"
        data-active={theme === "light"}
        onClick={() => onChange("light")}
        type="button"
      >
        <SunMedium size={15} strokeWidth={1.8} />
        <span>Light</span>
      </button>
      <button
        aria-pressed={theme === "dark"}
        className="dashboard-rail-theme-button"
        data-active={theme === "dark"}
        onClick={() => onChange("dark")}
        type="button"
      >
        <MoonStar size={15} strokeWidth={1.8} />
        <span>Dark</span>
      </button>
    </div>
  );
}

export function DashboardRailProfile({
  displayName,
  subjectPhone,
  subjectEmail,
  signOutRedirectTo = "/login",
}: DashboardRailProfileProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentView = resolveCurrentRailView(pathname, searchParams);
  const maskedPhone = formatPhone(subjectPhone);
  const secondaryLabel =
    maskedPhone ??
    (subjectEmail && subjectEmail !== displayName ? subjectEmail : "Backfill account");
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
      await signOutClientSession(signOutRedirectTo);
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
          <span>{secondaryLabel}</span>
        </div>
        <span className="dashboard-rail-profile-caret" aria-hidden="true">
          {menuOpen ? "▴" : "▾"}
        </span>
      </button>

      {menuOpen ? (
        <div className="dashboard-rail-profile-menu">
          <Link
            className="dashboard-rail-profile-item"
            data-active={currentView === "account"}
            href="/dashboard/account"
            onClick={() => setMenuOpen(false)}
          >
            Account
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
    </div>
  );
}
