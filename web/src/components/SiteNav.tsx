import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";

import { localePath, otherLocale } from "@/i18n/locales";

const ITEMS = [
  { href: "/", key: "demo" },
  { href: "/livraison/", key: "delivery" },
  { href: "/architecture/", key: "architecture" },
  { href: "/xops/", key: "xops" },
] as const;

type NavPath = (typeof ITEMS)[number]["href"];

/**
 * Onglets du site et sélecteur de langue : de simples liens (aucun JavaScript requis). Le
 * sélecteur mène à la même page dans l'autre langue ; `path` est le chemin français de la
 * page courante (par défaut, celui de l'onglet).
 */
export function SiteNav({ current, path }: { current: NavPath; path?: string }) {
  const t = useTranslations("nav");
  const locale = useLocale();
  const target = otherLocale(locale);
  return (
    <nav className="site-nav" aria-label={t("label")}>
      {ITEMS.map((item) => (
        <Link
          key={item.href}
          href={localePath(locale, item.href)}
          className="site-nav__link"
          aria-current={current === item.href ? "page" : undefined}
        >
          {t(item.key)}
        </Link>
      ))}
      {/* Autre racine de layout : lien <a> classique (rechargement complet, comme l'exige Next). */}
      <a
        href={localePath(target, path ?? current)}
        className="site-nav__link site-nav__lang"
        hrefLang={target}
        lang={target}
        aria-label={t("switchLabel")}
      >
        {t("switch")}
      </a>
    </nav>
  );
}
