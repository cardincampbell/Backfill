"use client";

import * as Accordion from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";

const faqs = [
  {
    question: "How does Backfill know who to call?",
    answer:
      "During setup, you define your team, their roles, and their availability. Backfill uses that data to build a prioritized call list — by role fit, availability, and standing. You control the order. We work it.",
  },
  {
    question: "What happens if nobody picks up or says yes?",
    answer:
      "Backfill keeps working the list. If the shift goes unfilled, you're notified immediately so you can step in — but you're never left in the dark mid-attempt. And you don't pay for unfilled shifts.",
  },
  {
    question: "Do my employees need to download an app?",
    answer:
      "No. Backfill reaches them the way they already communicate — by phone. No app installs, no new logins, no behavior change required from your team.",
  },
  {
    question: "What if I already use a scheduling platform?",
    answer:
      "Backfill integrates directly with 7shifts, Deputy, When I Work, and Homebase. Your existing schedule syncs automatically — no duplicate setup.",
  },
  {
    question: "What is Backfill Shifts, and do I have to use it?",
    answer:
      "Backfill Shifts is our built-in AI-native scheduling layer for businesses that don't have a scheduling platform. It's included with your Backfill account at no extra cost. If you already have a scheduler, you don't need it — but it's there if you do.",
  },
  {
    question: "How does billing work?",
    answer:
      "You pay $20 per successfully filled shift, plus a one-time location setup fee. If a shift goes unfilled, you're not charged. No monthly fees, no minimums, no surprises.",
  },
  {
    question: "How long does setup take?",
    answer: "Most customers are live within 24 hours of their first call with us. That's it.",
  },
];

export function LandingFaq() {
  return (
    <Accordion.Root type="single" collapsible className="space-y-2">
      {faqs.map((faq, index) => (
        <Accordion.Item
          key={faq.question}
          value={`item-${index}`}
          className="bg-white rounded-2xl border border-[#e2e8f0] overflow-hidden hover:border-[#c4d1e0] transition-all duration-300 hover:shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
        >
          <Accordion.Header>
            <Accordion.Trigger className="landing-faq-trigger group flex w-full items-center justify-between px-6 py-5 text-left">
              <span className="text-[16px] pr-6 tracking-[-0.01em] text-[#0A2540]" style={{ fontWeight: 530 }}>
                {faq.question}
              </span>
              <ChevronDown className="landing-faq-icon h-4 w-4 shrink-0 text-[#8898AA]" />
            </Accordion.Trigger>
          </Accordion.Header>
          <Accordion.Content className="landing-faq-content overflow-hidden">
            <div className="px-6 pb-5 text-[#425466] leading-[1.7] text-[15px]">{faq.answer}</div>
          </Accordion.Content>
        </Accordion.Item>
      ))}
    </Accordion.Root>
  );
}
