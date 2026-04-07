import { PortfolioAnalyzer } from "@/components/PortfolioAnalyzer";

// Cannot use ISR: accepts user-provided ?tickers= query params (infinite input space)
// Optimization: use client-side SWR/React Query with API proxy route — backend in-memory cache still helps
export const dynamic = "force-dynamic";

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/portfolio-analyzer`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function PortfolioAnalyzerPage() {
  const data = await getData();
  return <PortfolioAnalyzer initialData={data} />;
}
