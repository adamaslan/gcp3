import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(request: NextRequest): Promise<NextResponse> {
  const symbol = request.nextUrl.searchParams.get("symbol");
  const url = symbol
    ? `${BACKEND}/technical-signals?symbol=${encodeURIComponent(symbol)}`
    : `${BACKEND}/technical-signals`;

  if (!BACKEND) {
    console.error("[technical-signals] BACKEND_URL not set");
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  let res: Response;
  try {
    res = await fetch(url, { next: { revalidate: 7200 } });
  } catch (err) {
    console.error("[technical-signals] Network error:", err);
    return NextResponse.json({ error: "Network error", detail: String(err) }, { status: 503 });
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    console.error(`[technical-signals] Backend returned ${res.status}: ${body}`);
    return NextResponse.json({ error: "Backend unavailable", status: res.status, detail: body }, { status: 503 });
  }

  return NextResponse.json(await res.json(), {
    headers: {
      "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=7200",
    },
  });
}
