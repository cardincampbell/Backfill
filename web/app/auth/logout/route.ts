import { NextRequest, NextResponse } from "next/server";

import { API_BASE_URL } from "@/lib/api/client";
import {
  SESSION_COOKIE,
  SESSION_HANDOFF_COOKIE,
  TRUSTED_DEVICE_COOKIE,
} from "@/lib/auth/constants";

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

function clearCookie(
  response: NextResponse,
  request: NextRequest,
  name: string,
  httpOnly: boolean,
): void {
  response.cookies.set({
    name,
    value: "",
    httpOnly,
    sameSite: "lax",
    secure: request.nextUrl.protocol === "https:",
    path: "/",
    maxAge: 0,
    domain: deriveSharedCookieDomain(request.nextUrl.hostname),
  });
}

export async function POST(request: NextRequest) {
  let backendResponse: Response | null = null;

  try {
    backendResponse = await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: "POST",
      headers: {
        cookie: request.headers.get("cookie") ?? "",
        "user-agent": request.headers.get("user-agent") ?? "",
        "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "",
      },
      cache: "no-store",
    });
  } catch {
    backendResponse = null;
  }

  const response = new NextResponse(null, { status: 204 });
  if (backendResponse) {
    copyBackendHeaders(backendResponse, response);
  }

  clearCookie(response, request, SESSION_COOKIE, true);
  clearCookie(response, request, TRUSTED_DEVICE_COOKIE, true);
  clearCookie(response, request, SESSION_HANDOFF_COOKIE, false);

  return response;
}
