import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse, type NextRequest } from "next/server";

const isProtectedRoute = createRouteMatcher(["/os(.*)", "/leads(.*)"]);
const clerkConfigured = Boolean(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY && process.env.CLERK_SECRET_KEY,
);

function proxyWithoutClerk(request: NextRequest) {
  if (process.env.NODE_ENV === "production" && isProtectedRoute(request)) {
    return new NextResponse("Stonegate authentication is temporarily unavailable.", {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  }
  return NextResponse.next();
}

export default clerkConfigured
  ? clerkMiddleware(async (auth, request) => {
      if (isProtectedRoute(request)) {
        await auth.protect();
      }
    })
  : proxyWithoutClerk;

export const config = {
  matcher: [
    "/os/:path*",
    "/leads/:path*",
    "/sign-in/:path*",
    "/sign-up/:path*",
    "/__clerk/:path*",
  ],
};
