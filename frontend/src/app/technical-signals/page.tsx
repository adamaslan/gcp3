import { TechnicalSignals } from "@/components/TechnicalSignals";

export const dynamic = "force-dynamic";

async function getData() {
  const res = await fetch(`/api/technical-signals`, { next: { revalidate: 3600 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
}

export default async function TechnicalSignalsPage() {
  const data = await getData();
  return <TechnicalSignals data={data} />;
}
