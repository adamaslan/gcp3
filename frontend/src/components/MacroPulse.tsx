"use client";

interface Indicator {
  ticker: string;
  label: string;
  category: string;
  price?: number;
  change_pct?: number;
  change?: number;
  high?: number;
  low?: number;
  error?: string;
}

interface MacroData {
  date: string;
  indicators: Record<string, Indicator>;
  by_category: Record<string, Indicator[]>;
  ai_regime: string;
  ai_regime_score: number;
  ai_signals: string[];
  ai_summary: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  volatility: "Volatility",
  bonds: "Bonds / Rates",
  currency: "Currency",
  commodities: "Commodities",
  credit: "Credit Markets",
  inflation: "Inflation",
};

const REGIME_STYLES: Record<string, string> = {
  "Risk-On": "text-green-400 border-green-700 bg-green-950/20",
  "Risk-Off": "text-red-400 border-red-700 bg-red-950/20",
  "Transitional": "text-yellow-400 border-yellow-700 bg-yellow-950/20",
};

function IndicatorCard({ ind }: { ind: Indicator }) {
  const chg = ind.change_pct;
  const chgColor = chg === undefined ? "text-gray-500" : chg > 0 ? "text-green-400" : chg < 0 ? "text-red-400" : "text-gray-400";
  return (
    <div className="p-3 rounded-lg border border-gray-800 bg-gray-900/30">
      <div className="flex justify-between items-start">
        <div>
          <div className="text-xs text-gray-500 font-mono">{ind.ticker}</div>
          <div className="text-sm text-gray-200 mt-0.5">{ind.label}</div>
        </div>
        <div className="text-right">
          {ind.error ? (
            <span className="text-xs text-red-400">err</span>
          ) : (
            <>
              <div className="text-sm font-semibold text-gray-100">${ind.price?.toFixed(2)}</div>
              <div className={`text-xs ${chgColor}`}>{chg !== undefined ? `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%` : "—"}</div>
            </>
          )}
        </div>
      </div>
      {/* Intraday range — only shown when both high and low are present */}
      {ind.high !== undefined && ind.low !== undefined && !ind.error && (
        <div className="mt-2 text-xs text-gray-600 font-mono" title="Intraday low–high range">
          {ind.low.toFixed(2)} – {ind.high.toFixed(2)}
        </div>
      )}
    </div>
  );
}

export function MacroPulse({ data }: { data: MacroData }) {
  const regimeStyle = REGIME_STYLES[data.ai_regime] ?? REGIME_STYLES["Transitional"];
  const scoreAbs = Math.abs(data.ai_regime_score);
  const scoreWidth = Math.min(100, scoreAbs * 25);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Macro Pulse</h1>
        <p className="text-sm text-gray-500 mt-0.5">Cross-asset macro regime tracker · {data.date}</p>
      </div>

      {/* Regime card */}
      <div className={`p-5 rounded-xl border ${regimeStyle}`}>
        <div className="flex items-center gap-4 mb-3">
          <span className="text-xl font-bold">{data.ai_regime}</span>
          <div className="flex items-center gap-2">
            <div className="w-24 h-2 bg-gray-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${data.ai_regime_score > 0 ? "bg-green-500" : "bg-red-500"}`}
                style={{ width: `${scoreWidth}%` }}
              />
            </div>
            <span className="text-xs text-gray-400">score: {data.ai_regime_score > 0 ? "+" : ""}{data.ai_regime_score}</span>
          </div>
        </div>
        <p className="text-sm opacity-90 mb-3">{data.ai_summary}</p>
        <div className="space-y-1">
          {data.ai_signals.map((sig, i) => (
            <div key={i} className="text-xs opacity-75">• {sig}</div>
          ))}
        </div>
      </div>

      {/* Indicators by category */}
      {Object.entries(data.by_category).map(([cat, inds]) => (
        <div key={cat}>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
            {CATEGORY_LABELS[cat] ?? cat}
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {inds.map((ind) => <IndicatorCard key={ind.ticker} ind={ind} />)}
          </div>
        </div>
      ))}
    </div>
  );
}
