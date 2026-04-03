import { redirect } from "next/navigation";
import { getWorkspace } from "@/lib/api/workspace";
import { buildDashboardLocationPathFromAny } from "@/lib/dashboard-paths";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const workspace = await getWorkspace();
  if (!workspace) {
    redirect("/login");
  }

  if (!workspace.locations.length) {
    redirect("/dashboard/locations");
  }

  redirect(
    buildDashboardLocationPathFromAny(workspace.locations[0], {
      tab: "schedule",
    }),
  );
}
