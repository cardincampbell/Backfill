import {
  DashboardRailHomeLink,
  DashboardRailNav,
  DashboardRailProfile,
} from "@/components/dashboard-rail-nav";
import { getLocations } from "@/lib/api";
import { requireAuth } from "@/lib/auth/session";
import { buildDashboardLocationPath } from "@/lib/dashboard-paths";
import { redirect } from "next/navigation";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await requireAuth();
  if (session.onboarding_required) {
    redirect("/onboarding");
  }

  const locations = await getLocations();
  const primaryLocation = locations[0] ?? null;
  const primaryBasePath = primaryLocation
    ? buildDashboardLocationPath(primaryLocation)
    : "/dashboard";
  const profileDisplayName =
    session.organization?.name ??
    primaryLocation?.organization_name ??
    primaryLocation?.place_brand_name ??
    primaryLocation?.name ??
    "Backfill";

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
          <DashboardRailHomeLink fallbackBasePath={primaryBasePath} />

          <DashboardRailNav fallbackBasePath={primaryBasePath} />

          <DashboardRailProfile
            displayName={profileDisplayName}
            fallbackBasePath={primaryBasePath}
            locationCount={locations.length}
            subjectPhone={session.subject_phone}
          />
        </aside>

        <div className="dashboard-stage">
          <div className="dashboard-stage-content">{children}</div>
        </div>
      </div>
    </>
  );
}
