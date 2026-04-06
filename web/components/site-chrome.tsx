"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

type SiteChromeProps = {
  children: React.ReactNode;
};

export function SiteChrome({ children }: SiteChromeProps) {
  const pathname = usePathname();
  const currentYear = new Date().getFullYear();
  const isLiveAppSurface =
    pathname === "/dashboard" ||
    pathname === "/team" ||
    pathname === "/settings" ||
    pathname.startsWith("/settings/");
  const isReferenceAppSurface =
    pathname.startsWith("/dashboard/") ||
    pathname === "/dashboard-light" ||
    pathname === "/dashboard-dark" ||
    pathname === "/dashboard-single" ||
    pathname === "/dashboard-two";

  if (pathname === "/") {
    return <>{children}</>;
  }

  if (isLiveAppSurface || isReferenceAppSurface) {
    return <>{children}</>;
  }

  return (
    <>
      <header className="topbar-wrap px-5 sm:px-6 lg:px-8">
        <div className="topbar mx-auto flex h-[64px] max-w-[1200px] items-center justify-between gap-6 sm:h-[72px]">
          <Link
            className="text-[20px] tracking-[-0.02em] text-[#0A2540]"
            href="/"
            style={{ fontWeight: 620 }}
          >
            Backfill
          </Link>
          <nav className="nav hidden items-center gap-8 md:flex">
            <Link href="/#product">Product</Link>
            <Link href="/#pricing">Pricing</Link>
            <Link href="/#faq">FAQ</Link>
          </nav>
          <Link
            href="/login"
            className="text-[15px] text-[#425466] transition-colors hover:text-[#0A2540]"
            style={{ fontWeight: 450 }}
          >
            Sign In
          </Link>
        </div>
      </header>
      <div className="site-main">
        <div className="shell">{children}</div>
      </div>
      <footer className="footer bg-white px-5 py-12 sm:px-6 sm:py-16 lg:px-8">
        <div className="mx-auto max-w-[1200px]">
          <div className="mb-10 grid gap-10 border-t border-[#f0f0f5] pt-10 md:grid-cols-[1.4fr_repeat(2,minmax(0,1fr))]">
            <div>
              <div className="mb-3 text-[20px] tracking-[-0.02em] text-[#0A2540]" style={{ fontWeight: 620 }}>
                Backfill
              </div>
              <p className="max-w-[240px] text-[14px] leading-[1.65] text-[#8898AA]">
                AI-powered shift coverage for teams that cannot afford service interruptions.
              </p>
            </div>
            <div>
              <div className="mb-4 text-[13px] uppercase tracking-[0.1em] text-[#8898AA]" style={{ fontWeight: 550 }}>
                Product
              </div>
              <div className="space-y-3">
                <Link className="block text-[14px] text-[#425466] transition-colors hover:text-[#0A2540]" href="/#product" style={{ fontWeight: 420 }}>
                  How It Works
                </Link>
                <Link className="block text-[14px] text-[#425466] transition-colors hover:text-[#0A2540]" href="/#pricing" style={{ fontWeight: 420 }}>
                  Pricing
                </Link>
                <Link className="block text-[14px] text-[#425466] transition-colors hover:text-[#0A2540]" href="/try" style={{ fontWeight: 420 }}>
                  Try Backfill
                </Link>
              </div>
            </div>
            <div>
              <div className="mb-4 text-[13px] uppercase tracking-[0.1em] text-[#8898AA]" style={{ fontWeight: 550 }}>
                Company
              </div>
              <div className="space-y-3">
                <Link className="block text-[14px] text-[#425466] transition-colors hover:text-[#0A2540]" href="/login" style={{ fontWeight: 420 }}>
                  Sign In
                </Link>
                <a className="block text-[14px] text-[#425466] transition-colors hover:text-[#0A2540]" href="tel:18002225345" style={{ fontWeight: 420 }}>
                  1-800-BACKFILL
                </a>
                <Link className="block text-[14px] text-[#425466] transition-colors hover:text-[#0A2540]" href="/#faq" style={{ fontWeight: 420 }}>
                  FAQ
                </Link>
              </div>
            </div>
          </div>
          <div className="flex flex-col items-start justify-between gap-4 border-t border-[#f0f0f5] pt-8 text-[13px] text-[#8898AA] md:flex-row md:items-center">
            <div style={{ fontWeight: 400 }}>
              © <span suppressHydrationWarning>{currentYear}</span> Backfill Works, Inc. All rights reserved.
            </div>
            <div className="flex items-center gap-6">
              <a className="transition-colors hover:text-[#425466]" href="tel:18002225345" style={{ fontWeight: 420 }}>
                Call now
              </a>
              <Link className="transition-colors hover:text-[#425466]" href="/try" style={{ fontWeight: 420 }}>
                Try Backfill
              </Link>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
}
