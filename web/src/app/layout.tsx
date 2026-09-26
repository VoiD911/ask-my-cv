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

export const metadata: Metadata = {
  title: "Interroge mon CV — Steve Lang",
  description:
    "Posez vos questions au CV de Steve Lang et suivez en direct chaque étape du pipeline qui prépare la réponse.",
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
