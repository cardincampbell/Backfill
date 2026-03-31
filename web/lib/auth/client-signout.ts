import { logout } from "@/lib/api/auth";
import {
  clearBrowserSessionToken,
  getBrowserSessionToken,
} from "@/lib/auth/browser-session";
import {
  clearStoredPreviewPhone,
  clearStoredPreviewWorkspace,
} from "@/lib/auth/preview";

export async function signOutClientSession(redirectTo: string = "/login") {
  const sessionToken = getBrowserSessionToken();

  try {
    if (sessionToken) {
      await logout(sessionToken);
    }
  } catch {
    // Best-effort server revoke; clear local session regardless.
  } finally {
    clearBrowserSessionToken();
    clearStoredPreviewWorkspace();
    clearStoredPreviewPhone();
    window.location.assign(redirectTo);
  }
}
