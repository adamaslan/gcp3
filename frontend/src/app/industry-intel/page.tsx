export const dynamic = "force-dynamic";

import { Suspense } from "react";
import { IndustryTracker } from "@/components/IndustryTracker";

export const revalidate = 60;

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");

  // Fetch live quotes + returns concurrently from the consolidated endpoint
  const [intelRes, returnsRes] = await Promise.allSettled([
    fetch(`${base}/industry-intel`, { next: { revalidate: 60 } }),
    fetch(`${base}/industry-returns`, { next: { revalidate: 21600 } }),
  ]);

  if (intelRes.status === "rejected" || !intelRes.value.ok) {
    throw new Error("industry-intel backend error");
  }
  const quotes = await intelRes.value.json();

  // Merge returns into quotes (same logic as legacy industry-tracker page)
  if (returnsRes.status === "fulfilled" && returnsRes.value.ok) {
    const returns = await returnsRes.value.json();
    if (returns?.industries) {
      const returnsMap: Record<string, { returns?: Record<string, number>; "52w_high"?: number; "52w_low"?: number }> =
        Object.fromEntries(
          (returns.industries as Array<{ industry: string; returns?: Record<string, number>; "52w_high"?: number; "52w_low"?: number }>)
            .map((r) => [r.industry, r])
        );
      for (const [name, row] of Object.entries(quotes.industries) as Array<[string, { returns?: Record<string, number>; "52w_high"?: number; "52w_low"?: number }]>) {
        const r = returnsMap[name];
        if (r) {
          row.returns = r.returns;
          row["52w_high"] = r["52w_high"];
          row["52w_low"] = r["52w_low"];
        }
      }
      if (returns.stale_as_of) {
        quotes.returns_stale_as_of = returns.stale_as_of;
      }
    }
  }

  return quotes;
}

async function IndustryIntelContent() {
  const data = await getData();
  return <IndustryTracker data={data} />;
}

export default function IndustryIntelPage() {
  return (
    <Suspense fallback={<div className="p-8 text-gray-400">Loading industry intelligence...</div>}>
      <IndustryIntelContent />
    </Suspense>
  );
}
