import {
  DashboardRailHomeLink,
  DashboardRailNav,
  DashboardRailProfile,
} from "@/components/dashboard-rail-nav";
import { getV2Workspace } from "@/lib/api/v2-workspace";
import {
  buildDashboardLocationPathFromAny,
} from "@/lib/dashboard-paths";
import { redirect } from "next/navigation";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const v2Workspace = await getV2Workspace();

  let primaryBasePath = "/dashboard";
  let profileDisplayName = "Backfill";
  let subjectPhone: string | null = null;
  let locationCount = 0;
  let signOutRedirectTo = "/login";

  if (v2Workspace) {
    if (v2Workspace.onboarding_required) {
      redirect("/onboarding");
    }
    const primaryLocation = v2Workspace.locations[0] ?? null;
    primaryBasePath = primaryLocation
      ? buildDashboardLocationPathFromAny(primaryLocation)
      : "/dashboard/ops";
    profileDisplayName =
      v2Workspace.user.full_name ??
      v2Workspace.user.email ??
      primaryLocation?.business_name ??
      "Backfill";
    subjectPhone = v2Workspace.user.primary_phone_e164 ?? null;
    locationCount = v2Workspace.locations.length;
  } else {
    redirect("/login");
  }

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
            locationCount={locationCount}
            signOutRedirectTo={signOutRedirectTo}
            subjectPhone={subjectPhone}
          />
        </aside>

        <div className="dashboard-stage">
          <div className="dashboard-stage-content">{children}</div>
        </div>
      </div>
    </>
  );
}
