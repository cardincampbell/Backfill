import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth/constants";

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

export async function POST(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value?.trim();
  if (!token) {
    return new NextResponse(null, { status: 204 });
  }

  const response = new NextResponse(null, { status: 204 });
  response.cookies.set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    secure: request.nextUrl.protocol === "https:",
    path: "/",
    maxAge: DEFAULT_SESSION_MAX_AGE_SECONDS,
    domain: deriveSharedCookieDomain(request.nextUrl.hostname),
  });
  return response;
}
