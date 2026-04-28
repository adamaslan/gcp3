import type { Metadata } from "next";
import Link from "next/link";
import { ARTICLE_TYPES } from "@/lib/article-types";

export const revalidate = 14400;

export const metadata: Metadata = {
  title: "Content Archive",
  description:
    "Browse daily AI-generated market articles by type — story, blog, correlation, review, morning, macro, and AI summary.",
};

export default function ContentArchiveHub() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950">
      <header className="relative overflow-hidden border-b border-gray-800">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-900 via-purple-900 to-pink-900 opacity-50" />
        <div className="absolute inset-0 opacity-30 bg-[radial-gradient(circle_at_20%_20%,rgba(139,92,246,0.4),transparent_50%),radial-gradient(circle_at_80%_60%,rgba(236,72,153,0.3),transparent_50%)]" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 py-12 sm:py-16 text-white">
          <Link
            href="/content"
            className="inline-flex items-center gap-2 text-sm font-medium text-gray-300 hover:text-white mb-6 transition-colors"
          >
            ← Latest content
          </Link>
          <div className="flex items-center gap-3 mb-3">
            <span className="text-3xl sm:text-4xl">📚</span>
            <span className="rounded-full bg-white/10 backdrop-blur border border-white/20 px-3 py-1 text-xs font-bold uppercase tracking-widest">
              Daily Series
            </span>
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black leading-tight tracking-tight">
            Content Archive
          </h1>
          <p className="mt-4 text-base sm:text-lg max-w-2xl text-gray-300">
            Seven independent AI pipelines write fresh market analysis every
            trading day. Pick a flavor.
          </p>
        </div>
      </header>

      <section className="max-w-7xl mx-auto px-4 sm:px-6 py-10 sm:py-14">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {ARTICLE_TYPES.map((t) => (
            <Link
              key={t.id}
              href={`/content/archive/${t.id}`}
              className="group relative overflow-hidden rounded-2xl border border-gray-800 hover:border-gray-700 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl"
            >
              <div className={`absolute inset-0 bg-gradient-to-br ${t.gradient} opacity-90`} />
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.2),transparent_60%)]" />
              <div className="relative p-6 text-white min-h-[200px] flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-3xl">{t.icon}</span>
                    <span className="rounded-full bg-white/15 backdrop-blur px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest">
                      {t.id}
                    </span>
                  </div>
                  <h2 className="text-2xl font-extrabold mb-2">{t.label}</h2>
                  <p className="text-sm opacity-90">{t.description}</p>
                </div>
                <div className="mt-4 inline-flex items-center gap-2 text-sm font-bold">
                  Browse
                  <span className="transition-transform group-hover:translate-x-1">
                    →
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
