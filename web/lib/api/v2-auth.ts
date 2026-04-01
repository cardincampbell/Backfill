import { apiFetchV2, fetchV2Json, V2_API_PREFIX } from "./v2-client";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export type V2Session = {
  id: string;
  user_id: string;
  risk_level: string;
  elevated_actions: string[];
  last_seen_at?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  session_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type V2Membership = {
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

export type V2AuthUser = {
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

export type V2AuthMeResponse = {
  user: V2AuthUser;
  session: V2Session;
  memberships: V2Membership[];
  onboarding_required: boolean;
};

export type V2OTPChallenge = {
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

export type V2OTPChallengeRequestResponse = {
  challenge: V2OTPChallenge;
  user_exists: boolean;
  user_id?: string | null;
};

export type V2OTPChallengeVerifyResponse = {
  challenge: V2OTPChallenge;
  user: V2AuthUser;
  session?: V2Session | null;
  token?: string | null;
  onboarding_required: boolean;
  step_up_granted: boolean;
};

export type V2ManagerInvitePreview = {
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

export async function getV2AuthMe(): Promise<V2AuthMeResponse | null> {
  return fetchV2Json<V2AuthMeResponse>(`${V2_API_PREFIX}/auth/me`);
}

export async function requestV2Challenge(input: {
  phone_e164: string;
  purpose: "sign_in" | "sign_up";
  locale?: string;
}) {
  const response = await apiFetchV2(`${V2_API_PREFIX}/auth/challenges/request`, {
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
  return (await response.json()) as V2OTPChallengeRequestResponse;
}

export async function requestV2ChallengeAuto(
  phone_e164: string,
  locale: string = "en",
) {
  try {
    const response = await requestV2Challenge({
      phone_e164,
      purpose: "sign_in",
      locale,
    });
    return { ...response, requestedPurpose: "sign_in" as const };
  } catch (error) {
    if (error instanceof Error && error.message === "user_not_found") {
      const response = await requestV2Challenge({
        phone_e164,
        purpose: "sign_up",
        locale,
      });
      return { ...response, requestedPurpose: "sign_up" as const };
    }
    throw error;
  }
}

export async function verifyV2Challenge(input: {
  challenge_id: string;
  phone_e164: string;
  code: string;
  ttl_hours?: number;
}) {
  const response = await apiFetchV2(`${V2_API_PREFIX}/auth/challenges/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      challenge_id: input.challenge_id,
      phone_e164: input.phone_e164,
      code: input.code,
      ttl_hours: input.ttl_hours ?? 336,
    }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as V2OTPChallengeVerifyResponse;
}

export async function logoutV2(): Promise<void> {
  const response = await apiFetchV2(`${V2_API_PREFIX}/auth/logout`, {
    method: "POST",
  });
  if (!response.ok && response.status !== 204) {
    throw new Error(await parseError(response));
  }
}

export async function getV2ManagerInvitePreview(
  inviteToken: string,
): Promise<V2ManagerInvitePreview> {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/manager-invites/${inviteToken}`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as V2ManagerInvitePreview;
}

export async function requestV2ManagerInviteChallenge(input: {
  inviteToken: string;
  phone_e164: string;
  manager_name?: string;
  locale?: string;
}) {
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/manager-invites/${input.inviteToken}/request-challenge`,
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
  return (await response.json()) as V2OTPChallengeRequestResponse & {
    invite_mode: "setup_new" | "existing_user";
  };
}

export async function completeV2OnboardingProfile(input: {
  full_name: string;
  email: string;
}) {
  const response = await apiFetchV2(`${V2_API_PREFIX}/onboarding/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    user: V2AuthUser;
    memberships: V2Membership[];
    onboarding_required: boolean;
  };
}

export async function bootstrapV2OwnerWorkspace(input: {
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
  const response = await apiFetchV2(
    `${V2_API_PREFIX}/onboarding/bootstrap-owner`,
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
    user: V2AuthUser;
    business: { id: string; brand_name?: string | null; legal_name: string; slug: string };
    location: { id: string; name: string; slug: string };
    owner_membership: V2Membership;
    onboarding_required: boolean;
    created_at: string;
  };
}
