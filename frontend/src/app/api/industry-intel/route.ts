import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(req: NextRequest): Promise<NextResponse> {
  if (!BACKEND) {
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  const view = req.nextUrl.searchParams.get("view") ?? "full";
  const url = `${BACKEND}/industry-intel?view=${view}`;

  let res: Response;
  try {
    res = await fetch(url, { next: { revalidate: 60 } });
  } catch (err) {
    return NextResponse.json({ error: "Network error reaching backend", detail: String(err) }, { status: 503 });
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    return NextResponse.json({ error: "Backend unavailable", status: res.status, detail: body }, { status: 503 });
  }

  const data = await res.json();
  return NextResponse.json(data, {
    headers: { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300" },
  });
}
