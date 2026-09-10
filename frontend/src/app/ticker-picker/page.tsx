"use client";

import { useState, useCallback } from "react";

// ─── Tool definitions ────────────────────────────────────────────────────────

interface Tool {
  id: string;
  label: string;
  description: string;
  buildUrl: (ticker: string) => string;
  method?: "GET" | "POST";
  body?: (ticker: string) => unknown;
}

const TOOLS: Tool[] = [
  {
    id: "signals",
    label: "Signals",
    description: "1D/5D/1M/3M/6M/1Y BUY·SELL·HOLD signals",
    buildUrl: (t) => `/api/proxy?path=${encodeURIComponent(`/signals/${t}`)}`,
  },
  {
    id: "signals_scope",
    label: "Signals (all scopes)",
    description: "All signals via ?symbol= param",
    buildUrl: (t) => `/api/proxy?path=${encodeURIComponent(`/signals?symbol=${t}`)}`,
  },
  {
    id: "swing",
    label: "Swing Agent",
    description: "Run swing agent for ticker",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/agents/swing/run")}`,
    method: "POST",
    body: (t) => ({ candidates: [t], mode: "manual", include_llm: false }),
  },
  {
    id: "growth",
    label: "Growth Agent",
    description: "Run growth agent for ticker",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/agents/growth/run")}`,
    method: "POST",
    body: (t) => ({ candidates: [t], mode: "manual", include_llm: false }),
  },
  {
    id: "swing_llm",
    label: "Swing + LLM",
    description: "Swing agent with AI commentary on",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/agents/swing/run")}`,
    method: "POST",
    body: (t) => ({ candidates: [t], mode: "manual", include_llm: true }),
  },
  {
    id: "screener",
    label: "Screener",
    description: "Full screener (all tickers)",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/screener")}`,
  },
  {
    id: "swing_predictions",
    label: "Swing Predictions",
    description: "Swing predictions (sp500 universe)",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/swing-predictions?universe=sp500&top_n=10")}`,
  },
  {
    id: "market_overview",
    label: "Market Overview",
    description: "SPY/QQQ/VIX/breadth snapshot",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/market-overview")}`,
  },
  {
    id: "earnings_radar",
    label: "Earnings Radar",
    description: "Upcoming earnings + estimates",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/earnings-radar")}`,
  },
  {
    id: "macro_pulse",
    label: "Macro Pulse",
    description: "Fed, yields, CPI, DXY indicators",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/macro-pulse")}`,
  },
  {
    id: "industry_intel",
    label: "Industry Intel",
    description: "50-industry ETF tracker",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/industry-intel")}`,
  },
  {
    id: "industry_returns",
    label: "Industry Returns",
    description: "1W / 1M / 3M industry return ranks",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/industry-returns")}`,
  },
  {
    id: "debug_costs",
    label: "Debug: Costs",
    description: "LLM token spend by endpoint",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/debug/costs")}`,
  },
  {
    id: "debug_status",
    label: "Debug: Status",
    description: "Cache and data freshness status",
    buildUrl: () => `/api/proxy?path=${encodeURIComponent("/debug/status")}`,
  },
];

// ─── Quick-pick chips ─────────────────────────────────────────────────────────

const QUICK_PICKS = [
  "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD",
  "NFLX", "PLTR", "CRWD", "COIN", "SPY", "QQQ",
  "JPM", "AVGO", "QCOM", "ANET", "MCHP", "TMO", "WMT",
];

// ─── Helper: pretty-print JSON with colour ─────────────────────────────────────

function JsonView({ data }: { data: unknown }) {
  const text = JSON.stringify(data, null, 2);
  return (
    <pre className="text-xs font-mono text-green-300 whitespace-pre-wrap break-all leading-relaxed overflow-auto max-h-[60vh]">
      {text}
    </pre>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

interface RunResult {
  toolId: string;
  ticker: string;
  status: number;
  data: unknown;
  ms: number;
}

export default function TickerPickerPage() {
  const [ticker, setTicker] = useState("AAPL");
  const [customInput, setCustomInput] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);

  const activeTicker = (customInput.trim().toUpperCase() || ticker).split(/[\s,]+/)[0] ?? "AAPL";

  const runTool = useCallback(async (tool: Tool) => {
    setRunning(tool.id);
    setResult(null);
    const t0 = Date.now();
    try {
      const url = tool.buildUrl(activeTicker);
      const opts: RequestInit = tool.method === "POST"
        ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(tool.body!(activeTicker)) }
        : {};
      const res = await fetch(url, opts);
      const data = await res.json().catch(() => null);
      setResult({ toolId: tool.id, ticker: activeTicker, status: res.status, data, ms: Date.now() - t0 });
    } catch (err) {
      setResult({ toolId: tool.id, ticker: activeTicker, status: 0, data: { error: String(err) }, ms: Date.now() - t0 });
    } finally {
      setRunning(null);
    }
  }, [activeTicker]);

  return (
    <div className="flex gap-4 min-h-screen" style={{ maxWidth: "100%" }}>

      {/* ── Left panel ───────────────────────────────────────────────── */}
      <div className="w-72 shrink-0 space-y-4">

        {/* Ticker selector */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
          <p className="text-xs text-blue-400 font-semibold uppercase tracking-widest mb-2">Active Ticker</p>

          {/* Type-in */}
          <input
            type="text"
            value={customInput}
            onChange={(e) => setCustomInput(e.target.value.toUpperCase())}
            placeholder="Type ticker…"
            className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-1.5 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 mb-2"
          />

          {/* Quick picks */}
          <div className="flex flex-wrap gap-1.5">
            {QUICK_PICKS.map((t) => (
              <button
                key={t}
                onClick={() => { setCustomInput(""); setTicker(t); }}
                className={`px-2 py-0.5 rounded text-xs font-mono border transition-colors ${
                  activeTicker === t
                    ? "bg-blue-900 border-blue-500 text-blue-200"
                    : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white hover:border-gray-500"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="mt-2 text-center">
            <span className="text-lg font-bold text-white font-mono">{activeTicker}</span>
          </div>
        </div>

        {/* Tool list */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-3 space-y-1">
          <p className="text-xs text-blue-400 font-semibold uppercase tracking-widest mb-2">Tools</p>
          {TOOLS.map((tool) => (
            <button
              key={tool.id}
              onClick={() => runTool(tool)}
              disabled={running === tool.id}
              className={`w-full text-left px-3 py-2 rounded text-sm transition-colors border ${
                result?.toolId === tool.id
                  ? "bg-blue-950 border-blue-700 text-blue-200"
                  : "bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700 hover:text-white"
              } ${running === tool.id ? "opacity-50 cursor-wait" : ""}`}
            >
              <div className="font-semibold text-xs">
                {running === tool.id ? "⟳ " : ""}{tool.label}
                {tool.method === "POST" && <span className="ml-1 text-yellow-600 font-mono text-xs">POST</span>}
              </div>
              <div className="text-gray-500 text-xs mt-0.5 leading-tight">{tool.description}</div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Right panel: result ───────────────────────────────────────── */}
      <div className="flex-1 min-w-0">
        {!result && !running && (
          <div className="h-full flex items-center justify-center text-gray-600 text-sm">
            Pick a ticker · click a tool
          </div>
        )}

        {running && (
          <div className="flex items-center gap-2 text-gray-400 text-sm p-4 animate-pulse">
            <span className="text-lg">⟳</span>
            Running <strong className="text-white">{TOOLS.find(t => t.id === running)?.label}</strong> for <strong className="text-blue-400">{activeTicker}</strong>…
          </div>
        )}

        {result && (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
            {/* Header bar */}
            <div className="flex items-center gap-3 flex-wrap">
              <span className="font-bold text-white font-mono">{result.ticker}</span>
              <span className="text-blue-400 text-sm">{TOOLS.find(t => t.id === result.toolId)?.label}</span>
              <span className={`text-xs px-2 py-0.5 rounded font-mono ${result.status >= 200 && result.status < 300 ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>
                {result.status || "ERR"}
              </span>
              <span className="text-gray-500 text-xs">{result.ms}ms</span>
              <button
                onClick={() => navigator.clipboard.writeText(JSON.stringify(result.data, null, 2))}
                className="ml-auto text-xs px-2 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded border border-gray-700"
              >
                Copy JSON
              </button>
            </div>

            {/* JSON output */}
            <div className="bg-gray-950 rounded p-3 border border-gray-800">
              <JsonView data={result.data} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
