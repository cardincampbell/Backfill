import { redirect } from "next/navigation";

import { AccountSettingsPanel } from "@/components/account-settings-panel";
import { getAuthMe } from "@/lib/api/auth";

export const dynamic = "force-dynamic";

export default async function DashboardAccountPage() {
  const authMe = await getAuthMe();
  if (!authMe) {
    redirect("/login");
  }

  return (
    <main className="section">
      <AccountSettingsPanel session={authMe} />
    </main>
  );
}
