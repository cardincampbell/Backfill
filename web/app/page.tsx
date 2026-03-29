import Link from "next/link";

import { StatCard } from "@/components/stat-card";
import { getSupportSnapshot } from "@/lib/api";

export default async function HomePage() {
  const { summary, backendReachable } = await getSupportSnapshot();

  return (
    <main className="landing-page">
      <section className="hero-premium">
        <div className="hero-premium-copy">
          <span className="eyebrow">Backfill Shifts</span>
          <div className="hero-signature">Coverage command for premium operators</div>
          <h1>AI schedules the week. Backfill closes the gap before service feels it.</h1>
          <p className="lede">
            Built for hospitality, care, and multi-site operators who need schedule clarity,
            callout recovery, and manager control without operational drag.
          </p>
          <div className="hero-actions">
            <Link className="button" href="/dashboard">
              Open operations
            </Link>
            <Link className="button-secondary" href="/setup/choose">
              Start setup
            </Link>
          </div>
          <div className="hero-note">
            1-800-BACKFILL remains the command surface. The web layer handles precision, review, and launch.
          </div>
        </div>

        <div className="hero-premium-visual" aria-hidden="true">
          <div className="hero-device">
            <div className="hero-device-top">
              <span>Backfill live</span>
              <strong>Coverage orchestration</strong>
            </div>
            <div className="hero-device-body">
              <div className="signal-row signal-row-live">
                <span className="signal-label">Open shift</span>
                <span className="signal-value">Line Cook · 6:00 PM</span>
              </div>
              <div className="signal-row">
                <span className="signal-label">Action</span>
                <span className="signal-value">Broadcasting to eligible staff</span>
              </div>
              <div className="signal-row">
                <span className="signal-label">Manager</span>
                <span className="signal-value">Approval by text enabled</span>
              </div>
              <div className="signal-divider" />
              <div className="signal-feed">
                <div className="signal-event">
                  <span>18:03</span>
                  <p>Schedule published to enrolled employees.</p>
                </div>
                <div className="signal-event">
                  <span>18:07</span>
                  <p>Worker reported callout by SMS.</p>
                </div>
                <div className="signal-event">
                  <span>18:11</span>
                  <p>Replacement claimed. Manager review requested.</p>
                </div>
                <div className="signal-event signal-event-strong">
                  <span>18:13</span>
                  <p>Shift filled. Schedule writeback completed.</p>
                </div>
              </div>
            </div>
          </div>
          <div className="hero-reflection" />
        </div>
      </section>

      <section className="section landing-metrics">
        <div className="live-band">
          <div className="live-band-title">
            <span className="eyebrow">Network state</span>
            <h2>Operational visibility without the clutter.</h2>
          </div>
          <div className="live-band-grid">
            <StatCard
              label="Locations"
              value={summary?.locations ?? "\u2014"}
              hint="Live location graph"
            />
            <StatCard
              label="Workers"
              value={summary?.workers ?? "\u2014"}
              hint="Reachable labor pool"
            />
            <StatCard
              label="Active cascades"
              value={summary?.cascades_active ?? "\u2014"}
              hint="Coverage runs in motion"
            />
            <StatCard
              label="Filled shifts"
              value={summary?.shifts_filled ?? "\u2014"}
              hint="Confirmed outcomes"
            />
          </div>
        </div>
      </section>

      <section className="section landing-story">
        <div className="section-head">
          <div>
            <span className="eyebrow">Product thesis</span>
            <h2>One operating layer for schedule clarity, fill speed, and exception control.</h2>
            <p className="muted">
              Designed for teams that need the polish of enterprise software and the speed of text.
            </p>
          </div>
        </div>

        <div className="story-grid">
          <article className="story-block">
            <span>Scheduler-connected</span>
            <h3>Sync the roster and week automatically.</h3>
            <p>
              Connect Deputy, 7shifts, When I Work, or Homebase and let Backfill handle the operational edge cases.
            </p>
          </article>
          <article className="story-block">
            <span>Backfill native</span>
            <h3>Launch without waiting on a scheduler migration.</h3>
            <p>
              Upload a CSV, review a draft schedule, publish by text, and use Backfill Shifts as the day-one operating layer.
            </p>
          </article>
          <article className="story-block">
            <span>Text-first control</span>
            <h3>Managers approve by text. Workers respond by text.</h3>
            <p>
              Publish, approve, review, call out, claim, and recover without forcing the team into heavy admin software.
            </p>
          </article>
        </div>
      </section>

      <section className="section workflow-strip">
        <div className="process-row">
          <div className="process-step">
            <span>01</span>
            <h3>Import or connect</h3>
            <p>Bring roster and schedule data in through integrations, CSV upload, or manual launch.</p>
          </div>
          <div className="process-step">
            <span>02</span>
            <h3>Review the week</h3>
            <p>Approve drafts, inspect exceptions, and publish from a polished operator surface instead of spreadsheet chaos.</p>
          </div>
          <div className="process-step">
            <span>03</span>
            <h3>Recover in real time</h3>
            <p>When a callout lands, Backfill routes outreach, escalates intelligently, and closes the loop with the manager.</p>
          </div>
        </div>
      </section>

      <section className="section final-cta">
        <div className="final-cta-copy">
          <span className="eyebrow">Launch</span>
          <h2>Give the site lead one calm place to run the week.</h2>
          <p className="muted">
            {backendReachable
              ? "The backend is live. Start with scheduler connection or launch Backfill Shifts directly."
              : "Connect the API to bring the live operational layer online."}
          </p>
        </div>
        <div className="cta-row">
          <Link className="button" href="/setup/connect">
            Connect scheduler
          </Link>
          <Link className="button-secondary" href="/setup/upload">
            Start Backfill Shifts
          </Link>
          <Link className="button-secondary" href="/join">
            Worker profile
          </Link>
        </div>
      </section>
    </main>
  );
}
