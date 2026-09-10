import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(req: NextRequest): Promise<NextResponse> {
  const ticker = req.nextUrl.searchParams.get("ticker");
  if (!ticker) {
    return NextResponse.json({ error: "ticker param required" }, { status: 400 });
  }

  if (!BACKEND) {
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  try {
    const res = await fetch(`${BACKEND}/signals/${encodeURIComponent(ticker.toUpperCase())}`, {
      next: { revalidate: 0 },
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return NextResponse.json({ error: "Backend error", status: res.status, detail: body }, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ error: "Network error", detail: String(err) }, { status: 503 });
  }
}
