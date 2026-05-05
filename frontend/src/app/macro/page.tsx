import type { Metadata } from "next";
import { MacroPulse } from "@/components/MacroPulse";
import { EarningsRadar } from "@/components/EarningsRadar";
import { Disclaimer } from "@/components/Disclaimer";
import { buildOgImageUrl } from "@/lib/og";

export const revalidate = 900;

export const metadata: Metadata = {
  title: "Macro & Earnings",
  description: "Macro pulse with 11 cross-asset indicators and risk regime, plus earnings radar tracking EPS beats/misses and forward outlook.",
  openGraph: {
    title: "Macro & Earnings | Nuwrrrld Financial",
    description: "11 cross-asset macro indicators · Risk regime · EPS beats/misses · Forward earnings outlook.",
    images: [
      {
        url: buildOgImageUrl("Macro & Earnings", "11 cross-asset indicators · Risk regime · EPS beats/misses"),
        width: 1200,
        height: 630,
        alt: "Macro & Earnings — Nuwrrrld Financial",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Macro & Earnings | Nuwrrrld Financial",
    description: "11 cross-asset macro indicators · Risk regime · EPS beats/misses · Forward earnings outlook.",
    images: [buildOgImageUrl("Macro & Earnings", "11 cross-asset indicators · Risk regime · EPS beats/misses")],
  },
};

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

      <Disclaimer />
    </div>
  );
}
