"use client";

import { useMemo } from "react";

import { useAppWorkspace, useAppWorkspaceReady } from "@/components/app-workspace";
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

  return (
    <Scheduler
      embeddedInShell
      location={location}
      backHref={buildDashboardLocationBasePathFromAny(location)}
    />
  );
}
