import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL!;

async function handler(req: NextRequest, method: string): Promise<NextResponse> {
  const path = req.nextUrl.searchParams.get("path");
  if (!path) return NextResponse.json({ error: "path param required" }, { status: 400 });
  if (!BACKEND) return NextResponse.json({ error: "BACKEND_URL not configured" }, { status: 500 });

  const url = `${BACKEND}${path}`;
  try {
    const opts: RequestInit = { method, next: { revalidate: 0 } };
    if (method === "POST") {
      const body = await req.text();
      opts.body = body;
      opts.headers = { "Content-Type": "application/json" };
    }
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => null);
    return NextResponse.json(data ?? { error: "empty response" }, { status: res.status });
  } catch (err) {
    return NextResponse.json({ error: "Network error", detail: String(err) }, { status: 503 });
  }
}

export async function GET(req: NextRequest): Promise<NextResponse> {
  return handler(req, "GET");
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  return handler(req, "POST");
}
