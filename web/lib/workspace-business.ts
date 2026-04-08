import type { Workspace, WorkspaceBusiness } from "@/lib/api/workspace";

function readBusinessSlugFromPathname(pathname: string | null | undefined) {
  if (!pathname) {
    return null;
  }

  const parts = pathname.split("/").filter(Boolean);
  if (parts.length < 2) {
    return null;
  }

  if (parts[0] === "location" || parts[0] === "scheduler") {
    return parts[1] ?? null;
  }

  return null;
}

export function resolvePreferredWorkspaceBusiness(
  workspace: Workspace | null,
  pathname?: string | null,
): WorkspaceBusiness | null {
  const businesses = workspace?.businesses ?? [];
  if (businesses.length === 0) {
    return null;
  }

  const activeBusinessSlug = readBusinessSlugFromPathname(pathname);
  if (activeBusinessSlug) {
    const activeBusiness = businesses.find(
      (business) => business.business_slug === activeBusinessSlug,
    );
    if (activeBusiness) {
      return activeBusiness;
    }
  }

  return businesses[0] ?? null;
}
