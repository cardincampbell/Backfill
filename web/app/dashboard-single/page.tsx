import { AppSessionGate } from "@/components/app-session-gate";
import DashboardSingle from "@/components/source-dashboard/DashboardSingle";

export const dynamic = "force-dynamic";

export default function DashboardSinglePage() {
  return (
    <AppSessionGate>
      <DashboardSingle />
    </AppSessionGate>
  );
}
