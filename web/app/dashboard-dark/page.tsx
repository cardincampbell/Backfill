import { AppSessionGate } from "@/components/app-session-gate";
import DashboardDark from "@/components/source-dashboard/DashboardDark";

export const dynamic = "force-dynamic";

export default function DashboardDarkPage() {
  return (
    <AppSessionGate>
      <DashboardDark />
    </AppSessionGate>
  );
}
