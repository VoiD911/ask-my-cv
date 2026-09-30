import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { RootDocument } from "@/components/RootDocument";
import { SITE_URL } from "@/i18n/metadata";

import "../globals.css";

// Racine française : les URL publiques existantes (/, /architecture/, /xops/, /livraison/…)
// restent inchangées. L'anglais a sa propre racine sous app/(en)/en.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0a1110",
};

export default function FrenchLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <RootDocument locale="fr">{children}</RootDocument>;
}
