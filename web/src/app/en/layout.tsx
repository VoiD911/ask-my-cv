import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { RootDocument } from "@/components/RootDocument";
import { SITE_URL } from "@/i18n/metadata";

import "../globals.css";

// Racine anglaise (/en/…) : mêmes pages que la racine française, textes traduits.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0a1110",
};

export default function EnglishLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <RootDocument locale="en">{children}</RootDocument>;
}
