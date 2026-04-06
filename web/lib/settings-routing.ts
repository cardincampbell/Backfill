export type SettingsScope = "business" | "personal";

export type SettingsSectionKey =
  | "company"
  | "locations"
  | "billing"
  | "business-notifications"
  | "integrations"
  | "profile"
  | "security"
  | "personal-notifications"
  | "appearance";

export const DEFAULT_SECTION_BY_SCOPE: Record<SettingsScope, SettingsSectionKey> = {
  business: "company",
  personal: "profile",
};

export const SECTION_KEYS_BY_SCOPE: Record<SettingsScope, SettingsSectionKey[]> = {
  business: [
    "company",
    "locations",
    "billing",
    "business-notifications",
    "integrations",
  ],
  personal: [
    "profile",
    "security",
    "personal-notifications",
    "appearance",
  ],
};

export function normalizeSettingsScope(
  value: string | null | undefined,
): SettingsScope {
  return value === "personal" ? "personal" : "business";
}

export function normalizeSettingsSection(
  scope: SettingsScope,
  value: string | null | undefined,
): SettingsSectionKey {
  return SECTION_KEYS_BY_SCOPE[scope].includes(value as SettingsSectionKey)
    ? (value as SettingsSectionKey)
    : DEFAULT_SECTION_BY_SCOPE[scope];
}

export function buildSettingsPath(
  scope: SettingsScope,
  section: SettingsSectionKey,
): string {
  return `/settings/${scope}/${section}`;
}
