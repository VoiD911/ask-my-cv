import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import { pageMetadata } from "@/i18n/metadata";
import { xopsText } from "@/lib/xops-content.en";
import { XopsView } from "@/views/XopsView";

const LOCALE = "en";
const text = xopsText(LOCALE).page;

export const metadata: Metadata = pageMetadata(LOCALE, "/xops/", {
  title: text.title,
  description: text.description,
});

export default function Page() {
  setRequestLocale(LOCALE);
  return <XopsView />;
}
