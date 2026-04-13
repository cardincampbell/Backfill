import { API_PREFIX, fetchAppJson } from "./backend-client";

export type LocationWeatherForecastPoint = {
  forecast_at: string;
  temperature_f?: number | null;
  precipitation_probability?: number | null;
  precipitation_inches?: number | null;
  wind_speed_mph?: number | null;
  weather_code?: number | null;
  weather_label: string;
  severity_flag: "none" | "monitor" | "high";
};

export type LocationWeatherForecastSummary = {
  worst_severity_flag: "none" | "monitor" | "high";
  monitor_hour_count: number;
  high_hour_count: number;
  precipitation_hour_count: number;
  peak_precipitation_inches: number;
  peak_wind_speed_mph: number;
};

export type LocationWeatherForecast = {
  business_id: string;
  location_id: string;
  provider: string;
  timezone: string;
  latitude: number;
  longitude: number;
  fetched_at: string;
  range_start: string;
  range_end: string;
  summary: LocationWeatherForecastSummary;
  points: LocationWeatherForecastPoint[];
};

type ForecastQuery = {
  startsAt?: string;
  endsAt?: string;
  hours?: number;
};

export async function getLocationWeatherForecast(
  businessId: string,
  locationId: string,
  query: ForecastQuery = {},
) {
  const params = new URLSearchParams();
  if (query.startsAt) {
    params.set("starts_at", query.startsAt);
  }
  if (query.endsAt) {
    params.set("ends_at", query.endsAt);
  }
  if (typeof query.hours === "number") {
    params.set("hours", String(query.hours));
  }
  const qs = params.size ? `?${params.toString()}` : "";
  return fetchAppJson<LocationWeatherForecast>(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/weather/forecast${qs}`,
  );
}
