"use client";

import { Screener } from "@/components/Screener";
import { useEffect, useState } from "react";

interface Quote {
  ticker: string;
  price: number;
  change: number;
  change_pct: number;
  signal: string;
  source: string;
  [key: string]: string | number;
}

interface ScreenerData {
  date: string;
  total_screened: number;
  gainers: Quote[];
  losers: Quote[];
  signal_counts: Record<string, number>;
  breadth_pct: number;
  ai_regime: string;
  quotes: Record<string, Quote>;
  sources?: Record<string, number>;
}

export default function ScreenerPage() {
  const [data, setData] = useState<ScreenerData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("/api/screener");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setData(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) return <div className="p-8">Loading screener data...</div>;
  if (error) return <div className="p-8 text-red-600">Error: {error}</div>;
  if (!data) return <div className="p-8">No data available</div>;

  return <Screener data={data} />;
}
