import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { edgeFetch } from "@/lib/edge";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

/** List the agent-spark agents this signed-in customer is entitled to, with
 * their running/stopped status -- proxied through the same authenticated
 * edge path as /api/llm and /api/docling (see lib/edge.ts). */
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
    const upstream = await edgeFetch("/v1/agents", session.customer_id, { method: "GET" });
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
