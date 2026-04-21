const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://nuwrrrld.com";

export function buildOgImageUrl(title: string, description: string): string {
  const base = `${siteUrl}/api/og`;
  const params = new URLSearchParams({ title, description, domain: "nuwrrrld.com" });
  return `${base}?${params.toString()}`;
}
