"use client";

interface SectorRow {
  sector: string;
  etf: string;
  momentum_score: number;
  price: number;
  change_pct: number;
  change: number;
  error?: string;
}

interface SectorRotationData {
  date: string;
  sectors: Record<string, SectorRow>;
  ranked: SectorRow[];
  leaders: SectorRow[];
  laggards: SectorRow[];
  ai_analysis: string;
}

function MomentumBar({ score }: { score: number }) {
  const width = Math.min(100, Math.abs(score) * 20);
  const color = score > 0 ? "bg-green-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${width}%` }} />
      </div>
      <span className={`text-xs font-mono ${score > 0 ? "text-green-400" : score < 0 ? "text-red-400" : "text-gray-500"}`}>
        {score > 0 ? "+" : ""}{score.toFixed(3)}
      </span>
    </div>
  );
}

export function SectorRotation({ data }: { data: SectorRotationData }) {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Sector Rotation</h1>
        <p className="text-sm text-gray-500 mt-0.5">11 GICS sectors · {data.date}</p>
      </div>

      {/* AI Analysis */}
      <div className="p-4 rounded-xl border border-purple-800/40 bg-purple-950/10">
        <div className="text-xs font-semibold text-purple-400 uppercase tracking-wide mb-1">AI Rotation Analysis</div>
        <p className="text-sm text-gray-300">{data.ai_analysis}</p>
      </div>

      {/* Leaders & Laggards */}
      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 rounded-xl border border-green-800/60 bg-green-950/10">
          <h3 className="text-xs font-semibold text-green-400 uppercase tracking-wide mb-3">Leading Sectors</h3>
          {data.leaders.map((r) => (
            <div key={r.sector} className="flex justify-between items-center py-1.5">
              <div>
                <div className="text-sm text-gray-200">{r.sector}</div>
                <div className="text-xs text-gray-600">{r.etf}</div>
              </div>
              <MomentumBar score={r.momentum_score} />
            </div>
          ))}
        </div>
        <div className="p-4 rounded-xl border border-red-800/60 bg-red-950/10">
          <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-3">Lagging Sectors</h3>
          {data.laggards.map((r) => (
            <div key={r.sector} className="flex justify-between items-center py-1.5">
              <div>
                <div className="text-sm text-gray-200">{r.sector}</div>
                <div className="text-xs text-gray-600">{r.etf}</div>
              </div>
              <MomentumBar score={r.momentum_score} />
            </div>
          ))}
        </div>
      </div>

      {/* Full rankings */}
      <div className="rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-900">
            <tr>
              <th className="text-left px-3 py-2 text-gray-500 w-8">#</th>
              <th className="text-left px-3 py-2 text-gray-400">Sector</th>
              <th className="text-left px-3 py-2 text-gray-400">ETF</th>
              <th className="text-right px-3 py-2 text-gray-400">Price</th>
              <th className="text-right px-3 py-2 text-gray-400">Chg %</th>
              <th className="text-left px-3 py-2 text-gray-400">Momentum</th>
            </tr>
          </thead>
          <tbody>
            {data.ranked.map((r, i) => (
              <tr key={r.sector} className="border-t border-gray-800/60 hover:bg-gray-900/40">
                <td className="px-3 py-2 text-gray-600 text-xs">{i + 1}</td>
                <td className="px-3 py-2 text-gray-200">{r.sector}</td>
                <td className="px-3 py-2 text-blue-400 font-mono text-xs">{r.etf}</td>
                <td className="px-3 py-2 text-right text-gray-300">${r.price?.toFixed(2)}</td>
                <td className={`px-3 py-2 text-right ${r.change_pct > 0 ? "text-green-400" : r.change_pct < 0 ? "text-red-400" : "text-gray-400"}`}>
                  {r.change_pct > 0 ? "+" : ""}{r.change_pct?.toFixed(2)}%
                </td>
                <td className="px-3 py-2"><MomentumBar score={r.momentum_score} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
