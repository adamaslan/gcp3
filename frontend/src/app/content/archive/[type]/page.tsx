import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

const ARTICLE_TYPES = {
  story: {
    label: "Story",
    description: "Single extreme-pair correlation deep-dive",
    backendType: "story",
    gradient: "from-purple-700 via-pink-700 to-rose-700",
    accent: "purple",
    icon: "📖",
  },
  blog: {
    label: "Daily Blog",
    description: "Themed daily blog post",
    backendType: "blog",
    gradient: "from-blue-700 via-cyan-700 to-teal-700",
    accent: "blue",
    icon: "📰",
  },
  correlation: {
    label: "Correlation",
    description: "Cross-asset correlation analysis",
    backendType: "correlation",
    gradient: "from-emerald-700 via-green-700 to-lime-700",
    accent: "emerald",
    icon: "🔗",
  },
  review: {
    label: "Blog Review",
    description: "Self-review and improvement suggestions",
    backendType: "review",
    gradient: "from-orange-700 via-amber-700 to-yellow-700",
    accent: "orange",
    icon: "✍️",
  },
  morning: {
    label: "Morning Brief",
    description: "Pre-open market tone snapshot",
    backendType: null,
    gradient: "from-fuchsia-700 via-purple-700 to-indigo-700",
    accent: "fuchsia",
    icon: "☀️",
  },
  macro: {
    label: "Macro Pulse",
    description: "AI macro regime summary",
    backendType: null,
    gradient: "from-rose-700 via-pink-700 to-fuchsia-700",
    accent: "rose",
    icon: "🌐",
  },
  "ai-summary": {
    label: "AI Summary",
    description: "Daily AI-written market brief",
    backendType: null,
    gradient: "from-sky-700 via-blue-700 to-indigo-700",
    accent: "sky",
    icon: "🤖",
  },
} as const;

type TypeId = keyof typeof ARTICLE_TYPES;

const TYPE_IDS = Object.keys(ARTICLE_TYPES) as TypeId[];

export async function generateMetadata({
  params,
}: {
  params: Promise<{ type: string }>;
}): Promise<Metadata> {
  const { type } = await params;
  const meta = ARTICLE_TYPES[type as TypeId];
  if (!meta) return { title: "Not found" };
  return {
    title: `${meta.label} Archive`,
    description: meta.description,
  };
}

async function fetchTodayArticle(typeId: TypeId): Promise<unknown | null> {
  const meta = ARTICLE_TYPES[typeId];
  if (!meta.backendType) return null;
  const base = process.env.BACKEND_URL;
  if (!base) return null;
  try {
    const res = await fetch(`${base}/content?type=${meta.backendType}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function formatDate(d: string | undefined): string {
  if (!d) return "";
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return d;
  return dt.toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function StructuredFields({
  data,
  exclude,
}: {
  data: Record<string, unknown>;
  exclude: Set<string>;
}) {
  const fields = Object.entries(data).filter(
    ([k, v]) =>
      !exclude.has(k) &&
      v != null &&
      v !== "" &&
      (typeof v !== "object" ||
        (Array.isArray(v) ? v.length : Object.keys(v).length)),
  );
  if (fields.length === 0) return null;
  return (
    <dl className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
      {fields.map(([k, v]) => (
        <div
          key={k}
          className="rounded-xl border border-gray-800 bg-gray-900/60 p-4"
        >
          <dt className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-1">
            {k.replace(/_/g, " ")}
          </dt>
          <dd className="text-sm text-gray-200 break-words">
            {typeof v === "string" || typeof v === "number" ? (
              String(v)
            ) : (
              <pre className="whitespace-pre-wrap font-mono text-[11px] text-gray-300 max-h-48 overflow-auto">
                {JSON.stringify(v, null, 2)}
              </pre>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default async function ArchiveTypePage({
  params,
}: {
  params: Promise<{ type: string }>;
}) {
  const { type } = await params;
  const meta = ARTICLE_TYPES[type as TypeId];
  if (!meta) notFound();

  const article = (await fetchTodayArticle(type as TypeId)) as
    | Record<string, unknown>
    | null;

  const title =
    (article?.title as string | undefined) ||
    (article?.blog_title as string | undefined) ||
    meta.label;
  const body =
    (article?.body as string | undefined) ||
    (article?.summary as string | undefined) ||
    (article?.brief as string | undefined) ||
    (article?.ai_summary as string | undefined) ||
    "";
  const dateStr = (article?.date as string | undefined) ?? "";

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950">
      <header className="relative overflow-hidden border-b border-gray-800">
        <div className={`absolute inset-0 bg-gradient-to-br ${meta.gradient}`} />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.2),transparent_60%)]" />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 py-12 sm:py-16 text-white">
          <Link
            href="/content/archive"
            className="inline-flex items-center gap-2 text-sm font-medium text-white/80 hover:text-white mb-6 transition-colors"
          >
            ← All article types
          </Link>
          <div className="flex items-center gap-3 mb-3">
            <span className="text-3xl">{meta.icon}</span>
            <span className="rounded-full bg-white/15 backdrop-blur px-3 py-1 text-xs font-bold uppercase tracking-widest">
              {meta.label}
            </span>
            {dateStr && (
              <time className="text-xs font-medium opacity-90">
                {formatDate(dateStr)}
              </time>
            )}
          </div>
          <h1 className="text-3xl sm:text-5xl font-black leading-tight tracking-tight drop-shadow">
            {title}
          </h1>
          <p className="mt-4 text-sm sm:text-base opacity-90">
            {meta.description}
          </p>
        </div>
      </header>

      <nav className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 sm:px-6">
          <div className="flex gap-1 overflow-x-auto py-3">
            {TYPE_IDS.map((id) => {
              const t = ARTICLE_TYPES[id];
              const active = id === type;
              return (
                <Link
                  key={id}
                  href={`/content/archive/${id}`}
                  className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
                    active
                      ? "bg-white text-gray-900 shadow-md"
                      : "text-gray-400 hover:text-white hover:bg-white/5"
                  }`}
                >
                  {t.label}
                </Link>
              );
            })}
          </div>
        </div>
      </nav>

      <section className="max-w-4xl mx-auto px-4 sm:px-6 py-10 sm:py-14">
        {!article ? (
          <div className="rounded-2xl border-2 border-dashed border-gray-700 bg-gray-900/40 p-12 text-center">
            <div className="text-5xl mb-4">📭</div>
            <h2 className="text-xl font-bold text-white mb-2">
              {meta.backendType
                ? `No ${meta.label.toLowerCase()} for today`
                : `${meta.label} archive coming soon`}
            </h2>
            <p className="text-gray-400">
              {meta.backendType
                ? "The pipeline hasn't generated this article today, or the backend is unreachable."
                : "This article type is not yet exposed via the /content endpoint. Wire it up in the backend to enable browsing."}
            </p>
          </div>
        ) : (
          <>
            <article className="rounded-2xl bg-gray-900/60 border border-gray-800 p-6 sm:p-10">
              {body ? (
                <div className="prose prose-invert prose-lg max-w-none">
                  {body.split(/\n{2,}/).map((para, i) => (
                    <p key={i} className="text-gray-200">
                      {para.trim()}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500 italic">
                  No prose body — see structured fields below.
                </p>
              )}
            </article>

            <details className="mt-8 rounded-xl border border-gray-800 bg-gray-900/40 p-4">
              <summary className="cursor-pointer text-sm font-bold text-gray-300">
                Show structured fields ({Object.keys(article).length})
              </summary>
              <StructuredFields
                data={article}
                exclude={
                  new Set([
                    "title",
                    "body",
                    "summary",
                    "slug",
                    "date",
                    "blog_title",
                  ])
                }
              />
            </details>
          </>
        )}
      </section>
    </div>
  );
}
