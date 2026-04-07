import { NewsSentiment } from "@/components/NewsSentiment";
export const dynamic = "force-dynamic";


export const revalidate = 1800; // 30 minutes — news cycles hourly, 30min staleness is acceptable, 3x/day scheduler refresh

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/news-sentiment`, { next: { revalidate: 1800 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function NewsSentimentPage() {
  const data = await getData();
  return <NewsSentiment data={data} />;
}
