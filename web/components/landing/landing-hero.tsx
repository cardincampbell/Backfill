"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { motion, useScroll, useTransform } from "motion/react";

const LandingPhoneMockup = dynamic(
  () =>
    import("./landing-phone-mockup").then((module) => ({
      default: module.LandingPhoneMockup,
    })),
  {
    loading: () => (
      <div className="mx-auto w-full max-w-[280px] sm:max-w-[340px] lg:max-w-[380px]">
        <div className="aspect-[393/852] rounded-[46px] border border-[#d8dee6] bg-[linear-gradient(180deg,#f7f8fa_0%,#eef2f6_100%)] shadow-[0_20px_60px_rgba(0,0,0,0.12)]" />
      </div>
    ),
  },
);

const HERO_STATS = [
  { value: "< 4 min", label: "Avg. fill time" },
  { value: "93%", label: "Shifts covered" },
  { value: "1,200", label: "Businesses" },
  { value: "0", label: "Scrambling" },
];

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

export function LandingHero() {
  const { scrollY } = useScroll();
  const heroY = useTransform(scrollY, [0, 1100], [0, 44]);
  const heroOpacity = useTransform(scrollY, [0, 260, 980], [1, 0.95, 0.42]);

  return (
    <section className="relative overflow-hidden px-5 pb-20 pt-28 sm:px-6 sm:pb-32 sm:pt-36 lg:px-8">
      <div className="absolute inset-0 bg-[#fafbfd]" />
      <div className="absolute right-[-300px] top-[-400px] h-[1000px] w-[1000px] rounded-full bg-gradient-to-bl from-[#635BFF]/[0.13] via-[#80b3ff]/[0.11] to-transparent blur-[100px]" />
      <div className="absolute bottom-[-200px] left-[-200px] h-[700px] w-[700px] rounded-full bg-gradient-to-tr from-[#635BFF]/[0.10] via-transparent to-transparent blur-[80px]" />
      <DotGrid className="opacity-50" />
      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-white to-transparent" />

      <div className="relative mx-auto max-w-[1200px]">
        <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
          <motion.div
            style={{ y: heroY, opacity: heroOpacity }}
            className="mx-auto flex min-h-[calc(100svh-140px)] max-w-xl flex-col text-left lg:mx-0 lg:min-h-0 lg:-translate-y-[20px] lg:translate-x-[50px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            <div className="flex flex-1 flex-col justify-center">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6 }}
                className="mb-6 inline-flex w-fit items-center gap-2.5 self-start border border-[#e2e8f0] bg-white/80 px-4 py-1.5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] backdrop-blur-sm backfill-ui-radius sm:mb-8"
              >
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#635BFF]" />
                <span
                  className="text-[13px] text-[#425466]"
                  style={{ fontWeight: 500 }}
                >
                  Always on autonomous shift coverage
                </span>
              </motion.div>

              <motion.h1
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.1 }}
                className="mb-5 text-[64px] leading-[1.06] tracking-[-0.035em] sm:mb-7 sm:text-[48px] md:text-[56px] lg:text-[68px]"
                style={{ fontWeight: 780 }}
              >
                <span className="text-[#0A2540]">From Callout</span>{" "}
                <br className="hidden lg:block" />
                <span className="bg-gradient-to-r from-[#0A2540] via-[#635BFF] to-[#00C7B7] bg-clip-text text-transparent">
                  to Covered.
                </span>
              </motion.h1>

              <motion.p
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.2 }}
                className="mb-8 max-w-md text-[21px] leading-[1.75] text-[#425466] sm:mb-10 sm:text-[18px] lg:mx-0"
              >
                Callouts happen. Scrambling doesn&apos;t have to. Backfill
                handles callouts and last-minute shift changes automatically —
                so you never have to.
              </motion.p>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.3 }}
                className="mb-4 sm:mb-12"
              >
                <Link
                  href="/try"
                  className="group inline-flex w-full items-center justify-center gap-2.5 bg-[#0A2540] px-8 py-4 text-[17px] text-white shadow-[0_4px_14px_rgba(10,37,64,0.35)] transition-all duration-300 hover:-translate-y-[1px] hover:shadow-[0_6px_24px_rgba(10,37,64,0.45)] backfill-ui-radius sm:w-auto sm:px-7 sm:py-3.5 sm:text-[16px]"
                  style={{ fontWeight: 500 }}
                >
                  Try Backfill Free
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </Link>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.4 }}
                className="flex justify-start gap-6 border-t border-[#e2e8f0]/80 pb-4 pt-8 sm:gap-10 lg:pb-0"
              >
                {HERO_STATS.map((stat) => (
                  <div key={stat.label}>
                    <div
                      className="text-[20px] tracking-[-0.03em] text-[#0A2540] sm:text-[26px]"
                      style={{ fontWeight: 650 }}
                    >
                      {stat.value}
                    </div>
                    <div
                      className="mt-1 text-[11px] text-[#8898AA] sm:text-[13px]"
                      style={{ fontWeight: 470 }}
                    >
                      {stat.label}
                    </div>
                  </div>
                ))}
              </motion.div>
            </div>
          </motion.div>

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
  );
}
