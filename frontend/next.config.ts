import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // BUILD_STANDALONE=true is set in the Docker/Cloud Run build (cloudbuild.yaml).
  // Vercel builds do not set this, so output defaults to undefined (standard Vercel mode).
  output: process.env.BUILD_STANDALONE === "true" ? "standalone" : undefined,
};

export default nextConfig;
