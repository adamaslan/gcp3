import { Screener } from "@/components/Screener";
export const dynamic = "force-dynamic";


export const revalidate = 1800; // 30 minutes — scheduler refreshes 3x/day, 30min ISR catches fresh data sooner

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/screener`, { next: { revalidate: 1800 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function ScreenerPage() {
  const data = await getData();
  return <Screener data={data} />;
}
