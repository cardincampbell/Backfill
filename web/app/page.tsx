import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { SectionCard } from "@/components/section-card";
import { StatCard } from "@/components/stat-card";
import { getSupportSnapshot } from "@/lib/api";

export default async function HomePage() {
  const { summary, backendReachable } = await getSupportSnapshot();

  return (
    <main>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Autonomous Coverage Engine</span>
          <h1>Autonomous coverage infrastructure for hourly labor.</h1>
          <p className="lede">
            Workers call or text <strong>1-800-BACKFILL</strong>. Backfill identifies the gap,
            broadcasts to the fastest trusted replacement path, confirms coverage, and texts the
            site lead once the shift is handled.
          </p>
          <div className="cta-row">
            <Link className="button" href="/dashboard">
              View operations dashboard
            </Link>
            <Link className="button-secondary" href="/setup/connect">
              Start location setup
            </Link>
          </div>
        </div>
        <div className="hero-grid">
          <StatCard
            label="Active cascades"
            value={summary?.cascades_active ?? "Offline"}
            hint="Live coverage events from the backend"
          />
          <StatCard
            label="Vacant shifts"
            value={summary?.shifts_vacant ?? "Offline"}
            hint="Open coverage gaps in Native Lite"
          />
          <StatCard
            label="Filled shifts"
            value={summary?.shifts_filled ?? "Offline"}
            hint="Confirmed coverage outcomes"
          />
          <StatCard
            label="Workers tracked"
            value={summary?.workers ?? "Offline"}
            hint="Internal staff and alumni records"
          />
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Structured surfaces</h2>
            <p className="muted">
              The phone starts everything. These pages handle the structured work that does not belong in a call.
            </p>
          </div>
        </div>
        <div className="feature-grid">
          <SectionCard title="Connect a scheduler">
            <p>Route supported operators to 7shifts, Deputy, When I Work, or Homebase setup without turning the website into the product.</p>
            <p>Current supported integrations are restaurant-heavy, but the core workflow stays location-based.</p>
            <p><Link className="text-link" href="/setup/connect">Open connect flow</Link></p>
          </SectionCard>
          <SectionCard title="Upload a roster">
            <p>Handle CSV onboarding for locations that have structured data but no supported writeable scheduler.</p>
            <p><Link className="text-link" href="/setup/upload">Open upload path</Link></p>
          </SectionCard>
          <SectionCard title="Add a team manually">
            <p>Give no-software operators a fast path to get live with names, phone numbers, roles, and site contacts.</p>
            <p><Link className="text-link" href="/setup/add">Open manual setup</Link></p>
          </SectionCard>
          <SectionCard title="Complete worker details">
            <p>Use the follow-up pages for certifications, preferences, and confirmed shifts after consent is collected by phone or text.</p>
            <p><Link className="text-link" href="/join">Open worker profile flow</Link></p>
          </SectionCard>
        </div>
      </section>

      <section className="section">
        <div className="two-up">
          <div className="callout">
            <h3>Manager experience</h3>
            <p>
              Coverage in progress. Then one text:
              <strong> Shift filled.</strong> No routine coordination, no site-lead scramble.
            </p>
          </div>
          {backendReachable ? (
            <div className="callout">
              <h3>Backend status</h3>
              <p>The Next app is reading live FastAPI data server-side so setup, dashboard, and status surfaces stay tied to the operating ledger.</p>
            </div>
          ) : (
            <EmptyState
              title="Backend unavailable"
              body="Set BACKFILL_API_BASE_URL in Vercel or your local .env.local so the web app can reach the FastAPI service."
            />
          )}
        </div>
      </section>
    </main>
  );
}
