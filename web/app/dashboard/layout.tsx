import Link from "next/link";

import { getLocations } from "@/lib/api";
import { requireAuth } from "@/lib/auth/session";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAuth();

  const locations = await getLocations();
  const primaryLocation = locations[0] ?? null;
  const primaryHref = primaryLocation
    ? buildDashboardLocationPath(primaryLocation, { tab: "schedule" })
    : "/dashboard";
  const coverageHref = primaryLocation
    ? buildDashboardLocationPath(primaryLocation, { tab: "coverage" })
    : "/dashboard";
  const teamHref = primaryLocation
    ? buildDashboardLocationPath(primaryLocation, { tab: "roster" })
    : "/dashboard";

  return (
    <>
      <style>{`
        .topbar-wrap,
        .footer {
          display: none !important;
        }

        .site-main {
          width: 100%;
          padding: 0;
        }

        .site-main > .shell {
          width: 100%;
          max-width: none;
          padding: 0;
        }
      `}</style>

      <div className="dashboard-app-shell">
        <aside className="dashboard-rail">
          <Link className="dashboard-rail-brand" href={primaryHref}>
            <span className="dashboard-rail-brand-mark">B</span>
            <span className="dashboard-rail-brand-copy">
              <strong>Backfill</strong>
              <small>Manager workspace</small>
            </span>
          </Link>

          <nav className="dashboard-rail-nav">
            <Link className="dashboard-rail-link" href={primaryHref}>
              <span className="dashboard-rail-link-icon">▦</span>
              <span>Week board</span>
            </Link>
            <Link className="dashboard-rail-link" href={coverageHref}>
              <span className="dashboard-rail-link-icon">◔</span>
              <span>Coverage</span>
            </Link>
            <Link className="dashboard-rail-link" href={teamHref}>
              <span className="dashboard-rail-link-icon">◉</span>
              <span>Team</span>
            </Link>
            <Link className="dashboard-rail-link" href="/dashboard/ops">
              <span className="dashboard-rail-link-icon">⋯</span>
              <span>Ops index</span>
            </Link>
          </nav>
        </aside>

        <div className="dashboard-stage">
          <div className="dashboard-stage-header">
            <div>
              <div className="dashboard-stage-kicker">Schedule-first operations</div>
              <h1>AI-native shift management</h1>
            </div>
            <div className="dashboard-stage-meta">
              <span className="dashboard-stage-meta-pill">Live board</span>
              <span className="dashboard-stage-meta-copy">
                Who works when, what is open, and what needs attention now.
              </span>
            </div>
          </div>
          <div className="dashboard-stage-content">{children}</div>
        </div>
      </div>
    </>
  );
}
