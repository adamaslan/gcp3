import { CorrelationArticle } from "@/components/CorrelationArticle";
export const dynamic = "force-dynamic";


export const revalidate = 14400; // 4 hours — cross-asset correlation, generated once daily

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/correlation-article`, { next: { revalidate: 14400 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function CorrelationArticlePage() {
  const data = await getData();
  return <CorrelationArticle data={data} />;
}
