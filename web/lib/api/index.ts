// Barrel re-export — all domain API modules
// Existing imports from "@/lib/shifts-api" continue to work unchanged.

export { API_BASE_URL, USE_MOCKS, apiFetch, fetchJson } from "./client";
export * from "./auth";
export * from "./schedules";
export * from "./templates";
export * from "./publishing";
export * from "./operations";
