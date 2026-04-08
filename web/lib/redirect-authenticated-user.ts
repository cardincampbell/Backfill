import { redirect } from "next/navigation";
import { cookies } from "next/headers";

import { getAuthMe } from "@/lib/api/auth";
import { TRUSTED_DEVICE_COOKIE } from "@/lib/auth/constants";

export async function redirectAuthenticatedUser(
  options?: { skipTrustedDeviceRedirect?: boolean },
): Promise<void> {
  const session = await getAuthMe();

  if (!session) {
    const cookieStore = await cookies();
    const trustedDevice = cookieStore.get(TRUSTED_DEVICE_COOKIE)?.value?.trim();
    if (trustedDevice && !options?.skipTrustedDeviceRedirect) {
      redirect("/auth/entry");
    }
    return;
  }

  redirect(session.onboarding_required ? "/onboarding" : "/dashboard");
}
