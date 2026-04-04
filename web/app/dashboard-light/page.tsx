import DashboardLight from "@/components/source-dashboard/DashboardLight";
import { requireAppSession } from "@/lib/require-app-session";

export const dynamic = "force-dynamic";

export default async function DashboardLightPage() {
  await requireAppSession();
  return <DashboardLight />;
}
