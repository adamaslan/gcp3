import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!BACKEND) {
    console.error("[market-summary] BACKEND_URL not set");
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  const daysParam = request.nextUrl.searchParams.get("days");
  if (daysParam && !["7", "14", "30"].includes(daysParam)) {
    return NextResponse.json({ error: "Invalid 'days' parameter. Must be one of 7, 14, 30." }, { status: 400 });
  }
  const days = daysParam ?? "7";

  let res: Response;
  try {
    res = await fetch(`${BACKEND}/market-summary?days=${days}`, { next: { revalidate: 3600 } });
  } catch (err) {
    console.error("[market-summary] Network error:", err);
    return NextResponse.json({ error: "Network error", detail: String(err) }, { status: 503 });
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    console.error(`[market-summary] Backend returned ${res.status}: ${body}`);
    return NextResponse.json({ error: "Backend unavailable", status: res.status, detail: body }, { status: 503 });
  }

  return NextResponse.json(await res.json(), {
    headers: {
      "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=7200",
    },
  });
}
