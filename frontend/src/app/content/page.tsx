import Link from "next/link";
import { DailyBlog } from "@/components/DailyBlog";
import { BlogReview } from "@/components/BlogReview";
import { CorrelationArticle } from "@/components/CorrelationArticle";

export const revalidate = 14400;

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

  const tabs = ["blog", "review", "correlation"] as const;
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
          {activeTab === "blog" && data.blog && !data.blog.error && (
            <DailyBlog data={data.blog} />
          )}
          {activeTab === "review" && data.review && !data.review.error && (
            <BlogReview data={data.review} />
          )}
          {activeTab === "correlation" && data.correlation && !data.correlation.error && (
            <CorrelationArticle data={data.correlation} />
          )}
        </>
      )}
    </div>
  );
}
