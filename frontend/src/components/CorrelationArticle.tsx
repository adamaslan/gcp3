"use client";

interface FocusPair {
  pair_id: string;
  signal: "agreement" | "divergence" | "neutral";
  score: number;
  summary: string;
}

interface NewsArticle {
  headline: string;
  source: string;
  url: string;
  summary: string;
}

interface CorrelationSnapshot {
  agreements: number;
  divergences: number;
  neutral: number;
}

interface CorrelationArticleData {
  date: string;
  title: string;
  body: string;
  focus_pairs: FocusPair[];
  sources_used: string[];
  news_articles: NewsArticle[];
  correlation_snapshot: CorrelationSnapshot;
  stale?: boolean;
  stale_date?: string;
}

const SIGNAL_COLORS: Record<string, string> = {
  agreement: "border-green-800/40 bg-green-950/10",
  divergence: "border-red-800/40 bg-red-950/10",
  neutral: "border-gray-800/40 bg-gray-950/10",
};

const SIGNAL_BADGE_COLORS: Record<string, string> = {
  agreement: "text-green-400",
  divergence: "text-red-400",
  neutral: "text-gray-400",
};

export function CorrelationArticle({ data }: { data: CorrelationArticleData }) {
  const snapshot = data.correlation_snapshot || { agreements: 0, divergences: 0, neutral: 0 };

  return (
    <div className="space-y-5">
      {/* Stale banner */}
      {data.stale && (
        <div className="p-4 rounded-lg border border-yellow-800/40 bg-yellow-950/20">
          <p className="text-sm text-yellow-400">
            📅 Showing yesterday's article ({data.stale_date}) — today's will appear shortly.
          </p>
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">{data.title}</h1>
        <p className="text-sm text-gray-500 mt-0.5">{data.date}</p>
      </div>

      {/* Correlation snapshot badges */}
      <div className="flex flex-wrap gap-3 text-xs">
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-green-800/40 bg-green-950/10">
          <span className="text-green-400 font-semibold">{snapshot.agreements}</span>
          <span className="text-gray-600">agreements</span>
        </div>
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-red-800/40 bg-red-950/10">
          <span className="text-red-400 font-semibold">{snapshot.divergences}</span>
          <span className="text-gray-600">divergences</span>
        </div>
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-gray-800/40 bg-gray-950/10">
          <span className="text-gray-400 font-semibold">{snapshot.neutral}</span>
          <span className="text-gray-600">neutral</span>
        </div>
      </div>

      {/* Focus pairs */}
      <div className="space-y-2">
        <div className="text-xs font-semibold text-blue-400 uppercase tracking-wide">Focus Correlations</div>
        {data.focus_pairs.map((pair) => (
          <div key={pair.pair_id} className={`p-3 rounded-lg border ${SIGNAL_COLORS[pair.signal]}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1">
                <div className="text-xs font-mono text-gray-400">{pair.pair_id}</div>
                <p className="text-sm text-gray-200 mt-1">{pair.summary}</p>
              </div>
              <div className="text-right whitespace-nowrap">
                <span className={`text-sm font-semibold ${SIGNAL_BADGE_COLORS[pair.signal]} capitalize`}>
                  {pair.signal}
                </span>
                <div className="text-xs text-gray-500 mt-0.5">{pair.score.toFixed(2)}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Article body */}
      <div className="p-6 rounded-xl border border-gray-700 bg-gray-900/40">
        <div className="text-xs font-semibold text-blue-400 uppercase tracking-wide mb-4">Article</div>
        <div className="prose prose-invert max-w-none">
          {data.body.split("\n\n").map((para, i) => (
            <p key={i} className="text-gray-200 leading-relaxed text-sm mb-3 last:mb-0">
              {para}
            </p>
          ))}
        </div>
      </div>

      {/* Sources used */}
      {data.sources_used && data.sources_used.length > 0 && (
        <div className="p-4 rounded-lg border border-gray-800/40 bg-gray-950/10">
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Data Sources</div>
          <div className="flex flex-wrap gap-2">
            {data.sources_used.map((source) => (
              <span
                key={source}
                className="px-2 py-1 rounded text-xs bg-gray-800 text-gray-300 capitalize"
              >
                {source.replace("-", " ")}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* News articles */}
      {data.news_articles && data.news_articles.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-purple-400 uppercase tracking-wide">Supporting News</div>
          {data.news_articles.map((article, i) => (
            <a
              key={i}
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-3 rounded-lg border border-purple-800/40 bg-purple-950/10 block hover:border-purple-600/60 transition-colors"
            >
              <div className="text-xs text-purple-400 font-semibold">{article.source}</div>
              <p className="text-sm text-gray-200 mt-1 font-semibold">{article.headline}</p>
              {article.summary && <p className="text-xs text-gray-400 mt-1">{article.summary}</p>}
            </a>
          ))}
        </div>
      )}

      {/* Footer note */}
      <div className="flex gap-2 text-xs text-gray-600">
        <span>🔗</span>
        <span>Correlation article generated by analyzing cross-source market patterns and news.</span>
      </div>
    </div>
  );
}
