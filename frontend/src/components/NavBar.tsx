"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
  { href: "/ai-summary", label: "AI Summary" },
  { href: "/morning-brief", label: "Morning Brief" },
  { href: "/industry-tracker", label: "Industries" },
  { href: "/screener", label: "Screener" },
  { href: "/sector-rotation", label: "Sectors" },
  { href: "/earnings-radar", label: "Earnings" },
  { href: "/macro-pulse", label: "Macro" },
  { href: "/news-sentiment", label: "News" },
  { href: "/portfolio-analyzer", label: "Portfolio" },
  { href: "/technical-signals", label: "Signals" },
  { href: "/industry-returns", label: "Returns" },
  { href: "/market-summary", label: "Mkt Summary" },
  { href: "/correlation-article", label: "Correlations" },
];

export function NavBar() {
  const pathname = usePathname();
  return (
    <nav className="border-b border-gray-800 px-6 py-2 flex items-center gap-1 overflow-x-auto">
      <Link href="/" className="font-bold text-white mr-4 shrink-0 text-sm">GCP3</Link>
      {NAV_LINKS.map(({ href, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors shrink-0 whitespace-nowrap ${
              active
                ? "bg-gray-700 text-white"
                : "text-gray-400 hover:text-white hover:bg-gray-800"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
