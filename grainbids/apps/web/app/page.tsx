import Link from "next/link";
import DashboardPage from "./dashboard/page";

import { isAdminRole, USER_ROLE } from "@/lib/api";

export default function HomePage() {
  const admin = isAdminRole(USER_ROLE);
  return (
    <>
      <main className="mx-auto max-w-6xl px-6 py-14">
        <section className="rounded-2xl border border-black/10 bg-white/70 p-8 shadow-sm backdrop-blur">
          <p className="text-xs uppercase tracking-[0.18em] text-black/55">GrainBids</p>
          <h1 className="mt-3 max-w-4xl font-[family-name:var(--font-serif)] text-5xl leading-tight tracking-tight">
            Local grain prices, basis movement, and quote-ready market context.
          </h1>
          <p className="mt-4 max-w-3xl text-base text-black/70">
            Table-first market intelligence for merchandisers, elevators, feed mills, and farms. Open the market view in one click, then filter by commodity, location, and company.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/bids" className="rounded-md border border-black/20 bg-black px-5 py-2.5 text-sm text-white">
              Open Market
            </Link>
            <Link href="mailto:demo@grainbids.com" className="rounded-md border border-black/20 bg-white px-5 py-2.5 text-sm">
              Request Demo
            </Link>
            {admin ? (
              <Link href="/sources" className="rounded-md border border-black/20 bg-white px-5 py-2.5 text-sm">
                Admin Login
              </Link>
            ) : null}
          </div>
        </section>
      </main>
      <DashboardPage />
    </>
  );
}
