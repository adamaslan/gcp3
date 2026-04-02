import { Screener } from "@/components/Screener";

export const dynamic = "force-dynamic";

async function getData() {
  const res = await fetch(`/api/screener`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function ScreenerPage() {
  const data = await getData();
  return <Screener data={data} />;
}
