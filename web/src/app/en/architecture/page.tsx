import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import { pageMetadata } from "@/i18n/metadata";
import { architectureContent } from "@/lib/architecture-content.en";
import { ArchitectureView } from "@/views/ArchitectureView";

const LOCALE = "en";
const text = architectureContent(LOCALE).page;

export const metadata: Metadata = pageMetadata(LOCALE, "/architecture/", {
  title: text.title,
  description: text.description,
});

export default function Page() {
  setRequestLocale(LOCALE);
  return <ArchitectureView />;
}
