import { EarningsRadar } from "@/components/EarningsRadar";

export const dynamic = "force-dynamic";

async function getData() {
  const res = await fetch(`/api/earnings-radar`, { next: { revalidate: 21600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function EarningsRadarPage() {
  const data = await getData();
  return <EarningsRadar data={data} />;
}
