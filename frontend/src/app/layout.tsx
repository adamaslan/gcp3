import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "GCP3 Finance",
  description: "12 real-time market intelligence tools powered by GCP + Claude AI",
};

const NAV_LINKS = [
  { href: "/ai-summary", label: "AI Summary" },
  { href: "/morning-brief", label: "Morning Brief" },
  { href: "/industry-tracker", label: "Industries" },
  { href: "/screener", label: "Screener" },
  { href: "/sector-rotation", label: "Sectors" },
  { href: "/earnings-radar", label: "Earnings" },
  { href: "/macro-pulse", label: "Macro" },
  { href: "/news-sentiment", label: "News" },
  { href: "/portfolio-analyzer", label: "Portfolio" },
  { href: "/technical-signals", label: "Signals" },
  { href: "/industry-returns", label: "Returns" },
  { href: "/market-summary", label: "Mkt Summary" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        <nav className="border-b border-gray-800 px-6 py-2 flex items-center gap-1 overflow-x-auto">
          <Link href="/" className="font-bold text-white mr-4 shrink-0 text-sm">GCP3</Link>
          {NAV_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="px-3 py-1.5 text-gray-400 hover:text-white text-sm transition-colors rounded-md hover:bg-gray-800 shrink-0 whitespace-nowrap"
            >
              {label}
            </Link>
          ))}
        </nav>
        <main className="max-w-5xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
