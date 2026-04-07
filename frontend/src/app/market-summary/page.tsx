import { MarketSummary } from "@/components/MarketSummary";

export const revalidate = 3600; // 1 hour — reads precomputed summaries from MCP pipeline

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/market-summary`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function MarketSummaryPage() {
  const data = await getData();
  return <MarketSummary data={data} />;
}
