"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion, useScroll, useTransform } from "motion/react";
import { ArrowRight, Check, Phone, Zap } from "lucide-react";

import { LandingBackfillShiftsInterface } from "./landing-backfill-shifts-interface";
import { LandingFaq } from "./landing-faq";
import { LandingPhoneMockup } from "./landing-phone-mockup";

function DotGrid({ className = '' }: { className?: string }) {
  return (
    <div
      className={`absolute inset-0 pointer-events-none ${className}`}
      style={{
        backgroundImage: 'radial-gradient(circle, rgba(99,91,255,0.07) 1px, transparent 1px)',
        backgroundSize: '24px 24px',
      }}
    />
  );
}

export default function LandingPage() {
  const [isScrolled, setIsScrolled] = useState(false);
  const { scrollY } = useScroll();
  const heroY = useTransform(scrollY, [0, 800], [0, 80]);
  const heroOpacity = useTransform(scrollY, [0, 500], [1, 0]);
  const currentYear = new Date().getFullYear();

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <div className="bg-white min-h-screen overflow-x-hidden" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Navigation */}
      <motion.nav
        initial={{ y: -100 }}
        animate={{ y: 0 }}
        transition={{ duration: 0.6 }}
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 px-5 sm:px-6 lg:px-8 ${
          isScrolled
            ? 'bg-white/80 backdrop-blur-2xl border-b border-neutral-200/60 shadow-[0_1px_3px_rgba(0,0,0,0.04)]'
            : 'bg-transparent'
        }`}
      >
        <div className="max-w-[1200px] mx-auto">
          <div className="flex items-center justify-between h-[64px] sm:h-[72px]">
            <Link href="/">
              <motion.div
                className="text-[20px] sm:text-[22px] tracking-[-0.02em] text-[#0A2540] cursor-pointer"
                style={{ fontWeight: 620 }}
                whileHover={{ scale: 1.02 }}
              >
                Backfill
              </motion.div>
            </Link>
            <div className="hidden md:flex items-center gap-8 mr-auto ml-12">
              {['Product', 'Pricing', 'FAQ'].map((item) => (
                <a
                  key={item}
                  href={`#${item.toLowerCase()}`}
                  className="text-[15px] text-[#425466] hover:text-[#0A2540] transition-colors"
                  style={{ fontWeight: 450 }}
                >
                  {item}
                </a>
              ))}
            </div>
            <div className="flex items-center gap-2 sm:gap-4">
              <Link href="/login" className="px-4 py-2 text-[#425466] hover:text-[#0A2540] transition-colors text-[15px]" style={{ fontWeight: 450 }}>
                Sign In
              </Link>
            </div>
          </div>
        </div>
      </motion.nav>

      {/* Hero Section */}
      <section className="relative pt-28 sm:pt-36 pb-20 sm:pb-32 px-5 sm:px-6 lg:px-8 overflow-hidden">
        {/* Background layers */}
        <div className="absolute inset-0 bg-[#fafbfd]" />
        <div className="absolute top-[-400px] right-[-300px] w-[1000px] h-[1000px] bg-gradient-to-bl from-[#635BFF]/[0.13] via-[#80b3ff]/[0.11] to-transparent rounded-full blur-[100px]" />
        <div className="absolute bottom-[-200px] left-[-200px] w-[700px] h-[700px] bg-gradient-to-tr from-[#635BFF]/[0.10] via-transparent to-transparent rounded-full blur-[80px]" />
        <DotGrid className="opacity-50" />
        {/* Bottom edge fade */}
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-white to-transparent" />

        <div className="max-w-[1200px] mx-auto relative">
          <div className="grid lg:grid-cols-2 gap-10 lg:gap-16 items-center">
            {/* Left Column */}
            <motion.div
              style={{ y: heroY, opacity: heroOpacity }}
              className="max-w-xl lg:translate-x-[50px] lg:-translate-y-[20px] min-h-[calc(100svh-140px)] lg:min-h-0 flex flex-col text-left mx-auto lg:mx-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <div className="flex-1 flex flex-col justify-center">
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6 }}
                  className="inline-flex items-center gap-2.5 px-4 py-1.5 bg-white/80 backdrop-blur-sm border border-[#e2e8f0] backfill-ui-radius mb-6 sm:mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.04)] self-start"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-[#635BFF] animate-pulse" />
                  <span className="text-[13px] text-[#425466]" style={{ fontWeight: 500 }}>Always on autonomous shift coverage</span>
                </motion.div>

                <motion.h1
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, delay: 0.1 }}
                  className="text-[64px] sm:text-[48px] md:text-[56px] lg:text-[68px] leading-[1.06] tracking-[-0.035em] mb-5 sm:mb-7"
                  style={{ fontWeight: 780 }}
                >
                  <span className="text-[#0A2540]">From Callout</span>{' '}
                  <br className="hidden lg:block" />
                  <span className="bg-gradient-to-r from-[#0A2540] via-[#635BFF] to-[#00C7B7] bg-clip-text text-transparent">to Covered.</span>
                </motion.h1>

                <motion.p
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, delay: 0.2 }}
                  className="text-[21px] sm:text-[18px] text-[#425466] mb-8 sm:mb-10 leading-[1.75] max-w-md lg:mx-0"
                >
                  Callouts happen. Scrambling doesn't have to. Backfill handles callouts and last-minute shift changes automatically — so you never have to.
                </motion.p>

                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, delay: 0.3 }}
                  className="mb-4 sm:mb-12"
                >
                  <Link
                    href="/try"
                    className="group w-full sm:w-auto px-8 py-4 sm:px-7 sm:py-3.5 bg-[#0A2540] text-white backfill-ui-radius transition-all duration-300 text-[17px] sm:text-[16px] inline-flex items-center justify-center sm:inline-flex gap-2.5 shadow-[0_4px_14px_rgba(10,37,64,0.35)] hover:shadow-[0_6px_24px_rgba(10,37,64,0.45)] hover:translate-y-[-1px]"
                    style={{ fontWeight: 500 }}
                  >
                    Try Backfill Free
                    <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
                  </Link>
                </motion.div>

                {/* Stats */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, delay: 0.4 }}
                  className="flex justify-start gap-6 sm:gap-10 pt-8 border-t border-[#e2e8f0]/80 pb-4 lg:pb-0"
                >
                  {[
                    { value: '< 4 min', label: 'Avg. fill time' },
                    { value: '93%', label: 'Shifts covered' },
                    { value: '1,200', label: 'Businesses' },
                    { value: '0', label: 'Scrambling' },
                  ].map((stat, i) => (
                    <div key={i}>
                      <div className="text-[20px] sm:text-[26px] tracking-[-0.03em] text-[#0A2540]" style={{ fontWeight: 650 }}>{stat.value}</div>
                      <div className="text-[11px] sm:text-[13px] text-[#8898AA] mt-1" style={{ fontWeight: 470 }}>{stat.label}</div>
                    </div>
                  ))}
                </motion.div>
              </div>
            </motion.div>

            {/* Right Column */}
            <motion.div
              initial={{ opacity: 0, y: 30, x: -5 }}
              animate={{ opacity: 1, y: 0, x: -5 }}
              transition={{ duration: 0.8, delay: 0.3 }}
              className="relative order-last hidden lg:block"
            >
              <LandingPhoneMockup />
            </motion.div>
          </div>
        </div>
      </section>

      {/* Social proof strip */}
      <section className="py-8 sm:py-10 px-5 sm:px-6 lg:px-8 bg-white border-y border-[#f0f0f5]">
        <div className="max-w-[1200px] mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="flex flex-wrap items-center justify-center gap-4 sm:gap-6 md:gap-12"
          >
            <span className="text-[13px] text-[#8898AA] uppercase tracking-[0.1em] w-full md:w-auto text-center" style={{ fontWeight: 500 }}>Built for</span>
            {['Restaurants', 'Retail', 'Healthcare', 'Hospitality', 'Warehouses'].map((industry) => (
              <span key={industry} className="text-[14px] sm:text-[15px] text-[#425466]/70" style={{ fontWeight: 450 }}>{industry}</span>
            ))}
          </motion.div>
        </div>
      </section>

      {/* The Problem Section */}
      <section className="relative bg-[#0A2540] text-white py-20 sm:py-32 px-5 sm:px-6 lg:px-8 overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.03]"
          style={{
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)',
            backgroundSize: '32px 32px',
          }}
        />
        <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-gradient-to-bl from-[#635BFF]/15 via-transparent to-transparent rounded-full blur-[120px]" />
        <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-gradient-to-tr from-[#00C7B7]/8 via-transparent to-transparent rounded-full blur-[100px]" />

        <div className="max-w-[900px] mx-auto relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <div className="text-[12px] tracking-[0.2em] text-[#635BFF] uppercase mb-5" style={{ fontWeight: 600 }}>
              The problem
            </div>
            <h2 className="text-[30px] sm:text-[44px] lg:text-[52px] leading-[1.1] tracking-[-0.03em] mb-6" style={{ fontWeight: 600 }}>
              It's 5:47 AM. Your opener just called out.
            </h2>
            <p className="text-[16px] sm:text-[19px] text-[#8898AA] mb-14 sm:mb-20 leading-[1.65]">
              Here's what that morning looks like without Backfill.
            </p>
          </motion.div>

          {/* Timeline */}
          <div className="space-y-0 relative">
            <div className="absolute left-[14px] sm:left-[108px] top-0 bottom-0 w-px bg-gradient-to-b from-[#635BFF]/30 via-white/[0.06] to-[#635BFF]/30" />
            {[
              { time: '5:47 AM', text: "Voicemail. Your opener isn't coming in. Service starts in two hours." },
              { time: '5:49 AM', text: 'You open the group chat. You start texting names. Most are asleep.' },
              { time: '5:58 AM', text: "Three replies. Two can't do it. One wants to negotiate hours." },
              { time: '6:15 AM', text: 'You call someone else. Rings out. You leave a voicemail and wait.' },
              { time: '6:34 AM', text: "Finally. Someone says yes. You've been at this for 47 minutes before your day even started." },
            ].map((item, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.08, duration: 0.5 }}
                viewport={{ once: true }}
                className="flex flex-col sm:flex-row gap-1 sm:gap-8 items-start group py-4 sm:py-5 pl-8 sm:pl-0"
              >
                <div className="text-[#8898AA] font-mono text-[13px] sm:text-[14px] sm:min-w-[88px] pt-0.5 group-hover:text-white/60 transition-colors" style={{ fontWeight: 450 }}>
                  {item.time}
                </div>
                <div className="relative">
                  <div className="absolute -left-[22px] sm:-left-[34px] top-[7px] w-2 h-2 rounded-full bg-[#1A3A5C] group-hover:bg-[#635BFF] transition-all border-2 border-[#0A2540] ring-[3px] ring-[#1A3A5C]/50 group-hover:ring-[#635BFF]/20" />
                  <div className="text-white/75 text-[15px] sm:text-[17px] leading-[1.65] group-hover:text-white/95 transition-colors">
                    {item.text}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Callout Box */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.3 }}
            className="mt-12 sm:mt-16 p-6 sm:p-8 backfill-ui-radius border border-white/[0.06] bg-white/[0.02]"
          >
            <p className="text-[15px] sm:text-[17px] text-[#8898AA] italic leading-[1.8]">
              "For a 30-location group, this is happening multiple times a week — across every location, every manager, every shift window. That's not a staffing problem. That's a systems problem."
            </p>
          </motion.div>
        </div>
      </section>

      {/* How It Works Section */}
      <section id="product" className="py-20 sm:py-32 px-5 sm:px-6 lg:px-8 bg-white relative overflow-hidden">
        <DotGrid className="opacity-30" />
        <div className="max-w-[1200px] mx-auto relative">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="max-w-2xl mb-14 sm:mb-20"
          >
            <div className="text-[12px] tracking-[0.2em] text-[#635BFF] uppercase mb-5" style={{ fontWeight: 600 }}>
              How it works
            </div>
            <h2 className="text-[30px] sm:text-[44px] lg:text-[52px] leading-[1.1] tracking-[-0.03em] mb-6 text-[#0A2540]" style={{ fontWeight: 600 }}>
              Three steps. Zero manual work.
            </h2>
            <p className="text-[16px] sm:text-[18px] text-[#425466] leading-[1.65]">
              No scrambling. No group chat. Our coverage engine takes over and notifies you when it&apos;s done.
            </p>
          </motion.div>

          <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-5">
            {[
              {
                step: '01',
                title: 'Callout Detected',
                subtitle: 'A shift opens',
                description: "When an employee calls out, a shift goes unclaimed, or a schedule changes — Backfill knows instantly, via your scheduler integration or directly through its own built-in calling line.",
                badge: 'Automatic detection',
                icon: <Zap className="h-5 w-5" />,
                color: '#635BFF',
                gradient: 'from-[#635BFF]/10 to-[#635BFF]/[0.02]',
              },
              {
                step: '02',
                title: 'Backfill Calls',
                subtitle: 'Your list gets worked',
                description: "Backfill's AI agent calls available employees in priority order — by role, availability, and standing. It explains the shift, fields questions, and waits for a clear yes.",
                badge: 'Voice AI · Calls in seconds',
                icon: <Phone className="h-5 w-5" />,
                color: '#0070F3',
                gradient: 'from-[#0070F3]/10 to-[#0070F3]/[0.02]',
              },
              {
                step: '03',
                title: 'Shift Filled',
                subtitle: 'First yes wins',
                description: "The moment someone confirms, the shift is locked. They get a confirmation. You get a notification. Everyone else automatically gets a clear — no awkward follow-up needed.",
                badge: 'Confirmed · Standby queue active',
                icon: <Check className="h-5 w-5" />,
                color: '#00C7B7',
                gradient: 'from-[#00C7B7]/10 to-[#00C7B7]/[0.02]',
              },
            ].map((item, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1, duration: 0.6 }}
                viewport={{ once: true }}
                className={`group relative bg-gradient-to-b ${item.gradient} p-8 backfill-ui-radius border border-[#e2e8f0] hover:border-[#c4d1e0] transition-all hover:shadow-[0_12px_40px_rgba(0,0,0,0.06)] hover:translate-y-[-2px] duration-300`}
              >
                {/* Step number watermark */}
                <div className="absolute top-6 right-6 text-[72px] leading-none tracking-[-0.04em] text-[#0A2540]/[0.04]" style={{ fontWeight: 700 }}>
                  {item.step}
                </div>

                <div className="flex items-center gap-3 mb-8">
                  <div
                    className="h-10 w-10 backfill-ui-radius flex items-center justify-center text-white"
                    style={{ backgroundColor: item.color }}
                  >
                    {item.icon}
                  </div>
                </div>
                <h3 className="text-[22px] tracking-[-0.02em] mb-1.5 text-[#0A2540]" style={{ fontWeight: 600 }}>{item.title}</h3>
                <div className="text-[14px] text-[#8898AA] mb-4" style={{ fontWeight: 450 }}>{item.subtitle}</div>
                <p className="text-[15px] text-[#425466] leading-[1.7] mb-6">{item.description}</p>
                <div className="inline-block px-3 py-1.5 bg-white/80 border border-[#e2e8f0] backfill-ui-radius text-[12px] text-[#425466]" style={{ fontWeight: 500 }}>
                  {item.badge}
                </div>
              </motion.div>
            ))}
          </div>

          {/* Section quote */}
          <motion.blockquote
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="mt-16 border-l-4 border-[#635BFF] pl-7 py-1 max-w-2xl"
          >
            <p className="text-[18px] sm:text-[20px] text-[#0A2540] leading-[1.65] italic mb-4" style={{ fontWeight: 450 }}>
              &ldquo;I used to spend the first hour of every morning chasing coverage. Now I check the app and it&apos;s already done.&rdquo;
            </p>
            <cite className="not-italic text-[13px] text-[#8898AA] tracking-[0.01em]" style={{ fontWeight: 500 }}>
              — Operations Manager, 3-location casual dining group, Los Angeles
            </cite>
          </motion.blockquote>
        </div>
      </section>

      {/* Backfill Shifts Section */}
      <section id="backfill-shifts" className="relative bg-[#0A2540] text-white py-20 sm:py-32 px-5 sm:px-6 lg:px-8 overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.025]"
          style={{
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)',
            backgroundSize: '32px 32px',
          }}
        />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[500px] bg-gradient-to-b from-[#635BFF]/12 via-transparent to-transparent rounded-full blur-[120px]" />

        <div className="max-w-[1200px] mx-auto relative z-10">
          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="mb-16"
          >
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 bg-[#635BFF]/15 border border-[#635BFF]/25 text-[#a5a0ff] backfill-ui-radius text-[12px] tracking-[0.08em] uppercase mb-8" style={{ fontWeight: 600 }}>
              <span className="w-1.5 h-1.5 rounded-full bg-[#635BFF]" />
              Backfill Shifts
            </div>
            <h2 className="text-[30px] sm:text-[44px] lg:text-[52px] leading-[1.08] tracking-[-0.03em] mb-6 max-w-3xl" style={{ fontWeight: 600 }}>
              Don't have scheduling software? Ours thinks for you.
            </h2>
            <div className="text-[16px] sm:text-[18px] text-[#8898AA] leading-[1.8] max-w-2xl space-y-5">
              <p>
                Backfill Shifts isn&apos;t asking you to change how you run your restaurant. It&apos;s asking you to stop doing one thing: the schedule in your head. Tell the AI what your week looks like. It drafts it, you approve it, and the coverage engine takes over from there.
              </p>
              <ul className="text-[#b0b8c8] space-y-2 list-none pl-0">
                <li>&ldquo;Add a closing shift Friday, same crew as last week.&rdquo; Done.</li>
                <li>&ldquo;Daniela can&apos;t do Tuesday — move her to Thursday.&rdquo; Done.</li>
              </ul>
              <p>
                You&apos;re not learning software. You&apos;re having a conversation.
              </p>
            </div>
          </motion.div>

          {/* Product Screenshot */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="mb-16"
          >
            <LandingBackfillShiftsInterface />
          </motion.div>

          {/* Features Grid */}
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                title: 'AI schedule generation',
                description: "Describe your week, your roles, your team. Backfill Shifts drafts the schedule. You approve, adjust, or just say what's wrong.",
              },
              {
                title: 'Natural language edits',
                description: "No forms, no dropdowns. Type or say the change, and the schedule updates. It's as fast as sending a text.",
              },
              {
                title: 'Pattern learning',
                description: 'The more you use it, the better it knows your operation. Recurring roles, preferred staff, shift windows — it stops asking what you always do.',
              },
              {
                title: 'Real-time coverage board',
                description: 'Every open shift, every in-progress fill attempt, every confirmation — across all locations — at a glance.',
              },
              {
                title: 'Standby queue management',
                description: 'Primary fill falls through? Your pre-ranked standby queue activates automatically. No second round of calls from you.',
              },
              {
                title: 'Upgrade anytime',
                description: 'Grow into a dedicated platform later? Everything ports over. No rebuilding from scratch.',
              },
            ].map((feature, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.06, duration: 0.5 }}
                viewport={{ once: true }}
                className="group p-6 backfill-ui-radius border border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04] hover:border-[#635BFF]/30 transition-all duration-300"
              >
                <h3 className="text-[17px] tracking-[-0.01em] mb-2 text-white/90 group-hover:text-white transition-colors" style={{ fontWeight: 550 }}>{feature.title}</h3>
                <p className="text-[14px] text-[#8898AA]/80 leading-[1.65] group-hover:text-[#8898AA] transition-colors">{feature.description}</p>
              </motion.div>
            ))}
          </div>

          {/* Bottom note */}
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.5 }}
            className="mt-12 text-center"
          >
            <p className="text-white/30 text-[14px]">
              Included for all Backfill customers. No additional cost.
            </p>
          </motion.div>
        </div>
      </section>

      {/* Integrations Section */}
      <section id="integrations" className="py-20 sm:py-28 px-5 sm:px-6 lg:px-8 bg-[#fafbfd] relative overflow-hidden">
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#e2e8f0] to-transparent" />
        <div className="max-w-[900px] mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <div className="text-[12px] tracking-[0.2em] text-[#635BFF] uppercase mb-5" style={{ fontWeight: 600 }}>
              Integrations
            </div>
            <h2 className="text-[30px] sm:text-[44px] lg:text-[52px] leading-[1.1] tracking-[-0.03em] mb-6 text-[#0A2540]" style={{ fontWeight: 600 }}>
              Plug in. Go live in 24 hours.
            </h2>
            <p className="text-[16px] sm:text-[18px] text-[#425466] mb-10 sm:mb-14 leading-[1.65]">
              Already using scheduling software? Backfill connects directly so your shifts, roles, and employee data are always in sync.
            </p>

            <div className="grid grid-cols-2 sm:flex sm:flex-wrap justify-center gap-3 mb-10 sm:mb-14">
              {['7shifts', 'Deputy', 'When I Work', 'Homebase'].map((integration) => (
                <motion.div
                  key={integration}
                  whileHover={{ scale: 1.02, y: -1 }}
                  className="px-6 py-4 bg-white border border-[#e2e8f0] backfill-ui-radius text-[16px] text-[#0A2540] shadow-[0_1px_3px_rgba(0,0,0,0.04)] hover:shadow-[0_8px_25px_rgba(0,0,0,0.07)] transition-all duration-300"
                  style={{ fontWeight: 500 }}
                >
                  {integration}
                </motion.div>
              ))}
            </div>

            <p className="text-[15px] text-[#8898AA] max-w-lg mx-auto leading-[1.7]">
              No manual data entry. No duplicate setup. Your employees, roles, and availability sync automatically.
            </p>
          </motion.div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="relative bg-gradient-to-b from-[#060F1F] via-[#0B1A33] to-[#060F1F] text-white py-20 sm:py-32 px-5 sm:px-6 lg:px-8 overflow-hidden">
        {/* Unique mesh gradient overlay for pricing */}
        <div className="absolute inset-0 pointer-events-none" style={{
          background: 'radial-gradient(ellipse 80% 60% at 50% 0%, rgba(99,91,255,0.18) 0%, transparent 60%), radial-gradient(ellipse 60% 50% at 80% 100%, rgba(0,199,183,0.1) 0%, transparent 50%), radial-gradient(ellipse 40% 40% at 20% 50%, rgba(99,91,255,0.08) 0%, transparent 50%)',
        }} />
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.04]"
          style={{
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />
        {/* Animated border glow at top */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#635BFF]/40 to-transparent" />
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#635BFF]/20 to-transparent" />
        <div className="max-w-[900px] mx-auto relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <div className="text-[12px] tracking-[0.2em] text-[#635BFF] uppercase mb-5" style={{ fontWeight: 600 }}>
              Pricing
            </div>
            <h2 className="text-[30px] sm:text-[44px] lg:text-[52px] leading-[1.1] tracking-[-0.03em] mb-6" style={{ fontWeight: 600 }}>
              You pay when we deliver.
            </h2>
            <p className="text-[16px] sm:text-[18px] text-[#8898AA] leading-[1.65] max-w-lg mx-auto">
              No monthly seat fees. No per-user subscriptions. Backfill charges like labor — when the work gets done.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="bg-white/[0.04] p-7 sm:p-10 lg:p-12 rounded-3xl border border-white/[0.08] backdrop-blur-sm relative overflow-hidden"
          >
            {/* Subtle inner glow */}
            <div className="absolute inset-0 pointer-events-none bg-gradient-to-br from-[#635BFF]/[0.06] via-transparent to-[#00C7B7]/[0.04] rounded-3xl" />
            <div className="relative z-10">
            <div className="text-center mb-10">
              <div className="text-[56px] sm:text-[72px] tracking-[-0.04em] mb-1" style={{ fontWeight: 600 }}>$20</div>
              <div className="text-[16px] text-[#8898AA]" style={{ fontWeight: 450 }}>per successfully filled shift</div>
            </div>

            <div className="mt-10 text-center">
              <Link
                href="/try"
                className="group px-7 py-3.5 bg-[#635BFF] text-white backfill-ui-radius transition-all duration-300 text-[15px] inline-flex items-center gap-2 shadow-[0_4px_20px_rgba(99,91,255,0.4)] hover:shadow-[0_6px_30px_rgba(99,91,255,0.55)] hover:translate-y-[-1px]"
                style={{ fontWeight: 500 }}
              >
                Get Started Free
                <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </div>
            </div>
          </motion.div>

          {/* Pricing quote */}
          <motion.blockquote
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="mt-10 border-l-4 border-[#635BFF]/60 pl-7 py-1 max-w-2xl mx-auto"
          >
            <p className="text-[17px] sm:text-[19px] text-white/80 leading-[1.65] italic mb-4" style={{ fontWeight: 400 }}>
              &ldquo;The first month I used Backfill I filled 11 shifts I would have had to handle manually. At 45 minutes each, that&apos;s over 8 hours back. The math wasn&apos;t hard.&rdquo;
            </p>
            <cite className="not-italic text-[13px] text-[#8898AA] tracking-[0.01em]" style={{ fontWeight: 500 }}>
              — GM, fast casual restaurants, 4 locations
            </cite>
          </motion.blockquote>
        </div>
      </section>

      {/* FAQ Section */}
      <section id="faq" className="py-20 sm:py-32 px-5 sm:px-6 lg:px-8 bg-[#fafbfd] relative">
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#e2e8f0] to-transparent" />
        <div className="max-w-[900px] mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="mb-16"
          >
            <div className="text-[12px] tracking-[0.2em] text-[#635BFF] uppercase mb-5" style={{ fontWeight: 600 }}>
              FAQ
            </div>
            <h2 className="text-[30px] sm:text-[44px] lg:text-[52px] leading-[1.1] tracking-[-0.03em] mb-5 text-[#0A2540]" style={{ fontWeight: 600 }}>
              Questions operators actually ask.
            </h2>
            <p className="text-[16px] sm:text-[18px] text-[#425466]">
              Straight answers. No runaround.
            </p>
          </motion.div>

          <LandingFaq />
        </div>
      </section>

      {/* Final CTA */}
      <section className="relative bg-[#0A2540] text-white py-24 sm:py-36 px-5 sm:px-6 lg:px-8 overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.02]"
          style={{
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.8) 1px, transparent 1px)',
            backgroundSize: '32px 32px',
          }}
        />
        <div className="absolute inset-0">
          <div className="absolute top-[-200px] left-1/2 -translate-x-1/2 w-[1000px] h-[500px] bg-gradient-to-b from-[#635BFF]/20 via-[#0070F3]/10 to-transparent rounded-full blur-[120px]" />
        </div>

        <div className="max-w-[700px] mx-auto text-center relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2 className="text-[30px] sm:text-[44px] lg:text-[56px] leading-[1.08] tracking-[-0.03em] mb-6" style={{ fontWeight: 600 }}>
              Ready to stop making those 6 AM calls?
            </h2>
            <p className="text-[16px] sm:text-[18px] text-[#8898AA] mb-10 leading-[1.65]">
              Join the operators who let Backfill handle the scramble.
            </p>
            <Link
              href="/try"
              className="group px-8 py-4 bg-white text-[#0A2540] backfill-ui-radius hover:bg-white/95 transition-all text-[16px] inline-flex items-center gap-2.5 shadow-[0_4px_20px_rgba(255,255,255,0.15)] hover:shadow-[0_6px_30px_rgba(255,255,255,0.2)] hover:translate-y-[-1px]"
              style={{ fontWeight: 550 }}
            >
              Start filling callouts autonomously
              <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-white py-12 sm:py-16 px-5 sm:px-6 lg:px-8 border-t border-[#f0f0f5]">
        <div className="max-w-[1200px] mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-10 mb-14">
            <div className="col-span-2 md:col-span-1">
              <div className="text-[20px] tracking-[-0.02em] text-[#0A2540] mb-3" style={{ fontWeight: 620 }}>Backfill</div>
              <p className="text-[14px] text-[#8898AA] leading-[1.65] max-w-[200px]">
                AI-powered shift coverage for teams that can't afford service interruptions.
              </p>
            </div>
            <div>
              <div className="text-[13px] text-[#8898AA] uppercase tracking-[0.1em] mb-4" style={{ fontWeight: 550 }}>Product</div>
              <div className="space-y-3">
                {[
                  { label: 'How It Works', href: '#product' },
                  { label: 'Backfill Shifts', href: '#backfill-shifts' },
                  { label: 'Integrations', href: '#integrations' },
                  { label: 'Pricing', href: '#pricing' },
                ].map((link) => (
                  <div key={link.label}>
                    <a 
                      href={link.href} 
                      className="text-[14px] text-[#425466] hover:text-[#0A2540] transition-colors" 
                      style={{ fontWeight: 420 }}
                      onClick={(e) => {
                        e.preventDefault();
                        const element = document.querySelector(link.href);
                        if (element) {
                          element.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                      }}
                    >
                      {link.label}
                    </a>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[13px] text-[#8898AA] uppercase tracking-[0.1em] mb-4" style={{ fontWeight: 550 }}>Company</div>
              <div className="space-y-3">
                {['About', 'Blog', 'Careers', 'Contact'].map((link) => (
                  <div key={link}>
                    <a href="#" className="text-[14px] text-[#425466] hover:text-[#0A2540] transition-colors" style={{ fontWeight: 420 }}>{link}</a>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[13px] text-[#8898AA] uppercase tracking-[0.1em] mb-4" style={{ fontWeight: 550 }}>Legal</div>
              <div className="space-y-3">
                {['Privacy', 'Terms', 'Security'].map((link) => (
                  <div key={link}>
                    <a href="#" className="text-[14px] text-[#425466] hover:text-[#0A2540] transition-colors" style={{ fontWeight: 420 }}>{link}</a>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="pt-8 border-t border-[#f0f0f5] flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="text-[13px] text-[#8898AA]" style={{ fontWeight: 400 }}>
              © <span suppressHydrationWarning>{currentYear}</span> Backfill Works, Inc. All rights reserved.
            </div>
            <div className="flex items-center gap-6">
              {['Twitter', 'LinkedIn'].map((social) => (
                <a key={social} href="#" className="text-[13px] text-[#8898AA] hover:text-[#425466] transition-colors" style={{ fontWeight: 420 }}>{social}</a>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
