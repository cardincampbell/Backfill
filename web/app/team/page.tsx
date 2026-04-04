import { AppSessionGate } from "@/components/app-session-gate";
import Team from "@/components/source-dashboard/Team";

export const dynamic = "force-dynamic";

export default function TeamPage() {
  return (
    <AppSessionGate>
      <Team />
    </AppSessionGate>
  );
}
