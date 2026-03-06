import { MorningBrief } from "@/components/MorningBrief";

export const dynamic = "force-dynamic";

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/morning-brief`, { next: { revalidate: 1800 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function MorningBriefPage() {
  const data = await getData();
  return <MorningBrief data={data} />;
}
