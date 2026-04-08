"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useAppWorkspace, useAppWorkspaceReady } from "@/components/app-workspace";
import { getLocationBoard } from "@/lib/api/workspace";
import { buildSchedulerBasePathFromAny } from "@/lib/dashboard-paths";
import Location from "./Location";
import { AppRouteState } from "./AppRouteState";

type LocationRouteResolverProps = {
  businessSlug: string;
  locationSlug: string;
};

type RouteMode = "loading" | "setup" | "redirecting";

export default function LocationRouteResolver({
  businessSlug,
  locationSlug,
}: LocationRouteResolverProps) {
  const router = useRouter();
  const workspace = useAppWorkspace();
  const workspaceReady = useAppWorkspaceReady();
  const [mode, setMode] = useState<RouteMode>("loading");
  const location = useMemo(
    () =>
      workspace?.locations.find(
        (item) =>
          item.business_slug === businessSlug && item.location_slug === locationSlug,
      ) ?? null,
    [businessSlug, locationSlug, workspace],
  );

  useEffect(() => {
    if (!workspaceReady || !location) {
      return;
    }

    let cancelled = false;
    setMode("loading");

    void (async () => {
      const board = await getLocationBoard(location.business_id, location.location_id);
      if (cancelled) {
        return;
      }

      if (board && !board.location_role_setup_required) {
        setMode("redirecting");
        router.replace(buildSchedulerBasePathFromAny(location));
        return;
      }

      setMode("setup");
    })();

    return () => {
      cancelled = true;
    };
  }, [
    location,
    router,
    workspaceReady,
  ]);

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

  if (mode === "setup") {
    return (
      <Location
        embeddedInShell
        location={location}
      />
    );
  }

  return (
    <AppRouteState
      loading
      title={mode === "redirecting" ? "Opening scheduler" : "Loading location"}
      description={
        mode === "redirecting"
          ? "This location is already configured. Opening the scheduler now."
          : "Checking the location configuration."
      }
    />
  );
}
