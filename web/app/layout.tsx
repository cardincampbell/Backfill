import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Backfill",
  description: "Autonomous coverage infrastructure for hourly labor."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="site-body">
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
                <small>Shift operations</small>
              </span>
            </Link>
            <nav className="nav">
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/try">Setup</Link>
              <Link href="/login">Sign in</Link>
            </nav>
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
      </body>
    </html>
  );
}
