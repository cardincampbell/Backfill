import { redirect } from "next/navigation";

import { getAuthMe } from "@/lib/api/auth";

export async function redirectAuthenticatedUser(): Promise<void> {
  const session = await getAuthMe();

  if (!session) {
    return;
  }

  redirect(session.onboarding_required ? "/onboarding" : "/dashboard");
}
