import { logout } from "@/lib/api/auth";
import {
  clearStoredPreviewPhone,
  clearStoredPreviewWorkspace,
} from "@/lib/auth/preview";

export async function signOutClientSession(redirectTo: string = "/login") {
  try {
    await logout();
  } catch {
    // Best-effort server revoke; clear local state regardless.
  } finally {
    clearStoredPreviewWorkspace();
    clearStoredPreviewPhone();
    window.location.assign(redirectTo);
  }
}
