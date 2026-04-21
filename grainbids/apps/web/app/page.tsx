import Link from "next/link";

export default function HomePage() {
  const modules = [
    { title: "Bids", href: "/bids", body: "Normalized bids, summary cards, top movers, and filters." },
    { title: "Sources", href: "/sources", body: "Daily source-file ingestion, run history, and source refresh." },
    { title: "Alerts", href: "/alerts", body: "Threshold rules built from normalized bid movement." },
    { title: "Quotes", href: "/quotes", body: "Delivered-value and quote export workflows." },
    { title: "Watchlists", href: "/watchlists", body: "Saved locations, commodities, and delivery windows." },
    { title: "Settings", href: "/settings", body: "Organization defaults, mappings, billing, and access." },
  ];

  return (
    <main className="mx-auto max-w-6xl px-6 py-14">
      <div className="flex items-baseline justify-between gap-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/50 px-3 py-1 text-xs text-black/70 backdrop-blur">
            <span className="h-2 w-2 rounded-full bg-[color:var(--brass)]" />
            GrainBids / Bids module
          </div>
          <h1 className="mt-6 text-balance font-[family-name:var(--font-serif)] text-5xl leading-[1.02] tracking-tight">
            Competitor bids and basis changes, without the spreadsheet chaos.
          </h1>
          <p className="mt-4 max-w-2xl text-pretty text-lg text-black/70">
            Ingest configured source files, normalize competitor rows, track basis deltas, and export a quote sheet.
          </p>
        </div>
      </div>

      <section className="mt-10 grid gap-4 md:grid-cols-3">
        {modules.map((module) => (
          <Card key={module.href} title={module.title} body={module.body} href={module.href} />
        ))}
      </section>

      <section className="mt-10 rounded-2xl border border-black/10 bg-white/60 p-6 backdrop-blur">
        <p className="text-sm text-black/70">API endpoints are live for source-file ingestion, normalized rows, summary cards, and movers.</p>
        <div className="mt-4 flex gap-2">
          <Link href="/sources" className="inline-flex rounded-md border border-black/20 bg-white/80 px-4 py-2 text-sm hover:border-black/40">
            Open Sources
          </Link>
          <Link href="/bids" className="inline-flex rounded-md border border-black/20 bg-white/80 px-4 py-2 text-sm hover:border-black/40">
            Open Bids
          </Link>
        </div>
      </section>
    </main>
  );
}

function Card({ title, body, href }: { title: string; body: string; href: string }) {
  return (
    <Link href={href} className="rounded-lg border border-black/10 bg-white/60 p-5 backdrop-blur transition hover:-translate-y-0.5 hover:border-black/20">
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-2 text-sm text-black/70">{body}</div>
    </Link>
  );
}
