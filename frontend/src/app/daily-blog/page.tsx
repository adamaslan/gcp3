import { DailyBlog } from "@/components/DailyBlog";

export const dynamic = "force-dynamic";

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/daily-blog`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function DailyBlogPage() {
  const data = await getData();
  return <DailyBlog data={data} />;
}
