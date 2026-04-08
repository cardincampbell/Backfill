"use client";

import { useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";

import { useAppWorkspace, useAppWorkspaceReady } from "@/components/app-workspace";
import { useLocationEntryMode } from "@/components/location-entry-provider";
import { buildDashboardLocationBasePathFromAny } from "@/lib/dashboard-paths";
import { AppRouteState } from "./AppRouteState";
import Scheduler from "./Scheduler";

type SchedulerRouteResolverProps = {
  businessSlug: string;
  locationSlug: string;
};

export default function SchedulerRouteResolver({
  businessSlug,
  locationSlug,
}: SchedulerRouteResolverProps) {
  const router = useRouter();
  const workspace = useAppWorkspace();
  const workspaceReady = useAppWorkspaceReady();
  const location = useMemo(
    () =>
      workspace?.locations.find(
        (item) =>
          item.business_slug === businessSlug && item.location_slug === locationSlug,
      ) ?? null,
    [businessSlug, locationSlug, workspace],
  );
  const entryMode = useLocationEntryMode(location?.location_id);

  useEffect(() => {
    if (!workspaceReady || !location || entryMode !== "setup") {
      return;
    }
    router.replace(buildDashboardLocationBasePathFromAny(location));
  }, [entryMode, location, router, workspaceReady]);

  if (!workspaceReady) {
    return (
      <AppRouteState
        loading
        title="Loading scheduler"
        description="We are restoring your workspace and opening the scheduler."
      />
    );
  }

  if (!location) {
    return (
      <AppRouteState
        title="Location not found"
        description="This scheduler could not be resolved from your current workspace."
      />
    );
  }

  if (entryMode === "setup") {
    return null;
  }

  return (
    <Scheduler
      embeddedInShell
      location={location}
      backHref={buildDashboardLocationBasePathFromAny(location)}
    />
  );
}
