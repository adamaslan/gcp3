import type { Metadata } from "next";
import { buildOgImageUrl } from "@/lib/og";

export const metadata: Metadata = {
  title: "Industry Returns",
  description: "Multi-period ETF returns (1W → 10Y) for 50 industries — leaders, laggards, and 52-week range data.",
  openGraph: {
    title: "Industry Returns | Nuwrrrld Financial",
    description: "Multi-period ETF returns (1W → 10Y) for 50 industries · Leaders · Laggards · 52-week range.",
    images: [
      {
        url: buildOgImageUrl("Industry Returns", "1W → 10Y ETF returns · 50 industries · Leaders & laggards"),
        width: 1200,
        height: 630,
        alt: "Industry Returns — Nuwrrrld Financial",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Industry Returns | Nuwrrrld Financial",
    description: "Multi-period ETF returns (1W → 10Y) for 50 industries · Leaders · Laggards · 52-week range.",
    images: [buildOgImageUrl("Industry Returns", "1W → 10Y ETF returns · 50 industries · Leaders & laggards")],
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
