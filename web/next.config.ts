import type { NextConfig } from "next";

// Export statique servi depuis S3 derrière CloudFront : aucune fonctionnalité serveur.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
