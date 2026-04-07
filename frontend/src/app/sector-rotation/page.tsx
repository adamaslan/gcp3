import { SectorRotation } from "@/components/SectorRotation";
export const dynamic = "force-dynamic";


export const revalidate = 3600; // 1 hour — momentum scores shift slowly, revalidation reads from warm Firestore

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/sector-rotation`, { next: { revalidate: 7200 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function SectorRotationPage() {
  const data = await getData();
  return <SectorRotation data={data} />;
}
