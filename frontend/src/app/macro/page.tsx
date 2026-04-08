import { MacroPulse } from "@/components/MacroPulse";
import { EarningsRadar } from "@/components/EarningsRadar";

export const revalidate = 900;

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) return { macro: null, earnings: null };
  try {
    const [macroRes, earningsRes] = await Promise.allSettled([
      fetch(`${base}/macro-pulse`, { next: { revalidate: 900 } }),
      fetch(`${base}/earnings-radar`, { next: { revalidate: 21600 } }),
    ]);

    const macro =
      macroRes.status === "fulfilled" && macroRes.value.ok
        ? await macroRes.value.json()
        : null;

    const earnings =
      earningsRes.status === "fulfilled" && earningsRes.value.ok
        ? await earningsRes.value.json()
        : null;

    return { macro, earnings };
  } catch {
    return { macro: null, earnings: null };
  }
}

export default async function MacroPage() {
  const { macro, earnings } = await getData();

  return (
    <div className="space-y-8 p-6">
      <h1 className="text-2xl font-bold text-white">Macro &amp; Earnings</h1>

      {macro ? (
        <section>
          <h2 className="text-lg font-semibold text-gray-300 mb-3">Macro Pulse</h2>
          <MacroPulse data={macro} />
        </section>
      ) : (
        <div className="h-48 bg-gray-800 rounded animate-pulse" />
      )}

      {earnings ? (
        <section>
          <h2 className="text-lg font-semibold text-gray-300 mb-3">Earnings Radar</h2>
          <EarningsRadar data={earnings} />
        </section>
      ) : (
        <div className="h-48 bg-gray-800 rounded animate-pulse" />
      )}
    </div>
  );
}
