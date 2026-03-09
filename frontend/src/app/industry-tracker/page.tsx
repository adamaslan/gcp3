import { IndustryTracker } from "@/components/IndustryTracker";


async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/industry-tracker`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function IndustryTrackerPage() {
  const data = await getData();
  return <IndustryTracker data={data} />;
}
