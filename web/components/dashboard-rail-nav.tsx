"use client";

import {
  Bot,
  Building2,
  CalendarDays,
  Layers3,
  LayoutGrid,
  MoonStar,
  Sparkles,
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
export type DashboardRailMode = "navigate" | "copilot";

type DashboardRailThemeToggleProps = {
  theme: DashboardTheme;
  onChange(theme: DashboardTheme): void;
};

type DashboardRailModeToggleProps = {
  mode: DashboardRailMode;
  onChange(mode: DashboardRailMode): void;
};

type DashboardRailCopilotProps = {
  businessCount: number;
  locationCount: number;
  fallbackBasePath: string;
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
  return (
    segments.length >= 3 &&
    segments[0] === "dashboard" &&
    !RESERVED_SEGMENTS.has(segments[1])
  );
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
  const parts = label.trim().split(/\s+/).filter(Boolean);
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

function buildTabHref(
  basePath: string,
  searchParams: { get(key: string): string | null },
  tab: string,
): string {
  if (tab === "locations") {
    return "/dashboard/locations";
  }
  const params = new URLSearchParams();
  for (const key of ["week_start", "job_id", "row", "shift_id"]) {
    const value = searchParams.get(key);
    if (value) {
      params.set(key, value);
    }
  }
  if (tab !== "schedule") {
    params.set("tab", tab);
  }
  return params.toString() ? `${basePath}?${params.toString()}` : basePath;
}

function resolveCopilotState(
  pathname: string,
  searchParams: { get(key: string): string | null },
  fallbackBasePath: string,
  businessCount: number,
  locationCount: number,
) {
  const basePath = buildActiveBasePath(pathname, fallbackBasePath);
  const currentView = resolveCurrentRailView(pathname, searchParams);

  if (pathname === "/dashboard/account") {
    return {
      title: "Account upkeep",
      summary:
        "Keep your personal profile, sign-in details, and session access clean without mixing in business controls.",
      stats: [
        { label: "Businesses", value: String(businessCount) },
        { label: "Locations", value: String(locationCount) },
      ],
      links: [
        { label: "Open locations", href: "/dashboard/locations", meta: "Businesses and managers" },
        { label: "Primary dashboard", href: fallbackBasePath, meta: "Jump back into operations" },
      ],
      notes: [
        "Verify your phone and email are still accurate.",
        "Use location settings from the location itself, not from account.",
      ],
      currentView,
    };
  }

  if (pathname === "/dashboard/locations" || pathname === "/dashboard/ops") {
    return {
      title: "Multi-location ops",
      summary:
        "Operate multiple businesses and locations from one account, then jump directly into schedule, team, or settings per site.",
      stats: [
        { label: "Businesses", value: String(businessCount) },
        { label: "Locations", value: String(locationCount) },
      ],
      links: [
        { label: "Open first location", href: fallbackBasePath, meta: "Go to the live operating view" },
        { label: "Account settings", href: "/dashboard/account", meta: "Profile and sign-in" },
      ],
      notes: [
        "Create the parent business first, then attach locations beneath it.",
        "Invite managers from the location card so access stays scoped correctly.",
      ],
      currentView,
    };
  }

  if (isLocationDashboardPath(pathname)) {
    const tab = searchParams.get("tab") ?? "schedule";
    const byTab = {
      schedule: {
        title: "Location control",
        summary:
          "Use the live board as the main operating surface, then move into coverage or team only when the board tells you to.",
        notes: [
          "Scan the week first, then act on the hotspots card.",
          "Use quick links to jump between schedule, team, and settings without losing context.",
        ],
      },
      coverage: {
        title: "Coverage focus",
        summary:
          "Stay on the coverage queue until gaps are either filled, queued, or escalated for review.",
        notes: [
          "Start with active offers, then review standby depth before broadcasting wider.",
          "Use manager actions for approvals and edge cases that cannot auto-resolve.",
        ],
      },
      actions: {
        title: "Manager actions",
        summary:
          "This view is for approvals, exceptions, and anything the automation deliberately left to a human.",
        notes: [
          "Resolve the top decision first, then return to the queue.",
          "If a shift is already moving, avoid duplicating coverage from another screen.",
        ],
      },
      roster: {
        title: "Team operations",
        summary:
          "Manage enrollments, roles, reliability, and blast readiness here before changing any coverage rules.",
        notes: [
          "Reliability and role coverage should drive who gets priority.",
          "Only add workers to a location if they can actually cover there.",
        ],
      },
      settings: {
        title: "Location setup",
        summary:
          "Tune policies, integrations, and Backfill Shifts settings at the location level so behavior stays predictable.",
        notes: [
          "Keep manager approval rules tight for sensitive shifts.",
          "Use location settings for policy and account settings for the user profile only.",
        ],
      },
    } as const;

    const tabState = byTab[tab as keyof typeof byTab] ?? byTab.schedule;

    return {
      title: tabState.title,
      summary: tabState.summary,
      stats: [
        { label: "Businesses", value: String(businessCount) },
        { label: "Locations", value: String(locationCount) },
      ],
      links: [
        { label: "Schedule", href: buildTabHref(basePath, searchParams, "schedule"), meta: "Live board" },
        { label: "Coverage", href: buildTabHref(basePath, searchParams, "coverage"), meta: "Queue and standby" },
        { label: "Team", href: buildTabHref(basePath, searchParams, "roster"), meta: "Workers and reliability" },
      ],
      notes: tabState.notes,
      currentView,
    };
  }

  return {
    title: "Backfill Copilot",
    summary:
      "Use the rail to move between the operational surface, the multi-location overview, and your account controls.",
    stats: [
      { label: "Businesses", value: String(businessCount) },
      { label: "Locations", value: String(locationCount) },
    ],
    links: [
      { label: "Locations", href: "/dashboard/locations", meta: "Overview" },
      { label: "Account", href: "/dashboard/account", meta: "Profile" },
    ],
    notes: ["Use the shell search to jump quickly to locations, team, or coverage."],
    currentView,
  };
}

export function DashboardRailHomeLink() {
  return (
    <Link className="dashboard-rail-brand" href="/dashboard">
      <span className="dashboard-rail-brand-mark">B</span>
      <span className="dashboard-rail-brand-copy">
        <strong>Backfill</strong>
      </span>
    </Link>
  );
}

export function DashboardRailModeToggle({
  mode,
  onChange,
}: DashboardRailModeToggleProps) {
  return (
    <div className="dashboard-rail-mode-toggle">
      <button
        aria-pressed={mode === "navigate"}
        className="dashboard-rail-mode-button"
        data-active={mode === "navigate"}
        onClick={() => onChange("navigate")}
        type="button"
      >
        <LayoutGrid size={15} strokeWidth={1.85} />
        <span>Navigate</span>
      </button>
      <button
        aria-pressed={mode === "copilot"}
        className="dashboard-rail-mode-button"
        data-active={mode === "copilot"}
        onClick={() => onChange("copilot")}
        type="button"
      >
        <Sparkles size={15} strokeWidth={1.85} />
        <span>Copilot</span>
      </button>
    </div>
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
        const href = buildTabHref(basePath, searchParams, item.key);

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

export function DashboardRailCopilot({
  businessCount,
  locationCount,
  fallbackBasePath,
}: DashboardRailCopilotProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const state = resolveCopilotState(
    pathname,
    searchParams,
    fallbackBasePath,
    businessCount,
    locationCount,
  );

  return (
    <div className="dashboard-copilot-panel">
      <div className="dashboard-copilot-head">
        <span className="dashboard-copilot-badge">
          <Bot size={14} strokeWidth={1.85} />
          Copilot
        </span>
        <strong>{state.title}</strong>
        <p>{state.summary}</p>
      </div>

      <div className="dashboard-copilot-stats">
        {state.stats.map((item) => (
          <div className="dashboard-copilot-stat" key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>

      <div className="dashboard-copilot-section">
        <span className="dashboard-copilot-label">Suggested paths</span>
        <div className="dashboard-copilot-links">
          {state.links.map((link) => (
            <Link className="dashboard-copilot-link" href={link.href} key={link.label}>
              <strong>{link.label}</strong>
              <span>{link.meta}</span>
            </Link>
          ))}
        </div>
      </div>

      <div className="dashboard-copilot-section">
        <span className="dashboard-copilot-label">Focus right now</span>
        <div className="dashboard-copilot-notes">
          {state.notes.map((note) => (
            <div className="dashboard-copilot-note" key={note}>
              <span className="dashboard-copilot-note-dot" aria-hidden="true" />
              <span>{note}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
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
    (subjectEmail && subjectEmail !== displayName
      ? subjectEmail
      : "Backfill account");
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
