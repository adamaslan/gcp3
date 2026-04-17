import type { Metadata } from "next";
import { MorningBrief } from "@/components/MorningBrief";
import { AiSummary } from "@/components/AiSummary";
import { NewsSentiment } from "@/components/NewsSentiment";
import { MarketSummary } from "@/components/MarketSummary";
import { buildOgImageUrl } from "@/lib/og";

export const revalidate = 900;

export const metadata: Metadata = {
  title: "Market Overview",
  description: "Morning brief (SPY, QQQ, IWM, DIA), AI summary, news sentiment, and 7-day market history — updated every 15 minutes.",
  openGraph: {
    title: "Market Overview | Nuwrrrld Financial",
    description: "Morning brief (SPY, QQQ, IWM, DIA), AI summary, news sentiment, and 7-day market history.",
    images: [
      {
        url: buildOgImageUrl("Market Overview", "Morning brief · AI summary · News sentiment · 7-day market history"),
        width: 1200,
        height: 630,
        alt: "Market Overview — Nuwrrrld Financial",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Market Overview | Nuwrrrld Financial",
    description: "Morning brief (SPY, QQQ, IWM, DIA), AI summary, news sentiment, and 7-day market history.",
    images: [buildOgImageUrl("Market Overview", "Morning brief · AI summary · News sentiment · 7-day market history")],
  },
};

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) return null;
  try {
    const res = await fetch(`${base}/market-overview`, { next: { revalidate: 900 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function MarketOverviewPage() {
  const data = await getData();

  if (!data) {
    return (
      <div className="p-8 text-gray-400 animate-pulse">
        <div className="h-8 w-48 bg-gray-800 rounded mb-6" />
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-32 bg-gray-800 rounded mb-4" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-8 p-6">
      <h1 className="text-2xl font-bold text-white">Market Overview</h1>

      {data.brief && !data.brief.error && (
        <section>
          <h2 className="text-lg font-semibold text-gray-300 mb-3">Morning Brief</h2>
          <MorningBrief data={data.brief} />
        </section>
      )}

      {data.ai_summary && !data.ai_summary.error && (
        <section>
          <h2 className="text-lg font-semibold text-gray-300 mb-3">AI Summary</h2>
          <AiSummary data={data.ai_summary} />
        </section>
      )}

      {data.sentiment && !data.sentiment.error && (
        <section>
          <h2 className="text-lg font-semibold text-gray-300 mb-3">News Sentiment</h2>
          <NewsSentiment data={data.sentiment} />
        </section>
      )}

      {data.history && !data.history.error && (
        <section>
          <h2 className="text-lg font-semibold text-gray-300 mb-3">Market History</h2>
          <MarketSummary data={data.history} selectedDays="7" />
        </section>
      )}
    </div>
  );
}
