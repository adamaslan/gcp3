import { NewsSentiment } from "@/components/NewsSentiment";

export const dynamic = "force-dynamic";

async function getData() {
  const res = await fetch(`/api/news-sentiment`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function NewsSentimentPage() {
  const data = await getData();
  return <NewsSentiment data={data} />;
}
