import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(request: NextRequest): Promise<NextResponse> {
  const tickers = request.nextUrl.searchParams.get("tickers");
  const backendUrl = tickers
    ? `${BACKEND}/portfolio-analyzer?tickers=${encodeURIComponent(tickers)}`
    : `${BACKEND}/portfolio-analyzer`;

  console.log("[portfolio-analyzer] Fetching from backend:", backendUrl);

  if (!BACKEND) {
    console.error("[portfolio-analyzer] BACKEND_URL env var is not set");
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  let res: Response;
  try {
    res = await fetch(backendUrl, { cache: "no-store" });
  } catch (err) {
    console.error("[portfolio-analyzer] Network error:", err);
    return NextResponse.json({ error: "Network error reaching backend", detail: String(err) }, { status: 503 });
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    console.error(`[portfolio-analyzer] Backend returned ${res.status}: ${body}`);
    return NextResponse.json({ error: "Backend unavailable", status: res.status, detail: body }, { status: 503 });
  }

  const data = await res.json();
  return NextResponse.json(data);
}
