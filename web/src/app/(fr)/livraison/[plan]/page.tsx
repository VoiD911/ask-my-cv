import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { pageMetadata } from "@/i18n/metadata";
import { MESSAGES } from "@/i18n/messages";
import { translator } from "@/i18n/translator";
import { deliveryPlans } from "@/lib/delivery";
import { PlanView } from "@/views/PlanView";

const LOCALE = "fr";
const text = MESSAGES[LOCALE].delivery;

type Props = { params: Promise<{ plan: string }> };

export function generateStaticParams() {
  return deliveryPlans.map((plan) => ({ plan: plan.id }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { plan: id } = await params;
  const plan = deliveryPlans.find((item) => item.id === id);
  if (!plan) return { title: text.planNotFound };
  return pageMetadata(LOCALE, `/livraison/${plan.id}/`, { title: translator(LOCALE)("delivery.planTitle", { id: plan.id }) });
}

export default async function Page({ params }: Props) {
  const { plan: id } = await params;
  const plan = deliveryPlans.find((item) => item.id === id);
  if (!plan) notFound();
  setRequestLocale(LOCALE);
  return <PlanView plan={plan} />;
}
