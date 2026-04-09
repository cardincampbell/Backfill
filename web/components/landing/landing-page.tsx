import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowRight, Check, Phone, Zap } from "lucide-react";

import { LandingHero } from "@/components/landing/landing-hero";
import { LandingNav } from "@/components/landing/landing-nav";
import { LandingReveal } from "@/components/landing/landing-reveal";

const LandingBackfillShiftsInterface = dynamic(
  () =>
    import("./landing-backfill-shifts-interface").then((module) => ({
      default: module.LandingBackfillShiftsInterface,
    })),
  {
    loading: () => (
      <div className="w-full overflow-hidden rounded-[24px] border border-[#d8dee6] bg-white shadow-[0_8px_40px_rgba(0,0,0,0.12)]">
        <div className="grid min-h-[520px] md:min-h-[620px] md:grid-cols-[260px_minmax(0,1fr)]">
          <div className="hidden border-r border-[#e2e8f0] bg-[#0D1B2A] md:block" />
          <div className="bg-[linear-gradient(180deg,#ffffff_0%,#f7f8fa_100%)]" />
        </div>
      </div>
    ),
  },
);

const LandingFaq = dynamic(
  () =>
    import("./landing-faq").then((module) => ({
      default: module.LandingFaq,
    })),
  {
    loading: () => (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={index}
            className="h-[74px] rounded-[20px] border border-[#e2e8f0] bg-white shadow-[0_2px_12px_rgba(0,0,0,0.03)]"
          />
        ))}
      </div>
    ),
  },
);

const INDUSTRIES = [
  "Restaurants",
  "Retail",
  "Healthcare",
  "Hospitality",
  "Warehouses",
];

const PROBLEM_TIMELINE = [
  {
    time: "5:47 AM",
    text: "Voicemail. Your opener isn't coming in. Service starts in two hours.",
  },
  {
    time: "5:49 AM",
    text: "You open the group chat. You start texting names. Most are asleep.",
  },
  {
    time: "5:58 AM",
    text: "Three replies. Two can't do it. One wants to negotiate hours.",
  },
  {
    time: "6:15 AM",
    text: "You call someone else. Rings out. You leave a voicemail and wait.",
  },
  {
    time: "6:34 AM",
    text: "Finally. Someone says yes. You've been at this for 47 minutes before your day even started.",
  },
];

const HOW_IT_WORKS = [
  {
    step: "01",
    title: "Callout Detected",
    subtitle: "A shift opens",
    description:
      "When an employee calls out, a shift goes unclaimed, or a schedule changes — Backfill knows instantly, via your scheduler integration or directly through its own built-in calling line.",
    badge: "Automatic detection",
    icon: <Zap className="h-5 w-5" />,
    color: "#635BFF",
    gradient: "from-[#635BFF]/10 to-[#635BFF]/[0.02]",
  },
  {
    step: "02",
    title: "Backfill Calls",
    subtitle: "Your list gets worked",
    description:
      "Backfill's AI agent calls available employees in priority order — by role, availability, and standing. It explains the shift, fields questions, and waits for a clear yes.",
    badge: "Voice AI · Calls in seconds",
    icon: <Phone className="h-5 w-5" />,
    color: "#0070F3",
    gradient: "from-[#0070F3]/10 to-[#0070F3]/[0.02]",
  },
  {
    step: "03",
    title: "Shift Filled",
    subtitle: "First yes wins",
    description:
      "The moment someone confirms, the shift is locked. They get a confirmation. You get a notification. Everyone else automatically gets a clear — no awkward follow-up needed.",
    badge: "Confirmed · Standby queue active",
    icon: <Check className="h-5 w-5" />,
    color: "#00C7B7",
    gradient: "from-[#00C7B7]/10 to-[#00C7B7]/[0.02]",
  },
];

const SHIFT_FEATURES = [
  {
    title: "AI schedule generation",
    description:
      "Describe your week, your roles, your team. Backfill Shifts drafts the schedule. You approve, adjust, or just say what's wrong.",
  },
  {
    title: "Natural language edits",
    description:
      "No forms, no dropdowns. Type or say the change, and the schedule updates. It's as fast as sending a text.",
  },
  {
    title: "Pattern learning",
    description:
      "The more you use it, the better it knows your operation. Recurring roles, preferred staff, shift windows — it stops asking what you always do.",
  },
  {
    title: "Real-time coverage board",
    description:
      "Every open shift, every in-progress fill attempt, every confirmation — across all locations — at a glance.",
  },
  {
    title: "Standby queue management",
    description:
      "Primary fill falls through? Your pre-ranked standby queue activates automatically. No second round of calls from you.",
  },
  {
    title: "Upgrade anytime",
    description:
      "Grow into a dedicated platform later? Everything ports over. No rebuilding from scratch.",
  },
];

const INTEGRATIONS = ["7shifts", "Deputy", "When I Work", "Homebase"];

const FOOTER_PRODUCT_LINKS = [
  { label: "How It Works", href: "#product" },
  { label: "Backfill Shifts", href: "#backfill-shifts" },
  { label: "Integrations", href: "#integrations" },
  { label: "Pricing", href: "#pricing" },
];

const FOOTER_COMPANY_LINKS = ["About", "Blog", "Careers", "Contact"];
const FOOTER_LEGAL_LINKS = ["Privacy", "Terms", "Security"];
const FOOTER_SOCIAL_LINKS = ["Twitter", "LinkedIn"];

function DotGrid({ className = "" }: { className?: string }) {
  return (
    <div
      className={`pointer-events-none absolute inset-0 ${className}`}
      style={{
        backgroundImage:
          "radial-gradient(circle, rgba(99,91,255,0.07) 1px, transparent 1px)",
        backgroundSize: "24px 24px",
      }}
    />
  );
}

export default function LandingPage() {
  const currentYear = new Date().getFullYear();

  return (
    <div
      className="landing-page min-h-screen overflow-x-hidden bg-white"
      style={{ fontFamily: "'Inter', system-ui, sans-serif" }}
    >
      <LandingNav />
      <LandingHero />

      <section className="border-y border-[#f0f0f5] bg-white px-5 py-8 sm:px-6 sm:py-10 lg:px-8">
        <LandingReveal className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-center gap-4 sm:gap-6 md:gap-12" distance={12} duration={0.5}>
          <span
            className="w-full text-center text-[13px] uppercase tracking-[0.1em] text-[#8898AA] md:w-auto"
            style={{ fontWeight: 500 }}
          >
            Built for
          </span>
          {INDUSTRIES.map((industry) => (
            <span
              key={industry}
              className="text-[14px] text-[#425466]/70 sm:text-[15px]"
              style={{ fontWeight: 450 }}
            >
              {industry}
            </span>
          ))}
        </LandingReveal>
      </section>

      <section className="relative overflow-hidden bg-[#0A2540] px-5 py-20 text-white sm:px-6 sm:py-32 lg:px-8">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />
        <div className="absolute right-0 top-0 h-[600px] w-[600px] rounded-full bg-gradient-to-bl from-[#635BFF]/15 via-transparent to-transparent blur-[120px]" />
        <div className="absolute bottom-0 left-0 h-[400px] w-[400px] rounded-full bg-gradient-to-tr from-[#00C7B7]/8 via-transparent to-transparent blur-[100px]" />

        <div className="relative z-10 mx-auto max-w-[900px]">
          <LandingReveal className="mb-14 sm:mb-20">
            <div
              className="mb-5 text-[12px] uppercase tracking-[0.2em] text-[#635BFF]"
              style={{ fontWeight: 600 }}
            >
              The problem
            </div>
            <h2
              className="mb-6 text-[30px] leading-[1.1] tracking-[-0.03em] sm:text-[44px] lg:text-[52px]"
              style={{ fontWeight: 600 }}
            >
              It&apos;s 5:47 AM. Your opener just called out.
            </h2>
            <p className="text-[16px] leading-[1.65] text-[#8898AA] sm:text-[19px]">
              Here&apos;s what that morning looks like without Backfill.
            </p>
          </LandingReveal>

          <div className="relative space-y-0">
            <div className="absolute bottom-0 left-[14px] top-0 w-px bg-gradient-to-b from-[#635BFF]/30 via-white/[0.06] to-[#635BFF]/30 sm:left-[108px]" />
            {PROBLEM_TIMELINE.map((item, index) => (
              <LandingReveal
                key={item.time}
                axis="x"
                delay={index * 0.08}
                duration={0.5}
                distance={20}
                className="group flex flex-col items-start gap-1 py-4 pl-8 sm:flex-row sm:gap-8 sm:py-5 sm:pl-0"
              >
                <div
                  className="pt-0.5 font-mono text-[13px] text-[#8898AA] transition-colors group-hover:text-white/60 sm:min-w-[88px] sm:text-[14px]"
                  style={{ fontWeight: 450 }}
                >
                  {item.time}
                </div>
                <div className="relative">
                  <div className="absolute -left-[22px] top-[7px] h-2 w-2 rounded-full border-2 border-[#0A2540] bg-[#1A3A5C] ring-[3px] ring-[#1A3A5C]/50 transition-all group-hover:bg-[#635BFF] group-hover:ring-[#635BFF]/20 sm:-left-[34px]" />
                  <div className="text-[15px] leading-[1.65] text-white/75 transition-colors group-hover:text-white/95 sm:text-[17px]">
                    {item.text}
                  </div>
                </div>
              </LandingReveal>
            ))}
          </div>

          <LandingReveal
            className="mt-12 border border-white/[0.06] bg-white/[0.02] p-6 backfill-ui-radius sm:mt-16 sm:p-8"
            delay={0.3}
          >
            <p className="text-[15px] italic leading-[1.8] text-[#8898AA] sm:text-[17px]">
              &quot;For a 30-location group, this is happening multiple times a
              week — across every location, every manager, every shift window.
              That&apos;s not a staffing problem. That&apos;s a systems problem.&quot;
            </p>
          </LandingReveal>
        </div>
      </section>

      <section
        id="product"
        className="relative overflow-hidden bg-white px-5 py-20 sm:px-6 sm:py-32 lg:px-8"
      >
        <DotGrid className="opacity-30" />
        <div className="relative mx-auto max-w-[1200px]">
          <LandingReveal className="mb-14 max-w-2xl sm:mb-20">
            <div
              className="mb-5 text-[12px] uppercase tracking-[0.2em] text-[#635BFF]"
              style={{ fontWeight: 600 }}
            >
              How it works
            </div>
            <h2
              className="mb-6 text-[30px] leading-[1.1] tracking-[-0.03em] text-[#0A2540] sm:text-[44px] lg:text-[52px]"
              style={{ fontWeight: 600 }}
            >
              Three steps. Zero manual work.
            </h2>
            <p className="text-[16px] leading-[1.65] text-[#425466] sm:text-[18px]">
              No scrambling. No group chat. Our coverage engine takes over and
              notifies you when it&apos;s done.
            </p>
          </LandingReveal>

          <div className="grid gap-5 sm:grid-cols-2 md:grid-cols-3">
            {HOW_IT_WORKS.map((item, index) => (
              <LandingReveal
                key={item.step}
                delay={index * 0.1}
                distance={30}
                className={`group relative border border-[#e2e8f0] bg-gradient-to-b ${item.gradient} p-8 transition-all duration-300 hover:-translate-y-[2px] hover:border-[#c4d1e0] hover:shadow-[0_12px_40px_rgba(0,0,0,0.06)] backfill-ui-radius`}
              >
                <div
                  className="absolute right-6 top-6 text-[72px] leading-none tracking-[-0.04em] text-[#0A2540]/[0.04]"
                  style={{ fontWeight: 700 }}
                >
                  {item.step}
                </div>

                <div className="mb-8 flex items-center gap-3">
                  <div
                    className="flex h-10 w-10 items-center justify-center text-white backfill-ui-radius"
                    style={{ backgroundColor: item.color }}
                  >
                    {item.icon}
                  </div>
                </div>
                <h3
                  className="mb-1.5 text-[22px] tracking-[-0.02em] text-[#0A2540]"
                  style={{ fontWeight: 600 }}
                >
                  {item.title}
                </h3>
                <div
                  className="mb-4 text-[14px] text-[#8898AA]"
                  style={{ fontWeight: 450 }}
                >
                  {item.subtitle}
                </div>
                <p className="mb-6 text-[15px] leading-[1.7] text-[#425466]">
                  {item.description}
                </p>
                <div
                  className="inline-block border border-[#e2e8f0] bg-white/80 px-3 py-1.5 text-[12px] text-[#425466] backfill-ui-radius"
                  style={{ fontWeight: 500 }}
                >
                  {item.badge}
                </div>
              </LandingReveal>
            ))}
          </div>

          <LandingReveal
            as="blockquote"
            className="mt-16 max-w-2xl border-l-4 border-[#635BFF] pl-7 py-1"
            delay={0.2}
          >
            <p
              className="mb-4 text-[18px] italic leading-[1.65] text-[#0A2540] sm:text-[20px]"
              style={{ fontWeight: 450 }}
            >
              &ldquo;I used to spend the first hour of every morning chasing
              coverage. Now I check the app and it&apos;s already done.&rdquo;
            </p>
            <cite
              className="text-[13px] tracking-[0.01em] text-[#8898AA] not-italic"
              style={{ fontWeight: 500 }}
            >
              — Operations Manager, 3-location casual dining group, Los Angeles
            </cite>
          </LandingReveal>
        </div>
      </section>

      <section
        id="backfill-shifts"
        className="relative overflow-hidden bg-[#0A2540] px-5 py-20 text-white sm:px-6 sm:py-32 lg:px-8"
      >
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.025]"
          style={{
            backgroundImage:
              "radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />
        <div className="absolute left-1/2 top-0 h-[500px] w-[900px] -translate-x-1/2 rounded-full bg-gradient-to-b from-[#635BFF]/12 via-transparent to-transparent blur-[120px]" />

        <div className="relative z-10 mx-auto max-w-[1200px]">
          <LandingReveal className="mb-16">
            <div
              className="mb-8 inline-flex items-center gap-2 border border-[#635BFF]/25 bg-[#635BFF]/15 px-3.5 py-1.5 text-[12px] uppercase tracking-[0.08em] text-[#a5a0ff] backfill-ui-radius"
              style={{ fontWeight: 600 }}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[#635BFF]" />
              Backfill Shifts
            </div>
            <h2
              className="mb-6 max-w-3xl text-[30px] leading-[1.08] tracking-[-0.03em] sm:text-[44px] lg:text-[52px]"
              style={{ fontWeight: 600 }}
            >
              Don&apos;t have scheduling software? Ours thinks for you.
            </h2>
            <div className="max-w-2xl space-y-5 text-[16px] leading-[1.8] text-[#8898AA] sm:text-[18px]">
              <p>
                Backfill Shifts isn&apos;t asking you to change how you run your
                restaurant. It&apos;s asking you to stop doing one thing: the
                schedule in your head. Tell the AI what your week looks like.
                It drafts it, you approve it, and the coverage engine takes
                over from there.
              </p>
              <ul className="list-none space-y-2 pl-0 text-[#b0b8c8]">
                <li>
                  &ldquo;Add a closing shift Friday, same crew as last
                  week.&rdquo; Done.
                </li>
                <li>
                  &ldquo;Daniela can&apos;t do Tuesday — move her to Thursday.&rdquo;
                  Done.
                </li>
              </ul>
              <p>
                You&apos;re not learning software. You&apos;re having a
                conversation.
              </p>
            </div>
          </LandingReveal>

          <LandingReveal className="mb-16" delay={0.2} distance={30}>
            <LandingBackfillShiftsInterface />
          </LandingReveal>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {SHIFT_FEATURES.map((feature, index) => (
              <LandingReveal
                key={feature.title}
                delay={index * 0.06}
                duration={0.5}
                className="group border border-white/[0.06] bg-white/[0.02] p-6 transition-all duration-300 hover:border-[#635BFF]/30 hover:bg-white/[0.04] backfill-ui-radius"
              >
                <h3
                  className="mb-2 text-[17px] tracking-[-0.01em] text-white/90 transition-colors group-hover:text-white"
                  style={{ fontWeight: 550 }}
                >
                  {feature.title}
                </h3>
                <p className="text-[14px] leading-[1.65] text-[#8898AA]/80 transition-colors group-hover:text-[#8898AA]">
                  {feature.description}
                </p>
              </LandingReveal>
            ))}
          </div>

          <LandingReveal className="mt-12 text-center" delay={0.5} opacityOnly>
            <p className="text-[14px] text-white/30">
              Included for all Backfill customers. No additional cost.
            </p>
          </LandingReveal>
        </div>
      </section>

      <section
        id="integrations"
        className="relative overflow-hidden bg-[#fafbfd] px-5 py-20 sm:px-6 sm:py-28 lg:px-8"
      >
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#e2e8f0] to-transparent" />
        <LandingReveal className="mx-auto max-w-[900px] text-center">
          <div
            className="mb-5 text-[12px] uppercase tracking-[0.2em] text-[#635BFF]"
            style={{ fontWeight: 600 }}
          >
            Integrations
          </div>
          <h2
            className="mb-6 text-[30px] leading-[1.1] tracking-[-0.03em] text-[#0A2540] sm:text-[44px] lg:text-[52px]"
            style={{ fontWeight: 600 }}
          >
            Plug in. Go live in 24 hours.
          </h2>
          <p className="mb-10 text-[16px] leading-[1.65] text-[#425466] sm:mb-14 sm:text-[18px]">
            Already using scheduling software? Backfill connects directly so
            your shifts, roles, and employee data are always in sync.
          </p>

          <div className="mb-10 grid grid-cols-2 justify-center gap-3 sm:mb-14 sm:flex sm:flex-wrap">
            {INTEGRATIONS.map((integration) => (
              <div
                key={integration}
                className="border border-[#e2e8f0] bg-white px-6 py-4 text-[16px] text-[#0A2540] shadow-[0_1px_3px_rgba(0,0,0,0.04)] transition-all duration-300 hover:-translate-y-[1px] hover:scale-[1.02] hover:shadow-[0_8px_25px_rgba(0,0,0,0.07)] backfill-ui-radius"
                style={{ fontWeight: 500 }}
              >
                {integration}
              </div>
            ))}
          </div>

          <p className="mx-auto max-w-lg text-[15px] leading-[1.7] text-[#8898AA]">
            No manual data entry. No duplicate setup. Your employees, roles,
            and availability sync automatically.
          </p>
        </LandingReveal>
      </section>

      <section
        id="pricing"
        className="relative overflow-hidden bg-gradient-to-b from-[#060F1F] via-[#0B1A33] to-[#060F1F] px-5 py-20 text-white sm:px-6 sm:py-32 lg:px-8"
      >
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(99,91,255,0.18) 0%, transparent 60%), radial-gradient(ellipse 60% 50% at 80% 100%, rgba(0,199,183,0.1) 0%, transparent 50%), radial-gradient(ellipse 40% 40% at 20% 50%, rgba(99,91,255,0.08) 0%, transparent 50%)",
          }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              "radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)",
            backgroundSize: "24px 24px",
          }}
        />
        <div className="absolute left-0 right-0 top-0 h-px bg-gradient-to-r from-transparent via-[#635BFF]/40 to-transparent" />
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#635BFF]/20 to-transparent" />

        <div className="relative z-10 mx-auto max-w-[900px]">
          <LandingReveal className="mb-16 text-center">
            <div
              className="mb-5 text-[12px] uppercase tracking-[0.2em] text-[#635BFF]"
              style={{ fontWeight: 600 }}
            >
              Pricing
            </div>
            <h2
              className="mb-6 text-[30px] leading-[1.1] tracking-[-0.03em] sm:text-[44px] lg:text-[52px]"
              style={{ fontWeight: 600 }}
            >
              You pay when we deliver.
            </h2>
            <p className="mx-auto max-w-lg text-[16px] leading-[1.65] text-[#8898AA] sm:text-[18px]">
              No monthly seat fees. No per-user subscriptions. Backfill charges
              like labor — when the work gets done.
            </p>
          </LandingReveal>

          <LandingReveal
            className="relative overflow-hidden rounded-[32px] border border-white/[0.08] bg-white/[0.04] p-7 backdrop-blur-sm sm:p-10 lg:p-12"
          >
            <div className="absolute inset-0 rounded-[32px] bg-gradient-to-br from-[#635BFF]/[0.06] via-transparent to-[#00C7B7]/[0.04]" />
            <div className="relative z-10">
              <div className="mb-10 text-center">
                <div
                  className="mb-1 text-[56px] tracking-[-0.04em] sm:text-[72px]"
                  style={{ fontWeight: 600 }}
                >
                  $20
                </div>
                <div
                  className="text-[16px] text-[#8898AA]"
                  style={{ fontWeight: 450 }}
                >
                  per successfully filled shift
                </div>
              </div>

              <div className="mt-10 text-center">
                <Link
                  href="/try"
                  className="group inline-flex items-center gap-2 bg-[#635BFF] px-7 py-3.5 text-[15px] text-white shadow-[0_4px_20px_rgba(99,91,255,0.4)] transition-all duration-300 hover:-translate-y-[1px] hover:shadow-[0_6px_30px_rgba(99,91,255,0.55)] backfill-ui-radius"
                  style={{ fontWeight: 500 }}
                >
                  Get Started Free
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </Link>
              </div>
            </div>
          </LandingReveal>

          <LandingReveal
            as="blockquote"
            className="mx-auto mt-10 max-w-3xl border-l-4 border-[#635BFF]/60 pl-7 py-1"
            delay={0.2}
          >
            <p
              className="mb-4 text-[17px] italic leading-[1.65] text-white/80 sm:text-[19px]"
              style={{ fontWeight: 400 }}
            >
              &ldquo;The first month I used Backfill I filled 11 shifts I would
              have had to handle manually. At 45 minutes each, that&apos;s over
              8 hours back. The math wasn&apos;t hard.&rdquo;
            </p>
            <cite
              className="text-[13px] tracking-[0.01em] text-[#8898AA] not-italic"
              style={{ fontWeight: 500 }}
            >
              — GM, fast casual restaurants, 4 locations
            </cite>
          </LandingReveal>
        </div>
      </section>

      <section className="relative bg-[#fafbfd] px-5 py-20 sm:px-6 sm:py-32 lg:px-8">
        <div className="absolute left-0 right-0 top-0 h-px bg-gradient-to-r from-transparent via-[#e2e8f0] to-transparent" />
        <div className="mx-auto max-w-[900px]">
          <LandingReveal className="mb-16">
            <div
              className="mb-5 text-[12px] uppercase tracking-[0.2em] text-[#635BFF]"
              style={{ fontWeight: 600 }}
            >
              FAQ
            </div>
            <h2
              className="mb-5 text-[30px] leading-[1.1] tracking-[-0.03em] text-[#0A2540] sm:text-[44px] lg:text-[52px]"
              style={{ fontWeight: 600 }}
            >
              Questions operators actually ask.
            </h2>
            <p className="text-[16px] text-[#425466] sm:text-[18px]">
              Straight answers. No runaround.
            </p>
          </LandingReveal>

          <LandingFaq />
        </div>
      </section>

      <section className="relative overflow-hidden bg-[#0A2540] px-5 py-24 text-white sm:px-6 sm:py-36 lg:px-8">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage:
              "radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />
        <div className="absolute inset-0">
          <div className="absolute left-1/2 top-[-200px] h-[500px] w-[1000px] -translate-x-1/2 rounded-full bg-gradient-to-b from-[#635BFF]/20 via-[#0070F3]/10 to-transparent blur-[120px]" />
        </div>

        <LandingReveal className="relative z-10 mx-auto max-w-[700px] text-center">
          <h2
            className="mb-6 text-[30px] leading-[1.08] tracking-[-0.03em] sm:text-[44px] lg:text-[56px]"
            style={{ fontWeight: 600 }}
          >
            Ready to stop making those 6 AM calls?
          </h2>
          <p className="mb-10 text-[16px] leading-[1.65] text-[#8898AA] sm:text-[18px]">
            Join the operators who let Backfill handle the scramble.
          </p>
          <Link
            href="/try"
            className="group inline-flex items-center gap-2.5 bg-white px-8 py-4 text-[16px] text-[#0A2540] shadow-[0_4px_20px_rgba(255,255,255,0.15)] transition-all hover:-translate-y-[1px] hover:bg-white/95 hover:shadow-[0_6px_30px_rgba(255,255,255,0.2)] backfill-ui-radius"
            style={{ fontWeight: 550 }}
          >
            Start filling callouts autonomously
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </LandingReveal>
      </section>

      <footer className="border-t border-[#f0f0f5] bg-white px-5 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="mx-auto max-w-[1200px]">
          <div className="mb-14 grid grid-cols-2 gap-10 md:grid-cols-4">
            <div className="col-span-2 md:col-span-1">
              <div
                className="mb-3 text-[20px] tracking-[-0.02em] text-[#0A2540]"
                style={{ fontWeight: 620 }}
              >
                Backfill
              </div>
              <p className="max-w-[200px] text-[14px] leading-[1.65] text-[#8898AA]">
                AI-powered shift coverage for teams that can&apos;t afford
                service interruptions.
              </p>
            </div>
            <div>
              <div
                className="mb-4 text-[13px] uppercase tracking-[0.1em] text-[#8898AA]"
                style={{ fontWeight: 550 }}
              >
                Product
              </div>
              <div className="space-y-3">
                {FOOTER_PRODUCT_LINKS.map((link) => (
                  <div key={link.label}>
                    <a
                      href={link.href}
                      className="text-[14px] text-[#425466] transition-colors hover:text-[#0A2540]"
                      style={{ fontWeight: 420 }}
                    >
                      {link.label}
                    </a>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div
                className="mb-4 text-[13px] uppercase tracking-[0.1em] text-[#8898AA]"
                style={{ fontWeight: 550 }}
              >
                Company
              </div>
              <div className="space-y-3">
                {FOOTER_COMPANY_LINKS.map((link) => (
                  <div key={link}>
                    <a
                      href="#"
                      className="text-[14px] text-[#425466] transition-colors hover:text-[#0A2540]"
                      style={{ fontWeight: 420 }}
                    >
                      {link}
                    </a>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div
                className="mb-4 text-[13px] uppercase tracking-[0.1em] text-[#8898AA]"
                style={{ fontWeight: 550 }}
              >
                Legal
              </div>
              <div className="space-y-3">
                {FOOTER_LEGAL_LINKS.map((link) => (
                  <div key={link}>
                    <a
                      href="#"
                      className="text-[14px] text-[#425466] transition-colors hover:text-[#0A2540]"
                      style={{ fontWeight: 420 }}
                    >
                      {link}
                    </a>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="flex flex-col items-center justify-between gap-4 border-t border-[#f0f0f5] pt-8 md:flex-row">
            <div className="text-[13px] text-[#8898AA]" style={{ fontWeight: 400 }}>
              © {currentYear} Backfill Works, Inc. All rights reserved.
            </div>
            <div className="flex items-center gap-6">
              {FOOTER_SOCIAL_LINKS.map((social) => (
                <a
                  key={social}
                  href="#"
                  className="text-[13px] text-[#8898AA] transition-colors hover:text-[#425466]"
                  style={{ fontWeight: 420 }}
                >
                  {social}
                </a>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
