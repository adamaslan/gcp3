"use client";
import { useState } from "react";

interface Article {
  id?: number;
  headline: string;
  source?: string;
  url?: string;
  datetime?: number;
  category: string;
  sentiment: string;
  score: number;
}

interface NewsData {
  date: string;
  total_articles: number;
  by_category: Record<string, Article[]>;
  avg_sentiment_score: number;
  overall_sentiment: string;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  most_positive: Article[];
  most_negative: Article[];
  ai_narrative: string;
}

const SENTIMENT_BADGE: Record<string, string> = {
  positive: "bg-green-900 text-green-300",
  negative: "bg-red-900 text-red-300",
  neutral: "bg-gray-800 text-gray-400",
};

const OVERALL_STYLE: Record<string, string> = {
  positive: "text-green-400 border-green-700 bg-green-950/20",
  negative: "text-red-400 border-red-700 bg-red-950/20",
  neutral: "text-yellow-400 border-yellow-700 bg-yellow-950/20",
};

function ArticleRow({ a }: { a: Article }) {
  const ts = a.datetime ? new Date(a.datetime * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
  return (
    <div className="py-2.5 border-t border-gray-800/60 first:border-0">
      <div className="flex justify-between items-start gap-2">
        <p className="text-sm text-gray-200 flex-1 leading-snug">{a.headline}</p>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${SENTIMENT_BADGE[a.sentiment]}`}>
          {a.sentiment}
        </span>
      </div>
      <div className="flex gap-3 mt-1">
        {a.source && <span className="text-xs text-gray-600">{a.source}</span>}
        {ts && <span className="text-xs text-gray-700">{ts}</span>}
      </div>
    </div>
  );
}

export function NewsSentiment({ data }: { data: NewsData }) {
  const [activeTab, setActiveTab] = useState<string>("general");
  const tabs = Object.keys(data.by_category);
  const overallStyle = OVERALL_STYLE[data.overall_sentiment] ?? OVERALL_STYLE.neutral;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">News Sentiment</h1>
        <p className="text-sm text-gray-500 mt-0.5">{data.total_articles} articles analyzed · {data.date}</p>
      </div>

      {/* Overall sentiment */}
      <div className={`p-5 rounded-xl border ${overallStyle}`}>
        <div className="flex items-center gap-3 mb-2">
          <span className="text-lg font-bold capitalize">{data.overall_sentiment}</span>
          <span className="text-sm opacity-75">
            avg score: {data.avg_sentiment_score > 0 ? "+" : ""}{data.avg_sentiment_score.toFixed(3)}
          </span>
        </div>
        <p className="text-sm opacity-90">{data.ai_narrative}</p>
        <div className="flex gap-4 mt-3 text-xs">
          <span className="text-green-400">● {data.positive_count} positive</span>
          <span className="text-red-400">● {data.negative_count} negative</span>
          <span className="text-gray-500">● {data.neutral_count} neutral</span>
        </div>
      </div>

      {/* Category tabs */}
      <div className="flex gap-1 bg-gray-900 rounded-lg p-1 w-fit">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors capitalize ${
              activeTab === t ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Articles */}
      <div className="rounded-xl border border-gray-800 px-4 py-2">
        {(data.by_category[activeTab] ?? []).map((a, i) => (
          <ArticleRow key={a.id ?? i} a={a} />
        ))}
      </div>
    </div>
  );
}
