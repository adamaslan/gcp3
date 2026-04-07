import { MarketSummary } from "@/components/MarketSummary";

export const dynamic = "force-dynamic"; // Skip prerendering; ISR revalidates on first request
export const revalidate = 3600; // 1 hour — reads precomputed summaries from MCP pipeline

const VALID_DAYS = ["7", "14", "30"] as const;
type ValidDays = typeof VALID_DAYS[number];

async function getData(days: ValidDays): Promise<ReturnType<typeof Response.prototype.json>> {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/market-summary?days=${days}`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function MarketSummaryPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}): Promise<JSX.Element> {
  const { days: daysParam } = await searchParams;
  const days: ValidDays = VALID_DAYS.includes(daysParam as ValidDays)
    ? (daysParam as ValidDays)
    : "7";
  const data = await getData(days);
  return <MarketSummary data={data} selectedDays={days} />;
}
