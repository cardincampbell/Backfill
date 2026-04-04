import { getWorkspace } from "@/lib/api/workspace";
import { redirect } from "next/navigation";

export async function requireAppSession() {
  const workspace = await getWorkspace();

  if (!workspace) {
    redirect("/login");
  }

  if (workspace.onboarding_required) {
    redirect("/onboarding");
  }

  return workspace;
}
