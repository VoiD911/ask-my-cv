import type { NextConfig } from "next";

// Export statique servi depuis S3 derrière CloudFront : aucune fonctionnalité serveur.
//
// next-intl sans middleware (incompatible avec `output: "export"`) : la langue de chaque page
// est fixée par sa racine de layout, app/(fr) (URL existantes) ou app/en, via
// `setRequestLocale`. L'alias `next-intl/config` est déclaré ici directement, comme le fait
// `createNextIntlPlugin` pour Turbopack : le plugin charge au démarrage l'extracteur de
// messages et son binaire natif @swc/core, inutiles ici (catalogues JSON écrits à la main).
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  // Deux racines de layout (fr, en) : la 404 commune vient de app/global-not-found.tsx.
  experimental: { globalNotFound: true },
  turbopack: {
    resolveAlias: { "next-intl/config": "./src/i18n/request.ts" },
  },
};

export default nextConfig;
