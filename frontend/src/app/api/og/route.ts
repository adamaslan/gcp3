import { ImageResponse } from "next/og";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const title = searchParams.get("title") || "Nuwrrrld Financial";
  const description = searchParams.get("description") || "Helping everyone make better financial choices";
  const domain = searchParams.get("domain") || "nuwrrrld.com";

  try {
    return new ImageResponse(
      (
        <div
          style={{
            fontSize: 48,
            background: "#0f172a",
            color: "#f3f4f6",
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "40px",
            fontFamily: "system-ui",
          }}
        >
          <div
            style={{
              fontSize: 64,
              fontWeight: "bold",
              marginBottom: "20px",
              textAlign: "center",
              maxWidth: "90%",
            }}
          >
            {title}
          </div>
          <div
            style={{
              fontSize: 32,
              color: "#d1d5db",
              marginBottom: "40px",
              textAlign: "center",
              maxWidth: "90%",
            }}
          >
            {description}
          </div>
          <div
            style={{
              fontSize: 24,
              color: "#9ca3af",
              marginTop: "auto",
            }}
          >
            {domain}
          </div>
        </div>
      ),
      {
        width: 1024,
        height: 541,
      }
    );
  } catch (error) {
    console.error("OG image generation error:", error);
    return new Response("Failed to generate OG image", { status: 500 });
  }
}
