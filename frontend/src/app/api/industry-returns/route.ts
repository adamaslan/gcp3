import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(): Promise<NextResponse> {
  if (!BACKEND) {
    console.error("[industry-returns] BACKEND_URL not set");
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  let res: Response;
  try {
    res = await fetch(`${BACKEND}/industry-returns`, { next: { revalidate: 21600 } });
  } catch (err) {
    console.error("[industry-returns] Network error:", err);
    return NextResponse.json({ error: "Network error", detail: String(err) }, { status: 503 });
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    console.error(`[industry-returns] Backend returned ${res.status}: ${body}`);
    return NextResponse.json({ error: "Backend unavailable", status: res.status, detail: body }, { status: 503 });
  }

  return NextResponse.json(await res.json());
}
