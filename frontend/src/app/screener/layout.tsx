import type { Metadata } from "next";
import { buildOgImageUrl } from "@/lib/og";

export const metadata: Metadata = {
  title: "Stock Screener",
  description: "40+ large-cap stocks with momentum signals (strong buy → strong sell), market breadth %, and AI regime read — updated hourly.",
  openGraph: {
    title: "Stock Screener | Nuwrrrld Financial",
    description: "40+ large-cap stocks · Momentum signals · Market breadth % · AI regime read.",
    images: [
      {
        url: buildOgImageUrl("Stock Screener", "40+ large-caps · Strong buy → strong sell · AI regime read"),
        width: 1200,
        height: 630,
        alt: "Stock Screener — Nuwrrrld Financial",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Stock Screener | Nuwrrrld Financial",
    description: "40+ large-cap stocks · Momentum signals · Market breadth % · AI regime read.",
    images: [buildOgImageUrl("Stock Screener", "40+ large-caps · Strong buy → strong sell · AI regime read")],
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
