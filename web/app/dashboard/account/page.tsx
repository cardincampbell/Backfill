import { redirect } from "next/navigation";

import { AccountSettingsPanelV2 } from "@/components/account-settings-panel-v2";
import { getV2AuthMe } from "@/lib/api/v2-auth";

export const dynamic = "force-dynamic";

export default async function DashboardAccountPage() {
  const authMe = await getV2AuthMe();
  if (!authMe) {
    redirect("/login");
  }

  return (
    <main className="section">
      <AccountSettingsPanelV2 session={authMe} />
    </main>
  );
}
