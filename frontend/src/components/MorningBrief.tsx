"use client";

interface IndexData {
  symbol: string;
  price?: number;
  change?: number;
  change_pct?: number;
  error?: string;
}

interface BriefData {
  date: string;
  market_tone: "bullish" | "bearish" | "neutral";
  avg_change_pct: number;
  indices: Record<string, IndexData>;
  summary: string;
}

const TONE_STYLES = {
  bullish: "text-green-400 border-green-700 bg-green-950/20",
  bearish: "text-red-400 border-red-700 bg-red-950/20",
  neutral: "text-yellow-400 border-yellow-700 bg-yellow-950/20",
};

function ChangeCell({ pct }: { pct?: number }) {
  if (pct === undefined) return <span className="text-gray-500">—</span>;
  const color = pct > 0 ? "text-green-400" : pct < 0 ? "text-red-400" : "text-gray-400";
  return <span className={color}>{pct > 0 ? "+" : ""}{pct.toFixed(2)}%</span>;
}

export function MorningBrief({ data }: { data: BriefData }) {
  const toneStyle = TONE_STYLES[data.market_tone];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Morning Brief</h1>
        <span className="text-sm text-gray-500">{data.date}</span>
      </div>

      {/* Tone + Summary */}
      <div className={`p-5 rounded-xl border ${toneStyle}`}>
        <div className="flex items-center gap-3 mb-2">
          <span className="text-lg font-bold capitalize">{data.market_tone}</span>
          <span className="text-sm opacity-75">avg {data.avg_change_pct > 0 ? "+" : ""}{data.avg_change_pct.toFixed(2)}%</span>
        </div>
        <p className="text-sm opacity-90">{data.summary}</p>
      </div>

      {/* Index Table */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-900">
            <tr>
              <th className="text-left px-4 py-3 text-gray-400 font-medium">Index</th>
              <th className="text-left px-4 py-3 text-gray-400 font-medium">Symbol</th>
              <th className="text-right px-4 py-3 text-gray-400 font-medium">Price</th>
              <th className="text-right px-4 py-3 text-gray-400 font-medium">Change</th>
              <th className="text-right px-4 py-3 text-gray-400 font-medium">Change %</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.indices).map(([name, idx]) => (
              <tr key={name} className="border-t border-gray-800 hover:bg-gray-900/50">
                <td className="px-4 py-3 text-gray-200">{name}</td>
                <td className="px-4 py-3 text-blue-400 font-mono">{idx.symbol}</td>
                <td className="px-4 py-3 text-right text-gray-300">
                  {idx.price !== undefined ? `$${idx.price.toFixed(2)}` : <span className="text-red-400 text-xs">{idx.error}</span>}
                </td>
                <td className="px-4 py-3 text-right"><ChangeCell pct={idx.change} /></td>
                <td className="px-4 py-3 text-right"><ChangeCell pct={idx.change_pct} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
