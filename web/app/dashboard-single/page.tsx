import DashboardSingle from "@/components/source-dashboard/DashboardSingle";
import { requireAppSession } from "@/lib/require-app-session";

export const dynamic = "force-dynamic";

export default async function DashboardSinglePage() {
  await requireAppSession();
  return <DashboardSingle />;
}
