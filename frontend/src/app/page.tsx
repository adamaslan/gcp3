import Link from "next/link";

const TOOLS = [
  {
    href: "/ai-summary",
    title: "AI Market Summary",
    description: "Claude-powered synthesis of all data sources into a daily market brief.",
    badge: "AI",
    badgeColor: "bg-blue-600 text-white",
    accent: "hover:border-blue-500",
  },
  {
    href: "/morning-brief",
    title: "Morning Brief",
    description: "Daily market tone, major index performance, and overall summary.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-indigo-500",
  },
  {
    href: "/industry-tracker",
    title: "Industry Tracker",
    description: "50-industry ETF performance rankings. Leaders, laggards, and daily change.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-purple-500",
  },
  {
    href: "/screener",
    title: "Stock Screener",
    description: "40+ large-cap movers ranked by signal strength: strong buy to strong sell.",
    badge: "AI",
    badgeColor: "bg-green-700 text-green-100",
    accent: "hover:border-green-500",
  },
  {
    href: "/sector-rotation",
    title: "Sector Rotation",
    description: "11 GICS sector momentum scores + AI regime detection (offensive vs defensive).",
    badge: "AI",
    badgeColor: "bg-purple-700 text-purple-100",
    accent: "hover:border-purple-500",
  },
  {
    href: "/earnings-radar",
    title: "Earnings Radar",
    description: "EPS beats and misses for 20+ tracked companies with AI earnings outlook.",
    badge: "AI",
    badgeColor: "bg-yellow-700 text-yellow-100",
    accent: "hover:border-yellow-500",
  },
  {
    href: "/macro-pulse",
    title: "Macro Pulse",
    description: "VIX, bonds, dollar, gold, oil, credit — cross-asset macro regime signal.",
    badge: "AI",
    badgeColor: "bg-orange-700 text-orange-100",
    accent: "hover:border-orange-500",
  },
  {
    href: "/news-sentiment",
    title: "News Sentiment",
    description: "Real-time market news scored for positive/negative sentiment by AI.",
    badge: "AI",
    badgeColor: "bg-pink-700 text-pink-100",
    accent: "hover:border-pink-500",
  },
  {
    href: "/portfolio-analyzer",
    title: "Portfolio Analyzer",
    description: "Enter any tickers — get live data, diversification grade, and AI insights.",
    badge: "AI",
    badgeColor: "bg-teal-700 text-teal-100",
    accent: "hover:border-teal-500",
  },
  {
    href: "/technical-signals",
    title: "Technical Signals",
    description: "AI-ranked BUY/HOLD/SELL signals from MACD, RSI, ADX across tracked tickers.",
    badge: "AI",
    badgeColor: "bg-cyan-700 text-cyan-100",
    accent: "hover:border-cyan-500",
  },
  {
    href: "/industry-returns",
    title: "Industry Returns",
    description: "Multi-period ETF returns (1W–5Y) across 50 industries, sortable by timeframe.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-violet-500",
  },
  {
    href: "/market-summary",
    title: "Market Summary",
    description: "7-day trend from AI signal pipeline — regime, top bullish/bearish, high confidence.",
    badge: "AI",
    badgeColor: "bg-rose-700 text-rose-100",
    accent: "hover:border-rose-500",
  },
];

export default function Home() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">GCP3 Finance</h1>
        <p className="mt-2 text-gray-400">12 real-time market intelligence tools powered by GCP + Claude AI.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {TOOLS.map((tool) => (
          <Link
            key={tool.href}
            href={tool.href}
            className={`block p-6 rounded-xl border border-gray-800 ${tool.accent} transition-colors`}
          >
            <div className="flex items-start justify-between mb-2">
              <h2 className="text-base font-semibold text-white">{tool.title}</h2>
              {tool.badge && (
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${tool.badgeColor}`}>
                  {tool.badge}
                </span>
              )}
            </div>
            <p className="text-sm text-gray-400 leading-relaxed">{tool.description}</p>
          </Link>
        ))}
      </div>

      <div className="border-t border-gray-800 pt-6 flex flex-wrap items-center gap-4 text-xs text-gray-600">
        <span>12 MCP tools</span>
        <span>·</span>
        <span>Finnhub market data</span>
        <span>·</span>
        <span>Claude claude-sonnet-4-6 AI</span>
        <span>·</span>
        <span>Firestore cache</span>
        <span>·</span>
        <span>Cloud Run</span>
      </div>
    </div>
  );
}
