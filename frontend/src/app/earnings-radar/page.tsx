import { EarningsRadar } from "@/components/EarningsRadar";
export const dynamic = "force-dynamic";


export const revalidate = 21600; // 6 hours — EPS data doesn't change intraday, long ISR is correct

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/earnings-radar`, { next: { revalidate: 21600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function EarningsRadarPage() {
  const data = await getData();
  return <EarningsRadar data={data} />;
}
