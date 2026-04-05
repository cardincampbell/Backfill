import { NextRequest, NextResponse } from "next/server";

import { API_BASE_URL } from "@/lib/api/client";
import {
  SESSION_COOKIE,
  TRUSTED_DEVICE_COOKIE,
} from "@/lib/auth/constants";

const SESSION_TOKEN_HEADER = "x-backfill-session-token";
const TRUSTED_DEVICE_HEADER = "x-backfill-trusted-device";
const DEFAULT_SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60;

type BackendRestorePayload = {
  restored?: boolean;
  session?: {
    expires_at?: string | null;
  } | null;
  onboarding_required?: boolean;
};

function deriveSharedCookieDomain(hostname: string): string | undefined {
  const normalized = hostname.trim().toLowerCase();
  if (!normalized || normalized === "localhost" || normalized === "127.0.0.1") {
    return undefined;
  }
  if (normalized === "usebackfill.com" || normalized === "www.usebackfill.com") {
    return ".usebackfill.com";
  }
  return undefined;
}

function maxAgeFromPayload(payload: BackendRestorePayload): number {
  const expiresAt =
    typeof payload.session?.expires_at === "string"
      ? Date.parse(payload.session.expires_at)
      : NaN;
  if (Number.isFinite(expiresAt)) {
    return Math.max(60, Math.floor((expiresAt - Date.now()) / 1000));
  }
  return DEFAULT_SESSION_MAX_AGE_SECONDS;
}

function copyBackendHeaders(source: Response, target: NextResponse): void {
  const requestId = source.headers.get("x-backfill-request-id");
  const retryAfter = source.headers.get("retry-after");
  if (requestId) {
    target.headers.set("X-Backfill-Request-ID", requestId);
  }
  if (retryAfter) {
    target.headers.set("Retry-After", retryAfter);
  }
}

export async function POST(request: NextRequest) {
  const backendResponse = await fetch(`${API_BASE_URL}/api/auth/restore`, {
    method: "POST",
    headers: {
      cookie: request.headers.get("cookie") ?? "",
      "user-agent": request.headers.get("user-agent") ?? "",
      "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "",
    },
    cache: "no-store",
  });

  if (backendResponse.status === 204) {
    const response = new NextResponse(null, { status: 204 });
    copyBackendHeaders(backendResponse, response);
    return response;
  }

  const payload = (await backendResponse.json()) as BackendRestorePayload;
  const response = NextResponse.json(
    backendResponse.ok
      ? {
          restored: payload.restored === true,
          onboarding_required: Boolean(payload.onboarding_required),
        }
      : payload,
    { status: backendResponse.status },
  );
  copyBackendHeaders(backendResponse, response);

  const sessionToken = backendResponse.headers.get(SESSION_TOKEN_HEADER)?.trim();
  if (backendResponse.ok && sessionToken) {
    response.cookies.set({
      name: SESSION_COOKIE,
      value: sessionToken,
      httpOnly: true,
      sameSite: "lax",
      secure: request.nextUrl.protocol === "https:",
      path: "/",
      maxAge: maxAgeFromPayload(payload),
      domain: deriveSharedCookieDomain(request.nextUrl.hostname),
    });
  }

  const trustedDeviceId = backendResponse.headers.get(TRUSTED_DEVICE_HEADER)?.trim();
  if (trustedDeviceId) {
    response.cookies.set({
      name: TRUSTED_DEVICE_COOKIE,
      value: trustedDeviceId,
      httpOnly: true,
      sameSite: "lax",
      secure: request.nextUrl.protocol === "https:",
      path: "/",
      maxAge: maxAgeFromPayload(payload),
      domain: deriveSharedCookieDomain(request.nextUrl.hostname),
    });
  }

  return response;
}
