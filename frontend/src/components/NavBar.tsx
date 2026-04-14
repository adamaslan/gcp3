"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
  { href: "/market-overview", label: "Market" },
  { href: "/industry-intel", label: "Industries" },
  { href: "/industry-returns", label: "Returns" },
  { href: "/signals", label: "Signals" },
  { href: "/screener", label: "Screener" },
  { href: "/macro", label: "Macro" },
  { href: "/content", label: "Content" },
];

export function NavBar() {
  const pathname = usePathname();
  return (
    <nav className="border-b border-gray-800 px-4 sm:px-6 py-0 flex items-center gap-0.5 overflow-x-auto scrollbar-none">
      <Link href="/" className="font-bold text-white mr-3 shrink-0 text-sm py-3">Nuwrrrld</Link>
      {NAV_LINKS.map(({ href, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={`px-3 py-3 text-sm rounded-md transition-colors shrink-0 whitespace-nowrap min-h-[44px] flex items-center ${
              active
                ? "text-white border-b-2 border-blue-500"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
