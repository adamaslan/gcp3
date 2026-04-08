import Link from "next/link";

const TOOLS = [
  {
    href: "/market-overview",
    title: "Market",
    description: "Morning brief (SPY, QQQ, IWM, DIA), AI summary, news sentiment, and 7-day market history.",
    badge: "AI",
    badgeColor: "bg-blue-600 text-white",
    accent: "hover:border-blue-500",
  },
  {
    href: "/industry-intel",
    title: "Industries",
    description: "50-industry ETF rankings via Finnhub with live price data and momentum metrics.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-purple-500",
  },
  {
    href: "/industry-returns",
    title: "Returns",
    description: "Multi-period ETF returns (1W → 10Y) for 50 industries, sourced from Firestore industry cache.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-violet-500",
  },
  {
    href: "/signals",
    title: "Signals",
    description: "BUY/HOLD/SELL signals from the MCP analysis pipeline, ranked by confidence with bull/bear counts.",
    badge: "AI",
    badgeColor: "bg-cyan-700 text-cyan-100",
    accent: "hover:border-cyan-500",
  },
  {
    href: "/screener",
    title: "Screener",
    description: "40+ large-cap stocks with momentum signals (strong buy → strong sell), breadth %, and AI regime read.",
    badge: "AI",
    badgeColor: "bg-green-700 text-green-100",
    accent: "hover:border-green-500",
  },
  {
    href: "/macro",
    title: "Macro",
    description: "Macro pulse (11 cross-asset indicators, risk regime) and earnings radar (EPS beats/misses, outlook).",
    badge: "AI",
    badgeColor: "bg-orange-700 text-orange-100",
    accent: "hover:border-orange-500",
  },
  {
    href: "/content",
    title: "Content",
    description: "Daily blog insights, blog management, and deep dives into cross-asset correlations.",
    badge: null,
    badgeColor: "",
    accent: "hover:border-blue-500",
  },
];

export default function Home() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Nuwrrrld Financial</h1>
        <p className="mt-2 text-gray-400">{TOOLS.length} free real-time market intelligence tools powered by Finnhub, Gemini AI, and GCP.</p>
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
