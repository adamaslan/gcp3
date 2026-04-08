export const dynamic = "force-dynamic";

import { MorningBrief } from "@/components/MorningBrief";
import { AiSummary } from "@/components/AiSummary";
import { NewsSentiment } from "@/components/NewsSentiment";
import { MarketSummary } from "@/components/MarketSummary";

export const revalidate = 900;

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/market-overview`, { next: { revalidate: 900 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function MarketOverviewPage() {
  const data = await getData();

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
