"use client";

interface AiSummaryData {
  date: string;
  brief: string;
  market_tone: string;
  macro_regime: string;
  leading_sectors: string[];
  lagging_sectors: string[];
  breadth_pct: number;
  news_sentiment: string;
  sources: string[];
}

const TONE_STYLES: Record<string, string> = {
  bullish: "text-green-400",
  bearish: "text-red-400",
  neutral: "text-yellow-400",
};

const REGIME_DOT: Record<string, string> = {
  "Risk-On": "bg-green-400",
  "Risk-Off": "bg-red-400",
  "Transitional": "bg-yellow-400",
};

const SENTIMENT_DOT: Record<string, string> = {
  positive: "bg-green-400",
  negative: "bg-red-400",
  neutral: "bg-yellow-400",
};

export function AiSummary({ data }: { data: AiSummaryData }) {
  const toneColor = TONE_STYLES[data.market_tone] ?? "text-gray-400";
  const regimeDot = REGIME_DOT[data.macro_regime] ?? "bg-gray-400";
  const sentimentDot = SENTIMENT_DOT[data.news_sentiment] ?? "bg-gray-400";
  const breadthColor = data.breadth_pct > 0 ? "text-green-400" : data.breadth_pct < 0 ? "text-red-400" : "text-gray-400";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">AI Market Summary</h1>
        <p className="text-sm text-gray-500 mt-0.5">Claude-powered synthesis of all 8 data sources · {data.date}</p>
      </div>

      {/* Meta badges */}
      <div className="flex flex-wrap gap-3 text-xs">
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-700 bg-gray-900">
          <span className={`font-semibold ${toneColor} capitalize`}>{data.market_tone}</span>
          <span className="text-gray-600">market tone</span>
        </div>
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-700 bg-gray-900">
          <span className={`w-1.5 h-1.5 rounded-full ${regimeDot}`} />
          <span className="text-gray-300">{data.macro_regime}</span>
          <span className="text-gray-600">macro</span>
        </div>
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-700 bg-gray-900">
          <span className={`font-semibold ${breadthColor}`}>{data.breadth_pct > 0 ? "+" : ""}{data.breadth_pct}%</span>
          <span className="text-gray-600">breadth</span>
        </div>
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-700 bg-gray-900">
          <span className={`w-1.5 h-1.5 rounded-full ${sentimentDot}`} />
          <span className="text-gray-300 capitalize">{data.news_sentiment}</span>
          <span className="text-gray-600">news</span>
        </div>
      </div>

      {/* Main brief */}
      <div className="p-6 rounded-xl border border-gray-700 bg-gray-900/40">
        <div className="text-xs font-semibold text-blue-400 uppercase tracking-wide mb-4">Daily Brief</div>
        <div className="prose prose-invert max-w-none">
          {data.brief.split("\n\n").map((para, i) => (
            <p key={i} className="text-gray-200 leading-relaxed text-sm mb-3 last:mb-0">{para}</p>
          ))}
        </div>
      </div>

      {/* Sector context */}
      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 rounded-xl border border-green-800/40 bg-green-950/10">
          <h3 className="text-xs font-semibold text-green-400 uppercase tracking-wide mb-2">Leading Sectors</h3>
          {(data.leading_sectors ?? []).map((s) => (
            <div key={s} className="text-sm text-gray-300 py-0.5">• {s}</div>
          ))}
        </div>
        <div className="p-4 rounded-xl border border-red-800/40 bg-red-950/10">
          <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-2">Lagging Sectors</h3>
          {(data.lagging_sectors ?? []).map((s) => (
            <div key={s} className="text-sm text-gray-300 py-0.5">• {s}</div>
          ))}
        </div>
      </div>

      {/* Sources */}
      <div className="flex flex-wrap gap-2">
        <span className="text-xs text-gray-600">Data sources:</span>
        {(data.sources ?? []).map((s) => (
          <span key={s} className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-500">{s.replace("_", " ")}</span>
        ))}
      </div>
    </div>
  );
}
