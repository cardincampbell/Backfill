import { AppShellLayout } from "@/components/app-shell-layout";
import { requireAppSession } from "@/lib/require-app-session";

export default async function LiveAppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAppSession();

  return <AppShellLayout>{children}</AppShellLayout>;
}
