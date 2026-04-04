import Settings from "@/components/source-dashboard/Settings";
import { requireAppSession } from "@/lib/require-app-session";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  await requireAppSession();
  return <Settings />;
}
