import Link from "next/link";

export default function HomePage() {
  return (
    <main className="lp">
      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <nav className="lp-nav">
        <div className="lp-nav-inner">
          <Link href="/" className="lp-logo">Backfill</Link>
          <Link href="/onboarding" className="lp-nav-cta">Try Backfill Free</Link>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="lp-hero">
        <div className="lp-hero-inner">
          <span className="lp-eyebrow">AI shift coverage &middot; Always on</span>
          <h1 className="lp-hero-headline">
            From Callout<br />to Covered.
          </h1>
          <p className="lp-hero-sub">
            Callouts happen. Scrambling doesn&rsquo;t have to. Backfill handles callouts and
            last-minute shift changes automatically &mdash; so you never have to.
          </p>
          <div className="lp-hero-actions">
            <Link href="/onboarding" className="lp-btn-primary">Try Backfill Free</Link>
          </div>
          <p className="lp-hero-note">Or call us at <a href="tel:18002225345" style={{ color: "inherit", textDecoration: "underline", textDecorationColor: "var(--muted)" }}>1-800-BACKFILL</a> &mdash; we&rsquo;ll have you live in 24 hours.</p>

          <div className="lp-stats-row">
            <div className="lp-stat">
              <span className="lp-stat-value">$20</span>
              <span className="lp-stat-label">per shift filled, flat</span>
            </div>
            <div className="lp-stat">
              <span className="lp-stat-value">&lt; 4 min</span>
              <span className="lp-stat-label">average fill time</span>
            </div>
            <div className="lp-stat">
              <span className="lp-stat-value">0</span>
              <span className="lp-stat-label">manager hours spent</span>
            </div>
            <div className="lp-stat">
              <span className="lp-stat-value">24/7</span>
              <span className="lp-stat-label">on-call coverage</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── The Problem ──────────────────────────────────────────────────── */}
      <section className="lp-section lp-problem">
        <div className="lp-section-inner">
          <span className="lp-eyebrow">The problem</span>
          <h2 className="lp-section-headline">
            It&rsquo;s 5:47 AM. Your opener just called out.
          </h2>
          <p className="lp-section-sub">
            Here&rsquo;s what that morning looks like without Backfill.
          </p>

          <div className="lp-timeline">
            <div className="lp-timeline-entry">
              <span className="lp-timeline-time">5:47 AM</span>
              <p>Voicemail. Your opener isn&rsquo;t coming in. Service starts in two hours.</p>
            </div>
            <div className="lp-timeline-entry">
              <span className="lp-timeline-time">5:49 AM</span>
              <p>You open the group chat. You start texting names. Most are asleep.</p>
            </div>
            <div className="lp-timeline-entry">
              <span className="lp-timeline-time">5:58 AM</span>
              <p>Three replies. Two can&rsquo;t do it. One wants to negotiate hours.</p>
            </div>
            <div className="lp-timeline-entry">
              <span className="lp-timeline-time">6:15 AM</span>
              <p>You call someone else. Rings out. You leave a voicemail and wait.</p>
            </div>
            <div className="lp-timeline-entry lp-timeline-entry-last">
              <span className="lp-timeline-time">6:34 AM</span>
              <p>Finally. Someone says yes. You&rsquo;ve been at this for 47 minutes before your day even started.</p>
            </div>
          </div>

          <blockquote className="lp-callout-box">
            &ldquo;For a 30-location group, this is happening multiple times a week &mdash; across every
            location, every manager, every shift window. That&rsquo;s not a staffing problem.
            That&rsquo;s a systems problem.&rdquo;
          </blockquote>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section className="lp-section">
        <div className="lp-section-inner">
          <span className="lp-eyebrow">How it works</span>
          <h2 className="lp-section-headline">Three steps. Zero manual work.</h2>
          <p className="lp-section-sub">
            Backfill plugs into your existing workflow. When a shift opens, the engine takes over.
          </p>

          <div className="lp-steps-grid">
            <article className="lp-step-card">
              <span className="lp-step-num">01</span>
              <h3>Callout Detected</h3>
              <p>
                When an employee calls out, a shift goes unclaimed, or a schedule changes &mdash;
                Backfill knows instantly, via your scheduler integration or directly through its
                own built-in calling line.
              </p>
              <span className="lp-badge">Automatic detection</span>
            </article>
            <article className="lp-step-card">
              <span className="lp-step-num">02</span>
              <h3>Backfill Calls</h3>
              <p>
                Backfill&rsquo;s AI agent calls available employees in priority order &mdash; by role,
                availability, and standing. It explains the shift, fields questions, and waits for
                a clear yes.
              </p>
              <span className="lp-badge">Voice AI &middot; Calls go out in seconds</span>
            </article>
            <article className="lp-step-card">
              <span className="lp-step-num">03</span>
              <h3>Shift Filled</h3>
              <p>
                The moment someone confirms, the shift is locked. They get a confirmation. You get
                a notification. Everyone else automatically gets a clear &mdash; no awkward follow-up needed.
              </p>
              <span className="lp-badge">Confirmed &middot; Standby queue activated</span>
            </article>
          </div>
        </div>
      </section>

      {/* ── Integrations ─────────────────────────────────────────────────── */}
      <section className="lp-section">
        <div className="lp-section-inner lp-integrations">
          <span className="lp-eyebrow">Works with your scheduler</span>
          <h2 className="lp-section-headline">Plug in. Go live in 24 hours.</h2>
          <p className="lp-section-sub">
            Already using scheduling software? Backfill connects directly so your shifts, roles,
            and employee data are always in sync.
          </p>
          <div className="lp-chip-row">
            <span className="lp-chip">7shifts</span>
            <span className="lp-chip">Deputy</span>
            <span className="lp-chip">When I Work</span>
            <span className="lp-chip">Homebase</span>
          </div>
          <p className="lp-integration-note">
            No manual data entry. No duplicate setup. Your employees, roles, and availability
            already live in your scheduler &mdash; we sync with it automatically.
          </p>
        </div>
      </section>

      {/* ── Backfill Shifts (dark section) ────────────────────────────────── */}
      <section className="lp-section lp-shifts-section">
        <div className="lp-section-inner">
          <div className="lp-shifts-grid">
            <div className="lp-shifts-left">
              <span className="lp-tag">NEW &mdash; Backfill Shifts</span>
              <h2 className="lp-section-headline lp-headline-light">
                Don&rsquo;t have scheduling software? Ours thinks for you.
              </h2>
              <p className="lp-shifts-body">
                Backfill Shifts isn&rsquo;t just a scheduler. It&rsquo;s an AI-native scheduling layer
                built directly into your Backfill account &mdash; one that builds your schedule,
                learns your operation, and updates itself in plain language.
              </p>
              <p className="lp-shifts-body">
                Tell it what you need. &ldquo;Add a closing shift Friday, same crew as last week.&rdquo;
                Done. &ldquo;Daniela can&rsquo;t do Tuesday &mdash; move her to Thursday.&rdquo; Done. No
                grid-clicking. No manual juggling. Just say what you need and your schedule reflects it.
              </p>
              <p className="lp-shifts-body">
                When a shift opens, the Backfill coverage engine takes over automatically &mdash; same
                as any integrated scheduler, without the third-party subscription.
              </p>
              <p className="lp-shifts-included">Included for all Backfill customers. No additional cost.</p>
            </div>
            <div className="lp-shifts-right">
              <div className="lp-feature-item">
                <h4>AI schedule generation</h4>
                <p>Describe your week, your roles, your team. Backfill Shifts drafts the schedule. You approve, adjust, or just say what&rsquo;s wrong.</p>
              </div>
              <div className="lp-feature-item">
                <h4>Natural language edits</h4>
                <p>No forms, no dropdowns. Type or say the change, and the schedule updates. It&rsquo;s as fast as sending a text.</p>
              </div>
              <div className="lp-feature-item">
                <h4>Pattern learning</h4>
                <p>The more you use it, the better it knows your operation. Recurring roles, preferred staff, shift windows &mdash; it stops asking what you always do.</p>
              </div>
              <div className="lp-feature-item">
                <h4>Real-time coverage board</h4>
                <p>Every open shift, every in-progress fill attempt, every confirmation &mdash; across all locations &mdash; at a glance.</p>
              </div>
              <div className="lp-feature-item">
                <h4>Standby queue management</h4>
                <p>Primary fill falls through? Your pre-ranked standby queue activates automatically. No second round of calls from you.</p>
              </div>
              <div className="lp-feature-item">
                <h4>Upgrade anytime</h4>
                <p>Grow into a dedicated platform later? Everything ports over. No rebuilding from scratch.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Pricing ──────────────────────────────────────────────────────── */}
      <section className="lp-section">
        <div className="lp-section-inner lp-pricing-section">
          <span className="lp-eyebrow">Pricing</span>
          <h2 className="lp-section-headline">You pay when we deliver.</h2>
          <p className="lp-section-sub">
            No monthly seat fees. No per-user subscriptions. Backfill charges like labor &mdash;
            when the work gets done.
          </p>

          <div className="lp-pricing-card">
            <div className="lp-pricing-amount">
              <span className="lp-pricing-dollar">$20</span>
              <span className="lp-pricing-unit">per successfully filled shift</span>
            </div>
            <div className="lp-pricing-lines">
              <div className="lp-pricing-line">
                <span>One-time location setup</span>
                <span>Flat fee per site</span>
              </div>
              <div className="lp-pricing-line">
                <span>Backfill Shifts included</span>
                <span>No extra cost</span>
              </div>
              <div className="lp-pricing-line">
                <span>Scheduler integrations</span>
                <span>Included</span>
              </div>
              <div className="lp-pricing-line">
                <span>Unfilled attempts</span>
                <span>$0</span>
              </div>
              <div className="lp-pricing-line">
                <span>Monthly commitment</span>
                <span>None</span>
              </div>
            </div>
          </div>

          <blockquote className="lp-pricing-philosophy">
            &ldquo;Our take: AI agents aren&rsquo;t software. They&rsquo;re labor. You wouldn&rsquo;t pay
            a staffing agency a monthly retainer whether they filled your shifts or not &mdash;
            and you shouldn&rsquo;t pay us that way either.&rdquo;
          </blockquote>
        </div>
      </section>

      {/* ── FAQ ──────────────────────────────────────────────────────────── */}
      <section className="lp-section">
        <div className="lp-section-inner">
          <span className="lp-eyebrow">FAQ</span>
          <h2 className="lp-section-headline">Questions operators actually ask.</h2>
          <p className="lp-section-sub">Straight answers. No runaround.</p>

          <div className="lp-faq-list">
            <details className="lp-faq">
              <summary>How does Backfill know who to call?</summary>
              <p>During setup, you define your team, their roles, and their availability. Backfill uses that data to build a prioritized call list &mdash; by role fit, availability, and standing. You control the order. We work it.</p>
            </details>
            <details className="lp-faq">
              <summary>What happens if nobody picks up or says yes?</summary>
              <p>Backfill keeps working the list. If the shift goes unfilled, you&rsquo;re notified immediately so you can step in &mdash; but you&rsquo;re never left in the dark mid-attempt. And you don&rsquo;t pay for unfilled shifts.</p>
            </details>
            <details className="lp-faq">
              <summary>Do my employees need to download an app?</summary>
              <p>No. Backfill reaches them the way they already communicate &mdash; by phone. No app installs, no new logins, no behavior change required from your team.</p>
            </details>
            <details className="lp-faq">
              <summary>What if I already use a scheduling platform?</summary>
              <p>Backfill integrates directly with 7shifts, Deputy, When I Work, and Homebase. Your existing schedule syncs automatically &mdash; no duplicate setup.</p>
            </details>
            <details className="lp-faq">
              <summary>What is Backfill Shifts, and do I have to use it?</summary>
              <p>Backfill Shifts is our built-in AI-native scheduling layer for businesses that don&rsquo;t have a scheduling platform. It&rsquo;s included with your Backfill account at no extra cost. If you already have a scheduler, you don&rsquo;t need it &mdash; but it&rsquo;s there if you do.</p>
            </details>
            <details className="lp-faq">
              <summary>How does billing work?</summary>
              <p>You pay $20 per successfully filled shift, plus a one-time location setup fee. If a shift goes unfilled, you&rsquo;re not charged. No monthly fees, no minimums, no surprises.</p>
            </details>
            <details className="lp-faq">
              <summary>How long does setup take?</summary>
              <p>Most customers are live within 24 hours of their first call with us. That&rsquo;s it.</p>
            </details>
            <details className="lp-faq">
              <summary>Is Backfill only for restaurants?</summary>
              <p>Backfill was built with restaurant and hospitality operators in mind &mdash; environments where shift coverage is mission-critical and time-sensitive. If that sounds like your operation, we&rsquo;re a fit.</p>
            </details>
          </div>
        </div>
      </section>

      {/* ── Final CTA ────────────────────────────────────────────────────── */}
      <section className="lp-section lp-final-cta">
        <div className="lp-section-inner lp-final-cta-inner">
          <h2>Ready to stop making those 6 AM calls?</h2>
          <p>See how Backfill handles it in a 20-minute demo. No pressure, no commitment.</p>
          <Link href="/onboarding" className="lp-btn-primary lp-btn-lg">Try Backfill Free</Link>
          <span className="lp-final-note">Or call us at <a href="tel:18002225345" style={{ color: "inherit", textDecoration: "underline" }}>1-800-BACKFILL</a> &middot; Mon&ndash;Fri 8am&ndash;6pm PT</span>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="lp-footer">
        <div className="lp-footer-inner">
          <span className="lp-footer-logo">Backfill</span>
          <span className="lp-footer-copy">&copy; 2026 Backfill Technologies, Inc.</span>
        </div>
      </footer>
    </main>
  );
}
