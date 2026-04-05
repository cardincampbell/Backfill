import { apiFetchApp, fetchAppJson, API_PREFIX } from "./backend-client";
import {
  SESSION_COOKIE,
  SESSION_HANDOFF_COOKIE,
  SESSION_HANDOFF_STORAGE_KEY,
} from "@/lib/auth/constants";

export type AppearancePreference = "light" | "dark" | "system";

async function parseError(response: Response): Promise<string> {
  const requestId = response.headers.get("X-Backfill-Request-ID");
  try {
    const payload = (await response.clone().json()) as {
      detail?: string;
      debug?: string;
      request_id?: string;
      method?: string;
      path?: string;
    };
    const detail = payload.detail?.trim();
    if (detail && /^[a-z0-9_]+$/i.test(detail)) {
      return detail;
    }

    const parts = [detail ?? `Request failed with status ${response.status}`];
    if (payload.debug) {
      parts.push(payload.debug);
    }
    if (payload.method && payload.path) {
      parts.push(`${payload.method} ${payload.path}`);
    }
    if (payload.request_id ?? requestId) {
      parts.push(`request_id=${payload.request_id ?? requestId}`);
    }
    return parts.join(" · ");
  } catch {
    try {
      const text = (await response.clone().text()).trim();
      const parts = [`Request failed with status ${response.status}`];
      if (text) {
        parts.push(text.slice(0, 300));
      }
      if (requestId) {
        parts.push(`request_id=${requestId}`);
      }
      if (response.url) {
        parts.push(response.url);
      }
      return parts.join(" · ");
    } catch {
      const parts = [`Request failed with status ${response.status}`];
      if (requestId) {
        parts.push(`request_id=${requestId}`);
      }
      if (response.url) {
        parts.push(response.url);
      }
      return parts.join(" · ");
    }
  }
}

export type Session = {
  id: string;
  user_id: string;
  device_fingerprint?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  risk_level: string;
  elevated_actions: string[];
  last_seen_at?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  session_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type Membership = {
  id: string;
  user_id: string;
  business_id: string;
  location_id?: string | null;
  role: string;
  status: string;
  invited_by_user_id?: string | null;
  accepted_at?: string | null;
  revoked_at?: string | null;
  membership_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AuthUser = {
  id: string;
  full_name?: string | null;
  email?: string | null;
  primary_phone_e164?: string | null;
  is_phone_verified: boolean;
  onboarding_completed_at?: string | null;
  last_sign_in_at?: string | null;
  profile_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AuthMeResponse = {
  user: AuthUser;
  session: Session;
  memberships: Membership[];
  onboarding_required: boolean;
};

export type OTPChallenge = {
  id: string;
  user_id?: string | null;
  phone_e164: string;
  external_sid?: string | null;
  channel: string;
  purpose: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  requested_for_business_id?: string | null;
  requested_for_location_id?: string | null;
  expires_at?: string | null;
  approved_at?: string | null;
  challenge_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type OTPChallengeRequestResponse = {
  challenge?: OTPChallenge | null;
  session?: Session | null;
  token?: string | null;
  onboarding_required: boolean;
  otp_required: boolean;
};

export type OTPChallengeVerifyResponse = {
  challenge: OTPChallenge;
  user: AuthUser;
  session?: Session | null;
  token?: string | null;
  onboarding_required: boolean;
  step_up_granted: boolean;
};

type SessionNavigationResponse = {
  session?: Session | null;
  token?: string | null;
  onboarding_required: boolean;
};

const DEFAULT_SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60;

function deriveSharedCookieDomain(hostname: string): string | null {
  const normalized = hostname.trim().toLowerCase();
  if (!normalized || normalized === "localhost" || /^\d{1,3}(?:\.\d{1,3}){3}$/.test(normalized)) {
    return null;
  }
  if (normalized === "usebackfill.com") {
    return ".usebackfill.com";
  }
  if (normalized === "www.usebackfill.com") {
    return ".usebackfill.com";
  }
  return null;
}

export type ManagerInvitePreview = {
  invite_email: string;
  manager_name?: string | null;
  business_id: string;
  business_name: string;
  location_id: string;
  location_name: string;
  location_address?: string | null;
  expires_at?: string | null;
  invite_status: string;
  invite_mode: "setup_new" | "existing_user";
};

export async function getAuthMe(): Promise<AuthMeResponse | null> {
  return fetchAppJson<AuthMeResponse>(`${API_PREFIX}/auth/me`);
}

export async function getAuthSessions(): Promise<Session[]> {
  const response = await apiFetchApp(`${API_PREFIX}/auth/sessions`);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as Session[];
}

export async function revokeAuthSession(
  sessionId: string,
): Promise<{ revoked: boolean }> {
  const response = await apiFetchApp(`${API_PREFIX}/auth/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as { revoked: boolean };
}

function maxAgeSecondsFromExpiry(expiresAtRaw: string | null | undefined): number {
  const expiresAt = expiresAtRaw ? Date.parse(expiresAtRaw) : NaN;
  if (Number.isFinite(expiresAt)) {
    return Math.max(60, Math.floor((expiresAt - Date.now()) / 1000));
  }
  return DEFAULT_SESSION_MAX_AGE_SECONDS;
}

function maxAgeSecondsFromSessionResponse(
  response: SessionNavigationResponse,
): number {
  return maxAgeSecondsFromExpiry(response.session?.expires_at);
}

function persistCookie(
  name: string,
  value: string,
  options: {
    maxAgeSeconds: number;
    domain: string | null;
  },
): void {
  const { maxAgeSeconds, domain } = options;
  const normalizedMaxAge =
    maxAgeSeconds <= 0 ? 0 : Math.max(60, Math.floor(maxAgeSeconds));
  const parts = [
    `${name}=${encodeURIComponent(value)}`,
    "Path=/",
    "SameSite=Lax",
    `Max-Age=${normalizedMaxAge}`,
  ];

  if (window.location.protocol === "https:") {
    parts.push("Secure");
  }

  if (domain) {
    parts.push(`Domain=${domain}`);
  }

  document.cookie = parts.join("; ");
}

export function persistVerifiedSessionHandoff(
  response: SessionNavigationResponse,
): void {
  if (typeof window === "undefined" || !response.token) {
    return;
  }

  const domain = deriveSharedCookieDomain(window.location.hostname);
  const maxAgeSeconds = maxAgeSecondsFromSessionResponse(response);

  try {
    window.sessionStorage.setItem(SESSION_HANDOFF_STORAGE_KEY, response.token);
  } catch {
    // Ignore storage failures and rely on cookies only.
  }

  persistCookie(SESSION_HANDOFF_COOKIE, "1", {
    maxAgeSeconds: Math.min(maxAgeSeconds, 5 * 60),
    domain,
  });
  persistCookie(SESSION_COOKIE, response.token, {
    maxAgeSeconds,
    domain,
  });
}

export function clearVerifiedSessionHandoff(): void {
  if (typeof window === "undefined") {
    return;
  }

  const domain = deriveSharedCookieDomain(window.location.hostname);
  try {
    window.sessionStorage.removeItem(SESSION_HANDOFF_STORAGE_KEY);
  } catch {
    // Ignore storage cleanup failures.
  }

  persistCookie(SESSION_HANDOFF_COOKIE, "", {
    maxAgeSeconds: 0,
    domain,
  });
}

function readStoredVerifiedSessionToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const token = window.sessionStorage.getItem(SESSION_HANDOFF_STORAGE_KEY)?.trim();
    return token || null;
  } catch {
    return null;
  }
}

function hasSessionHandoffCookie(): boolean {
  if (typeof document === "undefined") {
    return false;
  }
  return document.cookie
    .split(";")
    .some((cookie) =>
      cookie.trim().startsWith(`${SESSION_HANDOFF_COOKIE}=`),
    );
}

export function hasStoredSessionHandoff(): boolean {
  return Boolean(
    readStoredVerifiedSessionToken() && hasSessionHandoffCookie(),
  );
}

export async function installVerifiedSessionForApp(
  response: SessionNavigationResponse,
): Promise<void> {
  if (!response.token) {
    return;
  }

  const completionResponse = await fetch("/auth/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      token: response.token,
      maxAge: maxAgeSecondsFromSessionResponse(response),
      domain:
        typeof window === "undefined"
          ? null
          : deriveSharedCookieDomain(window.location.hostname),
    }),
  });

  if (!completionResponse.ok) {
    throw new Error(await parseError(completionResponse));
  }

  clearVerifiedSessionHandoff();
}

export async function installStoredSessionForApp(
  session: Pick<AuthMeResponse, "session">,
): Promise<void> {
  const token = readStoredVerifiedSessionToken();
  if (!token) {
    return;
  }

  const completionResponse = await fetch("/auth/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      token,
      maxAge: maxAgeSecondsFromExpiry(session.session?.expires_at),
      domain:
        typeof window === "undefined"
          ? null
          : deriveSharedCookieDomain(window.location.hostname),
    }),
  });

  if (!completionResponse.ok) {
    throw new Error(await parseError(completionResponse));
  }

  clearVerifiedSessionHandoff();
}

export async function refreshAppSessionCookie(): Promise<void> {
  const response = await fetch("/auth/refresh", {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok && response.status !== 204) {
    throw new Error(await parseError(response));
  }
  clearVerifiedSessionHandoff();
}

export function replaceWithAuthDestination(onboardingRequired: boolean): void {
  if (typeof window === "undefined") {
    return;
  }
  window.location.replace(onboardingRequired ? "/onboarding" : "/dashboard");
}

export async function finalizeVerifiedSessionNavigation(
  response: SessionNavigationResponse,
): Promise<void> {
  persistVerifiedSessionHandoff(response);
  if (
    typeof document !== "undefined" &&
    typeof window !== "undefined" &&
    response.token
  ) {
    const form = document.createElement("form");
    form.method = "POST";
    form.action = "/auth/complete";
    form.style.display = "none";

    const fields = {
      token: response.token,
      maxAge: String(maxAgeSecondsFromSessionResponse(response)),
      domain: deriveSharedCookieDomain(window.location.hostname) ?? "",
      destination: response.onboarding_required ? "/onboarding" : "/dashboard",
    };

    for (const [name, value] of Object.entries(fields)) {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = value;
      form.appendChild(input);
    }

    document.body.appendChild(form);
    form.submit();
    return;
  }

  try {
    await installVerifiedSessionForApp(response);
  } catch {
    // Fall back to a direct navigation if the app-host completion route is unavailable.
  }
  replaceWithAuthDestination(response.onboarding_required);
}

export async function requestChallenge(input: {
  phone_e164: string;
  purpose: "sign_in" | "sign_up";
  locale?: string;
}) {
  const response = await apiFetchApp(`${API_PREFIX}/auth/challenges/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      phone_e164: input.phone_e164,
      purpose: input.purpose,
      locale: input.locale ?? "en",
    }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as OTPChallengeRequestResponse;
}

export async function requestChallengeAuto(
  phone_e164: string,
  locale: string = "en",
) {
  const response = await requestChallenge({
    phone_e164,
    purpose: "sign_in",
    locale,
  });
  return {
    ...response,
    requestedPurpose: "sign_in" as const,
  };
}

export async function verifyChallenge(input: {
  challenge_id: string;
  phone_e164: string;
  code: string;
}) {
  const response = await apiFetchApp(`${API_PREFIX}/auth/challenges/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      challenge_id: input.challenge_id,
      phone_e164: input.phone_e164,
      code: input.code,
    }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as OTPChallengeVerifyResponse;
}

export async function logout(): Promise<void> {
  const response = await apiFetchApp(`${API_PREFIX}/auth/logout`, {
    method: "POST",
  });
  if (!response.ok && response.status !== 204) {
    throw new Error(await parseError(response));
  }
  clearVerifiedSessionHandoff();
}

export async function getManagerInvitePreview(
  inviteToken: string,
): Promise<ManagerInvitePreview> {
  const response = await apiFetchApp(
    `${API_PREFIX}/manager-invites/${inviteToken}`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ManagerInvitePreview;
}

export async function requestManagerInviteChallenge(input: {
  inviteToken: string;
  phone_e164: string;
  manager_name?: string;
  locale?: string;
}) {
  const response = await apiFetchApp(
    `${API_PREFIX}/manager-invites/${input.inviteToken}/request-challenge`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        phone_e164: input.phone_e164,
        manager_name: input.manager_name,
        locale: input.locale ?? "en",
      }),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as OTPChallengeRequestResponse & {
    invite_mode: "setup_new" | "existing_user";
  };
}

export async function completeOnboardingProfile(input: {
  full_name: string;
  email: string;
}) {
  const response = await apiFetchApp(`${API_PREFIX}/onboarding/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    user: AuthUser;
    memberships: Membership[];
    onboarding_required: boolean;
  };
}

export async function updateAccountProfile(input: {
  full_name: string;
  email: string;
  appearance_preference?: AppearancePreference;
}) {
  const response = await apiFetchApp(`${API_PREFIX}/account/profile`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    user: AuthUser;
    onboarding_required: boolean;
  };
}

export async function bootstrapOwnerWorkspace(input: {
  profile: { full_name: string; email: string };
  business: {
    legal_name: string;
    brand_name?: string | null;
    vertical?: string | null;
    primary_phone_e164?: string | null;
    primary_email?: string | null;
    timezone?: string;
    place_metadata?: Record<string, unknown>;
  };
  location: {
    name: string;
    address_line_1?: string;
    locality?: string | null;
    region?: string | null;
    postal_code?: string | null;
    country_code?: string;
    timezone?: string;
    latitude?: number;
    longitude?: number;
    google_place_id?: string;
    google_place_metadata?: Record<string, unknown>;
    settings?: Record<string, unknown>;
  };
}) {
  const response = await apiFetchApp(
    `${API_PREFIX}/onboarding/bootstrap-owner`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    user: AuthUser;
    business: { id: string; brand_name?: string | null; legal_name: string; slug: string };
    location: { id: string; name: string; slug: string };
    owner_membership: Membership;
    onboarding_required: boolean;
    created_at: string;
  };
}
