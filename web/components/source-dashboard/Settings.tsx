"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Building2,
  Camera,
  Globe,
  Mail,
  MapPin,
  Monitor,
  Phone,
  User,
} from "lucide-react";
import { useRouter } from "next/navigation";

import {
  type AppearancePreference,
  useAppAppearancePreference,
  useAppSession,
  useResolvedAppAppearance,
  useSessionUserDisplay,
  useUpdateAppAppearancePreference,
  useUpdateAppSession,
} from "@/components/app-session-gate";
import { updateAccountProfile } from "@/lib/api/auth";
import {
  getBusinessProfile,
  updateBusinessProfile,
  type BusinessProfile,
  getWorkspace,
} from "@/lib/api/workspace";
import DashboardShell from "./DashboardShell";

type SettingsScope = "business" | "personal";

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
  industry: string;
  businessEmail: string;
  companyAddress: string;
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

function getCompanyAddress(business: BusinessProfile | null): string {
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
    industry: business.vertical ?? "",
    businessEmail: business.primary_email ?? "",
    companyAddress: getCompanyAddress(business),
    timezone: business.timezone,
  };
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
    normalizeText(left.industry) === normalizeText(right.industry) &&
    normalizeEmail(left.businessEmail) === normalizeEmail(right.businessEmail) &&
    normalizeText(left.companyAddress) === normalizeText(right.companyAddress) &&
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
      className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-[13px] transition-all duration-300 ${
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
      className={`w-full px-3.5 py-2.5 rounded-lg border text-[13px] placeholder-[#8898AA]/50 focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all ${
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
  const { className, dark, ...rest } = props;
  return (
    <select
      {...rest}
      className={`w-full px-3.5 py-2.5 rounded-lg border text-[13px] focus:outline-none focus:border-[#635BFF]/40 focus:shadow-[0_0_0_3px_rgba(99,91,255,0.08)] transition-all appearance-none ${
        dark
          ? "border-white/[0.08] bg-white/[0.04] text-white"
          : "border-[#E5E7EB] bg-white text-[#0A2540]"
      } ${className ?? ""}`}
      style={{ fontWeight: 440 }}
    />
  );
}

export default function Settings() {
  const router = useRouter();
  const session = useAppSession();
  const updateSession = useUpdateAppSession();
  const appearancePreference = useAppAppearancePreference();
  const updateAppearancePreference = useUpdateAppAppearancePreference();
  const resolvedAppearance = useResolvedAppAppearance();
  const isDark = resolvedAppearance === "dark";
  const { fullName, initials, phone } = useSessionUserDisplay();

  const [scope, setScope] = useState<SettingsScope>("business");
  const [business, setBusiness] = useState<BusinessProfile | null>(null);
  const [businessLoading, setBusinessLoading] = useState(true);

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
  const [personalBaseline, setPersonalBaseline] = useState<PersonalFormState>(() =>
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
    industry: "",
    businessEmail: "",
    companyAddress: "",
    timezone: "America/Los_Angeles",
  });
  const [companyBaseline, setCompanyBaseline] = useState<CompanyFormState>({
    companyName: "",
    industry: "",
    businessEmail: "",
    companyAddress: "",
    timezone: "America/Los_Angeles",
  });

  const [personalSaving, setPersonalSaving] = useState(false);
  const [businessSaving, setBusinessSaving] = useState(false);
  const [feedback, setFeedback] = useState<Record<SettingsScope, Feedback>>({
    business: null,
    personal: null,
  });

  useEffect(() => {
    if (!session) {
      return;
    }
    const nextForm = buildPersonalForm(
      session.user.full_name,
      session.user.email,
      resolveAppearancePreference(session.user.profile_metadata?.appearance_preference),
    );
    setPersonalForm(nextForm);
    setPersonalBaseline(nextForm);
  }, [session]);

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
          setScope("personal");
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
              message: "Could not load the company profile right now.",
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

  const activeDirty = scope === "business" ? companyDirty : personalDirty;
  const activeSaving = scope === "business" ? businessSaving : personalSaving;

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

  const activeCanSave = scope === "business" ? companyCanSave : personalCanSave;

  const businessLabel = useMemo(() => {
    if (!business) {
      return "No business selected";
    }
    return business.brand_name ?? business.legal_name;
  }, [business]);

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
        resolveAppearancePreference(response.user.profile_metadata?.appearance_preference),
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
      router.refresh();
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
        vertical: normalizeText(companyForm.industry) || null,
        primary_email: normalizeEmail(companyForm.businessEmail) || null,
        timezone: normalizeText(companyForm.timezone),
        company_address: normalizeText(companyForm.companyAddress) || null,
      });
      const nextBaseline = buildCompanyForm(response);
      setBusiness(response);
      setCompanyForm(nextBaseline);
      setCompanyBaseline(nextBaseline);
      setFeedback((current) => ({
        ...current,
        business: { tone: "success", message: "Company profile updated." },
      }));
      router.refresh();
    } catch (error) {
      setFeedback((current) => ({
        ...current,
        business: {
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not update the company profile.",
        },
      }));
    } finally {
      setBusinessSaving(false);
    }
  }

  async function handleSaveActive() {
    if (scope === "business") {
      await saveBusiness();
      return;
    }
    await savePersonal();
  }

  return (
    <DashboardShell activeNav="Settings">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="overflow-hidden"
      >
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1
              className={`text-[24px] sm:text-[28px] md:text-[32px] tracking-[-0.025em] mb-1 ${isDark ? "text-white" : "text-[#0A2540]"}`}
              style={{ fontWeight: 620 }}
            >
              Settings
            </h1>
            <p
              className={`text-[13px] sm:text-[15px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}
              style={{ fontWeight: 420 }}
            >
              Keep the core account and company profile accurate while the rest
              of settings are still being wired.
            </p>
          </div>
          {activeDirty ? (
            <motion.button
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="hidden sm:block px-5 py-2.5 rounded-full text-[13px] text-white whitespace-nowrap transition-all duration-300 hover:shadow-[0_0_24px_rgba(99,91,255,0.25)] disabled:opacity-60 disabled:hover:shadow-none"
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
              {activeSaving ? "Saving…" : "Save changes"}
            </motion.button>
          ) : null}
        </div>

        <div className="mb-6">
          <div className={`inline-flex items-center rounded-xl p-1 gap-0.5 ${isDark ? "bg-white/[0.04]" : "bg-[#F0F0F5]"}`}>
            <ScopeButton
              active={scope === "business"}
              dark={isDark}
              icon={Building2}
              label="Business"
              onClick={() => setScope("business")}
            />
            <ScopeButton
              active={scope === "personal"}
              dark={isDark}
              icon={User}
              label="Personal"
              onClick={() => setScope("personal")}
            />
          </div>
        </div>

        <div className={`${isDark ? "bg-[#0F2E4C] border-white/[0.08] shadow-[0_1px_3px_rgba(0,0,0,0.25)]" : "bg-white border-[#E5E7EB] shadow-[0_1px_3px_rgba(0,0,0,0.04)]"} border rounded-2xl p-4 sm:p-6`}>
          <div className={`flex items-center gap-3 mb-6 pb-5 border-b ${isDark ? "border-white/[0.06]" : "border-[#F0F0F5]"}`}>
            <div className={`w-9 h-9 rounded-xl ${isDark ? "bg-white/[0.06]" : "bg-[#635BFF]/10"} flex items-center justify-center`}>
              {scope === "business" ? (
                <Building2 size={16} className="text-[#635BFF]" />
              ) : (
                <User size={16} className="text-[#635BFF]" />
              )}
            </div>
            <div>
              <h2
                className={`text-[16px] ${isDark ? "text-white" : "text-[#0A2540]"}`}
                style={{ fontWeight: 580 }}
              >
                {scope === "business" ? "Company Profile" : "My Profile"}
              </h2>
              <p
                className={`text-[11px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}
                style={{ fontWeight: 420 }}
              >
                {scope === "business"
                  ? business
                    ? `High-level profile for ${businessLabel}.`
                    : "No business profile is available on this account yet."
                  : "The personal details tied to your Backfill sign-in."}
              </p>
            </div>
          </div>

          {feedback[scope] ? (
            <div
              className="mb-5 rounded-xl px-4 py-3 text-[13px]"
              data-tone={feedback[scope]?.tone}
              role="status"
              style={{
                background:
                  feedback[scope]?.tone === "success"
                    ? "rgba(0, 184, 147, 0.08)"
                    : "rgba(229, 72, 77, 0.08)",
                color:
                  feedback[scope]?.tone === "success" ? "#067A64" : "#C13535",
                fontWeight: 500,
              }}
            >
              {feedback[scope]?.message}
            </div>
          ) : null}

          <AnimatePresence mode="wait">
            {scope === "business" ? (
              <motion.div
                key="business"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
              >
                {businessLoading ? (
                  <div className={`py-10 text-[13px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}>
                    Loading company profile…
                  </div>
                ) : business ? (
                  <div className="space-y-5">
                    <div className="flex items-center gap-4">
                      <div className="relative">
                        <div
                          className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center text-white text-[18px]"
                          style={{ fontWeight: 600 }}
                        >
                          {businessLabel.charAt(0).toUpperCase()}
                        </div>
                        <button
                          className={`absolute -bottom-1 -right-1 w-6 h-6 rounded-full ${isDark ? "bg-[#0F2E4C] border-white/[0.08]" : "bg-white border-[#E5E7EB]"} border flex items-center justify-center shadow-sm opacity-60`}
                          disabled
                          type="button"
                        >
                          <Camera size={11} className="text-[#8898AA]" />
                        </button>
                      </div>
                      <div>
                        <h3
                          className={`text-[15px] ${isDark ? "text-white" : "text-[#0A2540]"}`}
                          style={{ fontWeight: 560 }}
                        >
                          {businessLabel}
                        </h3>
                        <p
                          className={`text-[12px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}
                          style={{ fontWeight: 420 }}
                        >
                          Primary business profile for this account.
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <SettingsField icon={Building2} label="Company Name">
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

                      <SettingsField icon={Building2} label="Industry">
                        <SettingsSelect
                          dark={isDark}
                          onChange={(event) =>
                            setCompanyForm((current) => ({
                              ...current,
                              industry: event.target.value,
                            }))
                          }
                          value={companyForm.industry}
                        >
                          <option value="">Select industry</option>
                          <option value="healthcare">Healthcare</option>
                          <option value="hospitality">Hospitality</option>
                          <option value="staffing">Staffing Agency</option>
                          <option value="retail">Retail</option>
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
                        placeholder="ops@company.com"
                        type="email"
                        value={companyForm.businessEmail}
                      />
                    </SettingsField>

                    <SettingsField icon={MapPin} label="Company Address">
                      <SettingsInput
                        dark={isDark}
                        onChange={(event) =>
                          setCompanyForm((current) => ({
                            ...current,
                            companyAddress: event.target.value,
                          }))
                        }
                        placeholder="Headquarters or mailing address"
                        type="text"
                        value={companyForm.companyAddress}
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
                        <option value="America/Los_Angeles">
                          Pacific Time (PT)
                        </option>
                        <option value="America/Denver">
                          Mountain Time (MT)
                        </option>
                        <option value="America/Chicago">
                          Central Time (CT)
                        </option>
                        <option value="America/New_York">
                          Eastern Time (ET)
                        </option>
                      </SettingsSelect>
                    </SettingsField>
                  </div>
                ) : (
                  <div className={`py-10 text-[13px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}>
                    Create a business first, then you can manage its top-level
                    profile here.
                  </div>
                )}
              </motion.div>
            ) : (
              <motion.div
                key="personal"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                className="space-y-5"
              >
                <div className="flex items-center gap-4">
                  <div className="relative">
                    <div
                      className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#635BFF] to-[#8B5CF6] flex items-center justify-center text-white text-[18px]"
                      style={{ fontWeight: 600 }}
                    >
                      {initials}
                    </div>
                    <button
                      className={`absolute -bottom-1 -right-1 w-6 h-6 rounded-full ${isDark ? "bg-[#0F2E4C] border-white/[0.08]" : "bg-white border-[#E5E7EB]"} border flex items-center justify-center shadow-sm opacity-60`}
                      disabled
                      type="button"
                    >
                      <Camera size={11} className="text-[#8898AA]" />
                    </button>
                  </div>
                  <div>
                    <h3
                      className={`text-[15px] ${isDark ? "text-white" : "text-[#0A2540]"}`}
                      style={{ fontWeight: 560 }}
                    >
                      {fullName}
                    </h3>
                    <p
                      className={`text-[12px] ${isDark ? "text-[#C1CED8]" : "text-[#8898AA]"}`}
                      style={{ fontWeight: 420 }}
                    >
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
                  <SettingsInput
                    dark={isDark}
                    disabled
                    readOnly
                    type="tel"
                    value={phone ?? "Not set"}
                  />
                </SettingsField>

                <SettingsField icon={Monitor} label="Appearance">
                  <SettingsSelect
                    dark={isDark}
                    onChange={(event) =>
                      setPersonalForm((current) => ({
                        ...current,
                        appearancePreference: event.target.value as AppearancePreference,
                      }))
                    }
                    value={personalForm.appearancePreference}
                  >
                    <option value="light">Light</option>
                    <option value="system">System</option>
                    <option value="dark">Dark</option>
                  </SettingsSelect>
                </SettingsField>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>

      <AnimatePresence>
        {activeDirty ? (
          <motion.div
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
            className={`fixed bottom-0 left-0 right-0 z-30 sm:hidden px-4 pb-[calc(env(safe-area-inset-bottom)+12px)] pt-3 border-t ${isDark ? "from-[#071B2F] via-[#071B2F] to-[#071B2F]/80 border-white/[0.08]" : "from-white via-white to-white/80 border-[#E5E7EB]"} bg-gradient-to-t`}
          >
            <button
              className="w-full py-3 rounded-full text-[14px] text-white transition-all duration-300 active:scale-[0.98] disabled:opacity-60"
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
                : scope === "business"
                  ? "Save company profile"
                  : "Save personal info"}
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </DashboardShell>
  );
}
