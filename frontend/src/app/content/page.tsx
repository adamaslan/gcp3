import type { Metadata } from "next";
import Link from "next/link";
import { DailyBlog } from "@/components/DailyBlog";
import { BlogReview } from "@/components/BlogReview";
import { CorrelationArticle } from "@/components/CorrelationArticle";
import { StoryArticle } from "@/components/StoryArticle";
import { buildOgImageUrl } from "@/lib/og";

export const revalidate = 14400;

export const metadata: Metadata = {
  title: "Content",
  description: "Daily blog insights, AI-written market stories, cross-asset correlation deep dives, and blog review — updated throughout the trading day.",
  openGraph: {
    title: "Content | Nuwrrrld Financial",
    description: "Daily blog · AI market stories · Cross-asset correlations · Blog review.",
    images: [
      {
        url: buildOgImageUrl("Market Content", "Daily blog · AI market stories · Cross-asset correlations"),
        width: 1200,
        height: 630,
        alt: "Content — Nuwrrrld Financial",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Content | Nuwrrrld Financial",
    description: "Daily blog · AI market stories · Cross-asset correlations · Blog review.",
    images: [buildOgImageUrl("Market Content", "Daily blog · AI market stories · Cross-asset correlations")],
  },
};

async function getData() {
  const base = process.env.BACKEND_URL;
  if (!base) return null;
  try {
    const res = await fetch(`${base}/content`, { next: { revalidate: 14400 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function ContentPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;
  const data = await getData();

  const tabs = ["blog", "review", "correlation", "story"] as const;
  type Tab = (typeof tabs)[number];
  const activeTab: Tab = tabs.includes(tab as Tab) ? (tab as Tab) : "blog";

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-white mb-6">Content</h1>

      <div className="flex gap-2 mb-6 border-b border-gray-700">
        {(
          [
            { id: "blog", label: "Blog" },
            { id: "review", label: "Review" },
            { id: "correlation", label: "Correlations" },
            { id: "story", label: "Story" },
          ] as { id: Tab; label: string }[]
        ).map(({ id, label }) => (
          <Link
            key={id}
            href={`?tab=${id}`}
            className={`px-4 py-2 text-sm font-medium rounded-t-md transition-colors ${
              activeTab === id
                ? "bg-gray-700 text-white border-b-2 border-blue-500"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {label}
          </Link>
        ))}
      </div>

      {!data ? (
        <div className="h-64 bg-gray-800 rounded animate-pulse" />
      ) : (
        <>
          {activeTab === "blog" && (
            data.blog?.error
              ? <div className="p-6 rounded-xl border border-yellow-800/40 bg-yellow-950/10 text-yellow-400 text-sm">Blog generation temporarily unavailable — AI writer hit a rate limit. Check back soon.</div>
              : data.blog && <DailyBlog data={data.blog} />
          )}
          {activeTab === "review" && (
            data.review?.error
              ? <div className="p-6 rounded-xl border border-yellow-800/40 bg-yellow-950/10 text-yellow-400 text-sm">{data.review.error}</div>
              : data.review && <BlogReview data={data.review} />
          )}
          {activeTab === "correlation" && (
            data.correlation?.error
              ? <div className="p-6 rounded-xl border border-yellow-800/40 bg-yellow-950/10 text-yellow-400 text-sm">Correlation analysis temporarily unavailable — AI writer hit a rate limit. Check back soon.</div>
              : data.correlation && <CorrelationArticle data={data.correlation} />
          )}
          {activeTab === "story" && (
            data.story?.error
              ? <div className="p-6 rounded-xl border border-yellow-800/40 bg-yellow-950/10 text-yellow-400 text-sm">Story generation temporarily unavailable. Check back soon.</div>
              : data.story && <StoryArticle data={data.story} />
          )}
        </>
      )}
    </div>
  );
}
