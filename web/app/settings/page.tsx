import { AppSessionGate } from "@/components/app-session-gate";
import Settings from "@/components/source-dashboard/Settings";

export const dynamic = "force-dynamic";

export default function SettingsPage() {
  return (
    <AppSessionGate>
      <Settings />
    </AppSessionGate>
  );
}
