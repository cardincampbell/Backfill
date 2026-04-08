import { AppShellLayout } from "@/components/app-shell-layout";
import {
  APP_SHELL_SIDEBAR_TAB_COOKIE,
  normalizeAppShellSidebarTab,
} from "@/lib/app-shell-prefs";
import { getWorkspace } from "@/lib/api/workspace";
import { requireAppSession } from "@/lib/require-app-session";
import { cookies } from "next/headers";

export default async function LiveAppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const initialSession = await requireAppSession();
  const initialWorkspace = await getWorkspace();
  const cookieStore = await cookies();
  const initialSidebarTab = normalizeAppShellSidebarTab(
    cookieStore.get(APP_SHELL_SIDEBAR_TAB_COOKIE)?.value,
  );

  return (
    <AppShellLayout
      initialSidebarTab={initialSidebarTab}
      initialSession={initialSession}
      initialWorkspace={initialWorkspace}
    >
      {children}
    </AppShellLayout>
  );
}
