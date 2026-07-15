import Link from "next/link";
import DashboardPage from "./dashboard/page";
import MarketReportSignup from "./_components/market-report-signup";

export default function HomePage() {
  return (
    <>
      <main className="mx-auto max-w-6xl px-6 py-14">
        <section className="rounded-2xl border border-black/10 bg-white/70 p-8 shadow-sm backdrop-blur">
          <p className="text-xs uppercase tracking-[0.18em] text-black/55">GrainBids</p>
          <h1 className="mt-3 max-w-4xl font-[family-name:var(--font-serif)] text-5xl leading-tight tracking-tight">
            Local grain prices, basis movement, and quote-ready market context.
          </h1>
          <p className="mt-4 max-w-3xl text-base text-black/70">
            Compare posted corn, soybean, and wheat bids by commodity, location, delivery period, and company.
            <span className="mt-1 block">Built for farmers and the commercial teams that monitor local grain markets.</span>
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/bids" className="rounded-md border border-black/20 bg-black px-5 py-2.5 text-sm text-white">
              Open Market
            </Link>
            <Link href="mailto:demo@grainbids.com" className="rounded-md border border-black/20 bg-white px-5 py-2.5 text-sm">
              Request Demo
            </Link>
            <Link href="#market-report" className="rounded-md border border-black/20 bg-white px-5 py-2.5 text-sm">
              Join the Free Farmer Beta
            </Link>
          </div>
        </section>
        <div className="mt-6">
          <MarketReportSignup />
        </div>
      </main>
      <DashboardPage />
    </>
  );
}
