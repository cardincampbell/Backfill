import Link from "next/link";

import { DashboardRailNav } from "@/components/dashboard-rail-nav";
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
  const primaryBasePath = primaryLocation
    ? buildDashboardLocationPath(primaryLocation)
    : "/dashboard";
  const primaryHref = primaryLocation
    ? buildDashboardLocationPath(primaryLocation, { tab: "schedule" })
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
            </span>
          </Link>

          <DashboardRailNav fallbackBasePath={primaryBasePath} />
        </aside>

        <div className="dashboard-stage">
          <div className="dashboard-stage-content">{children}</div>
        </div>
      </div>
    </>
  );
}
