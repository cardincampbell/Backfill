import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth/constants";

type CompletionPayload = {
  token?: unknown;
  maxAge?: unknown;
  domain?: unknown;
  destination?: unknown;
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

function normalizeDestination(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  if (trimmed === "/dashboard" || trimmed === "/onboarding") {
    return trimmed;
  }
  return null;
}

async function parseCompletionPayload(
  request: NextRequest,
): Promise<CompletionPayload | null> {
  const contentType = request.headers.get("content-type")?.toLowerCase() ?? "";

  if (
    contentType.includes("application/x-www-form-urlencoded") ||
    contentType.includes("multipart/form-data")
  ) {
    try {
      const form = await request.formData();
      return {
        token: form.get("token"),
        maxAge: Number(form.get("maxAge")),
        domain: form.get("domain"),
        destination: form.get("destination"),
      };
    } catch {
      return null;
    }
  }

  try {
    return (await request.json()) as CompletionPayload;
  } catch {
    return null;
  }
}

export async function POST(request: NextRequest) {
  const payload = await parseCompletionPayload(request);
  if (!payload) {
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

  const destination = normalizeDestination(payload.destination);
  const response = destination
    ? NextResponse.redirect(new URL(destination, request.url), { status: 303 })
    : NextResponse.json({ ok: true });
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
