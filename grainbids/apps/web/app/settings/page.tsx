import Link from "next/link";
import { isAdminRole, USER_ROLE } from "@/lib/api";

export default function SettingsPage() {
  if (!isAdminRole(USER_ROLE)) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <div className="rounded-xl border border-black/10 bg-white/80 p-6 shadow-sm">
          <p className="text-xs uppercase tracking-[0.16em] text-black/50">Admin route</p>
          <h1 className="mt-2 font-[family-name:var(--font-serif)] text-3xl">Access restricted</h1>
          <p className="mt-3 text-sm text-black/70">Settings is currently available only to admin users.</p>
          <div className="mt-5">
            <Link href="/bids" className="rounded-md border border-black/20 bg-white px-4 py-2 text-sm">
              Return to Market
            </Link>
          </div>
        </div>
      </main>
    );
  }

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
