import { TechnicalSignals } from "@/components/TechnicalSignals";

export const revalidate = 3600;

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) return null;
  try {
    const res = await fetch(`${base}/signals`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function SignalsPage() {
  const data = await getData();
  if (!data) {
    return (
      <div className="p-8 text-gray-400 animate-pulse">
        <div className="h-8 w-48 bg-gray-800 rounded mb-6" />
        <div className="h-64 bg-gray-800 rounded mb-4" />
        <div className="h-64 bg-gray-800 rounded" />
      </div>
    );
  }
  return <TechnicalSignals data={data} />;
}
