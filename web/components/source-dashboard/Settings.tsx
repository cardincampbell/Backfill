"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import {
  Bell,
  Building2,
  Camera,
  Check,
  ChevronRight,
  CreditCard,
  FileText,
  Globe,
  Link2,
  Mail,
  MapPin,
  Monitor,
  Palette,
  Phone,
  Shield,
  Smartphone,
  User,
  Zap,
} from "lucide-react";

import {
  type AppearancePreference,
  useAppAppearancePreference,
  useAppSession,
  useResolvedAppAppearance,
  useSessionUserDisplay,
  useUpdateAppAppearancePreference,
  useUpdateAppSession,
} from "@/components/app-session-gate";
import {
  getAuthSessions,
  revokeAuthSession,
  type Session as AuthSessionRecord,
  updateAccountProfile,
} from "@/lib/api/auth";
import {
  buildSettingsPath,
  DEFAULT_SECTION_BY_SCOPE,
  type SettingsScope,
  normalizeSettingsSection,
  normalizeSettingsScope,
  type SettingsSectionKey,
} from "@/lib/settings-routing";
import {
  getBusinessProfile,
  updateBusinessProfile,
  type BusinessProfile,
  getWorkspace,
} from "@/lib/api/workspace";
import { BrandedSelect } from "./BrandedSelect";
import DashboardShell from "./DashboardShell";

type Feedback = {
  tone: "success" | "error";
  message: string;
} | null;

type PersonalFormState = {
  fullName: string;
  email: string;
  appearancePreference: AppearancePreference;
};

type CompanyFormState = {
  companyName: string;
  businessType: string;
  businessEmail: string;
  businessAddress: string;
  timezone: string;
};

function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function normalizeText(value: string): string {
  return value.trim();
}

function getBusinessAddress(business: BusinessProfile | null): string {
  if (!business) {
    return "";
  }
  const raw = business.settings?.["company_profile_address"];
  return typeof raw === "string" ? raw : "";
}

function resolveAppearancePreference(
  value: unknown,
): AppearancePreference {
  return value === "light" || value === "dark" || value === "system"
    ? value
    : "system";
}

function buildPersonalForm(
  fullName: string | null | undefined,
  email: string | null | undefined,
  appearancePreference: AppearancePreference,
): PersonalFormState {
  return {
    fullName: fullName ?? "",
    email: email ?? "",
    appearancePreference,
  };
}

function buildCompanyForm(business: BusinessProfile): CompanyFormState {
  return {
    companyName: business.brand_name ?? business.legal_name,
    businessType: business.vertical ?? "",
    businessEmail: business.primary_email ?? "",
    businessAddress: getBusinessAddress(business),
    timezone: business.timezone,
  };
}

function formatSessionTimestamp(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function extractUserAgentVersion(
  source: string,
  pattern: RegExp,
): string | undefined {
  const match = source.match(pattern);
  if (!match?.[1]) {
    return undefined;
  }
  return match[1].replace(/_/g, ".");
}

function formatUserAgentDeviceLabel(userAgent: string | null | undefined): string {
  const source = userAgent?.trim() ?? "";
  if (!source) {
    return "Unknown Device";
  }

  const browser = /Edg\//i.test(source)
    ? "Edge"
    : /CriOS\//i.test(source)
      ? "Chrome"
      : /FxiOS\//i.test(source)
        ? "Firefox"
    : /OPR\//i.test(source)
      ? "Opera"
      : /Chrome\//i.test(source)
        ? "Chrome"
        : /Firefox\//i.test(source)
          ? "Firefox"
          : /Safari\//i.test(source)
            ? "Safari"
            : "Browser";

  const device = /iPhone/i.test(source)
    ? "iPhone"
    : /iPad/i.test(source)
      ? "iPad"
      : /Android/i.test(source)
        ? "Android Device"
        : /Macintosh|Mac OS X/i.test(source)
          ? "Mac"
          : /Windows/i.test(source)
            ? "Windows PC"
            : /CrOS/i.test(source)
              ? "Chromebook"
              : /Linux/i.test(source)
                ? "Linux"
                : "Unknown Device";

  const osLabel = /iPhone|iPad|iPod/i.test(source)
    ? (() => {
        const version = extractUserAgentVersion(source, /OS ([0-9_]+)/i);
        return version ? `iOS ${version}` : "iOS";
      })()
    : /Android/i.test(source)
      ? (() => {
          const version = extractUserAgentVersion(source, /Android ([0-9.]+)/i);
          return version ? `Android ${version}` : "Android";
        })()
      : /Macintosh|Mac OS X/i.test(source)
        ? (() => {
            const version = extractUserAgentVersion(source, /Mac OS X ([0-9_]+)/i);
            return version ? `macOS ${version}` : "macOS";
          })()
        : /Windows/i.test(source)
          ? (() => {
              const version = extractUserAgentVersion(source, /Windows NT ([0-9.]+)/i);
              return version ? `Windows ${version}` : "Windows";
            })()
          : /CrOS/i.test(source)
            ? "ChromeOS"
            : /Linux/i.test(source)
              ? "Linux"
              : null;

  return [device, osLabel, browser].filter(Boolean).join(" • ");
}

function formatSessionDeviceLabel(session: AuthSessionRecord): string {
  return formatUserAgentDeviceLabel(session.user_agent);
}

function formatSessionMeta(session: AuthSessionRecord): string {
  const parts: string[] = [];
  const lastSeen =
    formatSessionTimestamp(
      session.last_seen_at ?? session.updated_at ?? session.created_at,
    );
  if (lastSeen) {
    parts.push(lastSeen);
  }
  if (session.ip_address?.trim()) {
    parts.push(session.ip_address.trim());
  }
  return parts.join(" • ") || "Active session";
}

function formsMatchPersonal(
  left: PersonalFormState,
  right: PersonalFormState,
): boolean {
  return (
    normalizeText(left.fullName) === normalizeText(right.fullName) &&
    normalizeEmail(left.email) === normalizeEmail(right.email) &&
    left.appearancePreference === right.appearancePreference
  );
}

function formsMatchCompany(
  left: CompanyFormState,
  right: CompanyFormState,
): boolean {
  return (
    normalizeText(left.companyName) === normalizeText(right.companyName) &&
    normalizeText(left.businessType) === normalizeText(right.businessType) &&
    normalizeEmail(left.businessEmail) === normalizeEmail(right.businessEmail) &&
    normalizeText(left.businessAddress) === normalizeText(right.businessAddress) &&
    normalizeText(left.timezone) === normalizeText(right.timezone)
  );
}

function ScopeButton({
  active,
  dark,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  dark: boolean;
  icon: typeof Building2;
  label: string;
  onClick(): void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-5 py-2.5 backfill-ui-radius text-[13px] transition-all duration-300 ${
        active
          ? dark
            ? "bg-white/[0.08] text-white shadow-[0_1px_3px_rgba(0,0,0,0.25)]"
            : "bg-white text-[#0A2540] shadow-[0_1px_3px_rgba(0,0,0,0.08)]"
          : dark
            ? "text-[#8898AA] hover:text-[#C1CED8]"
            : "text-[#8898AA] hover:text-[#5E6D7A]"
      }`}
      style={{ fontWeight: active ? 540 : 420 }}
      type="button"
    >
      <Icon size={15} />
      {label}
    </button>
  );
}

function SettingsField({
  label,
  icon: Icon,
  children,
}: {
  label: string;
  icon: typeof Mail;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span
        className="mb-1.5 flex items-center gap-2 text-[11px] text-[#8898AA] uppercase tracking-[0.04em]"
        style={{ fontWeight: 500 }}
      >
        <Icon size={12} />
        {label}
      </span>
      {children}
    </label>
  );
}

function SettingsInput({
  dark,
  className,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & { dark?: boolean }) {
  return (
    <input
      {...rest}
      className={`w-full px-3.5 py-2.5 backfill-ui-radius border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${
        dark
          ? "border-white/[0.08] bg-white/[0.04] text-white"
          : "border-[#E5E7EB] text-[#0A2540]"
      } ${className ?? ""}`}
      style={{ fontWeight: 440 }}
    />
  );
}

function SettingsSelect(
  props: React.SelectHTMLAttributes<HTMLSelectElement> & { dark?: boolean },
) {
  const { className, dark: _dark, value, ...rest } = props;
  return (
    <BrandedSelect
      {...rest}
      className={className}
      dark={_dark}
      value={typeof value === "string" ? value : String(value ?? "")}
    />
  );
}

function Toggle({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange(next: boolean): void;
}) {
  return (
    <button
      className={`relative h-[22px] w-10 backfill-ui-radius transition-all duration-300 ${
        enabled ? "bg-[#635BFF]" : "bg-[#E5E7EB]"
      }`}
      onClick={() => onChange(!enabled)}
      type="button"
    >
      <motion.div
        animate={{ x: enabled ? 18 : 2 }}
        className="absolute top-[2px] h-[18px] w-[18px] rounded-full bg-white shadow-sm"
        transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
      />
    </button>
  );
}

const businessSections = [
  { key: "company", label: "Business Profile", icon: Building2, saveTarget: "business" as const },
  { key: "locations", label: "Locations", icon: MapPin, saveTarget: null },
  { key: "billing", label: "Billing & Plan", icon: CreditCard, saveTarget: null },
  { key: "business-notifications", label: "Notifications", icon: Bell, saveTarget: null },
  { key: "integrations", label: "Integrations", icon: Link2, saveTarget: null },
];

const BUSINESS_TYPE_OPTIONS = [
  { value: "", label: "Select business type" },
  { value: "restaurant", label: "Restaurant" },
  { value: "cafe", label: "Cafe" },
  { value: "bakery", label: "Bakery" },
  { value: "bar", label: "Bar" },
  { value: "retail", label: "Retail" },
  { value: "beauty", label: "Beauty" },
  { value: "fitness", label: "Fitness" },
  { value: "medical_clinic", label: "Medical Clinic" },
  { value: "dental_clinic", label: "Dental Clinic" },
  { value: "home_services", label: "Home Services" },
  { value: "warehouse", label: "Warehouse" },
  { value: "hotel", label: "Hotel" },
  { value: "professional_office", label: "Professional Office" },
  { value: "mixed_unknown", label: "General Business" },
];

const personalSections = [
  { key: "profile", label: "My Profile", icon: User, saveTarget: "personal" as const },
  { key: "security", label: "Security", icon: Shield, saveTarget: null },
  { key: "personal-notifications", label: "Notifications", icon: Bell, saveTarget: null },
  { key: "appearance", label: "Appearance", icon: Palette, saveTarget: "personal" as const },
];

export default function Settings({
  embeddedInShell = false,
  scope: requestedScope = "business",
  activeSection: requestedSection = "company",
}: {
  embeddedInShell?: boolean;
  scope?: SettingsScope;
  activeSection?: SettingsSectionKey;
}) {
  const router = useRouter();
  const session = useAppSession();
  const updateSession = useUpdateAppSession();
  const appearancePreference = useAppAppearancePreference();
  const updateAppearancePreference = useUpdateAppAppearancePreference();
  const resolvedAppearance = useResolvedAppAppearance();
  const isDark = resolvedAppearance === "dark";
  const { fullName, initials, phone } = useSessionUserDisplay();
  const [business, setBusiness] = useState<BusinessProfile | null>(null);
  const [businessLoading, setBusinessLoading] = useState(true);

  const [shiftAlerts, setShiftAlerts] = useState(true);
  const [complianceAlerts, setComplianceAlerts] = useState(true);
  const [weeklyReports, setWeeklyReports] = useState(false);
  const [escalations, setEscalations] = useState(true);
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [smsNotifications, setSmsNotifications] = useState(false);
  const [dailyDigest, setDailyDigest] = useState(true);
  const [twoFactor, setTwoFactor] = useState(true);
  const [language, setLanguage] = useState("en");
  const [dateFormat, setDateFormat] = useState("mdy");

  const [personalForm, setPersonalForm] = useState<PersonalFormState>(() =>
    buildPersonalForm(
      session?.user.full_name,
      session?.user.email,
      resolveAppearancePreference(
        session?.user.profile_metadata?.appearance_preference ??
          appearancePreference,
      ),
    ),
  );
  const [personalBaseline, setPersonalBaseline] =
    useState<PersonalFormState>(() =>
      buildPersonalForm(
        session?.user.full_name,
        session?.user.email,
        resolveAppearancePreference(
          session?.user.profile_metadata?.appearance_preference ??
            appearancePreference,
        ),
      ),
    );
  const [companyForm, setCompanyForm] = useState<CompanyFormState>({
    companyName: "",
    businessType: "",
    businessEmail: "",
    businessAddress: "",
    timezone: "America/Los_Angeles",
  });
  const [companyBaseline, setCompanyBaseline] = useState<CompanyFormState>({
    companyName: "",
    businessType: "",
    businessEmail: "",
    businessAddress: "",
    timezone: "America/Los_Angeles",
  });

  const [personalSaving, setPersonalSaving] = useState(false);
  const [businessSaving, setBusinessSaving] = useState(false);
  const [activeSessions, setActiveSessions] = useState<AuthSessionRecord[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionActionId, setSessionActionId] = useState<string | null>(null);
  const [sessionFeedback, setSessionFeedback] = useState<Feedback>(null);
  const [feedback, setFeedback] = useState<Record<SettingsScope, Feedback>>({
    business: null,
    personal: null,
  });
  const normalizedScope = normalizeSettingsScope(requestedScope);
  const scope =
    !businessLoading && !business ? "personal" : normalizedScope;
  const activeSection = normalizeSettingsSection(
    scope,
    scope === normalizedScope ? requestedSection : null,
  );

  useEffect(() => {
    if (!session) {
      setActiveSessions([]);
      setSessionsLoading(false);
      return;
    }
    const nextForm = buildPersonalForm(
      session.user.full_name,
      session.user.email,
      resolveAppearancePreference(
        session.user.profile_metadata?.appearance_preference,
      ),
    );
    setPersonalForm(nextForm);
    setPersonalBaseline(nextForm);
  }, [session]);

  useEffect(() => {
    if (!session) {
      return;
    }

    let cancelled = false;

    async function loadActiveSessions() {
      try {
        setSessionsLoading(true);
        const nextSessions = await getAuthSessions();
        if (cancelled) {
          return;
        }
        setActiveSessions(nextSessions);
        setSessionFeedback(null);
      } catch (error) {
        if (!cancelled) {
          setSessionFeedback({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not load active sessions.",
          });
        }
      } finally {
        if (!cancelled) {
          setSessionsLoading(false);
        }
      }
    }

    void loadActiveSessions();

    return () => {
      cancelled = true;
    };
  }, [session?.user.id]);

  useEffect(() => {
    let cancelled = false;

    async function loadBusiness() {
      try {
        setBusinessLoading(true);
        const nextWorkspace = await getWorkspace();
        if (cancelled) {
          return;
        }
        const targetBusinessId = nextWorkspace?.businesses[0]?.business_id ?? null;
        if (!targetBusinessId) {
          setBusiness(null);
          setBusinessLoading(false);
          return;
        }
        const nextBusiness = await getBusinessProfile(targetBusinessId);
        if (cancelled) {
          return;
        }
        const nextCompanyForm = buildCompanyForm(nextBusiness);
        setBusiness(nextBusiness);
        setCompanyForm(nextCompanyForm);
        setCompanyBaseline(nextCompanyForm);
      } catch (_error) {
        if (!cancelled) {
          setFeedback((current) => ({
            ...current,
            business: {
              tone: "error",
              message: "Could not load the business profile right now.",
            },
          }));
        }
      } finally {
        if (!cancelled) {
          setBusinessLoading(false);
        }
      }
    }

    void loadBusiness();

    return () => {
      cancelled = true;
    };
  }, []);

  const personalDirty = !formsMatchPersonal(personalForm, personalBaseline);
  const companyDirty =
    business !== null && !formsMatchCompany(companyForm, companyBaseline);

  const sections = scope === "business" ? businessSections : personalSections;
  const currentSection = sections.find((section) => section.key === activeSection);
  const activeSaveTarget = currentSection?.saveTarget ?? null;

  const personalCanSave =
    Boolean(normalizeText(personalForm.fullName)) &&
    isValidEmail(personalForm.email) &&
    personalDirty &&
    !personalSaving;

  const companyCanSave =
    business !== null &&
    Boolean(normalizeText(companyForm.companyName)) &&
    Boolean(normalizeText(companyForm.timezone)) &&
    (!normalizeText(companyForm.businessEmail) ||
      isValidEmail(companyForm.businessEmail)) &&
    companyDirty &&
    !businessSaving;

  const activeDirty =
    activeSaveTarget === "business"
      ? companyDirty
      : activeSaveTarget === "personal"
        ? personalDirty
        : false;
  const activeSaving =
    activeSaveTarget === "business"
      ? businessSaving
      : activeSaveTarget === "personal"
        ? personalSaving
        : false;
  const activeCanSave =
    activeSaveTarget === "business"
      ? companyCanSave
      : activeSaveTarget === "personal"
        ? personalCanSave
        : false;
  const activeFeedback =
    activeSaveTarget === "business"
      ? feedback.business
      : activeSaveTarget === "personal"
        ? feedback.personal
        : null;
  const currentSessionId = session?.session.id ?? null;
  const visibleSessions = useMemo(() => {
    return [...activeSessions].sort((left, right) => {
      const leftCurrent = left.id === currentSessionId ? 1 : 0;
      const rightCurrent = right.id === currentSessionId ? 1 : 0;
      if (leftCurrent !== rightCurrent) {
        return rightCurrent - leftCurrent;
      }
      const leftLastSeen = Date.parse(
        left.last_seen_at ?? left.updated_at ?? left.created_at,
      );
      const rightLastSeen = Date.parse(
        right.last_seen_at ?? right.updated_at ?? right.created_at,
      );
      return rightLastSeen - leftLastSeen;
    });
  }, [activeSessions, currentSessionId]);

  const businessLabel = useMemo(() => {
    if (!business) {
      return "No business selected";
    }
    return business.brand_name ?? business.legal_name;
  }, [business]);

  const businessDescription =
    activeSection === "company"
      ? business
        ? `High-level profile for ${businessLabel}.`
        : "No business profile is available on this account yet."
      : "Organization-wide setting";
  const personalDescription =
    activeSection === "appearance"
      ? "Control how Backfill looks on this device."
      : "Your personal preference";

  async function savePersonal() {
    if (!personalCanSave) {
      return;
    }
    setPersonalSaving(true);
    setFeedback((current) => ({ ...current, personal: null }));
    try {
      const response = await updateAccountProfile({
        full_name: normalizeText(personalForm.fullName),
        email: normalizeEmail(personalForm.email),
        appearance_preference: personalForm.appearancePreference,
      });
      const nextBaseline = buildPersonalForm(
        response.user.full_name,
        response.user.email,
        resolveAppearancePreference(
          response.user.profile_metadata?.appearance_preference,
        ),
      );
      setPersonalForm(nextBaseline);
      setPersonalBaseline(nextBaseline);
      updateAppearancePreference?.(nextBaseline.appearancePreference);
      updateSession?.((current) =>
        current
          ? {
              ...current,
              onboarding_required: response.onboarding_required,
              user: response.user,
            }
          : current,
      );
      setFeedback((current) => ({
        ...current,
        personal: { tone: "success", message: "Personal information updated." },
      }));
    } catch (error) {
      setFeedback((current) => ({
        ...current,
        personal: {
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not update personal information.",
        },
      }));
    } finally {
      setPersonalSaving(false);
    }
  }

  async function saveBusiness() {
    if (!companyCanSave || !business) {
      return;
    }
    setBusinessSaving(true);
    setFeedback((current) => ({ ...current, business: null }));
    try {
      const response = await updateBusinessProfile(business.id, {
        brand_name: normalizeText(companyForm.companyName),
        vertical: normalizeText(companyForm.businessType) || null,
        primary_email: normalizeEmail(companyForm.businessEmail) || null,
        timezone: normalizeText(companyForm.timezone),
        company_address: normalizeText(companyForm.businessAddress) || null,
      });
      const nextBaseline = buildCompanyForm(response);
      setBusiness(response);
      setCompanyForm(nextBaseline);
      setCompanyBaseline(nextBaseline);
      setFeedback((current) => ({
        ...current,
        business: { tone: "success", message: "Business profile updated." },
      }));
    } catch (error) {
      setFeedback((current) => ({
        ...current,
        business: {
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not update the business profile.",
        },
      }));
    } finally {
      setBusinessSaving(false);
    }
  }

  async function handleSaveActive() {
    if (activeSaveTarget === "business") {
      await saveBusiness();
      return;
    }
    if (activeSaveTarget === "personal") {
      await savePersonal();
    }
  }

  async function handleRevokeSession(sessionId: string) {
    if (sessionId === currentSessionId) {
      return;
    }
    setSessionActionId(sessionId);
    setSessionFeedback(null);
    try {
      await revokeAuthSession(sessionId);
      setActiveSessions((current) =>
        current.filter((record) => record.id !== sessionId),
      );
      setSessionFeedback({
        tone: "success",
        message: "Session revoked.",
      });
    } catch (error) {
      setSessionFeedback({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Could not revoke that session.",
      });
    } finally {
      setSessionActionId(null);
    }
  }

  function replaceSettingsLocation(
    nextScope: SettingsScope,
    nextSection: SettingsSectionKey,
  ) {
    router.replace(buildSettingsPath(nextScope, nextSection), { scroll: false });
  }

  function pushSettingsLocation(
    nextScope: SettingsScope,
    nextSection: SettingsSectionKey,
  ) {
    router.push(buildSettingsPath(nextScope, nextSection), { scroll: false });
  }

  function switchScope(nextScope: SettingsScope) {
    pushSettingsLocation(nextScope, DEFAULT_SECTION_BY_SCOPE[nextScope]);
  }

  useEffect(() => {
    if (businessLoading || business || normalizedScope !== "business") {
      return;
    }
    replaceSettingsLocation("personal", DEFAULT_SECTION_BY_SCOPE.personal);
  }, [business, businessLoading, normalizedScope, router]);

  const panelClass = isDark
    ? "bg-[#0F2E4C] border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.25)]"
    : "bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]";
  const borderClass = isDark ? "border-white/[0.06]" : "border-[#F0F0F5]";
  const textPrimary = isDark ? "text-white" : "text-[#0A2540]";
  const textSecondary = isDark ? "text-[#C1CED8]" : "text-[#5E6D7A]";
  const textMuted = "text-[#8898AA]";
  const subtleSurface = isDark ? "bg-white/[0.04]" : "bg-[#F0F0F5]";
  const rowHover = isDark ? "hover:bg-white/[0.04]" : "hover:bg-[#F7F8FA]";
  const cardSurface = isDark
    ? "bg-white/[0.03] border-white/[0.08]"
    : "bg-[#F7F8FA] border-[#E5E7EB]";
  const cardBg = isDark ? "bg-white/[0.03]" : "bg-[#F7F8FA]";

  function renderSectionContent() {
    if (scope === "business" && activeSection === "company") {
      if (businessLoading) {
        return (
          <div className={`py-10 text-[13px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}>
            Loading business profile…
          </div>
        );
      }

      if (!business) {
        return (
          <div className={`py-10 text-[13px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}>
            Create a business first, then you can manage its top-level profile here.
          </div>
        );
      }

      return (
        <div className="space-y-5">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="w-16 h-16 backfill-ui-radius bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center text-white text-[18px]" style={{ fontWeight: 600 }}>
                {businessLabel.charAt(0).toUpperCase()}
              </div>
              <button className={`absolute -bottom-1 -right-1 w-6 h-6 rounded-full ${isDark ? "bg-[#0F2E4C] border-white/[0.08]" : "bg-white border-[#E5E7EB]"} border flex items-center justify-center shadow-sm opacity-60`} disabled type="button">
                <Camera size={11} className="text-[#8898AA]" />
              </button>
            </div>
            <div>
              <h3 className={`text-[15px] ${textPrimary}`} style={{ fontWeight: 560 }}>
                {businessLabel}
              </h3>
              <p className={`text-[12px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`} style={{ fontWeight: 420 }}>
                Primary business profile for this account.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <SettingsField icon={Building2} label="Business Name">
              <SettingsInput
                dark={isDark}
                onChange={(event) =>
                  setCompanyForm((current) => ({
                    ...current,
                    companyName: event.target.value,
                  }))
                }
                type="text"
                value={companyForm.companyName}
              />
            </SettingsField>

            <SettingsField icon={Building2} label="Business Type">
              <SettingsSelect
                dark={isDark}
                onChange={(event) =>
                  setCompanyForm((current) => ({
                    ...current,
                    businessType: event.target.value,
                  }))
                }
                value={companyForm.businessType}
              >
                {BUSINESS_TYPE_OPTIONS.map((option) => (
                  <option key={option.value || "blank"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </SettingsSelect>
            </SettingsField>
          </div>

          <SettingsField icon={Mail} label="Business Email">
            <SettingsInput
              dark={isDark}
              onChange={(event) =>
                setCompanyForm((current) => ({
                  ...current,
                  businessEmail: event.target.value,
                }))
              }
              placeholder="ops@business.com"
              type="email"
              value={companyForm.businessEmail}
            />
          </SettingsField>

          <SettingsField icon={MapPin} label="Business Address">
            <SettingsInput
              dark={isDark}
              onChange={(event) =>
                setCompanyForm((current) => ({
                  ...current,
                  businessAddress: event.target.value,
                }))
              }
              placeholder="Headquarters or mailing address"
              type="text"
              value={companyForm.businessAddress}
            />
          </SettingsField>

          <SettingsField icon={Globe} label="Timezone">
            <SettingsSelect
              dark={isDark}
              onChange={(event) =>
                setCompanyForm((current) => ({
                  ...current,
                  timezone: event.target.value,
                }))
              }
              value={companyForm.timezone}
            >
              <option value="America/Los_Angeles">Pacific Time (PT)</option>
              <option value="America/Denver">Mountain Time (MT)</option>
              <option value="America/Chicago">Central Time (CT)</option>
              <option value="America/New_York">Eastern Time (ET)</option>
            </SettingsSelect>
          </SettingsField>
        </div>
      );
    }

    if (scope === "business" && activeSection === "locations") {
      const locations = [
        { name: "Downtown Medical Center", type: "Healthcare", emoji: "🏥", color: "#635BFF", staff: 48 },
        { name: "Sunrise Senior Living", type: "Senior Care", emoji: "🌅", color: "#00B893", staff: 32 },
        { name: "Bay Area Staffing Co.", type: "Staffing Agency", emoji: "🏢", color: "#FF6B35", staff: 120 },
        { name: "Coastal Hospitality Group", type: "Hospitality", emoji: "🏨", color: "#3B82F6", staff: 15 },
      ];

      return (
        <div className="space-y-3">
          {locations.map((location) => (
            <div key={location.name} className={`flex items-center gap-4 p-4 backfill-ui-radius border transition-all ${isDark ? "border-white/[0.08] hover:border-white/[0.14] hover:bg-white/[0.03]" : "border-[#E5E7EB] hover:border-[#D1D5DB] hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)]"}`}>
              <div className="w-10 h-10 backfill-ui-radius flex items-center justify-center text-[18px]" style={{ background: `${location.color}10` }}>
                {location.emoji}
              </div>
              <div className="flex-1">
                <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 520 }}>{location.name}</p>
                <p className={`text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                  {location.type} • {location.staff} staff
                </p>
              </div>
              <ChevronRight size={16} className={textMuted} />
            </div>
          ))}
        </div>
      );
    }

    if (scope === "business" && activeSection === "billing") {
      return (
        <div className="space-y-5">
          <div className={`p-5 backfill-ui-radius border ${isDark ? "border-[#635BFF]/25 bg-[#635BFF]/[0.08]" : "border-[#635BFF]/20 bg-gradient-to-br from-[#635BFF]/[0.04] to-[#8B5CF6]/[0.02]"}`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Zap size={16} className="text-[#635BFF]" />
                <span className={`text-[14px] ${textPrimary}`} style={{ fontWeight: 580 }}>Business Pro</span>
              </div>
              <span className="text-[11px] text-[#635BFF] px-2.5 py-1 backfill-ui-radius bg-[#635BFF]/10" style={{ fontWeight: 520 }}>
                Current Plan
              </span>
            </div>
            <div className="flex items-baseline gap-1 mb-3">
              <span className={`text-[28px] tracking-[-0.02em] ${textPrimary}`} style={{ fontWeight: 660 }}>$149</span>
              <span className={`text-[13px] ${textMuted}`} style={{ fontWeight: 420 }}>/month</span>
            </div>
            <div className="flex flex-wrap gap-3">
              {["Up to 4 locations", "Unlimited staff", "AI Copilot", "Priority support"].map((feature) => (
                <div key={feature} className="flex items-center gap-1.5">
                  <Check size={12} className="text-[#00B893]" />
                  <span className={`text-[11px] ${textSecondary}`} style={{ fontWeight: 440 }}>{feature}</span>
                </div>
              ))}
            </div>
          </div>

          <div className={`p-4 backfill-ui-radius border ${isDark ? "border-white/[0.08]" : "border-[#E5E7EB]"}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-7 backfill-ui-radius bg-[#1A1F36] flex items-center justify-center">
                  <span className="text-[10px] text-white" style={{ fontWeight: 600 }}>VISA</span>
                </div>
                <div>
                  <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 480 }}>•••• •••• •••• 4242</p>
                  <p className={`text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>Expires 12/27</p>
                </div>
              </div>
              <button className="text-[12px] text-[#635BFF] hover:text-[#4B3FD9] transition-colors" style={{ fontWeight: 500 }}>
                Update
              </button>
            </div>
          </div>

          <div>
            <h4 className={`text-[11px] uppercase tracking-[0.04em] mb-3 ${textMuted}`} style={{ fontWeight: 500 }}>
              Recent Invoices
            </h4>
            <div className="space-y-2">
              {[
                { date: "Apr 1, 2026", amount: "$149.00", status: "Paid" },
                { date: "Mar 1, 2026", amount: "$149.00", status: "Paid" },
                { date: "Feb 1, 2026", amount: "$149.00", status: "Paid" },
              ].map((invoice) => (
                <div key={invoice.date} className={`flex items-center justify-between py-2.5 border-b last:border-0 ${isDark ? "border-white/[0.06]" : "border-[#F7F8FA]"}`}>
                  <div className="flex items-center gap-3">
                    <FileText size={14} className={textMuted} />
                    <span className={`text-[12px] ${textSecondary}`} style={{ fontWeight: 440 }}>{invoice.date}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-[12px] ${textPrimary}`} style={{ fontWeight: 520 }}>{invoice.amount}</span>
                    <span className="text-[10px] text-[#00B893] bg-[#00B893]/10 px-2 py-0.5 backfill-ui-radius" style={{ fontWeight: 500 }}>{invoice.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      );
    }

    if (scope === "business" && activeSection === "business-notifications") {
      const items = [
        { label: "Shift Alerts", desc: "Get notified when shifts are posted, filled, or have callouts", enabled: shiftAlerts, onChange: setShiftAlerts },
        { label: "Compliance Alerts", desc: "Credential expirations, overtime limits, and break violations", enabled: complianceAlerts, onChange: setComplianceAlerts },
        { label: "Weekly Reports", desc: "Receive weekly summary reports via email every Monday", enabled: weeklyReports, onChange: setWeeklyReports },
        { label: "Escalations", desc: "Urgent notifications when shifts go unfilled past threshold", enabled: escalations, onChange: setEscalations },
      ];

      return (
        <div className="space-y-1">
          {items.map((item) => (
            <div key={item.label} className={`flex items-center justify-between p-4 backfill-ui-radius transition-colors ${rowHover}`}>
              <div>
                <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 500 }}>{item.label}</p>
                <p className={`text-[11px] mt-0.5 max-w-md ${textMuted}`} style={{ fontWeight: 420 }}>{item.desc}</p>
              </div>
              <Toggle enabled={item.enabled} onChange={item.onChange} />
            </div>
          ))}
        </div>
      );
    }

    if (scope === "business" && activeSection === "integrations") {
      const integrations = [
        { name: "Slack", desc: "Send shift notifications to channels", connected: true, color: "#4A154B", icon: "💬" },
        { name: "Google Calendar", desc: "Sync schedules with team calendars", connected: true, color: "#4285F4", icon: "📅" },
        { name: "QuickBooks", desc: "Export payroll and billing data", connected: false, color: "#2CA01C", icon: "💰" },
        { name: "ADP", desc: "Sync employee records and HR data", connected: false, color: "#D0271D", icon: "👥" },
      ];

      return (
        <div className="space-y-3">
          {integrations.map((integration) => (
            <div key={integration.name} className={`flex items-center gap-3 sm:gap-4 p-3 sm:p-4 backfill-ui-radius border transition-all ${isDark ? "border-white/[0.08] hover:border-white/[0.14]" : "border-[#E5E7EB] hover:border-[#D1D5DB]"}`}>
              <div className="w-10 h-10 backfill-ui-radius flex items-center justify-center text-[18px] shrink-0" style={{ background: `${integration.color}10` }}>
                {integration.icon}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-[13px] truncate ${textPrimary}`} style={{ fontWeight: 520 }}>{integration.name}</p>
                <p className={`text-[11px] truncate ${textMuted}`} style={{ fontWeight: 420 }}>{integration.desc}</p>
              </div>
              {integration.connected ? (
                <div className="flex items-center gap-2 shrink-0">
                  <span className="hidden sm:inline text-[11px] text-[#00B893] bg-[#00B893]/10 px-2.5 py-1 backfill-ui-radius" style={{ fontWeight: 500 }}>
                    Connected
                  </span>
                  <button className="text-[12px] text-[#8898AA] hover:text-[#E5484D] transition-colors" style={{ fontWeight: 440 }}>
                    Disconnect
                  </button>
                </div>
              ) : (
                <button className="px-3 sm:px-3.5 py-2 backfill-ui-radius text-[12px] text-[#635BFF] border border-[#635BFF]/20 hover:bg-[#635BFF]/[0.04] transition-all shrink-0" style={{ fontWeight: 500 }}>
                  Connect
                </button>
              )}
            </div>
          ))}
        </div>
      );
    }

    if (scope === "personal" && activeSection === "profile") {
      return (
        <div className="space-y-5">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="w-16 h-16 backfill-ui-radius bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center text-white text-[18px]" style={{ fontWeight: 600 }}>
                {initials}
              </div>
              <button className={`absolute -bottom-1 -right-1 w-6 h-6 rounded-full ${isDark ? "bg-[#0F2E4C] border-white/[0.08]" : "bg-white border-[#E5E7EB]"} border flex items-center justify-center shadow-sm opacity-60`} disabled type="button">
                <Camera size={11} className="text-[#8898AA]" />
              </button>
            </div>
            <div>
              <h3 className={`text-[15px] ${textPrimary}`} style={{ fontWeight: 560 }}>{fullName}</h3>
              <p className={`text-[12px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`} style={{ fontWeight: 420 }}>
                Phone sign-in stays managed separately from profile edits.
              </p>
            </div>
          </div>

          <SettingsField icon={User} label="Full Name">
            <SettingsInput
              autoComplete="name"
              dark={isDark}
              onChange={(event) =>
                setPersonalForm((current) => ({
                  ...current,
                  fullName: event.target.value,
                }))
              }
              type="text"
              value={personalForm.fullName}
            />
          </SettingsField>

          <SettingsField icon={Mail} label="Email">
            <SettingsInput
              autoComplete="email"
              dark={isDark}
              onChange={(event) =>
                setPersonalForm((current) => ({
                  ...current,
                  email: event.target.value,
                }))
              }
              type="email"
              value={personalForm.email}
            />
          </SettingsField>

          <SettingsField icon={Phone} label="Phone Username">
            <SettingsInput dark={isDark} disabled readOnly type="tel" value={phone ?? "Not set"} />
          </SettingsField>
        </div>
      );
    }

    if (scope === "personal" && activeSection === "security") {
      return (
        <div className="space-y-5">
          <div className={`p-4 backfill-ui-radius border ${isDark ? "border-white/[0.08]" : "border-[#E5E7EB]"}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 backfill-ui-radius bg-[#00B893]/10 flex items-center justify-center">
                  <Smartphone size={16} className="text-[#00B893]" />
                </div>
                <div>
                  <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 500 }}>Two-Factor Authentication</p>
                  <p className={`text-[11px] ${textMuted}`} style={{ fontWeight: 420 }}>
                    Add an extra layer of security to your account
                  </p>
                </div>
              </div>
              <Toggle enabled={twoFactor} onChange={setTwoFactor} />
            </div>
          </div>

          <div>
            <h4 className={`text-[13px] mb-3 ${textPrimary}`} style={{ fontWeight: 540 }}>Active Sessions</h4>
            {sessionFeedback ? (
              <div
                className="mb-3 backfill-ui-radius px-4 py-3 text-[12px]"
                role="status"
                style={{
                  background:
                    sessionFeedback.tone === "success"
                      ? "rgba(0, 184, 147, 0.08)"
                      : "rgba(229, 72, 77, 0.08)",
                  color:
                    sessionFeedback.tone === "success" ? "#067A64" : "#C13535",
                  fontWeight: 500,
                }}
              >
                {sessionFeedback.message}
              </div>
            ) : null}

            {sessionsLoading ? (
              <div className={`py-3 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
                Loading active sessions…
              </div>
            ) : (
              <div className="space-y-2">
                {visibleSessions.length > 0 ? (
                  visibleSessions.map((sessionItem) => {
                    const isCurrentSession = sessionItem.id === currentSessionId;
                    return (
                      <div key={sessionItem.id} className={`flex items-center justify-between gap-3 p-3 backfill-ui-radius ${cardBg}`}>
                        <div className="flex min-w-0 items-center gap-3">
                          <Monitor size={15} className={`${textMuted} shrink-0`} />
                          <div className="min-w-0">
                            <p className={`truncate text-[12px] ${textPrimary}`} style={{ fontWeight: 480 }}>
                              {formatSessionDeviceLabel(sessionItem)}
                            </p>
                            <p className={`truncate text-[10px] ${textMuted}`} style={{ fontWeight: 420 }}>
                              {formatSessionMeta(sessionItem)}
                            </p>
                          </div>
                        </div>
                        {isCurrentSession ? (
                          <span className="shrink-0 text-[10px] text-[#00B893] bg-[#00B893]/10 px-2 py-0.5 backfill-ui-radius" style={{ fontWeight: 500 }}>
                            This Device
                          </span>
                        ) : (
                          <button
                            className="shrink-0 text-[11px] text-[#E5484D] hover:text-[#C13535] transition-colors disabled:opacity-50"
                            disabled={sessionActionId === sessionItem.id}
                            onClick={() => {
                              void handleRevokeSession(sessionItem.id);
                            }}
                            style={{ fontWeight: 460 }}
                            type="button"
                          >
                            {sessionActionId === sessionItem.id ? "Revoking…" : "Revoke"}
                          </button>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className={`py-3 text-[12px] ${textMuted}`} style={{ fontWeight: 420 }}>
                    No active sessions found.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      );
    }

    if (scope === "personal" && activeSection === "personal-notifications") {
      const items = [
        { label: "Email Notifications", desc: "Receive updates and alerts via email", enabled: emailNotifications, onChange: setEmailNotifications },
        { label: "SMS Notifications", desc: "Receive urgent alerts via text message", enabled: smsNotifications, onChange: setSmsNotifications },
        { label: "Daily Digest", desc: "Get a summary of the day's activity each evening", enabled: dailyDigest, onChange: setDailyDigest },
      ];

      return (
        <div className="space-y-1">
          {items.map((item) => (
            <div key={item.label} className={`flex items-center justify-between p-4 backfill-ui-radius transition-colors ${rowHover}`}>
              <div>
                <p className={`text-[13px] ${textPrimary}`} style={{ fontWeight: 500 }}>{item.label}</p>
                <p className={`text-[11px] mt-0.5 ${textMuted}`} style={{ fontWeight: 420 }}>{item.desc}</p>
              </div>
              <Toggle enabled={item.enabled} onChange={item.onChange} />
            </div>
          ))}
        </div>
      );
    }

    if (scope === "personal" && activeSection === "appearance") {
      const themes = [
        { key: "light" as const, label: "Light", colors: ["#FFFFFF", "#F7F8FA"] },
        { key: "system" as const, label: "System", colors: ["#FFFFFF", "#0A2540"] },
        { key: "dark" as const, label: "Dark", colors: ["#0A2540", "#071B30"] },
      ];

      return (
        <div className="space-y-5">
          <div>
            <h4 className={`text-[13px] mb-3 ${textPrimary}`} style={{ fontWeight: 540 }}>Theme</h4>
            <div className="grid grid-cols-3 gap-3">
              {themes.map((theme) => {
                const selected = personalForm.appearancePreference === theme.key;
                return (
                  <button
                    key={theme.key}
                    className={`relative p-4 backfill-ui-radius border-2 transition-all duration-300 text-center ${
                      selected
                        ? "border-[#635BFF] bg-[#635BFF]/[0.03] shadow-[0_0_0_3px_rgba(99,91,255,0.1)]"
                        : isDark
                          ? "border-white/[0.08] hover:border-white/[0.16]"
                          : "border-[#E5E7EB] hover:border-[#D1D5DB]"
                    }`}
                    onClick={() =>
                      setPersonalForm((current) => ({
                        ...current,
                        appearancePreference: theme.key,
                      }))
                    }
                    type="button"
                  >
                    {selected ? (
                      <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-[#635BFF] flex items-center justify-center">
                        <Check size={11} className="text-white" />
                      </div>
                    ) : null}
                    <div className="flex items-center justify-center gap-1 mb-2">
                      <div className={`w-8 h-6 backfill-ui-radius border overflow-hidden flex ${isDark ? "border-white/[0.08]" : "border-[#E5E7EB]"}`}>
                        <div className="flex-1" style={{ background: theme.colors[0] }} />
                        <div className="flex-1" style={{ background: theme.colors[1] }} />
                      </div>
                    </div>
                    <span
                      className="text-[12px] block"
                      style={{
                        fontWeight: selected ? 540 : 440,
                        color: selected ? "#635BFF" : isDark ? "#C1CED8" : "#5E6D7A",
                      }}
                    >
                      {theme.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <SettingsField icon={Globe} label="Language">
            <SettingsSelect
              dark={isDark}
              onChange={(event) => setLanguage(event.target.value)}
              value={language}
            >
              <option value="en">English (US)</option>
              <option value="es">Español</option>
              <option value="fr">Français</option>
              <option value="de">Deutsch</option>
            </SettingsSelect>
          </SettingsField>

          <SettingsField icon={Globe} label="Date Format">
            <SettingsSelect
              dark={isDark}
              onChange={(event) => setDateFormat(event.target.value)}
              value={dateFormat}
            >
              <option value="mdy">MM/DD/YYYY</option>
              <option value="dmy">DD/MM/YYYY</option>
              <option value="ymd">YYYY-MM-DD</option>
            </SettingsSelect>
          </SettingsField>
        </div>
      );
    }

    return null;
  }

  const content = (
    <>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="overflow-hidden">
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1 className={`text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] mb-1 ${textPrimary}`} style={{ fontWeight: 620 }}>
              Settings
            </h1>
            <p className={`text-[13px] sm:text-[15px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`} style={{ fontWeight: 420 }}>
              Manage your business and personal preferences.
            </p>
          </div>
          {activeDirty ? (
            <motion.button
              animate={{ opacity: 1, scale: 1 }}
              className="hidden sm:block px-5 py-2.5 backfill-ui-radius text-[13px] text-white whitespace-nowrap transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)] disabled:opacity-60 disabled:hover:shadow-none"
              disabled={!activeCanSave}
              initial={{ opacity: 0, scale: 0.95 }}
              onClick={() => {
                void handleSaveActive();
              }}
              style={{
                fontWeight: 540,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
              type="button"
            >
              {activeSaving
                ? "Saving…"
                : activeSaveTarget === "business"
                  ? "Save business profile"
                  : activeSection === "appearance"
                    ? "Save appearance"
                    : "Save personal info"}
            </motion.button>
          ) : null}
        </div>

        <div className="mb-6">
          <div className={`inline-flex items-center backfill-ui-radius p-1 gap-0.5 ${subtleSurface}`}>
            <ScopeButton active={scope === "business"} dark={isDark} icon={Building2} label="Business" onClick={() => switchScope("business")} />
            <ScopeButton active={scope === "personal"} dark={isDark} icon={User} label="Personal" onClick={() => switchScope("personal")} />
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-6">
          <motion.div key={scope} animate={{ opacity: 1, x: 0 }} className="md:w-56 shrink-0" initial={{ opacity: 0, x: -8 }} transition={{ duration: 0.3 }}>
            <nav className="grid grid-cols-2 sm:grid-cols-3 md:flex md:flex-col gap-1.5 md:gap-0.5 pb-2 md:pb-0 md:sticky md:top-24">
              {sections.map((section) => (
                <button
                  key={section.key}
                  className={`flex items-center gap-2 md:gap-3 px-3 md:px-3.5 py-2.5 backfill-ui-radius text-left transition-all duration-200 md:w-full ${
                    activeSection === section.key
                      ? "bg-[#635BFF]/[0.08] text-[#635BFF]"
                      : `${textSecondary} ${rowHover}`
                  }`}
                  onClick={() =>
                    pushSettingsLocation(scope, section.key as SettingsSectionKey)
                  }
                  type="button"
                >
                  <section.icon size={16} className="shrink-0" />
                  <span className="text-[13px] truncate" style={{ fontWeight: activeSection === section.key ? 540 : 440 }}>
                    {section.label}
                  </span>
                </button>
              ))}
            </nav>
          </motion.div>

          <div className="flex-1 min-w-0">
            <div className={`${panelClass} border backfill-ui-radius p-4 sm:p-6`}>
              <div className={`flex items-center gap-3 mb-6 pb-5 border-b ${borderClass}`}>
                {currentSection ? (
                  <>
                    <div className={`w-9 h-9 backfill-ui-radius ${isDark ? "bg-white/[0.06]" : "bg-[#635BFF]/10"} flex items-center justify-center`}>
                      <currentSection.icon size={16} className="text-[#635BFF]" />
                    </div>
                    <div>
                      <h2 className={`text-[16px] ${textPrimary}`} style={{ fontWeight: 580 }}>
                        {currentSection.label}
                      </h2>
                      <p className={`text-[11px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`} style={{ fontWeight: 420 }}>
                        {scope === "business" ? businessDescription : personalDescription}
                      </p>
                    </div>
                  </>
                ) : null}
              </div>

              {activeFeedback ? (
                <div
                  className="mb-5 backfill-ui-radius px-4 py-3 text-[13px]"
                  data-tone={activeFeedback.tone}
                  role="status"
                  style={{
                    background:
                      activeFeedback.tone === "success"
                        ? "rgba(0, 184, 147, 0.08)"
                        : "rgba(229, 72, 77, 0.08)",
                    color:
                      activeFeedback.tone === "success" ? "#067A64" : "#C13535",
                    fontWeight: 500,
                  }}
                >
                  {activeFeedback.message}
                </div>
              ) : null}

              <AnimatePresence mode="wait">
                <motion.div key={`${scope}-${activeSection}`} animate={{ opacity: 1, y: 0 }} initial={{ opacity: 0, y: 8 }} transition={{ duration: 0.2 }}>
                  {renderSectionContent()}
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
      </motion.div>

      <AnimatePresence>
        {activeDirty ? (
          <motion.div
            animate={{ y: 0, opacity: 1 }}
            className={`fixed bottom-0 left-0 right-0 z-30 sm:hidden px-4 pb-[calc(env(safe-area-inset-bottom)+12px)] pt-3 border-t ${isDark ? "from-[#071B2F] via-[#071B2F] to-[#071B2F]/80 border-white/[0.08]" : "from-white via-white to-white/80 border-[#E5E7EB]"} bg-gradient-to-t`}
            exit={{ y: 80, opacity: 0 }}
            initial={{ y: 80, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
          >
            <button
              className="w-full py-3 backfill-ui-radius text-[14px] text-white transition-all duration-300 active:scale-[0.98] disabled:opacity-60"
              disabled={!activeCanSave}
              onClick={() => {
                void handleSaveActive();
              }}
              style={{
                fontWeight: 540,
                background: "linear-gradient(135deg, #635BFF, #8B5CF6)",
              }}
              type="button"
            >
              {activeSaving
                ? "Saving…"
                : activeSaveTarget === "business"
                  ? "Save business profile"
                  : activeSection === "appearance"
                    ? "Save appearance"
                    : "Save personal info"}
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );

  if (embeddedInShell) {
    return content;
  }

  return <DashboardShell activeNav="Settings">{content}</DashboardShell>;
}
