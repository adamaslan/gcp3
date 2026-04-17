import { clerkMiddleware } from "@clerk/nextjs/server";

// All routes are public by default — Clerk just wires up auth context.
// To protect a route, use `auth().protect()` inside the route handler or
// wrap routes with `createRouteMatcher` here.
export default clerkMiddleware();

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
  ],
};
