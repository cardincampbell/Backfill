"use client";

import { useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";

import { useAppWorkspace, useAppWorkspaceReady } from "@/components/app-workspace";
import { useLocationEntryMode } from "@/components/location-entry-provider";
import { buildSchedulerBasePathFromAny } from "@/lib/dashboard-paths";
import Location from "./Location";
import { AppRouteState } from "./AppRouteState";

type LocationRouteResolverProps = {
  businessSlug: string;
  locationSlug: string;
  editingEmployeeId?: string | null;
};

export default function LocationRouteResolver({
  businessSlug,
  locationSlug,
  editingEmployeeId = null,
}: LocationRouteResolverProps) {
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
    if (!workspaceReady || !location || entryMode !== "scheduler") {
      return;
    }

    router.replace(buildSchedulerBasePathFromAny(location));
  }, [entryMode, location, router, workspaceReady]);

  if (!workspaceReady) {
    return (
      <AppRouteState
        loading
        title="Loading location"
        description="We are restoring your workspace and opening this location."
      />
    );
  }

  if (!location) {
    return (
      <AppRouteState
        title="Location not found"
        description="This location could not be resolved from your current workspace."
      />
    );
  }

  if (entryMode === "setup") {
    return (
      <Location
        embeddedInShell
        editingEmployeeId={editingEmployeeId}
        location={location}
      />
    );
  }

  if (entryMode === "pending") {
    return (
      <AppRouteState
        loading
        title="Loading location"
        description="Checking the location configuration."
      />
    );
  }

  return null;
}
