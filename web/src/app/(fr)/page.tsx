import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import { pageMetadata } from "@/i18n/metadata";
import { MESSAGES } from "@/i18n/messages";
import { HomeView } from "@/views/HomeView";

const LOCALE = "fr";

export const metadata: Metadata = pageMetadata(LOCALE, "/", {
  title: MESSAGES[LOCALE].meta.homeTitle,
  description: MESSAGES[LOCALE].meta.homeDescription,
});

export default function Home() {
  setRequestLocale(LOCALE);
  return <HomeView />;
}
