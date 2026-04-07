import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(): Promise<NextResponse> {
  console.log("[screener] Fetching from backend:", BACKEND);

  if (!BACKEND) {
    console.error("[screener] BACKEND_URL env var is not set");
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  let res: Response;
  try {
    res = await fetch(`${BACKEND}/screener`, { next: { revalidate: 3600 } });
  } catch (err) {
    console.error("[screener] Network error reaching backend:", err);
    return NextResponse.json({ error: "Network error reaching backend", detail: String(err) }, { status: 503 });
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    console.error(`[screener] Backend returned ${res.status}: ${body}`);
    return NextResponse.json({ error: "Backend unavailable", status: res.status, detail: body }, { status: 503 });
  }

  const data = await res.json();
  return NextResponse.json(data, {
    headers: {
      "Cache-Control": "public, s-maxage=1800, stale-while-revalidate=3600",
    },
  });
}
