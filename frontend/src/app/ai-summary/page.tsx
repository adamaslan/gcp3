import { AiSummary } from "@/components/AiSummary";

export const dynamic = "force-dynamic";

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/ai-summary`, { next: { revalidate: 14400 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function AiSummaryPage() {
  const data = await getData();
  return <AiSummary data={data} />;
}
