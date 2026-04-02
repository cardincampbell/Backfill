import { redirect } from "next/navigation";
import { getV2Workspace } from "@/lib/api/v2-workspace";
import { buildDashboardLocationPathFromAny } from "@/lib/dashboard-paths";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const v2Workspace = await getV2Workspace();
  if (!v2Workspace) {
    redirect("/login");
  }

  if (!v2Workspace.locations.length) {
    redirect("/dashboard/locations");
  }

  redirect(
    buildDashboardLocationPathFromAny(v2Workspace.locations[0], {
      tab: "schedule",
    }),
  );
}
