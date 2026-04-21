import Link from "next/link";

export default function SettingsPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Settings</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Settings</h1>
      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Account and organization settings</h2>
        <p className="mt-2 text-sm text-black/65">Settings will hold organization defaults, source mappings, billing, and user access.</p>
        <Link href="/sources" className="mt-4 inline-flex rounded-md border border-black/20 bg-white/80 px-3 py-2 text-sm hover:border-black/40">
          Manage sources
        </Link>
      </section>
    </main>
  );
}
