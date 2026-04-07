import { IndustryReturns } from "@/components/IndustryReturns";
export const dynamic = "force-dynamic";


export const revalidate = 3600; // 1 hour — returns precomputed daily, reads from industry_cache (1 Firestore read, zero API)

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/industry-returns`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function IndustryReturnsPage() {
  const data = await getData();
  return <IndustryReturns data={data} />;
}
