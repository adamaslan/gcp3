import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(): Promise<NextResponse> {
  console.log("[blog-review] Fetching from backend:", BACKEND);

  if (!BACKEND) {
    console.error("[blog-review] BACKEND_URL env var is not set");
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  let res: Response;
  try {
    res = await fetch(`${BACKEND}/blog-review`, { next: { revalidate: 3600 } });
  } catch (err) {
    console.error("[blog-review] Network error reaching backend:", err);
    return NextResponse.json(
      { error: "Network error reaching backend", detail: String(err) },
      { status: 503 }
    );
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    console.error(`[blog-review] Backend returned ${res.status}: ${body}`);
    return NextResponse.json(
      { error: "Backend unavailable", status: res.status, detail: body },
      { status: 503 }
    );
  }

  let data: unknown;
  try {
    data = await res.json();
  } catch (err) {
    console.error("[blog-review] Failed to parse backend JSON:", err);
    return NextResponse.json({ error: "Invalid JSON from backend" }, { status: 502 });
  }

  console.log("[blog-review] Success");
  return NextResponse.json(data);
}
