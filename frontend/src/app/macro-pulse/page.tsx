import { MacroPulse } from "@/components/MacroPulse";
export const dynamic = "force-dynamic";


export const revalidate = 3600; // 1 hour — cross-asset indicators move slowly, same pattern as sector rotation

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/macro-pulse`, { next: { revalidate: 7200 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function MacroPulsePage() {
  const data = await getData();
  return <MacroPulse data={data} />;
}
