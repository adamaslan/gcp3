import { MacroPulse } from "@/components/MacroPulse";

export const dynamic = "force-dynamic";

async function getData() {
  const res = await fetch(`/api/macro-pulse`, { next: { revalidate: 7200 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function MacroPulsePage() {
  const data = await getData();
  return <MacroPulse data={data} />;
}
