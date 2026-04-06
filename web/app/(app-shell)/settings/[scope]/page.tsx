import { redirect } from "next/navigation";

import {
  buildSettingsPath,
  DEFAULT_SECTION_BY_SCOPE,
  normalizeSettingsScope,
} from "@/lib/settings-routing";

export const dynamic = "force-dynamic";

export default async function SettingsScopePage({
  params,
}: {
  params: Promise<{ scope: string }>;
}) {
  const { scope } = await params;
  const normalizedScope = normalizeSettingsScope(scope);
  redirect(
    buildSettingsPath(
      normalizedScope,
      DEFAULT_SECTION_BY_SCOPE[normalizedScope],
    ),
  );
}
