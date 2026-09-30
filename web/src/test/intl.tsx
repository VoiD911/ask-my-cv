/**
 * `@testing-library/react` avec le fournisseur next-intl : les composants traduits se rendent
 * comme dans l'application (catalogue complet de la langue voulue, français par défaut).
 */
import { render as rtlRender, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement, ReactNode } from "react";

import type { Locale } from "@/i18n/locales";
import { MESSAGES } from "@/i18n/messages";

export * from "@testing-library/react";

export function render(ui: ReactElement, options: RenderOptions & { locale?: Locale } = {}) {
  const { locale = "fr", ...rest } = options;
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone="UTC">
        {children}
      </NextIntlClientProvider>
    );
  }
  return rtlRender(ui, { wrapper: Wrapper, ...rest });
}
