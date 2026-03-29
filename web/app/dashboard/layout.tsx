import { requireAuth } from "@/lib/auth/session";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Gate all dashboard routes on authentication.
  // While AUTH_ENABLED is false, this is a no-op pass-through.
  await requireAuth();

  return <>{children}</>;
}
