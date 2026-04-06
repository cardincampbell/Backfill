import { redirect } from "next/navigation";

import {
  buildSettingsPath,
  DEFAULT_SECTION_BY_SCOPE,
} from "@/lib/settings-routing";

export const dynamic = "force-dynamic";

export default function SettingsPage() {
  redirect(
    buildSettingsPath("business", DEFAULT_SECTION_BY_SCOPE.business),
  );
}
