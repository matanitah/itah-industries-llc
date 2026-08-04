import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { edgeFetch } from "@/lib/edge";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

async function requireCustomer(): Promise<string | NextResponse> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const session = await verifySession(token);
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return session.customer_id;
}

export async function POST(request: NextRequest) {
  const customer = await requireCustomer();
  if (customer instanceof NextResponse) return customer;

  try {
    const form = await request.formData();
    const file = form.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json({ error: "file required" }, { status: 400 });
    }
    const upstreamForm = new FormData();
    upstreamForm.append("file", file, file.name);

    const upstream = await edgeFetch("/v1/docling/convert", customer, {
      method: "POST",
      body: upstreamForm,
    });
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
