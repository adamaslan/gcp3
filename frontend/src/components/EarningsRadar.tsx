"use client";

interface EarningsRecord {
  symbol: string;
  period?: string;
  actual?: number;
  estimate?: number;
  surprise?: number;
  year?: number;
  quarter?: number;
}

interface EarningsData {
  date: string;
  tracked: number;
  records: EarningsRecord[];
  beats: EarningsRecord[];
  misses: EarningsRecord[];
  beat_rate_pct: number;
  ai_outlook: string;
}

function SurpriseBar({ pct }: { pct: number }) {
  const isPos = pct >= 0;
  const width = Math.min(100, Math.abs(pct) * 5);
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full ${isPos ? "bg-green-500" : "bg-red-500"} rounded-full`} style={{ width: `${width}%` }} />
      </div>
      <span className={`text-xs font-mono ${isPos ? "text-green-400" : "text-red-400"}`}>
        {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
      </span>
    </div>
  );
}

export function EarningsRadar({ data }: { data: EarningsData }) {
  const beatColor = data.beat_rate_pct >= 70 ? "text-green-400" : data.beat_rate_pct >= 50 ? "text-yellow-400" : "text-red-400";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Earnings Radar</h1>
        <p className="text-sm text-gray-500 mt-0.5">{data.tracked} tracked symbols · {data.date}</p>
      </div>

      {/* Beat rate banner */}
      <div className="grid grid-cols-3 gap-4">
        <div className="p-4 rounded-xl border border-gray-800 text-center">
          <div className={`text-3xl font-bold ${beatColor}`}>{data.beat_rate_pct}%</div>
          <div className="text-xs text-gray-500 mt-1">Beat Rate</div>
        </div>
        <div className="p-4 rounded-xl border border-green-800/40 text-center">
          <div className="text-3xl font-bold text-green-400">{data.beats.length}</div>
          <div className="text-xs text-gray-500 mt-1">Beats</div>
        </div>
        <div className="p-4 rounded-xl border border-red-800/40 text-center">
          <div className="text-3xl font-bold text-red-400">{data.misses.length}</div>
          <div className="text-xs text-gray-500 mt-1">Misses</div>
        </div>
      </div>

      {/* AI Outlook */}
      <div className="p-4 rounded-xl border border-yellow-800/40 bg-yellow-950/10">
        <div className="text-xs font-semibold text-yellow-400 uppercase tracking-wide mb-1">AI Earnings Outlook</div>
        <p className="text-sm text-gray-300">{data.ai_outlook}</p>
      </div>

      {/* Beats & Misses */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h3 className="text-xs font-semibold text-green-400 uppercase tracking-wide mb-3">Top Beats</h3>
          <div className="rounded-xl border border-gray-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-900">
                <tr>
                  <th className="text-left px-3 py-2 text-gray-400">Symbol</th>
                  <th className="text-left px-3 py-2 text-gray-400">Period</th>
                  <th className="text-left px-3 py-2 text-gray-400">Surprise</th>
                </tr>
              </thead>
              <tbody>
                {data.beats.map((r) => (
                  <tr key={r.symbol} className="border-t border-gray-800/60">
                    <td className="px-3 py-2 font-mono text-blue-400">{r.symbol}</td>
                    <td className="px-3 py-2 text-gray-500 text-xs">{r.period ?? `Q${r.quarter} ${r.year}`}</td>
                    <td className="px-3 py-2"><SurpriseBar pct={r.surprise ?? 0} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-3">Top Misses</h3>
          <div className="rounded-xl border border-gray-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-900">
                <tr>
                  <th className="text-left px-3 py-2 text-gray-400">Symbol</th>
                  <th className="text-left px-3 py-2 text-gray-400">Period</th>
                  <th className="text-left px-3 py-2 text-gray-400">Surprise</th>
                </tr>
              </thead>
              <tbody>
                {data.misses.map((r) => (
                  <tr key={r.symbol} className="border-t border-gray-800/60">
                    <td className="px-3 py-2 font-mono text-blue-400">{r.symbol}</td>
                    <td className="px-3 py-2 text-gray-500 text-xs">{r.period ?? `Q${r.quarter} ${r.year}`}</td>
                    <td className="px-3 py-2"><SurpriseBar pct={r.surprise ?? 0} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
