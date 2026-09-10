import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

export async function GET(): Promise<NextResponse> {
  if (!BACKEND) {
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  const res = await fetch(`${BACKEND}/midday-quotes`, {
    next: { revalidate: 300 },
  }).catch((err: unknown) => {
    throw new Error(`Backend unreachable: ${String(err)}`);
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "(unreadable)");
    return NextResponse.json(
      { error: `Backend returned ${res.status}`, detail: body },
      { status: res.status }
    );
  }

  const data = await res.json().catch(() => null);
  if (!data) {
    return NextResponse.json({ error: "Invalid JSON from backend" }, { status: 502 });
  }

  return NextResponse.json(data, {
    headers: {
      "Cache-Control": "public, s-maxage=300, stale-while-revalidate=30",
    },
  });
}
