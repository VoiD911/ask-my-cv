import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import { pageMetadata } from "@/i18n/metadata";
import { MESSAGES } from "@/i18n/messages";
import { DeliveryView } from "@/views/DeliveryView";

const LOCALE = "en";
const text = MESSAGES[LOCALE].delivery;

export const metadata: Metadata = pageMetadata(LOCALE, "/livraison/", {
  title: text.title,
  description: text.description,
});

export default function Page() {
  setRequestLocale(LOCALE);
  return <DeliveryView />;
}
