import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Backfill",
  description: "AI coordination layer for shift coverage."
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
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/join">Worker Join</Link>
              <Link href="/partners">Partners</Link>
            </nav>
          </header>
          {children}
          <footer className="footer">
            <div>1-800-BACKFILL is the front door. The website exists to support what phone and text cannot do cleanly.</div>
          </footer>
        </div>
      </body>
    </html>
  );
}
