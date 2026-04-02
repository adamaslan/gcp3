import { PortfolioAnalyzer } from "@/components/PortfolioAnalyzer";

export const dynamic = "force-dynamic";

async function getData() {
  const res = await fetch(`/api/portfolio-analyzer`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function PortfolioAnalyzerPage() {
  const data = await getData();
  return <PortfolioAnalyzer initialData={data} />;
}
