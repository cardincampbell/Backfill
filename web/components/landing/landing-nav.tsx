import Link from "next/link";

import { AUTH_ENTRY_PATH } from "@/lib/auth/constants";

const NAV_ITEMS = [
  { label: "Product", href: "#product" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
];

export function LandingNav() {
  return (
    <nav className="fixed left-0 right-0 top-0 z-50 border-b border-neutral-200/60 bg-white/80 px-5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] backdrop-blur-2xl sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1200px]">
        <div className="flex h-[64px] items-center justify-between sm:h-[72px]">
          <Link
            href="/"
            className="text-[20px] tracking-[-0.02em] text-[#0A2540] transition-transform duration-200 hover:scale-[1.02] sm:text-[22px]"
            style={{ fontWeight: 620 }}
          >
            Backfill
          </Link>

          <div className="ml-12 mr-auto hidden items-center gap-8 md:flex">
            {NAV_ITEMS.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="text-[15px] text-[#425466] transition-colors hover:text-[#0A2540]"
                style={{ fontWeight: 450 }}
              >
                {item.label}
              </a>
            ))}
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
            <a
              href={AUTH_ENTRY_PATH}
              className="px-4 py-2 text-[15px] text-[#425466] transition-colors hover:text-[#0A2540]"
              style={{ fontWeight: 450 }}
            >
              Sign In
            </a>
          </div>
        </div>
      </div>
    </nav>
  );
}
