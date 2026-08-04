import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { getSparkStatus } from "@/lib/dynamo";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

export async function GET() {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const session = await verifySession(token);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const status = await getSparkStatus();
    const online = Boolean(status.online);
    return NextResponse.json(
      {
        ok: online,
        online,
        origin_base_url: status.origin_base_url || "",
        updated_at: status.updated_at || "",
      },
      { status: online ? 200 : 503 },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Status lookup failed";
    return NextResponse.json({ ok: false, online: false, error: message }, { status: 502 });
  }
}
