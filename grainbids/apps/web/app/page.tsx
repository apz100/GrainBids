import Link from "next/link";

export default function HomePage() {
  const modules = [
    { title: "Bids Dashboard", href: "/bids", body: "See local bid position, basis deltas, and top movers instantly." },
    { title: "Sources + SLA", href: "/sources", body: "Run ingestion cycles, monitor freshness, and diagnose rejects." },
    { title: "Alerts", href: "/alerts", body: "Trigger notifications when thresholds and deltas are hit." },
    { title: "Quotes", href: "/quotes", body: "Generate delivered values and export quote sheets." },
    { title: "Watchlists", href: "/watchlists", body: "Track key markets by commodity, location, and delivery window." },
    { title: "Signals", href: "/signals", body: "Forecast overlays with confidence scoring." },
    { title: "Settings", href: "/settings", body: "Manage organization defaults, roles, and integrations." },
  ];

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="rounded-3xl border border-black/10 bg-white/65 px-8 py-10 backdrop-blur">
        <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/70 px-3 py-1 text-xs text-black/70">
            <span className="h-2 w-2 rounded-full bg-[color:var(--brass)]" />
            GrainBids / Production
          </div>
        <h1 className="mt-6 text-balance font-[family-name:var(--font-serif)] text-5xl leading-[1.04] tracking-tight">
          See where your bid sits versus the local market in under 60 seconds.
        </h1>
        <p className="mt-4 max-w-3xl text-pretty text-lg text-black/70">
          GrainBids turns multi-source cash bid files into one decision dashboard: normalized rows, basis movement, open alerts,
          and quote-ready outputs.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/bids" className="rounded-xl border border-black/20 bg-black px-5 py-2.5 text-sm text-white">
            Open Dashboard
          </Link>
          <Link href="/sources" className="rounded-xl border border-black/20 bg-white px-5 py-2.5 text-sm">
            Run Ingestion
          </Link>
        </div>
      </header>

      <section className="mt-6 grid gap-3 sm:grid-cols-3">
        <Stat label="Coverage" value="US + Canada" />
        <Stat label="Cadence Target" value="08:00 + 15:00 ET" />
        <Stat label="Pipeline" value="Source -> Normalize -> Dashboard" />
      </section>

      <section className="mt-10 grid gap-4 md:grid-cols-3">
        {modules.map((module) => (
          <Card key={module.href} title={module.title} body={module.body} href={module.href} />
        ))}
      </section>

      <section className="mt-10 rounded-2xl border border-black/10 bg-white/60 p-6 backdrop-blur">
        <p className="text-sm text-black/70">
          Immediate priority: increase parse success rate and reduce reject-heavy source sheets from Sources diagnostics.
        </p>
      </section>
    </main>
  );
}

function Card({ title, body, href }: { title: string; body: string; href: string }) {
  return (
    <Link href={href} className="rounded-xl border border-black/10 bg-white/65 p-5 backdrop-blur transition hover:-translate-y-0.5 hover:border-black/20">
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-2 text-sm text-black/70">{body}</div>
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-black/10 bg-white/60 px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-black/50">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  );
}
