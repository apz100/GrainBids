"use client";

import { FormEvent, useEffect, useState } from "react";

type IngestionRun = {
  id: string;
  source_name: string;
  source_identifier: string;
  started_at: string | null;
  completed_at: string | null;
  status: string;
  raw_row_count: number | null;
  normalized_row_count: number | null;
  error_message: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function SourcesPage() {
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadRuns() {
    const res = await fetch(`${API_BASE}/api/ingestion/runs?limit=25`, { cache: "no-store" });
    const json = res.ok ? await res.json() : { rows: [] };
    setRuns(json.rows || []);
  }

  useEffect(() => {
    loadRuns().catch((err) => setError(String(err)));
  }, []);

  async function triggerIngestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    setError("");

    const form = new FormData(event.currentTarget);
    const params = new URLSearchParams();
    for (const key of ["source_file_path", "source_name", "source_id", "commodity_id"]) {
      const value = String(form.get(key) || "").trim();
      if (value) params.set(key, value);
    }

    try {
      const res = await fetch(`${API_BASE}/api/ingestion/source-file/run?${params.toString()}`, { method: "POST" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Ingestion failed");
      }
      setMessage(`Ingestion ${json.result.status}. Normalized ${json.result.normalized_row_count ?? 0} rows.`);
      await loadRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <header>
        <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Sources</p>
        <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Source Ingestion</h1>
        <p className="mt-2 text-sm text-black/65">Run and monitor configured daily source-file ingestion.</p>
      </header>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Manual admin trigger</h2>
        <form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={triggerIngestion}>
          <Field name="source_file_path" label="Source file path" placeholder="P:\Adam\DailyBids\latest.xlsx" />
          <Field name="source_name" label="Source name" placeholder="Daily bid file" />
          <Field name="source_id" label="Source ID" placeholder="UUID from sources table" />
          <Field name="commodity_id" label="Commodity ID" placeholder="UUID from commodities table" />
          <div className="md:col-span-2 flex items-center gap-3">
            <button disabled={loading} className="rounded-md border border-black/20 bg-black px-4 py-2 text-sm text-white disabled:opacity-50">
              {loading ? "Running..." : "Run ingestion"}
            </button>
            {message ? <span className="text-sm text-emerald-700">{message}</span> : null}
            {error ? <span className="text-sm text-red-700">{error}</span> : null}
          </div>
        </form>
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Recent ingestion runs</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Source</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Raw</th>
                <th className="px-2 py-2">Normalized</th>
                <th className="px-2 py-2">Started</th>
                <th className="px-2 py-2">File</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={6}>
                    No ingestion runs yet.
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr key={run.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{run.source_name}</td>
                    <td className="px-2 py-2">{run.status}</td>
                    <td className="px-2 py-2">{run.raw_row_count ?? "-"}</td>
                    <td className="px-2 py-2">{run.normalized_row_count ?? "-"}</td>
                    <td className="px-2 py-2">{run.started_at ? new Date(run.started_at).toLocaleString() : "-"}</td>
                    <td className="px-2 py-2">{run.source_identifier}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function Field({ name, label, placeholder }: { name: string; label: string; placeholder: string }) {
  return (
    <label className="text-sm">
      <span className="text-xs uppercase tracking-wide text-black/50">{label}</span>
      <input name={name} placeholder={placeholder} className="mt-1 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm" />
    </label>
  );
}
