import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ["argon2"],
  // Portal is reached via the named tunnel hostname in local demos.
  allowedDevOrigins: ["spark-origin.matanitah.com"],
};

export default nextConfig;
