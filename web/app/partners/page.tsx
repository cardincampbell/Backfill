import { SectionCard } from "@/components/section-card";

export default function PartnersPage() {
  return (
    <main className="section">
      <div className="page-head">
        <span className="eyebrow">Reserved for later</span>
        <h1>Agency partner surface placeholder.</h1>
        <p>
          This page is intentionally present as a TypeScript route, but the Tier 3 workflow remains out of scope for now.
        </p>
      </div>

      <div className="two-up">
        <SectionCard title="Why keep the route now?">
          <p>It lets the Vercel app own the eventual partner UX without blocking the current Native Lite and Tier 2 work.</p>
        </SectionCard>
        <SectionCard title="What is deferred?">
          <p>Request intake, accept/decline flows, candidate confirmations, SLA routing, and partner metrics.</p>
        </SectionCard>
      </div>
    </main>
  );
}
