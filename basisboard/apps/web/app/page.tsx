export default function HomePage() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-14">
      <div className="flex items-baseline justify-between gap-6">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/50 px-3 py-1 text-xs text-black/70 backdrop-blur">
            <span className="h-2 w-2 rounded-full bg-[color:var(--brass)]" />
            BasisBoard MVP scaffold
          </div>
          <h1 className="mt-6 text-balance font-[family-name:var(--font-serif)] text-5xl leading-[1.02] tracking-tight">
            Competitor bids and basis changes, without the spreadsheet chaos.
          </h1>
          <p className="mt-4 max-w-2xl text-pretty text-lg text-black/70">
            Upload a bid sheet, normalize competitor rows, track basis deltas, and export a quote sheet.
          </p>
        </div>
      </div>

      <section className="mt-10 grid gap-4 md:grid-cols-3">
        <Card title="Upload" body="Drop a CSV/XLSX, validate columns, store raw + normalized rows." />
        <Card title="Compare" body="Filter by location/commodity and see your position vs market." />
        <Card title="Alert" body="Create simple threshold rules and get notified on changes." />
      </section>

      <section className="mt-10 rounded-2xl border border-black/10 bg-white/60 p-6 backdrop-blur">
        <p className="text-sm text-black/70">
          Next step: wire this page to the API (`/health` and later `/normalized-prices`) and add auth.
        </p>
      </section>
    </main>
  );
}

function Card({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-black/10 bg-white/60 p-5 backdrop-blur transition hover:-translate-y-0.5 hover:border-black/20">
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-2 text-sm text-black/70">{body}</div>
    </div>
  );
}
