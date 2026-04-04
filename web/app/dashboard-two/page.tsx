import { AppSessionGate } from "@/components/app-session-gate";
import DashboardTwo from "@/components/source-dashboard/DashboardTwo";

export const dynamic = "force-dynamic";

export default function DashboardTwoPage() {
  return (
    <AppSessionGate>
      <DashboardTwo />
    </AppSessionGate>
  );
}
