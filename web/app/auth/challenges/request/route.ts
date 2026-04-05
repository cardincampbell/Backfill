import { NextRequest, NextResponse } from "next/server";

import { API_BASE_URL } from "@/lib/api/client";
import { TRUSTED_DEVICE_COOKIE } from "@/lib/auth/constants";

const TRUSTED_DEVICE_HEADER = "x-backfill-trusted-device";
const DEFAULT_SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60;

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

function maxAgeFromPayload(payload: unknown): number {
  if (!payload || typeof payload !== "object") {
    return DEFAULT_SESSION_MAX_AGE_SECONDS;
  }
  const session = (payload as { session?: { expires_at?: unknown } | null }).session;
  const expiresAt = typeof session?.expires_at === "string" ? Date.parse(session.expires_at) : NaN;
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
  const body = await request.text();
  const backendResponse = await fetch(`${API_BASE_URL}/api/auth/challenges/request`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      cookie: request.headers.get("cookie") ?? "",
      "user-agent": request.headers.get("user-agent") ?? "",
      "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "",
    },
    body,
    cache: "no-store",
  });

  const payload = await backendResponse.json();
  const response = NextResponse.json(payload, { status: backendResponse.status });
  copyBackendHeaders(backendResponse, response);

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
