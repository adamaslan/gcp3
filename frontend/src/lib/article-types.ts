// Shared article-type configuration used by /content/archive and
// /content/archive/[type]. Single source of truth — adding a type here
// surfaces it on both pages.

export type ArticleTypeId =
  | "story"
  | "blog"
  | "correlation"
  | "review"
  | "morning"
  | "macro"
  | "ai-summary";

export interface ArticleTypeConfig {
  id: ArticleTypeId;
  label: string;
  description: string;
  /** Backend `?type=` value, or null if not yet exposed via /content. */
  backendType: string | null;
  /** Tailwind gradient class fragment, e.g. "from-purple-600 via-pink-600 to-rose-600". */
  gradient: string;
  icon: string;
}

export const ARTICLE_TYPES: readonly ArticleTypeConfig[] = [
  {
    id: "story",
    label: "Story",
    description: "Single extreme-pair correlation deep-dive",
    backendType: "story",
    gradient: "from-purple-600 via-pink-600 to-rose-600",
    icon: "📖",
  },
  {
    id: "blog",
    label: "Daily Blog",
    description: "Themed daily blog post on a market topic",
    backendType: "blog",
    gradient: "from-blue-600 via-cyan-600 to-teal-600",
    icon: "📰",
  },
  {
    id: "correlation",
    label: "Correlation",
    description: "Cross-asset correlation analysis with news context",
    backendType: "correlation",
    gradient: "from-emerald-600 via-green-600 to-lime-600",
    icon: "🔗",
  },
  {
    id: "review",
    label: "Blog Review",
    description: "Self-review and improvement suggestions",
    backendType: "review",
    gradient: "from-orange-600 via-amber-600 to-yellow-600",
    icon: "✍️",
  },
  {
    id: "morning",
    label: "Morning Brief",
    description: "Pre-open market tone and indices snapshot",
    backendType: null,
    gradient: "from-fuchsia-600 via-purple-600 to-indigo-600",
    icon: "☀️",
  },
  {
    id: "macro",
    label: "Macro Pulse",
    description: "AI macro regime and indicator summary",
    backendType: null,
    gradient: "from-rose-600 via-pink-600 to-fuchsia-600",
    icon: "🌐",
  },
  {
    id: "ai-summary",
    label: "AI Summary",
    description: "Daily AI-written market brief",
    backendType: null,
    gradient: "from-sky-600 via-blue-600 to-indigo-600",
    icon: "🤖",
  },
] as const;

export function findArticleType(id: string): ArticleTypeConfig | undefined {
  return ARTICLE_TYPES.find((t) => t.id === id);
}
