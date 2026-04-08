"use client";

import { IndustryReturns } from "@/components/IndustryReturns";
import { useEffect, useState } from "react";

interface IndustryReturnsData {
  date: string;
  updated?: string;
  total: number;
  industries: Array<{
    etf: string;
    industry: string;
    updated?: string;
    "52w_high"?: number;
    "52w_low"?: number;
    returns: Record<string, number | undefined>;
  }>;
  leaders: Record<string, Array<{ industry: string; etf: string; return: number }>>;
  laggards: Record<string, Array<{ industry: string; etf: string; return: number }>>;
  periods_available: string[];
}

export default function IndustryReturnsPage() {
  const [data, setData] = useState<IndustryReturnsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("/api/industry-returns");
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

  if (loading) return <div className="p-8">Loading industry returns...</div>;
  if (error) return <div className="p-8 text-red-600">Error: {error}</div>;
  if (!data) return <div className="p-8">No data available</div>;

  return <IndustryReturns data={data} />;
}
