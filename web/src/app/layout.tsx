import type { Metadata, Viewport } from "next";
import { Instrument_Sans, Martian_Mono } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

// Polices auto-hébergées au build (aucune requête vers Google côté visiteur).
const instrument = Instrument_Sans({
  subsets: ["latin", "latin-ext"],
  axes: ["wdth"],
  variable: "--font-instrument",
  display: "swap",
});

const martian = Martian_Mono({
  subsets: ["latin", "latin-ext"],
  axes: ["wdth"],
  variable: "--font-martian",
  display: "swap",
});

const DESCRIPTION =
  "Pose tes questions au CV de Steve Lang, architecte principal en hyperautomatisation, IA générative et cloud, et suis en direct chaque étape du pipeline qui prépare la réponse.";

export const metadata: Metadata = {
  metadataBase: new URL("https://job.stevelang.net"),
  title: "Interroge mon CV — Steve Lang",
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    locale: "fr_CA",
    url: "/",
    siteName: "Interroge mon CV",
    title: "Interroge mon CV — Steve Lang",
    description: DESCRIPTION,
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0a1110",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="fr" className={`${instrument.variable} ${martian.variable}`}>
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
