import { redirect } from "next/navigation";

import Settings from "@/components/source-dashboard/Settings";
import {
  buildSettingsPath,
  normalizeSettingsScope,
  normalizeSettingsSection,
} from "@/lib/settings-routing";

export const dynamic = "force-dynamic";

export default async function SettingsSectionPage({
  params,
}: {
  params: Promise<{ scope: string; section: string }>;
}) {
  const { scope, section } = await params;
  const normalizedScope = normalizeSettingsScope(scope);
  const normalizedSection = normalizeSettingsSection(normalizedScope, section);

  if (scope !== normalizedScope || section !== normalizedSection) {
    redirect(buildSettingsPath(normalizedScope, normalizedSection));
  }

  return (
    <Settings
      embeddedInShell
      scope={normalizedScope}
      activeSection={normalizedSection}
    />
  );
}
