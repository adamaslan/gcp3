import { MarketSummary } from "@/components/MarketSummary";

export const dynamic = "force-dynamic";

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/market-summary?days=7`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function MarketSummaryPage() {
  const data = await getData();
  return <MarketSummary data={data} />;
}
