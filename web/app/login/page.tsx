import { LoginPageClient } from "@/components/auth/login-page-client";
import { redirectAuthenticatedUser } from "@/lib/redirect-authenticated-user";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams?: Promise<{ restore?: string }>;
}) {
  const resolvedSearchParams = await searchParams;
  await redirectAuthenticatedUser({
    skipTrustedDeviceRedirect: resolvedSearchParams?.restore === "failed",
  });

  return <LoginPageClient />;
}
