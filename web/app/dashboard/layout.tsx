import { DashboardShell } from "@/components/dashboard-shell";
import { getWorkspace } from "@/lib/api/workspace";
import {
  buildDashboardLocationPathFromAny,
} from "@/lib/dashboard-paths";
import { redirect } from "next/navigation";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const workspace = await getWorkspace();

  let primaryBasePath = "/dashboard";
  let profileDisplayName = "Backfill";
  let subjectPhone: string | null = null;
  let subjectEmail: string | null = null;
  let signOutRedirectTo = "/login";

  if (workspace) {
    if (workspace.onboarding_required) {
      redirect("/onboarding");
    }
    const primaryLocation = workspace.locations[0] ?? null;
    primaryBasePath = primaryLocation
      ? buildDashboardLocationPathFromAny(primaryLocation)
      : "/dashboard/locations";
    profileDisplayName =
      workspace.user.full_name ??
      workspace.user.email ??
      primaryLocation?.business_name ??
      "Backfill";
    subjectEmail = workspace.user.email ?? null;
    subjectPhone = workspace.user.primary_phone_e164 ?? null;
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

      <DashboardShell
        fallbackBasePath={primaryBasePath}
        profileDisplayName={profileDisplayName}
        signOutRedirectTo={signOutRedirectTo}
        subjectEmail={subjectEmail}
        subjectPhone={subjectPhone}
      >
        {children}
      </DashboardShell>
    </>
  );
}
