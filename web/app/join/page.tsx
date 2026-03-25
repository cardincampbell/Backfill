import { SectionCard } from "@/components/section-card";

export default function JoinPage() {
  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Worker support</span>
        <h1>Complete your profile after the call.</h1>
        <p>
          The phone number stays primary. This page exists for the details that are easier with a screen:
          certifications, preferences, and confirmed shift history.
        </p>
      </div>

      <div className="three-up">
        <SectionCard title="1. Confirm your details">
          <p>Name, phone, roles, certifications, and preferred response channel.</p>
        </SectionCard>
        <SectionCard title="2. Upload certifications">
          <p>Food handler, ServSafe, TIPS, or any role-specific requirements.</p>
        </SectionCard>
        <SectionCard title="3. Review upcoming shifts">
          <p>Keep one place for confirmed assignments and prior fill history.</p>
        </SectionCard>
      </div>

      <section className="section">
        <div className="callout">
          <h3>Suggested URL</h3>
          <p>
            Use <strong>backfill.com/join</strong> as the follow-up text destination after job-seeker or worker-intake calls.
          </p>
        </div>
      </section>
    </main>
  );
}
