import type { Metadata } from "next";
import { Suspense } from "react";
import { IndustryTracker } from "@/components/IndustryTracker";
import { buildOgImageUrl } from "@/lib/og";

export const revalidate = 60;

export const metadata: Metadata = {
  title: "Industry Intel",
  description: "50-industry ETF rankings with live Finnhub price data, momentum metrics, and sector rotation signals.",
  openGraph: {
    title: "Industry Intel | Nuwrrrld Financial",
    description: "50-industry ETF rankings with live price data and momentum metrics.",
    images: [
      {
        url: buildOgImageUrl("Industry Intel", "50-industry ETF rankings · Live prices · Momentum metrics"),
        width: 1200,
        height: 630,
        alt: "Industry Intel — Nuwrrrld Financial",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Industry Intel | Nuwrrrld Financial",
    description: "50-industry ETF rankings with live price data and momentum metrics.",
    images: [buildOgImageUrl("Industry Intel", "50-industry ETF rankings · Live prices · Momentum metrics")],
  },
};

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) return null;
  try {
    const res = await fetch(`${base}/industry-intel`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function IndustryIntelContent() {
  const data = await getData();
  if (!data) {
    return (
      <div className="p-8 text-gray-400 animate-pulse">
        <div className="h-8 w-48 bg-gray-800 rounded mb-6" />
        <div className="h-96 bg-gray-800 rounded" />
      </div>
    );
  }
  return <IndustryTracker data={data} />;
}

export default function IndustryIntelPage() {
  return (
    <Suspense fallback={
      <div className="p-8 text-gray-400 animate-pulse">
        <div className="h-8 w-48 bg-gray-800 rounded mb-6" />
        <div className="h-96 bg-gray-800 rounded" />
      </div>
    }>
      <IndustryIntelContent />
    </Suspense>
  );
}
