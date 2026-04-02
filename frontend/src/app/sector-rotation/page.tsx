import { SectorRotation } from "@/components/SectorRotation";

export const dynamic = "force-dynamic";

async function getData() {
  const res = await fetch(`/api/sector-rotation`, { next: { revalidate: 7200 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function SectorRotationPage() {
  const data = await getData();
  return <SectorRotation data={data} />;
}
