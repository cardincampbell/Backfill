import { AppSessionGate } from "@/components/app-session-gate";
import DashboardLight from "@/components/source-dashboard/DashboardLight";

export const dynamic = "force-dynamic";

export default function DashboardLightPage() {
  return (
    <AppSessionGate>
      <DashboardLight />
    </AppSessionGate>
  );
}
