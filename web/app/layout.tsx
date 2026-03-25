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
      <body>
        <div className="shell">
          <header className="topbar">
            <Link className="brand" href="/">
              <span className="brand-mark">B</span>
              <span>Backfill</span>
            </Link>
            <nav className="nav">
              <Link href="/">Home</Link>
              <Link href="/setup/connect">Setup</Link>
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/join">Join</Link>
              <Link href="/partners">Partners</Link>
            </nav>
          </header>
          {children}
          <footer className="footer">
            <div>1-800-BACKFILL is the command surface. The website handles structured setup, uploads, and visibility.</div>
          </footer>
        </div>
      </body>
    </html>
  );
}
