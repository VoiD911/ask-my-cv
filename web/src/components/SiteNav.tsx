import Link from "next/link";

const ITEMS = [
  { href: "/", label: "Démo" },
  { href: "/livraison/", label: "Livraison" },
  { href: "/architecture/", label: "Architecture" },
] as const;

export function SiteNav({ current }: { current: (typeof ITEMS)[number]["href"] }) {
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
