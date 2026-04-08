import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(req: NextRequest): Promise<NextResponse> {
  if (!BACKEND) {
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  const type = req.nextUrl.searchParams.get("type");
  const url = `${BACKEND}/content${type ? `?type=${type}` : ""}`;

  let res: Response;
  try {
    res = await fetch(url, { next: { revalidate: 14400 } });
  } catch (err) {
    return NextResponse.json({ error: "Network error reaching backend", detail: String(err) }, { status: 503 });
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    return NextResponse.json({ error: "Backend unavailable", status: res.status, detail: body }, { status: 503 });
  }

  const data = await res.json();
  return NextResponse.json(data, {
    headers: { "Cache-Control": "public, s-maxage=14400, stale-while-revalidate=28800" },
  });
}
