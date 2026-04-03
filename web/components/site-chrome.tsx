"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type SiteChromeProps = {
  children: React.ReactNode;
};

export function SiteChrome({ children }: SiteChromeProps) {
  const pathname = usePathname();

  if (pathname === "/") {
    return <>{children}</>;
  }

  return (
    <>
      <div className="site-ambient" aria-hidden="true">
        <div className="ambient-orb ambient-orb-one" />
        <div className="ambient-orb ambient-orb-two" />
        <div className="ambient-grid" />
      </div>
      <header className="topbar-wrap">
        <div className="shell topbar">
          <Link className="brand" href="/">
            <span className="brand-mark">B</span>
            <span className="brand-wordmark">
              <strong>Backfill</strong>
              <small>Callout to covered</small>
            </span>
          </Link>
          <nav className="nav">
            <Link href="/">Home</Link>
            <Link href="/dashboard">Dashboard</Link>
            <Link href="/try">Setup</Link>
          </nav>
          <div className="site-header-actions">
            <Link href="/login" className="site-header-link">
              Sign in
            </Link>
            <Link href="/try" className="site-header-button">
              Try Backfill
            </Link>
          </div>
        </div>
      </header>
      <div className="site-main">
        <div className="shell">{children}</div>
      </div>
      <footer className="shell footer">
        <div className="footer-kicker">Backfill shifts</div>
        <div className="footer-copy">
          Premium schedule, coverage, and exception handling for high-expectation hourly operators.
        </div>
        <div className="footer-meta">
          <span>1-800-BACKFILL</span>
          <span>AI schedules the week. Managers approve by text.</span>
        </div>
      </footer>
    </>
  );
}
