export function getApiBaseUrl(): string {
  const base = process.env.ITAH_API_BASE_URL;
  if (!base) {
    throw new Error("Missing ITAH_API_BASE_URL");
  }
  return base.replace(/\/$/, "");
}

export function portalEdgeHeaders(customerId: string): HeadersInit {
  const token = process.env.PORTAL_EDGE_TOKEN;
  if (!token) {
    throw new Error("Missing PORTAL_EDGE_TOKEN");
  }
  return {
    Authorization: "Bearer portal",
    "X-Itah-Portal-Token": token,
    "X-Itah-Customer-Id": customerId,
  };
}

export async function edgeFetch(
  path: string,
  customerId: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  const portal = portalEdgeHeaders(customerId);
  for (const [k, v] of Object.entries(portal)) {
    headers.set(k, v as string);
  }
  return fetch(`${getApiBaseUrl()}${path}`, { ...init, headers });
}
