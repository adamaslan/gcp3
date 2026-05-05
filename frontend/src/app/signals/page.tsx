import type { Metadata } from "next";
import { TechnicalSignals } from "@/components/TechnicalSignals";
import { Disclaimer } from "@/components/Disclaimer";
import { buildOgImageUrl } from "@/lib/og";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Technical Signals",
  description: "BUY/HOLD/SELL signals from the MCP analysis pipeline, ranked by confidence with bull/bear counts across 40+ large-cap stocks.",
  openGraph: {
    title: "Technical Signals | Nuwrrrld Financial",
    description: "BUY/HOLD/SELL signals ranked by confidence · Bull/bear counts · 40+ large-cap stocks.",
    images: [
      {
        url: buildOgImageUrl("Technical Signals", "BUY/HOLD/SELL signals · Ranked by confidence · Bull/bear counts"),
        width: 1200,
        height: 630,
        alt: "Technical Signals — Nuwrrrld Financial",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Technical Signals | Nuwrrrld Financial",
    description: "BUY/HOLD/SELL signals ranked by confidence · Bull/bear counts · 40+ large-cap stocks.",
    images: [buildOgImageUrl("Technical Signals", "BUY/HOLD/SELL signals · Ranked by confidence · Bull/bear counts")],
  },
};

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) return null;
  try {
    const res = await fetch(`${base}/signals`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function SignalsPage() {
  const data = await getData();
  if (!data) {
    return (
      <div className="p-8 text-gray-400 animate-pulse">
        <div className="h-8 w-48 bg-gray-800 rounded mb-6" />
        <div className="h-64 bg-gray-800 rounded mb-4" />
        <div className="h-64 bg-gray-800 rounded" />
      </div>
    );
  }
  return (
    <div>
      <TechnicalSignals data={data} />
      <Disclaimer />
    </div>
  );
}
