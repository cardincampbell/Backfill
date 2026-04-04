import DashboardDark from "@/components/source-dashboard/DashboardDark";
import { requireAppSession } from "@/lib/require-app-session";

export const dynamic = "force-dynamic";

export default async function DashboardDarkPage() {
  await requireAppSession();
  return <DashboardDark />;
}
