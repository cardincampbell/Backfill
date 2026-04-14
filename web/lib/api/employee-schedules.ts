import { API_BASE_URL } from "./client";

export type PublicEmployeeScheduleLocation = {
  location_id: string;
  location_name: string;
  location_timezone: string;
};

export type PublicEmployeeScheduleShift = {
  shift_id: string;
  location_id: string;
  location_name: string;
  role_id: string;
  role_name: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
  lifecycle_status: string;
  staffing_status: string;
  notes: string | null;
};

export type PublicEmployeeSchedule = {
  business_id: string;
  business_name: string;
  employee_id: string;
  employee_name: string;
  timezone: string;
  week_start_day: string;
  week_start_date: string;
  week_end_date: string;
  selected_location_id: string | null;
  selected_location_name: string | null;
  available_locations: PublicEmployeeScheduleLocation[];
  shifts: PublicEmployeeScheduleShift[];
};

export async function getPublicEmployeeSchedule(
  token: string,
  options?: {
    weekStart?: string | null;
    locationId?: string | null;
  }
): Promise<PublicEmployeeSchedule | null> {
  const params = new URLSearchParams();
  if (options?.weekStart) params.set("week_start", options.weekStart);
  if (options?.locationId) params.set("location_id", options.locationId);
  const query = params.toString();
  const response = await fetch(
    `${API_BASE_URL}/api/employee-schedules/${encodeURIComponent(token)}${query ? `?${query}` : ""}`,
    {
      cache: "no-store",
    }
  );
  if (!response.ok) return null;
  return (await response.json()) as PublicEmployeeSchedule;
}
