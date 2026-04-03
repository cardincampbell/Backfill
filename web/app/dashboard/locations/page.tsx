import { redirect } from "next/navigation";

import { AccountLocationsPanel } from "@/components/account-locations-panel";
import { getWorkspace } from "@/lib/api/workspace";

export const dynamic = "force-dynamic";

export default async function DashboardLocationsPage() {
  const workspace = await getWorkspace();
  if (!workspace) {
    redirect("/login");
  }

  return (
    <main className="section">
      <AccountLocationsPanel workspace={workspace} />
    </main>
  );
}
