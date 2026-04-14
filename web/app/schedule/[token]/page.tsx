import Link from "next/link";
import { notFound } from "next/navigation";

import {
  getPublicEmployeeSchedule,
  type PublicEmployeeSchedule,
  type PublicEmployeeScheduleShift,
} from "@/lib/api/employee-schedules";

export const dynamic = "force-dynamic";

type SchedulePageProps = {
  params: Promise<{
    token: string;
  }>;
  searchParams?: Promise<{
    week_start?: string | string[];
    location_id?: string | string[];
  }>;
};

type DaySection = {
  key: string;
  label: string;
  dateLabel: string;
  shifts: PublicEmployeeScheduleShift[];
};

function firstQueryValue(value: string | string[] | undefined): string | null {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value[0] ?? null;
  return null;
}

function dateKeyInTimezone(value: string, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(value));
  const year = parts.find((part) => part.type === "year")?.value ?? "0000";
  const month = parts.find((part) => part.type === "month")?.value ?? "01";
  const day = parts.find((part) => part.type === "day")?.value ?? "01";
  return `${year}-${month}-${day}`;
}

function parseDateOnly(value: string): Date {
  const [year, month, day] = value.split("-").map((part) => Number(part));
  return new Date(Date.UTC(year, month - 1, day));
}

function shiftDate(value: string, days: number): string {
  const base = parseDateOnly(value);
  base.setUTCDate(base.getUTCDate() + days);
  return base.toISOString().slice(0, 10);
}

function weekHref(
  token: string,
  options: {
    weekStart: string;
    locationId: string | null;
  }
): string {
  const params = new URLSearchParams({ week_start: options.weekStart });
  if (options.locationId) params.set("location_id", options.locationId);
  return `/schedule/${encodeURIComponent(token)}?${params.toString()}`;
}

function locationHref(
  token: string,
  options: {
    weekStart: string;
    locationId: string | null;
  }
): string {
  const params = new URLSearchParams({ week_start: options.weekStart });
  if (options.locationId) params.set("location_id", options.locationId);
  return `/schedule/${encodeURIComponent(token)}?${params.toString()}`;
}

function formatWeekLabel(schedule: PublicEmployeeSchedule): string {
  const start = parseDateOnly(schedule.week_start_date);
  const end = parseDateOnly(schedule.week_end_date);
  return `${start.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  })} - ${end.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  })}`;
}

function formatShiftTime(value: string, timezone: string): string {
  return new Date(value).toLocaleTimeString("en-US", {
    timeZone: timezone,
    hour: "numeric",
    minute: "2-digit",
  });
}

function buildDaySections(schedule: PublicEmployeeSchedule): DaySection[] {
  return Array.from({ length: 7 }, (_, index) => {
    const dateValue = shiftDate(schedule.week_start_date, index);
    const date = parseDateOnly(dateValue);
    return {
      key: dateValue,
      label: date.toLocaleDateString("en-US", {
        weekday: "long",
        timeZone: "UTC",
      }),
      dateLabel: date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      }),
      shifts: schedule.shifts.filter(
        (shift) => dateKeyInTimezone(shift.starts_at, shift.timezone) === dateValue
      ),
    };
  });
}

export default async function EmployeeSchedulePage({
  params,
  searchParams,
}: SchedulePageProps) {
  const resolvedParams = await params;
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const weekStart = firstQueryValue(resolvedSearchParams?.week_start);
  const locationId = firstQueryValue(resolvedSearchParams?.location_id);
  const schedule = await getPublicEmployeeSchedule(resolvedParams.token, {
    weekStart,
    locationId,
  });

  if (!schedule) notFound();

  const weekLabel = formatWeekLabel(schedule);
  const daySections = buildDaySections(schedule);
  const previousWeek = shiftDate(schedule.week_start_date, -7);
  const nextWeek = shiftDate(schedule.week_start_date, 7);

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#f5f8ff_0%,#ffffff_42%,#f7f8fb_100%)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <section className="overflow-hidden rounded-[28px] border border-[#dbe5f4] bg-white shadow-[0_24px_80px_rgba(10,37,64,0.08)]">
          <div className="border-b border-[#e7eef8] bg-[#0A2540] px-6 py-8 text-white sm:px-8">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <div className="text-[13px] uppercase tracking-[0.18em] text-[#9fb5d1]">
                  Published Schedule
                </div>
                <h1 className="mt-3 text-3xl tracking-[-0.04em] sm:text-4xl" style={{ fontWeight: 650 }}>
                  {schedule.employee_name}
                </h1>
                <p className="mt-3 max-w-2xl text-[15px] leading-7 text-[#d4deed]">
                  {schedule.business_name}
                  {schedule.selected_location_name ? ` · ${schedule.selected_location_name}` : " · All locations"}
                  {" · "}
                  {weekLabel}
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-[#d4deed]">
                <div className="font-medium text-white">Read-only share link</div>
                <div className="mt-1">
                  This page updates as published schedule changes are sent from Backfill.
                </div>
              </div>
            </div>
          </div>

          <div className="border-b border-[#e7eef8] px-6 py-5 sm:px-8">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap gap-2">
                <Link
                  href={weekHref(resolvedParams.token, {
                    weekStart: previousWeek,
                    locationId: schedule.selected_location_id,
                  })}
                  className="rounded-full border border-[#d6e2f2] px-4 py-2 text-sm text-[#0A2540] transition hover:border-[#0A2540]"
                >
                  Previous week
                </Link>
                <Link
                  href={weekHref(resolvedParams.token, {
                    weekStart: nextWeek,
                    locationId: schedule.selected_location_id,
                  })}
                  className="rounded-full border border-[#d6e2f2] px-4 py-2 text-sm text-[#0A2540] transition hover:border-[#0A2540]"
                >
                  Next week
                </Link>
              </div>
              <div className="text-sm text-[#52627a]">
                Week starts on <span className="font-medium text-[#0A2540]">{schedule.week_start_day}</span>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <Link
                href={locationHref(resolvedParams.token, {
                  weekStart: schedule.week_start_date,
                  locationId: null,
                })}
                className={`rounded-full px-4 py-2 text-sm transition ${
                  schedule.selected_location_id
                    ? "border border-[#d6e2f2] text-[#425466] hover:border-[#0A2540]"
                    : "bg-[#0A2540] text-white"
                }`}
              >
                All locations
              </Link>
              {schedule.available_locations.map((location) => {
                const selected = schedule.selected_location_id === location.location_id;
                return (
                  <Link
                    key={location.location_id}
                    href={locationHref(resolvedParams.token, {
                      weekStart: schedule.week_start_date,
                      locationId: location.location_id,
                    })}
                    className={`rounded-full px-4 py-2 text-sm transition ${
                      selected
                        ? "bg-[#0A2540] text-white"
                        : "border border-[#d6e2f2] text-[#425466] hover:border-[#0A2540]"
                    }`}
                  >
                    {location.location_name}
                  </Link>
                );
              })}
            </div>
          </div>

          <div className="grid gap-4 px-4 py-4 sm:px-6 sm:py-6 lg:grid-cols-2">
            {daySections.map((day) => (
              <section
                key={day.key}
                className="rounded-[24px] border border-[#e6edf7] bg-[#fbfcff] p-5"
              >
                <div className="flex items-baseline justify-between gap-4 border-b border-[#edf2f9] pb-3">
                  <div>
                    <h2 className="text-lg tracking-[-0.02em] text-[#0A2540]" style={{ fontWeight: 620 }}>
                      {day.label}
                    </h2>
                    <p className="text-sm text-[#6b7c93]">{day.dateLabel}</p>
                  </div>
                  <div className="text-sm text-[#6b7c93]">
                    {day.shifts.length} {day.shifts.length === 1 ? "shift" : "shifts"}
                  </div>
                </div>

                {day.shifts.length ? (
                  <div className="mt-4 space-y-3">
                    {day.shifts.map((shift) => (
                      <article
                        key={shift.shift_id}
                        className="rounded-2xl border border-[#d9e5f3] bg-white p-4 shadow-[0_12px_30px_rgba(10,37,64,0.04)]"
                      >
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div>
                            <div className="text-[15px] text-[#0A2540]" style={{ fontWeight: 620 }}>
                              {shift.role_name}
                            </div>
                            <div className="mt-1 text-sm text-[#52627a]">
                              {shift.location_name}
                            </div>
                          </div>
                          <div className="rounded-full bg-[#eef4fb] px-3 py-1 text-xs uppercase tracking-[0.14em] text-[#0A2540]">
                            {shift.lifecycle_status.replaceAll("_", " ")}
                          </div>
                        </div>
                        <div className="mt-4 text-[15px] text-[#102a43]" style={{ fontWeight: 560 }}>
                          {formatShiftTime(shift.starts_at, shift.timezone)} -{" "}
                          {formatShiftTime(shift.ends_at, shift.timezone)}
                        </div>
                        {shift.notes ? (
                          <p className="mt-3 text-sm leading-6 text-[#52627a]">{shift.notes}</p>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="mt-4 rounded-2xl border border-dashed border-[#d7e1ee] bg-white px-4 py-6 text-sm text-[#6b7c93]">
                    No published shifts for this day.
                  </div>
                )}
              </section>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
