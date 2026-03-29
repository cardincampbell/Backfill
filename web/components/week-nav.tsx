"use client";

import { useRouter } from "next/navigation";

type WeekNavProps = {
  locationId: number;
  weekStartDate: string;
};

function offsetWeek(weekStart: string, days: number): string {
  const d = new Date(weekStart + "T00:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function formatWeekLabel(weekStart: string): string {
  const start = new Date(weekStart + "T00:00:00");
  const end = new Date(weekStart + "T00:00:00");
  end.setDate(end.getDate() + 6);
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  return `${start.toLocaleDateString("en-US", opts)} \u2013 ${end.toLocaleDateString("en-US", opts)}`;
}

function currentMonday(): string {
  const today = new Date();
  const day = today.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const monday = new Date(today);
  monday.setDate(today.getDate() + diff);
  return monday.toISOString().slice(0, 10);
}

export function WeekNav({ locationId, weekStartDate }: WeekNavProps) {
  const router = useRouter();
  const thisMonday = currentMonday();
  const isCurrentWeek = weekStartDate === thisMonday;

  function navigate(weekStart: string) {
    router.push(`/dashboard/locations/${locationId}?tab=schedule&week_start=${weekStart}`);
  }

  return (
    <div className="week-nav">
      <button
        className="week-nav-arrow"
        onClick={() => navigate(offsetWeek(weekStartDate, -7))}
        aria-label="Previous week"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M9 3L5 7L9 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      <span className="week-nav-label">
        {formatWeekLabel(weekStartDate)}
      </span>
      <button
        className="week-nav-arrow"
        onClick={() => navigate(offsetWeek(weekStartDate, 7))}
        aria-label="Next week"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M5 3L9 7L5 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      {!isCurrentWeek && (
        <button
          className="week-nav-today"
          onClick={() => navigate(thisMonday)}
        >
          Today
        </button>
      )}
    </div>
  );
}
