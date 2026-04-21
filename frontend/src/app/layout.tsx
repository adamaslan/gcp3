import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";

import { ClerkProvider } from "@clerk/nextjs";

import { buildOgImageUrl } from "@/lib/og";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://nuwrrrld.com";


const siteDescription =
  "Nuwrrrld Financial — 15 free real-time market intelligence tools: AI summary, morning brief, stock screener, sector rotation, earnings radar, macro pulse, news sentiment, portfolio analyzer, and more.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Nuwrrrld Financial — Helping Everyone Make Better Financial Choices",
    template: "%s | Nuwrrrld Financial",
  },
  description: siteDescription,
  keywords: [
    "stock market tools",
    "real-time market data",
    "AI market summary",
    "stock screener",
    "sector rotation",
    "earnings radar",
    "macro pulse",
    "news sentiment",
    "portfolio analyzer",
    "technical signals",
    "industry tracker",
    "morning brief",
    "SPY QQQ IWM DIA",
    "VIX macro indicators",
    "financial choices",
    "Nuwrrrld Financial",
  ],
  openGraph: {
    type: "website",
    url: siteUrl,
    siteName: "Nuwrrrld Financial",
    title: "Nuwrrrld Financial — Helping Everyone Make Better Financial Choices",
    description: siteDescription,
    images: [
      {
        url: buildOgImageUrl(
          "Nuwrrrld Financial",
          "Helping everyone make better financial choices"
        ),
        width: 1200,
        height: 630,
        alt: "Nuwrrrld Financial — Helping everyone make better financial choices",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    site: "@nuwrrrld",
    title: "Nuwrrrld Financial — Helping Everyone Make Better Financial Choices",
    description: siteDescription,
    images: [
      buildOgImageUrl(
        "Nuwrrrld Financial",
        "Helping everyone make better financial choices"
      ),
    ],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className="bg-gray-950 text-gray-100 min-h-screen">
          <NavBar />
          <main className="max-w-5xl mx-auto px-4 py-5 sm:px-6 sm:py-8">{children}</main>
        </body>
      </html>
    </ClerkProvider>
  );
}
