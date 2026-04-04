import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth/constants";

type CompletionPayload = {
  token?: unknown;
  maxAge?: unknown;
  domain?: unknown;
};

function normalizeCookieDomain(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim().toLowerCase();
  if (!trimmed) {
    return undefined;
  }
  if (trimmed === ".usebackfill.com" || trimmed === "usebackfill.com") {
    return ".usebackfill.com";
  }
  return undefined;
}

function normalizeMaxAge(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value) && value >= 60) {
    return Math.floor(value);
  }
  return 14 * 24 * 60 * 60;
}

export async function POST(request: NextRequest) {
  let payload: CompletionPayload;
  try {
    payload = (await request.json()) as CompletionPayload;
  } catch {
    return NextResponse.json(
      { detail: "invalid_session_completion_payload" },
      { status: 400 },
    );
  }

  const token = typeof payload.token === "string" ? payload.token.trim() : "";
  if (!token) {
    return NextResponse.json(
      { detail: "missing_session_token" },
      { status: 400 },
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    secure: request.nextUrl.protocol === "https:",
    path: "/",
    maxAge: normalizeMaxAge(payload.maxAge),
    domain: normalizeCookieDomain(payload.domain),
  });
  return response;
}
