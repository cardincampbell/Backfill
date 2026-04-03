"use client";

import { Building2, Search, Settings2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  DashboardRailCopilot,
  DashboardRailHomeLink,
  DashboardRailModeToggle,
  DashboardRailNav,
  DashboardRailProfile,
  DashboardRailThemeToggle,
  type DashboardRailMode,
  type DashboardTheme,
} from "@/components/dashboard-rail-nav";

type DashboardShellProps = {
  children: React.ReactNode;
  businessCount: number;
  fallbackBasePath: string;
  locationCount: number;
  profileDisplayName: string;
  subjectPhone: string | null;
  subjectEmail: string | null;
  signOutRedirectTo?: string;
};

type QuickJumpItem = {
  label: string;
  description: string;
  href: string;
};

const THEME_STORAGE_KEY = "backfill-dashboard-theme";
const MODE_STORAGE_KEY = "backfill-dashboard-rail-mode";

function resolveInitialTheme(): DashboardTheme {
  if (typeof window === "undefined") {
    return "light";
  }
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function resolveInitialRailMode(): DashboardRailMode {
  if (typeof window === "undefined") {
    return "navigate";
  }
  const stored = window.localStorage.getItem(MODE_STORAGE_KEY);
  return stored === "copilot" ? "copilot" : "navigate";
}

function buildLocationBasePath(pathname: string, fallbackBasePath: string): string {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length >= 3 && segments[0] === "dashboard") {
    return `/dashboard/${segments[1]}/${segments[2]}`;
  }
  return fallbackBasePath;
}

function buildLocationHref(
  basePath: string,
  searchParams: { get(key: string): string | null },
  tab: string,
) {
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

function resolveUtilityMeta(
  pathname: string,
  searchParams: { get(key: string): string | null },
) {
  if (pathname === "/dashboard/locations" || pathname === "/dashboard/ops") {
    return {
      kicker: "Overview",
      title: "Multi-location dashboard",
      description:
        "Monitor your footprint, jump into a business, and manage managers from one operating surface.",
    };
  }

  if (pathname === "/dashboard/account") {
    return {
      kicker: "Personal",
      title: "Account settings",
      description:
        "Update your profile and sign-in details without mixing in business or location controls.",
    };
  }

  if (pathname.startsWith("/dashboard/")) {
    const tab = searchParams.get("tab") ?? "schedule";
    const copyByTab = {
      schedule: ["Operations", "Location dashboard", "Run the live board, inspect staffing, and manage the week from one place."],
      coverage: ["Coverage", "Coverage queue", "Advance active fills, watch standby depth, and resolve open shifts quickly."],
      actions: ["Approvals", "Manager actions", "Review exceptions and push the next human decision without losing context."],
      roster: ["Team", "Roster manager", "Keep roles, enrollments, and reliability aligned with what the location actually needs."],
      settings: ["Settings", "Location settings", "Tune policies, integrations, and launch state at the location level."],
    } as const;
    const active = copyByTab[tab as keyof typeof copyByTab] ?? copyByTab.schedule;
    return { kicker: active[0], title: active[1], description: active[2] };
  }

  return {
    kicker: "Dashboard",
    title: "Backfill",
    description: "Operate staffing, coverage, and team flows from a single control surface.",
  };
}

function resolveQuickJumpItems(
  pathname: string,
  searchParams: { get(key: string): string | null },
  fallbackBasePath: string,
): QuickJumpItem[] {
  const basePath = buildLocationBasePath(pathname, fallbackBasePath);

  const items: QuickJumpItem[] = [
    {
      label: "Locations",
      description: "Businesses, sites, and managers",
      href: "/dashboard/locations",
    },
    {
      label: "Account settings",
      description: "Profile and sign-in",
      href: "/dashboard/account",
    },
  ];

  if (basePath !== "/dashboard/locations") {
    items.unshift(
      {
        label: "Schedule",
        description: "Live board and upcoming shifts",
        href: buildLocationHref(basePath, searchParams, "schedule"),
      },
      {
        label: "Coverage",
        description: "Queue, offers, and standby",
        href: buildLocationHref(basePath, searchParams, "coverage"),
      },
      {
        label: "Team",
        description: "Workers, roles, and reliability",
        href: buildLocationHref(basePath, searchParams, "roster"),
      },
    );
  }

  return items;
}

function DashboardQuickJump({ items }: { items: QuickJumpItem[] }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return items.slice(0, 5);
    }
    return items.filter((item) => {
      const haystack = `${item.label} ${item.description}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [items, query]);

  return (
    <div
      className="dashboard-quickjump"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setOpen(false);
        }
      }}
    >
      <label className="dashboard-quickjump-input-wrap">
        <Search className="dashboard-quickjump-icon" size={16} strokeWidth={1.8} />
        <input
          className="dashboard-quickjump-input"
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setOpen(true)}
          placeholder="Jump to schedule, coverage, team, or settings"
          type="search"
          value={query}
        />
      </label>

      {open ? (
        <div className="dashboard-quickjump-results">
          {matches.length ? (
            matches.map((item) => (
              <Link
                className="dashboard-quickjump-option"
                href={item.href}
                key={item.href}
                onClick={() => {
                  setOpen(false);
                  setQuery("");
                }}
              >
                <strong>{item.label}</strong>
                <span>{item.description}</span>
              </Link>
            ))
          ) : (
            <div className="dashboard-quickjump-empty">
              No matching dashboard views.
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

export function DashboardShell({
  children,
  businessCount,
  fallbackBasePath,
  locationCount,
  profileDisplayName,
  subjectPhone,
  subjectEmail,
  signOutRedirectTo = "/login",
}: DashboardShellProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const utilityMeta = resolveUtilityMeta(pathname, searchParams);
  const quickJumpItems = resolveQuickJumpItems(
    pathname,
    searchParams,
    fallbackBasePath,
  );

  const [theme, setTheme] = useState<DashboardTheme>("light");
  const [railMode, setRailMode] = useState<DashboardRailMode>("navigate");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setTheme(resolveInitialTheme());
    setRailMode(resolveInitialRailMode());
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [ready, theme]);

  useEffect(() => {
    if (!ready) return;
    window.localStorage.setItem(MODE_STORAGE_KEY, railMode);
  }, [ready, railMode]);

  return (
    <div
      className="dashboard-app-shell"
      data-dashboard-theme={theme}
      suppressHydrationWarning
    >
      <aside className="dashboard-rail">
        <div className="dashboard-rail-top">
          <DashboardRailHomeLink />
          <DashboardRailModeToggle mode={railMode} onChange={setRailMode} />
        </div>

        {railMode === "navigate" ? (
          <DashboardRailNav fallbackBasePath={fallbackBasePath} />
        ) : (
          <DashboardRailCopilot
            businessCount={businessCount}
            fallbackBasePath={fallbackBasePath}
            locationCount={locationCount}
          />
        )}

        <DashboardRailThemeToggle theme={theme} onChange={setTheme} />

        <DashboardRailProfile
          displayName={profileDisplayName}
          signOutRedirectTo={signOutRedirectTo}
          subjectEmail={subjectEmail}
          subjectPhone={subjectPhone}
        />
      </aside>

      <div className="dashboard-stage">
        <header className="dashboard-utilitybar">
          <div className="dashboard-utilitybar-copy">
            <span className="dashboard-utilitybar-kicker">{utilityMeta.kicker}</span>
            <strong>{utilityMeta.title}</strong>
            <span>{utilityMeta.description}</span>
          </div>

          <div className="dashboard-utilitybar-controls">
            <DashboardQuickJump items={quickJumpItems} />
            <div className="dashboard-utilitybar-actions">
              <Link
                aria-label="Open locations"
                className="dashboard-utilitybar-action"
                href="/dashboard/locations"
              >
                <Building2 size={16} strokeWidth={1.8} />
                <span className="dashboard-utilitybar-badge">{locationCount}</span>
              </Link>
              <Link
                aria-label="Open account settings"
                className="dashboard-utilitybar-action"
                href="/dashboard/account"
              >
                <Settings2 size={16} strokeWidth={1.8} />
              </Link>
            </div>
          </div>
        </header>

        <div className="dashboard-stage-content">{children}</div>
      </div>
    </div>
  );
}
