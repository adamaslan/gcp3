"use client";

interface ExtremePair {
  pair_id: string;
  signal: "agreement" | "divergence" | "neutral";
  score: number;
  summary: string;
  source_a: string;
  source_b: string;
}

interface StoryArticleData {
  date: string;
  title: string;
  body: string;
  extreme_pair: ExtremePair;
  all_pairs_count: number;
  stale?: boolean;
  stale_date?: string;
}

const SIGNAL_COLORS: Record<string, string> = {
  agreement: "border-green-700/50 bg-green-950/20 text-green-300",
  divergence: "border-red-700/50 bg-red-950/20 text-red-300",
  neutral: "border-gray-700/50 bg-gray-800/20 text-gray-400",
};

const SIGNAL_LABEL: Record<string, string> = {
  agreement: "AGREEMENT",
  divergence: "DIVERGENCE",
  neutral: "NEUTRAL",
};

export function StoryArticle({ data }: { data: StoryArticleData }) {
  const pair = data.extreme_pair;
  const signalColors = SIGNAL_COLORS[pair.signal] ?? SIGNAL_COLORS.neutral;
  const signalLabel = SIGNAL_LABEL[pair.signal] ?? pair.signal.toUpperCase();
  const scoreAbs = Math.abs(pair.score).toFixed(2);

  const paragraphs = data.body
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);

  return (
    <div className="space-y-6">
      {data.stale && (
        <div className="bg-yellow-900/30 border border-yellow-700/40 rounded-lg px-4 py-2 text-sm text-yellow-300">
          Showing article from {data.stale_date} — fresh data unavailable
        </div>
      )}

      {/* Header */}
      <div>
        <div className="text-xs text-gray-500 mb-1 uppercase tracking-wide">
          Story Picker — {data.date}
        </div>
        <h2 className="text-xl font-bold text-white leading-tight">{data.title}</h2>
      </div>

      {/* Extreme pair badge */}
      <div className={`border rounded-lg px-4 py-3 ${signalColors}`}>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <span className="text-xs font-semibold uppercase tracking-widest opacity-70">
              {signalLabel}
            </span>
            <div className="text-sm font-medium mt-0.5">
              {pair.source_a.replace(/-/g, " ")} vs {pair.source_b.replace(/-/g, " ")}
            </div>
            <div className="text-xs opacity-70 mt-0.5">{pair.pair_id}</div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold tabular-nums">{scoreAbs}</div>
            <div className="text-xs opacity-60">score (0–1)</div>
          </div>
        </div>
        <p className="text-xs opacity-80 mt-2 border-t border-current/20 pt-2">{pair.summary}</p>
      </div>

      {/* Article body */}
      <div className="space-y-4">
        {paragraphs.map((para, i) => (
          <p key={i} className="text-gray-300 text-sm leading-relaxed">
            {para}
          </p>
        ))}
      </div>

      {/* Footer */}
      <div className="text-xs text-gray-600 border-t border-gray-800 pt-3">
        Isolated from {data.all_pairs_count} correlation pairs · Most extreme signal today
      </div>
    </div>
  );
}
