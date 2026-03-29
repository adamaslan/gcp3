"use client";
import { useState, useEffect } from "react";
import { IndustryTracker } from "@/components/IndustryTracker";

const CACHE_KEY = "gcp3:industry-tracker:v1";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type IndustryData = Parameters<typeof IndustryTracker>[0]["data"] & Record<string, any>;

function readCache(): IndustryData | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/**
 * Shown as the Suspense fallback while the async server component fetches.
 * Reads localStorage immediately so returning users see instant data
 * instead of a blank screen while the server revalidates.
 */
export function IndustryTrackerLocalFallback() {
  const [data, setData] = useState<IndustryData | null>(null);

  useEffect(() => {
    const cached = readCache();
    if (cached) setData(cached);
  }, []);

  if (!data) {
    return <div className="animate-pulse bg-gray-800 rounded h-96 w-full" />;
  }

  return (
    <div className="relative">
      <span className="absolute top-0 right-0 text-[10px] text-gray-600 select-none">cached</span>
      <IndustryTracker data={data} />
    </div>
  );
}

/**
 * Rendered by the server component once fresh data is available.
 * Saves that data to localStorage so the next visit can show it instantly.
 */
export function LocalStorageSaver({ data }: { data: IndustryData }) {
  useEffect(() => {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(data));
    } catch {}
  }, [data]);
  return null;
}
