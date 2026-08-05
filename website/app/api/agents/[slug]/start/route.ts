import { NextRequest } from "next/server";
import { proxyAgentAction } from "../../_shared";

export async function POST(_request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return proxyAgentAction(`/v1/agents/${encodeURIComponent(slug)}/start`, "POST");
}
