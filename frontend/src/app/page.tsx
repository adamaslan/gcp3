import Link from "next/link";

const TOOLS = [
  {
    href: "/ai-summary",
    title: "AI Market Summary",
    description: "Gemini 2.0 Flash synthesis of 5 live data sources (morning brief, sector rotation, macro pulse, screener, news) into a daily narrative with regime, tone, and leading/lagging sectors.",
    badge: "AI",
    badgeColor: "bg-blue-600 text-white",
    accent: "hover:border-blue-500",
  },
  {
    href: "/morning-brief",
    title: "Morning Brief",
    description: "SPY, QQQ, IWM, DIA — intraday price, change, open, and prior close via Finnhub. Bullish/bearish/neutral tone derived from average index change across the 4 major ETFs.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-indigo-500",
  },
  {
    href: "/industry-tracker",
    title: "Industry Tracker",
    description: "50-industry ETF rankings via Finnhub (yfinance fallback). When Alpha Vantage quota allows, enriched with 1-month cumulative return, mean daily return, and volatility (stddev).",
    badge: null,
    badgeColor: "",
    accent: "hover:border-purple-500",
  },
  {
    href: "/screener",
    title: "Stock Screener",
    description: "40+ large-cap stocks screened via Finnhub concurrent fetch with yfinance bulk fallback. Signals (strong buy → strong sell) from price momentum. Shows breadth % and AI regime read.",
    badge: "AI",
    badgeColor: "bg-green-700 text-green-100",
    accent: "hover:border-green-500",
  },
  {
    href: "/sector-rotation",
    title: "Sector Rotation",
    description: "11 GICS sectors ranked by momentum score (60% change %, 40% intraday position). Gemini 2.0 Flash detects offensive vs defensive rotation; falls back to rule-based when quota is saved.",
    badge: "AI",
    badgeColor: "bg-purple-700 text-purple-100",
    accent: "hover:border-purple-500",
  },
  {
    href: "/earnings-radar",
    title: "Earnings Radar",
    description: "EPS beats and misses for 20+ tracked companies from Finnhub earnings calendar. Beat rate %, top beats/misses, and AI earnings outlook. Cached 6 hours.",
    badge: "AI",
    badgeColor: "bg-yellow-700 text-yellow-100",
    accent: "hover:border-yellow-500",
  },
  {
    href: "/macro-pulse",
    title: "Macro Pulse",
    description: "11 cross-asset indicators: VIX, TLT, IEF, DXY, GLD, USO, HYG, LQD, TIP, PDBC, SHY. Rule-based regime scoring (Risk-On / Risk-Off / Transitional) with per-signal reasoning.",
    badge: "AI",
    badgeColor: "bg-orange-700 text-orange-100",
    accent: "hover:border-orange-500",
  },
  {
    href: "/news-sentiment",
    title: "News Sentiment",
    description: "Finnhub news across 4 categories (general, forex, crypto, merger) scored by keyword frequency. Positive/negative/neutral per headline, plus top movers and overall narrative.",
    badge: "AI",
    badgeColor: "bg-pink-700 text-pink-100",
    accent: "hover:border-pink-500",
  },
  {
    href: "/portfolio-analyzer",
    title: "Portfolio Analyzer",
    description: "Enter any tickers — fetches live quotes, sector/country profile from Finnhub. AI grades diversification (A–D), highlights concentration risk, winners/losers, and industry breakdown.",
    badge: "AI",
    badgeColor: "bg-teal-700 text-teal-100",
    accent: "hover:border-teal-500",
  },
  {
    href: "/technical-signals",
    title: "Technical Signals",
    description: "BUY/HOLD/SELL signals written to Firestore by the external MCP analysis pipeline. Reads the latest snapshot: ranked by signal confidence, with aggregate bull/bear counts.",
    badge: "AI",
    badgeColor: "bg-cyan-700 text-cyan-100",
    accent: "hover:border-cyan-500",
  },
  {
    href: "/industry-returns",
    title: "Industry Returns",
    description: "Multi-period ETF returns (1W → 10Y) for 50 industries, sourced from the Firestore industry_cache collection populated by the MCP pipeline. Sortable by any timeframe.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-violet-500",
  },
  {
    href: "/market-summary",
    title: "Market Summary",
    description: "7-day rolling trend from the AI signal pipeline stored in Firestore: daily bullish/bearish totals, average sentiment score, top conviction picks, and regime trend direction.",
    badge: "AI",
    badgeColor: "bg-rose-700 text-rose-100",
    accent: "hover:border-rose-500",
  },
  {
    href: "/daily-blog",
    title: "Daily Blog",
    description: "Daily insights and longer-form market analysis capturing the broader narrative.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-blue-500",
  },
  {
    href: "/blog-review",
    title: "Blog Review",
    description: "Review and manage daily blog entries or historical posts.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-amber-500",
  },
  {
    href: "/correlation-article",
    title: "Correlation Article",
    description: "Deep dive into cross-asset correlations and unearthing hidden market relationships.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-purple-500",
  },
];

export default function Home() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">GCP3 Finance</h1>
        <p className="mt-2 text-gray-400">{TOOLS.length} real-time market intelligence tools powered by GCP + Claude AI.</p>
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
        <span>{TOOLS.length} endpoints</span>
        <span>·</span>
        <span>Finnhub + yfinance + Alpha Vantage</span>
        <span>·</span>
        <span>Gemini 2.0 Flash</span>
        <span>·</span>
        <span>Firestore cache</span>
        <span>·</span>
        <span>Cloud Run</span>
      </div>
    </div>
  );
}
