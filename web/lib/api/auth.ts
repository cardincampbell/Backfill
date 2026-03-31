/**
 * Auth API functions — client-side calls for the login/verify flow.
 *
 * These are called from "use client" components and use the browser's
 * fetch directly (no server-side cookie injection needed).
 */

import { API_BASE_URL } from "./client";

// ── Types ────────────────────────────────────────────────────────────────

export type AccessRequestResponse = {
  request_id: number;
  destination: string;
  expires_at: string;
  message_sid: string | null;
  channel: string;
  organization_id: number | null;
  location_ids: number[];
};

export type AuthResponse = {
  principal_type: string;
  session_token: string | null;
  session_id: number | null;
  subject_phone: string | null;
  session_expires_at: string | null;
  onboarding_required: boolean;
  organization: {
    id: number;
    name: string;
    [key: string]: unknown;
  } | null;
  location_ids: number[];
  locations: Array<{
    id: number;
    name: string;
    [key: string]: unknown;
  }>;
};

export type LocationManagerInvitePreview = {
  invite_email: string;
  manager_name?: string | null;
  business_name: string;
  location_id: number;
  location_name: string;
  location_address?: string | null;
  expires_at: string;
  invite_status: string;
};

// ── API calls ────────────────────────────────────────────────────────────

/**
 * Request an SMS verification code for the given phone number.
 * POST /api/auth/request-access
 */
export async function requestAccess(phone: string): Promise<AccessRequestResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/request-access`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to send verification code");
  }
  return (await res.json()) as AccessRequestResponse;
}

export async function getLocationManagerInvitePreview(
  inviteToken: string,
): Promise<LocationManagerInvitePreview> {
  const res = await fetch(`${API_BASE_URL}/api/location-manager-invites/${inviteToken}`, {
    method: "GET",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to load invite");
  }
  return (await res.json()) as LocationManagerInvitePreview;
}

export async function requestLocationInviteAccess(
  inviteToken: string,
  managerName: string,
  phone: string,
): Promise<AccessRequestResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/location-manager-invites/${inviteToken}/request-access`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manager_name: managerName, phone }),
    },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to send verification code");
  }
  return (await res.json()) as AccessRequestResponse;
}

/**
 * Verify a one-time SMS code for a session.
 * POST /api/auth/exchange
 */
export async function verifyAccessCode(
  requestId: number,
  code: string,
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, code }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to verify code");
  }
  return (await res.json()) as AuthResponse;
}

export async function completeOnboardingProfile(
  sessionToken: string,
  managerName: string,
  managerEmail: string,
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/complete-onboarding`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${sessionToken}`,
    },
    body: JSON.stringify({
      manager_name: managerName,
      manager_email: managerEmail,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to complete onboarding");
  }
  return (await res.json()) as AuthResponse;
}

/**
 * Exchange a legacy one-time access token for a session.
 * POST /api/auth/exchange
 */
export async function exchangeToken(token: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Failed to verify access link");
  }
  return (await res.json()) as AuthResponse;
}

/**
 * Revoke the current session.
 * POST /api/auth/logout
 */
export async function logout(sessionToken: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${sessionToken}` },
  });
}
