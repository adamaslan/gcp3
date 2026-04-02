"use client";

interface MarketSnapshot {
  tone?: string;
  avg_change_pct?: number;
  macro_regime?: string;
  leaders?: string[];
  laggards?: string[];
  breadth_pct?: number;
  news_sentiment?: string;
  top_gainers?: string[];
  top_losers?: string[];
}

interface DailyBlogData {
  date: string;
  theme_id: string;
  title: string;
  tool: string;
  angle: string;
  body: string;
  market_snapshot?: MarketSnapshot;
  stale?: boolean;
  stale_date?: string;
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

export function DailyBlog({ data }: { data: DailyBlogData }) {
  const snapshot = data.market_snapshot || {};
  const toneColor = TONE_STYLES[snapshot.tone ?? ""] ?? "text-gray-400";
  const regimeDot = REGIME_DOT[snapshot.macro_regime ?? ""] ?? "bg-gray-400";
  const sentimentDot = SENTIMENT_DOT[snapshot.news_sentiment ?? ""] ?? "bg-gray-400";
  const breadthColor =
    (snapshot.breadth_pct ?? 0) > 0
      ? "text-green-400"
      : (snapshot.breadth_pct ?? 0) < 0
        ? "text-red-400"
        : "text-gray-400";

  return (
    <div className="space-y-5">
      {/* Stale banner */}
      {data.stale && (
        <div className="p-4 rounded-lg border border-yellow-800/40 bg-yellow-950/20">
          <p className="text-sm text-yellow-400">
            📅 Showing yesterday's post ({data.stale_date}) — today's will appear shortly.
          </p>
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{data.title}</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {data.tool} · {data.theme_id} · {data.date}
        </p>
      </div>

      {/* Angle tagline */}
      <p className="text-sm text-gray-300 italic border-l-2 border-blue-600 pl-3">
        {data.angle}
      </p>

      {/* Meta badges */}
      <div className="flex flex-wrap gap-3 text-xs">
        {snapshot.tone && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-700 bg-gray-900">
            <span className={`font-semibold ${toneColor} capitalize`}>{snapshot.tone}</span>
            <span className="text-gray-600">market tone</span>
          </div>
        )}
        {snapshot.macro_regime && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-700 bg-gray-900">
            <span className={`w-1.5 h-1.5 rounded-full ${regimeDot}`} />
            <span className="text-gray-300">{snapshot.macro_regime}</span>
            <span className="text-gray-600">macro</span>
          </div>
        )}
        {snapshot.breadth_pct !== undefined && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-700 bg-gray-900">
            <span className={`font-semibold ${breadthColor}`}>
              {snapshot.breadth_pct > 0 ? "+" : ""}
              {snapshot.breadth_pct}%
            </span>
            <span className="text-gray-600">breadth</span>
          </div>
        )}
        {snapshot.news_sentiment && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-700 bg-gray-900">
            <span className={`w-1.5 h-1.5 rounded-full ${sentimentDot}`} />
            <span className="text-gray-300 capitalize">{snapshot.news_sentiment}</span>
            <span className="text-gray-600">news</span>
          </div>
        )}
      </div>

      {/* Blog body */}
      <div className="p-6 rounded-xl border border-gray-700 bg-gray-900/40">
        <div className="text-xs font-semibold text-blue-400 uppercase tracking-wide mb-4">
          Today's Post
        </div>
        <div className="prose prose-invert max-w-none">
          {data.body.split("\n\n").map((para, i) => (
            <p key={i} className="text-gray-200 leading-relaxed text-sm mb-3 last:mb-0">
              {para}
            </p>
          ))}
        </div>
      </div>

      {/* Market context */}
      {snapshot.leaders && snapshot.leaders.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 rounded-xl border border-green-800/40 bg-green-950/10">
            <h3 className="text-xs font-semibold text-green-400 uppercase tracking-wide mb-2">
              Leading Sectors
            </h3>
            {(snapshot.leaders ?? []).map((s) => (
              <div key={s} className="text-sm text-gray-300 py-0.5">
                • {s}
              </div>
            ))}
          </div>
          <div className="p-4 rounded-xl border border-red-800/40 bg-red-950/10">
            <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-2">
              Lagging Sectors
            </h3>
            {(snapshot.laggards ?? []).map((s) => (
              <div key={s} className="text-sm text-gray-300 py-0.5">
                • {s}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
