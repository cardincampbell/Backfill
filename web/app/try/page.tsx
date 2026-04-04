import { TryPageClient } from "@/components/auth/try-page-client";
import { redirectAuthenticatedUser } from "@/lib/redirect-authenticated-user";

export const dynamic = "force-dynamic";

export default async function TryPage() {
  await redirectAuthenticatedUser();

  return <TryPageClient />;
}
