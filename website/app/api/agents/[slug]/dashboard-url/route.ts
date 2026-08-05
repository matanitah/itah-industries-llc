import { NextRequest } from "next/server";
import { proxyAgentAction } from "../../_shared";

/** Returns a short-lived, token-bearing URL for the agent's Streamlit
 * dashboard, reached directly over the Cloudflare Tunnel hostname (not
 * through API Gateway -- see spark-gateway routes/agents.py for why: Streamlit's
 * WebSocket traffic can't tunnel through an HTTP API's HTTP_PROXY integration).
 * The <iframe> on /app/agents/[slug] points at this URL. */
export async function POST(_request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return proxyAgentAction(`/v1/agents/${encodeURIComponent(slug)}/dashboard-url`, "POST");
}
