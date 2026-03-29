import Link from "next/link";

import { StatCard } from "@/components/stat-card";
import { getSupportSnapshot } from "@/lib/api";

export default async function HomePage() {
  const { summary, backendReachable } = await getSupportSnapshot();

  return (
    <main>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Backfill Shifts</span>
          <h1>Coverage infrastructure for hourly labor.</h1>
          <p className="lede">
            Workers call or text. Backfill identifies the gap, finds the fastest replacement,
            confirms coverage, and notifies the site lead. One text: <strong>Shift filled.</strong>
          </p>
          <div className="cta-row" style={{ marginTop: 24 }}>
            <Link className="button" href="/dashboard">
              Open dashboard
            </Link>
            <Link className="button-secondary" href="/setup/connect">
              Connect a scheduler
            </Link>
          </div>
        </div>
        <div className="hero-grid">
          <StatCard
            label="Active cascades"
            value={summary?.cascades_active ?? "\u2014"}
            hint="Live coverage events"
          />
          <StatCard
            label="Vacant shifts"
            value={summary?.shifts_vacant ?? "\u2014"}
            hint="Open coverage gaps"
          />
          <StatCard
            label="Filled"
            value={summary?.shifts_filled ?? "\u2014"}
            hint="Confirmed outcomes"
          />
          <StatCard
            label="Workers"
            value={summary?.workers ?? "\u2014"}
            hint="Tracked across locations"
          />
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Get started</h2>
            <p className="muted">
              Choose a setup path based on how this location manages scheduling today.
            </p>
          </div>
        </div>
        <div className="feature-grid">
          <Link href="/setup/connect" className="feature-card">
            <div className="feature-card-icon">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 2v6m0 0v6m0-6h6m-6 0H4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            </div>
            <div className="feature-card-title">Connect scheduler</div>
            <div className="feature-card-desc">Link 7shifts, Deputy, When I Work, or Homebase for automatic roster and schedule sync.</div>
          </Link>
          <Link href="/setup/upload" className="feature-card">
            <div className="feature-card-icon">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M3 14v2a2 2 0 002 2h10a2 2 0 002-2v-2M10 3v10m0-10L7 6m3-3l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </div>
            <div className="feature-card-title">Upload CSV</div>
            <div className="feature-card-desc">Import your roster and schedule from a spreadsheet to get operational fast.</div>
          </Link>
          <Link href="/setup/add" className="feature-card">
            <div className="feature-card-icon">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M4 5h12M4 10h8M4 15h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            </div>
            <div className="feature-card-title">Manual setup</div>
            <div className="feature-card-desc">Enter location and team details by hand when there is no scheduler or CSV ready yet.</div>
          </Link>
          <Link href="/join" className="feature-card">
            <div className="feature-card-icon">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="7" r="3" stroke="currentColor" strokeWidth="1.5"/><path d="M4 17c0-3.3 2.7-6 6-6s6 2.7 6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            </div>
            <div className="feature-card-title">Worker profile</div>
            <div className="feature-card-desc">Complete certifications, preferences, and confirmed shifts after enrollment.</div>
          </Link>
        </div>
      </section>

      <section className="section">
        <div className="two-up">
          <div className="callout">
            <h3>For managers</h3>
            <p style={{ color: "var(--muted)", margin: 0 }}>
              Coverage runs in the background. You get one text when it is done:
              <strong style={{ color: "var(--text)" }}> Shift filled.</strong> No routine coordination.
            </p>
          </div>
          <div className="callout">
            <h3>System status</h3>
            <p style={{ color: "var(--muted)", margin: 0 }}>
              {backendReachable
                ? "API connected. Dashboard data is live."
                : "API offline. Configure BACKFILL_API_BASE_URL to connect."}
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
