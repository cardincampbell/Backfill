import { logoutV2 } from "@/lib/api/v2-auth";
import {
  clearStoredPreviewPhone,
  clearStoredPreviewWorkspace,
} from "@/lib/auth/preview";

export async function signOutClientSession(redirectTo: string = "/login") {
  try {
    await logoutV2();
  } catch {
    // Best-effort server revoke; clear local state regardless.
  } finally {
    clearStoredPreviewWorkspace();
    clearStoredPreviewPhone();
    window.location.assign(redirectTo);
  }
}
