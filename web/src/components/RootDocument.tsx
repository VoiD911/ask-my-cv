import { NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { Instrument_Sans, Martian_Mono } from "next/font/google";
import type { ReactNode } from "react";

import type { Locale } from "@/i18n/locales";
import { clientMessages } from "@/i18n/messages";

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

/**
 * Document HTML commun aux deux racines de layout, (fr) et (en) : `<html lang>` exact par
 * langue, et seuls les messages des composants client envoyés au navigateur.
 */
export function RootDocument({ locale, children }: { locale: Locale; children: ReactNode }) {
  setRequestLocale(locale);
  return (
    <html lang={locale} className={`${instrument.variable} ${martian.variable}`}>
      <body className="min-h-dvh antialiased">
        <NextIntlClientProvider locale={locale} messages={clientMessages(locale)}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
