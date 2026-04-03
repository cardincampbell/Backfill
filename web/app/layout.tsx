import type { Metadata } from "next";

import { SiteChrome } from "@/components/site-chrome";
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
        <SiteChrome>{children}</SiteChrome>
      </body>
    </html>
  );
}
