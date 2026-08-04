/** Public hostnames for marketing vs customer portal. */
export const MARKETING_HOSTS = new Set(["matanitah.com", "www.matanitah.com"]);
export const PORTAL_HOST = "spark-origin.matanitah.com";

export function isMarketingHost(host: string | null): boolean {
  if (!host) return false;
  const h = host.split(":")[0].toLowerCase();
  return MARKETING_HOSTS.has(h);
}

export function isPortalHost(host: string | null): boolean {
  if (!host) return false;
  const h = host.split(":")[0].toLowerCase();
  return h === PORTAL_HOST;
}

export function isLocalHost(host: string | null): boolean {
  if (!host) return true;
  const h = host.split(":")[0].toLowerCase();
  return h === "localhost" || h === "127.0.0.1";
}

export function portalOrigin(): string {
  return `https://${PORTAL_HOST}`;
}

export function marketingOrigin(): string {
  return "https://matanitah.com";
}
