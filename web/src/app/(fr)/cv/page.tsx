import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import { pageMetadata } from "@/i18n/metadata";
import { MESSAGES } from "@/i18n/messages";
import { CvView } from "@/views/CvView";

const LOCALE = "fr";
const text = MESSAGES[LOCALE].cv;

export const metadata: Metadata = {
  ...pageMetadata(LOCALE, "/cv/", { title: text.title, description: text.description }),
  authors: [{ name: "Steve Lang" }],
};

export default function Page() {
  setRequestLocale(LOCALE);
  return <CvView />;
}
