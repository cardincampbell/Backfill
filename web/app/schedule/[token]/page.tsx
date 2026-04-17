import { notFound } from "next/navigation";

import { EmployeeScheduleClient } from "@/components/employee-schedule/EmployeeScheduleClient";
import { getPublicEmployeeSchedule } from "@/lib/api/employee-schedules";

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

function firstQueryValue(value: string | string[] | undefined): string | null {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value[0] ?? null;
  return null;
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

  if (!schedule) {
    notFound();
  }

  return <EmployeeScheduleClient schedule={schedule} token={resolvedParams.token} />;
}
