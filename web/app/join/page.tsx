import { SectionCard } from "@/components/section-card";

export default function JoinPage() {
  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Worker Follow-Up</span>
        <h1>Finish the details after consent is captured.</h1>
        <p>
          1-800-BACKFILL handles intent and action. This page handles the structured details that are easier
          with a screen: certifications, preferences, and confirmed shift history.
        </p>
      </div>

      <div className="three-up">
        <SectionCard title="1. Confirm profile">
          <p>Name, phone, roles, work area, and preferred response channel.</p>
        </SectionCard>
        <SectionCard title="2. Add credentials">
          <p>Food handler, ServSafe, TIPS, and any role-specific certifications used for matching.</p>
        </SectionCard>
        <SectionCard title="3. Review confirmed work">
          <p>Keep one place for confirmed shifts, prior fills, and follow-up instructions.</p>
        </SectionCard>
      </div>

      <section className="section">
        <div className="callout">
          <h3>Follow-up destination</h3>
          <p>
            Use <strong>backfill.com/join</strong> after consent is captured by phone or text and the worker needs to finish structured details.
          </p>
        </div>
      </section>
    </main>
  );
}
