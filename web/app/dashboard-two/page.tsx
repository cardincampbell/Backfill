import DashboardTwo from "@/components/source-dashboard/DashboardTwo";
import { requireAppSession } from "@/lib/require-app-session";

export const dynamic = "force-dynamic";

export default async function DashboardTwoPage() {
  await requireAppSession();
  return <DashboardTwo />;
}
