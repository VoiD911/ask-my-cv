import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

// Page 404 unique (export statique : 404.html servi par CloudFront pour toute URL inconnue).
// Deux racines de layout, (fr) et en : aucune ne peut composer une 404 commune, d'où
// global-not-found. Bilingue, français d'abord (langue par défaut du site).
export const metadata: Metadata = {
  title: "Page introuvable · Page not found",
  robots: { index: false, follow: true },
};

export default function GlobalNotFound() {
  return (
    <html lang="fr">
      <body className="min-h-dvh antialiased">
        <main className="page">
          <header className="titleblock">
            <div className="titleblock__main">
              <p className="titleblock__eyebrow">404</p>
              <h1 className="titleblock__name">Page introuvable</h1>
              <p className="titleblock__role">
                Cette page n&apos;existe pas. <Link href="/">Retour à l&apos;accueil</Link>
              </p>
              <p className="titleblock__role" lang="en">
                Page not found. <Link href="/en/">Back to the home page</Link>
              </p>
            </div>
          </header>
        </main>
      </body>
    </html>
  );
}
