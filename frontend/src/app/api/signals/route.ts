import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(req: NextRequest): Promise<NextResponse> {
  if (!BACKEND) {
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  const params = new URLSearchParams();
  const symbol = req.nextUrl.searchParams.get("symbol");
  const scope = req.nextUrl.searchParams.get("scope");
  if (symbol) params.set("symbol", symbol);
  if (scope) params.set("scope", scope);

  const url = `${BACKEND}/signals${params.size ? `?${params}` : ""}`;

  let res: Response;
  try {
    res = await fetch(url, { next: { revalidate: 3600 } });
  } catch (err) {
    return NextResponse.json({ error: "Network error reaching backend", detail: String(err) }, { status: 503 });
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    return NextResponse.json({ error: "Backend unavailable", status: res.status, detail: body }, { status: 503 });
  }

  const data = await res.json();
  return NextResponse.json(data, {
    headers: { "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=7200" },
  });
}
