import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

/**
 * Proxy for the /macro page: fans out to /macro-pulse and /earnings-radar
 * concurrently and merges them into a single payload.
 */
export async function GET(): Promise<NextResponse> {
  if (!BACKEND) {
    return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });
  }

  const [macroPulseRes, earningsRes] = await Promise.allSettled([
    fetch(`${BACKEND}/macro-pulse`, { cache: "no-store" }),
    fetch(`${BACKEND}/earnings-radar`, { cache: "no-store" }),
  ]);

  const getPayload = async (result: PromiseSettledResult<Response>, label: string) => {
    if (result.status === "rejected") return { error: String(result.reason) };
    if (!result.value.ok) {
      const body = await result.value.text().catch(() => "(unreadable)");
      return { error: `Backend ${label} returned ${result.value.status}`, detail: body };
    }
    return result.value.json().catch(() => ({ error: "Invalid JSON from backend" }));
  };

  const [macro_pulse, earnings_radar] = await Promise.all([
    getPayload(macroPulseRes, "macro-pulse"),
    getPayload(earningsRes, "earnings-radar"),
  ]);

  return NextResponse.json(
    { macro_pulse, earnings_radar },
    {
      headers: {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0, s-maxage=0",
        "Pragma": "no-cache",
        "Expires": "0",
      },
    }
  );
}
