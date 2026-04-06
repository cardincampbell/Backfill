import { AppShellLayout } from "@/components/app-shell-layout";
import {
  APP_SHELL_SIDEBAR_TAB_COOKIE,
  normalizeAppShellSidebarTab,
} from "@/lib/app-shell-prefs";
import { requireAppSession } from "@/lib/require-app-session";
import { cookies } from "next/headers";

export default async function LiveAppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAppSession();
  const cookieStore = await cookies();
  const initialSidebarTab = normalizeAppShellSidebarTab(
    cookieStore.get(APP_SHELL_SIDEBAR_TAB_COOKIE)?.value,
  );

  return (
    <AppShellLayout initialSidebarTab={initialSidebarTab}>
      {children}
    </AppShellLayout>
  );
}
