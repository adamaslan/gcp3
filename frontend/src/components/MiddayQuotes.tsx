import FreshnessBadge from "./FreshnessBadge";

interface Quote {
  price: number;
  change: number;
  change_pct: number;
  high: number;
  low: number;
  open: number;
  prev_close: number;
  source: string;
  fetched_at: string;
}

interface DataStatus {
  expected: number;
  available: number;
  failed: number;
  partial: boolean;
  failed_symbols?: string[];
}

interface MiddayPayload {
  quotes: Record<string, Quote>;
  data_status: DataStatus;
  trading_date: string;
  checkpoint_status?: string;
  checkpoint_written_at?: string;
}

async function fetchMiddayQuotes(): Promise<MiddayPayload | null> {
  // This is a server component. NEXT_PUBLIC_BASE_URL doesn't exist anywhere
  // in this codebase (no .env.example entry, no other reference) — it was
  // always undefined, so `base` was always "", and Node's server-side fetch
  // requires an absolute URL (no implicit browser-style origin resolution).
  // Every fetch here has therefore always thrown and been swallowed by the
  // catch below, silently returning null. NEXT_PUBLIC_APP_URL is the actual
  // env var this repo uses for its own origin (frontend/.env.example).
  const base = process.env.NEXT_PUBLIC_APP_URL ?? "";
  try {
    const res = await fetch(`${base}/api/midday-quotes`, { next: { revalidate: 300 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function Pct({ v }: { v: number }) {
  const cls = v > 0 ? "text-green-400" : v < 0 ? "text-red-400" : "text-gray-400";
  return (
    <span className={cls}>
      {v > 0 ? "+" : ""}
      {v.toFixed(2)}%
    </span>
  );
}

export default async function MiddayQuotes() {
  const data = await fetchMiddayQuotes();

  if (!data) {
    return (
      <div className="rounded-xl bg-gray-900 border border-gray-800 p-4">
        <p className="text-gray-500 text-sm">Midday quotes unavailable — next run at 12:00 PM ET.</p>
      </div>
    );
  }

  const { quotes, data_status, trading_date, checkpoint_status, checkpoint_written_at } = data;
  const symbols = Object.keys(quotes).sort();
  const sampleFetchedAt = symbols.length > 0 ? quotes[symbols[0]]?.fetched_at : undefined;

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-4 space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-white font-semibold text-base">Midday ETF Quotes</h2>
        <FreshnessBadge
          fetchedAt={checkpoint_written_at ?? sampleFetchedAt}
          source="yfinance"
          dataStatus={data_status}
          checkpointStatus={checkpoint_status}
        />
      </div>
      <p className="text-gray-500 text-xs">Trading date: {trading_date}</p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="pb-2 pr-4 font-medium">Symbol</th>
              <th className="pb-2 pr-4 font-medium text-right">Price</th>
              <th className="pb-2 pr-4 font-medium text-right">Chg%</th>
              <th className="pb-2 pr-4 font-medium text-right">High</th>
              <th className="pb-2 font-medium text-right">Low</th>
            </tr>
          </thead>
          <tbody>
            {symbols.map((sym) => {
              const q = quotes[sym];
              return (
                <tr key={sym} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-1.5 pr-4 font-mono text-gray-200">{sym}</td>
                  <td className="py-1.5 pr-4 text-right text-gray-200">${q.price.toFixed(2)}</td>
                  <td className="py-1.5 pr-4 text-right"><Pct v={q.change_pct} /></td>
                  <td className="py-1.5 pr-4 text-right text-gray-400">${q.high.toFixed(2)}</td>
                  <td className="py-1.5 text-right text-gray-400">${q.low.toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
