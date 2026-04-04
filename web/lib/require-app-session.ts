import { getAuthMe } from "@/lib/api/auth";
import {
  SESSION_COOKIE,
  SESSION_HANDOFF_COOKIE,
} from "@/lib/auth/constants";
import { redirect } from "next/navigation";
import { cookies } from "next/headers";

export async function requireAppSession() {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get(SESSION_COOKIE)?.value;
  const handoffCookie = cookieStore.get(SESSION_HANDOFF_COOKIE)?.value;

  if (!sessionCookie && !handoffCookie) {
    redirect("/login");
  }

  const session = await getAuthMe();

  if (!session && handoffCookie) {
    return null;
  }

  if (!session) {
    redirect("/login");
  }

  if (session.onboarding_required) {
    redirect("/onboarding");
  }

  return session;
}
