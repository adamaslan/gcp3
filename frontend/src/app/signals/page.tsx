import { TechnicalSignals } from "@/components/TechnicalSignals";

export const revalidate = 3600;

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/signals`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function SignalsPage() {
  const data = await getData();
  return <TechnicalSignals data={data} />;
}
