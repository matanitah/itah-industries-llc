export const SESSION_COOKIE = "itah_session";

export type SessionClaims = {
  sub: string;
  customer_id: string;
  exp?: number;
};

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env: ${name}`);
  }
  return value;
}

export function getSessionSecret(): string {
  return requireEnv("PORTAL_SESSION_SECRET");
}

export async function signSession(claims: Omit<SessionClaims, "exp">): Promise<string> {
  const { SignJWT } = await import("jose");
  const secret = new TextEncoder().encode(getSessionSecret());
  return new SignJWT({ customer_id: claims.customer_id })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(claims.sub)
    .setIssuedAt()
    .setExpirationTime("12h")
    .sign(secret);
}

export async function verifySession(token: string): Promise<SessionClaims | null> {
  try {
    const { jwtVerify } = await import("jose");
    const secret = new TextEncoder().encode(getSessionSecret());
    const { payload } = await jwtVerify(token, secret);
    const sub = typeof payload.sub === "string" ? payload.sub : null;
    const customerId =
      typeof payload.customer_id === "string" ? payload.customer_id : null;
    if (!sub || !customerId) return null;
    return { sub, customer_id: customerId, exp: payload.exp };
  } catch {
    return null;
  }
}
