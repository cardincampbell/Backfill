"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useAppWorkspace, useAppWorkspaceReady } from "@/components/app-workspace";
import {
  getLocationBoard,
  type WorkspaceLocation,
} from "@/lib/api/workspace";
import {
  buildDashboardLocationBasePathFromAny,
  buildSchedulerBasePathFromAny,
  type DashboardLocationLike,
} from "@/lib/dashboard-paths";

export type LocationEntryMode = "pending" | "setup" | "scheduler";

type LocationEntryContextValue = {
  getLocationEntryMode(locationId?: string | null): LocationEntryMode;
  getLocationEntryHref(location: DashboardLocationLike): string;
  setLocationEntryMode(locationId: string, mode: Exclude<LocationEntryMode, "pending">): void;
};

const LocationEntryContext = createContext<LocationEntryContextValue | null>(null);

function schedulerReadyFromBoard(locationBoard: Awaited<ReturnType<typeof getLocationBoard>>) {
  return Boolean(locationBoard && !locationBoard.location_role_setup_required);
}

export function LocationEntryProvider({ children }: { children: ReactNode }) {
  const workspace = useAppWorkspace();
  const workspaceReady = useAppWorkspaceReady();
  const locations = workspace?.locations ?? [];
  const [entryModes, setEntryModes] = useState<Record<string, Exclude<LocationEntryMode, "pending">>>({});
  const inFlightRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const activeIds = new Set(locations.map((location) => location.location_id));
    setEntryModes((current) => {
      const next = Object.fromEntries(
        Object.entries(current).filter(([locationId]) => activeIds.has(locationId)),
      );
      return Object.keys(next).length === Object.keys(current).length ? current : next;
    });
  }, [locations]);

  useEffect(() => {
    if (!workspaceReady || locations.length === 0) {
      return;
    }

    let cancelled = false;

    for (const location of locations) {
      const locationId = location.location_id;
      if (entryModes[locationId] || inFlightRef.current.has(locationId)) {
        continue;
      }

      inFlightRef.current.add(locationId);
      void getLocationBoard(location.business_id, location.location_id)
        .then((board) => {
          if (cancelled) {
            return;
          }
          setEntryModes((current) => ({
            ...current,
            [locationId]: schedulerReadyFromBoard(board) ? "scheduler" : "setup",
          }));
        })
        .catch(() => {
          if (cancelled) {
            return;
          }
          // Fall back to the scheduler path on transient failures to keep navigation immediate.
          setEntryModes((current) => ({
            ...current,
            [locationId]: "scheduler",
          }));
        })
        .finally(() => {
          inFlightRef.current.delete(locationId);
        });
    }

    return () => {
      cancelled = true;
    };
  }, [entryModes, locations, workspaceReady]);

  const getLocationEntryMode = useCallback(
    (locationId?: string | null): LocationEntryMode => {
      if (!locationId) {
        return "pending";
      }
      return entryModes[locationId] ?? "pending";
    },
    [entryModes],
  );

  const getLocationEntryHref = useCallback(
    (location: DashboardLocationLike) => {
      const setupHref = buildDashboardLocationBasePathFromAny(location);
      const schedulerHref = buildSchedulerBasePathFromAny(location);
      const locationId =
        typeof location.location_id === "string"
          ? location.location_id
          : typeof location.location_id === "number"
            ? String(location.location_id)
          : typeof location.id === "string"
            ? location.id
            : typeof location.id === "number"
              ? String(location.id)
            : null;
      const mode = getLocationEntryMode(locationId);
      return mode === "setup" ? setupHref : schedulerHref;
    },
    [getLocationEntryMode],
  );

  const setLocationEntryMode = useCallback(
    (locationId: string, mode: Exclude<LocationEntryMode, "pending">) => {
      setEntryModes((current) =>
        current[locationId] === mode ? current : { ...current, [locationId]: mode },
      );
    },
    [],
  );

  const value = useMemo<LocationEntryContextValue>(
    () => ({
      getLocationEntryMode,
      getLocationEntryHref,
      setLocationEntryMode,
    }),
    [getLocationEntryHref, getLocationEntryMode, setLocationEntryMode],
  );

  return (
    <LocationEntryContext.Provider value={value}>
      {children}
    </LocationEntryContext.Provider>
  );
}

function useLocationEntryContext() {
  const context = useContext(LocationEntryContext);
  if (!context) {
    throw new Error("LocationEntryProvider is required for location entry state.");
  }
  return context;
}

export function useLocationEntryMode(locationId?: string | null) {
  return useLocationEntryContext().getLocationEntryMode(locationId);
}

export function useLocationEntryHref(location: DashboardLocationLike) {
  return useLocationEntryContext().getLocationEntryHref(location);
}

export function useLocationEntryRouting() {
  const { getLocationEntryHref, getLocationEntryMode } = useLocationEntryContext();
  return { getLocationEntryHref, getLocationEntryMode };
}

export function useSetLocationEntryMode() {
  return useLocationEntryContext().setLocationEntryMode;
}

export function usePrimeLocationEntryHref(location: WorkspaceLocation) {
  return useLocationEntryHref({
    business_slug: location.business_slug,
    location_slug: location.location_slug,
    business_name: location.business_display_name,
    business_display_name: location.business_display_name,
    location_name: location.location_name,
    location_display_name: location.location_display_name,
    location_id: location.location_id,
  });
}
