import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://nuwrrrld.com";

const siteDescription =
  "Nuwrrrld Financial — 15 free real-time market intelligence tools: AI summary, morning brief, stock screener, sector rotation, earnings radar, macro pulse, news sentiment, portfolio analyzer, and more.";

export const metadata: Metadata = {
  title: "Nuwrrrld Financial — Helping Everyone Make Better Financial Choices",
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
  metadataBase: new URL(siteUrl),
  openGraph: {
    type: "website",
    url: siteUrl,
    title: "Nuwrrrld Financial — Helping Everyone Make Better Financial Choices",
    description: siteDescription,
    images: [
      {
        url: "/og-image.png",
        width: 1024,
        height: 541,
        alt: "Nuwrrrld Financial — Helping everyone make better financial choices",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Nuwrrrld Financial — Helping Everyone Make Better Financial Choices",
    description: siteDescription,
    images: ["/og-image.png"],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        <NavBar />
        <main className="max-w-5xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
