"use client";

import Link from "next/link";

import { isAdminRole } from "@/lib/api";
import { useAuthSession } from "./auth-session-provider";

type NavItem = { href: string; label: string };

const USER_NAV: NavItem[] = [
  { href: "/bids", label: "Market" },
  { href: "/alerts", label: "Alerts" },
  { href: "/quotes", label: "Quotes" },
  { href: "/watchlists", label: "Watchlists" },
];

const ADMIN_NAV: NavItem[] = [
  { href: "/sources", label: "Sources" },
  { href: "/settings", label: "Settings" },
];

export default function TopNav() {
  const { session } = useAuthSession();
  const admin = isAdminRole(session?.user_role);
  return (
    <header className="border-b border-black/10 bg-white/85 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between px-6">
        <Link href="/" className="font-[family-name:var(--font-serif)] text-4xl leading-none tracking-tight">
          GrainBids
        </Link>
        <nav className="flex items-center gap-6 text-sm text-black/70">
          {USER_NAV.map((item) => (
            <Link key={item.href} href={item.href} className="transition hover:text-black">
              {item.label}
            </Link>
          ))}
          {admin
            ? ADMIN_NAV.map((item) => (
                <Link key={item.href} href={item.href} className="transition hover:text-black">
                  {item.label}
                </Link>
              ))
            : null}
        </nav>
      </div>
    </header>
  );
}
