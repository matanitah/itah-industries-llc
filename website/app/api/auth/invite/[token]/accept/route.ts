import { NextRequest, NextResponse } from "next/server";
import { acceptPortalInvite } from "@/lib/dynamo";
import { SESSION_COOKIE, signSession } from "@/lib/session";

type Ctx = { params: Promise<{ token: string }> };

export async function POST(request: NextRequest, context: Ctx) {
  try {
    const { token } = await context.params;
    const body = await request.json();
    const username = String(body.username || "").trim();
    const password = String(body.password || "");
    const confirm = String(body.confirm || body.password_confirm || "");

    if (confirm && confirm !== password) {
      return NextResponse.json({ error: "Passwords do not match" }, { status: 400 });
    }

    const created = await acceptPortalInvite({ rawToken: token, username, password });
    const session = await signSession({
      sub: created.username,
      customer_id: created.customer_id,
    });
    const response = NextResponse.json({
      ok: true,
      username: created.username,
      customer_id: created.customer_id,
    });
    response.cookies.set(SESSION_COOKIE, session, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 12,
    });
    return response;
  } catch (err) {
    const message = err instanceof Error ? err.message : "Could not create account";
    const status =
      /expired|revoked|not found|already used|taken|must be|may only/i.test(message) ? 400 : 500;
    return NextResponse.json({ error: message }, { status });
  }
}
