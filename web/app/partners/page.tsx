import { SectionCard } from "@/components/section-card";

export default function PartnersPage() {
  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Tier 3 Network</span>
        <h1>Agency partner routing is part of the operating model.</h1>
        <p>
          Backfill does not run a labor marketplace. When internal and alumni coverage fail, the system routes
          structured requests to partner agencies and keeps the operator in one workflow.
        </p>
      </div>

      <div className="two-up">
        <SectionCard title="What partners receive">
          <p>Role, shift window, pay, location, certifications, urgency, notes, and acceptance deadline.</p>
        </SectionCard>
        <SectionCard title="What the system tracks">
          <p>Request status, response deadlines, candidate pending states, confirmations, and manager approval before external fill finalization.</p>
        </SectionCard>
      </div>

      <section className="section">
        <div className="callout">
          <h3>Current transport</h3>
          <p>Phase 1 stays simple: structured SMS and email first, richer partner portal later.</p>
        </div>
      </section>
    </main>
  );
}
