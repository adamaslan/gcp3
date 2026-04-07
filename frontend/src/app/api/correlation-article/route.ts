import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(): Promise<NextResponse> {
  console.log("[correlation-article] Fetching from backend:", BACKEND);

  if (!BACKEND) {
    console.error("[correlation-article] BACKEND_URL env var is not set");
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  let res: Response;
  try {
    res = await fetch(`${BACKEND}/correlation-article`, { next: { revalidate: 3600 } });
  } catch (err) {
    console.error("[correlation-article] Network error reaching backend:", err);
    return NextResponse.json(
      { error: "Network error reaching backend", detail: String(err) },
      { status: 503 }
    );
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    console.error(`[correlation-article] Backend returned ${res.status}: ${body}`);
    return NextResponse.json(
      { error: "Backend unavailable", status: res.status, detail: body },
      { status: 503 }
    );
  }

  let data: unknown;
  try {
    data = await res.json();
  } catch (err) {
    console.error("[correlation-article] Failed to parse backend JSON:", err);
    return NextResponse.json({ error: "Invalid JSON from backend" }, { status: 502 });
  }

  console.log("[correlation-article] Success");
  return NextResponse.json(data, {
    headers: {
      "Cache-Control": "public, s-maxage=14400, stale-while-revalidate=28800",
    },
  });
}
