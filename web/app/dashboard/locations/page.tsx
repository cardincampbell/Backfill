import { redirect } from "next/navigation";

import { AccountLocationsPanelV2 } from "@/components/account-locations-panel-v2";
import { getV2Workspace } from "@/lib/api/v2-workspace";

export const dynamic = "force-dynamic";

export default async function DashboardLocationsPage() {
  const v2Workspace = await getV2Workspace();
  if (!v2Workspace) {
    redirect("/login");
  }

  return (
    <main className="section">
      <AccountLocationsPanelV2 workspace={v2Workspace} />
    </main>
  );
}
