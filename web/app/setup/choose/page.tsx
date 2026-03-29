import Link from "next/link";

import { SectionCard } from "@/components/section-card";

type ChooseSetupPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ChooseSetupPage({ searchParams }: ChooseSetupPageProps) {
  const query = searchParams ? await searchParams : {};
  const locationId = typeof query.location_id === "string" ? query.location_id : undefined;
  const setupToken = typeof query.setup_token === "string" ? query.setup_token : undefined;
  const fromSignup = query.from_signup === "1";

  const params = new URLSearchParams();
  if (locationId) {
    params.set("location_id", locationId);
  }
  if (fromSignup) {
    params.set("from_signup", "1");
  }
  if (setupToken) {
    params.set("setup_token", setupToken);
  }
  const locationSuffix = params.toString() ? `?${params.toString()}` : "";

  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Getting Started</span>
        <h1>How does your team manage schedules?</h1>
        <p>
          {fromSignup
            ? "Choose how you'd like to get started with Backfill. You can always switch later."
            : "Connect your existing scheduler or use Backfill Shifts as your lightweight scheduling layer."}
        </p>
      </div>

      <div className="two-up">
        <SectionCard title="Connect an existing scheduler">
          <p>
            Already use 7shifts, Deputy, When I Work, or Homebase? Connect your account and
            Backfill will sync your roster and shifts automatically.
          </p>
          <p>Best for teams that already have a scheduling system they want to keep.</p>
          <div className="cta-row">
            <Link
              className="button"
              href={`/setup/connect${locationSuffix}`}
            >
              Connect scheduler
            </Link>
          </div>
        </SectionCard>

        <SectionCard title="Use Backfill Shifts">
          <p>
            No scheduler? No problem. Upload your team roster, build your schedule, and manage
            everything through text and this dashboard.
          </p>
          <p>Best for teams using spreadsheets, whiteboards, or group texts today.</p>
          <div className="cta-row">
            <Link
              className="button"
              href={`/setup/upload${locationSuffix}`}
            >
              Upload roster CSV
            </Link>
            <Link
              className="button-secondary"
              href={`/setup/add${locationSuffix}`}
            >
              Add team manually
            </Link>
          </div>
        </SectionCard>
      </div>

      <section className="section">
        <div className="callout">
          <h3>Not sure yet?</h3>
          <p>
            Start with Backfill Shifts now and connect a scheduler later. Your roster and
            schedule data will carry over. Text <strong>HELP</strong> to 1-800-BACKFILL
            if you need a hand.
          </p>
        </div>
      </section>
    </main>
  );
}
