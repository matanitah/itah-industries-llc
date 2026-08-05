import { NextRequest, NextResponse } from "next/server";
import {
  isLocalHost,
  isMarketingHost,
  isPortalHost,
  marketingOrigin,
  portalOrigin,
} from "@/lib/hosts";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

function portalPaths(pathname: string): boolean {
  return (
    pathname === "/login" ||
    pathname.startsWith("/invite") ||
    pathname.startsWith("/app") ||
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/api/llm") ||
    pathname.startsWith("/api/docling") ||
    pathname.startsWith("/api/health") ||
    pathname.startsWith("/api/agents")
  );
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const host = request.headers.get("host");

  // Production host split: personal site vs portal.
  if (isMarketingHost(host)) {
    if (portalPaths(pathname)) {
      return NextResponse.redirect(new URL(pathname + request.nextUrl.search, portalOrigin()));
    }
    return NextResponse.next();
  }

  if (isPortalHost(host)) {
    // Portal root → login (or chat if already signed in).
    if (pathname === "/" || pathname === "") {
      const token = request.cookies.get(SESSION_COOKIE)?.value;
      const session = token ? await verifySession(token) : null;
      if (session) {
        return NextResponse.redirect(new URL("/app/chat", request.url));
      }
      return NextResponse.redirect(new URL("/login", request.url));
    }
    // Keep marketing off the portal host.
    if (!portalPaths(pathname) && !pathname.startsWith("/_next") && !pathname.startsWith("/img") && pathname !== "/favicon.ico" && pathname !== "/matan_resume.pdf") {
      return NextResponse.redirect(new URL("/", marketingOrigin()));
    }
  }

  // Auth for portal surfaces (also on localhost during local dev).
  const needsAuth =
    pathname.startsWith("/app") ||
    pathname.startsWith("/api/llm") ||
    pathname.startsWith("/api/docling") ||
    pathname.startsWith("/api/health") ||
    pathname.startsWith("/api/agents");

  if (!needsAuth) {
    return NextResponse.next();
  }

  // On marketing host we already redirected portal paths; localhost keeps full app.
  if (isMarketingHost(host) && !isLocalHost(host)) {
    return NextResponse.redirect(new URL(pathname, portalOrigin()));
  }

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    const loginBase = isPortalHost(host) || isLocalHost(host) ? request.url : portalOrigin();
    return NextResponse.redirect(new URL("/login", loginBase));
  }

  const session = await verifySession(token);
  if (!session) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    const loginBase = isPortalHost(host) || isLocalHost(host) ? request.url : portalOrigin();
    const response = NextResponse.redirect(new URL("/login", loginBase));
    response.cookies.set(SESSION_COOKIE, "", { path: "/", maxAge: 0 });
    return response;
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/",
    "/login",
    "/invite/:path*",
    "/app/:path*",
    "/api/auth/:path*",
    "/api/llm/:path*",
    "/api/docling/:path*",
    "/api/health",
    "/api/agents/:path*",
    "/((?!_next/static|_next/image|.*\\..*).*)",
  ],
};
