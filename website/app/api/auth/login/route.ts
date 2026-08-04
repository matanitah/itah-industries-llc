import { NextRequest, NextResponse } from "next/server";
import * as argon2 from "argon2";
import { getPortalUser } from "@/lib/dynamo";
import { SESSION_COOKIE, signSession } from "@/lib/session";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const username = String(body.username || "").trim();
    const password = String(body.password || "");
    if (!username || !password) {
      return NextResponse.json({ error: "Username and password required" }, { status: 400 });
    }

    const user = await getPortalUser(username);
    if (!user || user.enabled === false) {
      return NextResponse.json({ error: "Invalid credentials" }, { status: 401 });
    }

    const ok = await argon2.verify(user.password_hash, password);
    if (!ok) {
      return NextResponse.json({ error: "Invalid credentials" }, { status: 401 });
    }

    const token = await signSession({ sub: user.username, customer_id: user.customer_id });
    const response = NextResponse.json({
      ok: true,
      username: user.username,
      customer_id: user.customer_id,
    });
    response.cookies.set(SESSION_COOKIE, token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 12,
    });
    return response;
  } catch (err) {
    const message = err instanceof Error ? err.message : "Login failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
