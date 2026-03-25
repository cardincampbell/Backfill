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
          <span className="eyebrow">Call. We fill.</span>
          <h1>AI shift coverage for hourly operations.</h1>
          <p className="lede">
            Workers call or text <strong>1-800-BACKFILL</strong>. Backfill identifies the shift,
            launches the fill cascade, confirms coverage, and keeps the restaurant in one workflow.
          </p>
          <div className="cta-row">
            <Link className="button" href="/dashboard">
              View restaurant dashboard
            </Link>
            <Link className="button-secondary" href="/join">
              Worker support layer
            </Link>
          </div>
        </div>
        <div className="hero-grid">
          <StatCard
            label="Active cascades"
            value={summary?.cascades_active ?? "Offline"}
            hint="Live from the FastAPI backend"
          />
          <StatCard
            label="Vacant shifts"
            value={summary?.shifts_vacant ?? "Offline"}
            hint="Current vacancies in Native Lite"
          />
          <StatCard
            label="Filled shifts"
            value={summary?.shifts_filled ?? "Offline"}
            hint="Recently confirmed coverage"
          />
          <StatCard
            label="Workers tracked"
            value={summary?.workers ?? "Offline"}
            hint="Roster and alumni records"
          />
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Support-layer surfaces</h2>
            <p className="muted">
              These pages exist for the tasks that are awkward over phone and text, not as the primary product entry point.
            </p>
          </div>
        </div>
        <div className="feature-grid">
          <SectionCard title="Restaurants">
            <p>View active vacancies, cascade status, roster data, and shift history.</p>
          </SectionCard>
          <SectionCard title="Workers">
            <p>Complete profiles, confirm certifications, and review upcoming confirmed shifts.</p>
          </SectionCard>
          <SectionCard title="Partners">
            <p>Reserve the portal surface for later without building the Tier 3 workflow yet.</p>
          </SectionCard>
          <SectionCard title="Prospects">
            <p>Keep marketing brutally simple: one number, one promise, one CTA.</p>
          </SectionCard>
        </div>
      </section>

      <section className="section">
        <div className="two-up">
          <div className="callout">
            <h3>Primary CTA</h3>
            <p>
              Every piece of marketing should resolve to one instruction:
              <strong> Call 1-800-BACKFILL.</strong>
            </p>
          </div>
          {backendReachable ? (
            <div className="callout">
              <h3>Backend status</h3>
              <p>The TypeScript frontend is reading live backend data server-side, which is the cleanest Vercel setup for now.</p>
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
