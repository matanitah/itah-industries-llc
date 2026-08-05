import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { edgeFetch } from "@/lib/edge";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

/** Shared auth-then-proxy body for /api/agents/[slug]/* routes: verifies the
 * portal session, then forwards to spark-gateway's /v1/agents/{slug}/* via
 * the same authenticated edge path as chat/docling (lib/edge.ts). */
export async function proxyAgentAction(
  agentSlugPath: string,
  method: "GET" | "POST",
): Promise<NextResponse> {
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
    const upstream = await edgeFetch(agentSlugPath, session.customer_id, { method });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Upstream error";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
