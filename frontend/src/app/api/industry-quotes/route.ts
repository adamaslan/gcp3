export const runtime = "edge";

import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(request: Request): Promise<NextResponse> {
  if (!BACKEND) {
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  const { searchParams } = new URL(request.url);
  const view = searchParams.get("view") ?? "full";

  let res: Response;
  try {
    res = await fetch(`${BACKEND}/industry-quotes?view=${encodeURIComponent(view)}`, { next: { revalidate: 3600 } });
  } catch (err) {
    return NextResponse.json(
      { error: "Network error reaching backend", detail: String(err) },
      { status: 503 }
    );
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    return NextResponse.json(
      { error: "Backend unavailable", status: res.status, detail: body },
      { status: 503 }
    );
  }

  return NextResponse.json(await res.json(), {
    headers: {
      "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300",
    },
  });
}
