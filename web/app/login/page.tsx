import { LoginPageClient } from "@/components/auth/login-page-client";
import { redirectAuthenticatedUser } from "@/lib/redirect-authenticated-user";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  await redirectAuthenticatedUser();

  return <LoginPageClient />;
}
