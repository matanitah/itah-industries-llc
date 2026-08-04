import { NextRequest, NextResponse } from "next/server";
import { getPortalInvite, inviteIsAcceptable } from "@/lib/dynamo";

type Ctx = { params: Promise<{ token: string }> };

export async function GET(_request: NextRequest, context: Ctx) {
  const { token } = await context.params;
  const check = inviteIsAcceptable(await getPortalInvite(token));
  if (!check.ok || !check.invite) {
    return NextResponse.json({ ok: false, error: check.error || "Invalid invite" }, { status: 400 });
  }
  return NextResponse.json({
    ok: true,
    email: check.invite.email,
    customer_id: check.invite.customer_id,
    expires_at: check.invite.expires_at,
  });
}
