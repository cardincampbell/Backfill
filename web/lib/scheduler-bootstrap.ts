import {
  listBusinessLocations,
  listBusinessRoles,
  type BusinessLocation,
  type BusinessRole,
} from "@/lib/api/businesses";
import {
  getLocationBoard,
  type WorkspaceBoard,
} from "@/lib/api/workspace";
import {
  listEmployees,
  type EmployeeSummary,
} from "@/lib/api/workforce";

export type SchedulerBootstrapData = {
  board: WorkspaceBoard | null;
  employees: EmployeeSummary[];
  roles: BusinessRole[];
  locations: BusinessLocation[];
  fetchedAt: number;
};

type CacheEntry = {
  promise: Promise<SchedulerBootstrapData>;
  data?: SchedulerBootstrapData;
};

const SCHEDULER_BOOTSTRAP_TTL_MS = 60_000;
const schedulerBootstrapCache = new Map<string, CacheEntry>();

function schedulerBootstrapKey(
  businessId: string,
  locationId: string,
  weekStart?: string,
) {
  return `${businessId}:${locationId}:${weekStart ?? "current"}`;
}

async function fetchSchedulerBootstrap(
  businessId: string,
  locationId: string,
  weekStart?: string,
): Promise<SchedulerBootstrapData> {
  const [board, employees, roles, locations] = await Promise.all([
    getLocationBoard(businessId, locationId, weekStart),
    listEmployees(businessId),
    listBusinessRoles(businessId),
    listBusinessLocations(businessId),
  ]);
  return {
    board,
    employees,
    roles,
    locations,
    fetchedAt: Date.now(),
  };
}

function isFresh(data: SchedulerBootstrapData | undefined) {
  if (!data) {
    return false;
  }
  return Date.now() - data.fetchedAt < SCHEDULER_BOOTSTRAP_TTL_MS;
}

export function getCachedSchedulerBootstrap(
  businessId: string,
  locationId: string,
  weekStart?: string,
) {
  const entry = schedulerBootstrapCache.get(
    schedulerBootstrapKey(businessId, locationId, weekStart),
  );
  return isFresh(entry?.data) ? entry?.data ?? null : null;
}

export function preloadSchedulerBootstrap(
  businessId: string,
  locationId: string,
  weekStart?: string,
  options?: { force?: boolean },
) {
  const key = schedulerBootstrapKey(businessId, locationId, weekStart);
  const existing = schedulerBootstrapCache.get(key);
  if (!options?.force && existing) {
    if (existing.data && isFresh(existing.data)) {
      return Promise.resolve(existing.data);
    }
    return existing.promise;
  }

  const promise = fetchSchedulerBootstrap(businessId, locationId, weekStart)
    .then((data) => {
      schedulerBootstrapCache.set(key, { promise, data });
      return data;
    })
    .catch((error) => {
      schedulerBootstrapCache.delete(key);
      throw error;
    });

  schedulerBootstrapCache.set(key, { promise });
  return promise;
}
