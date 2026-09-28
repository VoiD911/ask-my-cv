import Link from "next/link";

const ITEMS = [
  { href: "/", label: "Démo" },
  { href: "/livraison/", label: "Livraison" },
];

export function SiteNav({ current }: { current: "/" | "/livraison/" }) {
  return (
    <nav className="site-nav" aria-label="Navigation principale">
      {ITEMS.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className="site-nav__link"
          aria-current={current === item.href ? "page" : undefined}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
