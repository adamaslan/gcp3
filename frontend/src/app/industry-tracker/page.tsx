import { cache, Suspense } from "react";
import { IndustryTracker } from "@/components/IndustryTracker";
import { IndustryTrackerLocalFallback, LocalStorageSaver } from "./IndustryTrackerClient";

export const revalidate = 60;

const getQuotes = cache(async () => {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/industry-quotes`, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error(`Backend error ${res.status}`);
  return res.json();
});

const getReturns = cache(async () => {
  const base = process.env.BACKEND_URL;
  if (!base) throw new Error("BACKEND_URL is not configured");
  const res = await fetch(`${base}/industry-returns`, { next: { revalidate: 21600 } });
  if (!res.ok) return null;
  return res.json();
});

async function IndustryTrackerContent() {
  const [quotes, returns] = await Promise.all([getQuotes(), getReturns()]);

  // Merge returns data (returns/52w) into each industry row from quotes
  if (returns?.industries) {
    const returnsMap: Record<string, { returns?: Record<string, number>; "52w_high"?: number; "52w_low"?: number }> =
      Object.fromEntries(
        (returns.industries as Array<{ industry: string; returns?: Record<string, number>; "52w_high"?: number; "52w_low"?: number }>)
          .map((r) => [r.industry, r])
      );
    for (const row of Object.values(quotes.industries) as Array<{ industry?: string; returns?: Record<string, number>; "52w_high"?: number; "52w_low"?: number }>) {
      const r = returnsMap[row.industry ?? ""];
      if (r) {
        row.returns = r.returns;
        row["52w_high"] = r["52w_high"];
        row["52w_low"] = r["52w_low"];
      }
    }
  }

  return (
    <>
      <LocalStorageSaver data={quotes} />
      <IndustryTracker data={quotes} />
    </>
  );
}

export default function IndustryTrackerPage() {
  return (
    <Suspense fallback={<IndustryTrackerLocalFallback />}>
      <IndustryTrackerContent />
    </Suspense>
  );
}
