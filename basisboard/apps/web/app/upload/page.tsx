"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

type Source = {
  id: string;
  name: string;
  source_type: string;
  location_name: string | null;
  is_active: boolean;
};

type Commodity = {
  id: string;
  name: string;
  unit: string;
};

type UploadRow = {
  id: string;
  file_name: string;
  row_count: number | null;
  status: string;
  uploaded_at: string | null;
  source_id: string;
};

type UploadResponse = {
  upload_id: string;
  snapshot_id: string;
  inserted_rows: number;
  headers: string[];
  mapping: Record<string, string>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function UploadPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [commodities, setCommodities] = useState<Commodity[]>([]);
  const [uploads, setUploads] = useState<UploadRow[]>([]);

  const [sourceId, setSourceId] = useState("");
  const [commodityId, setCommodityId] = useState("");
  const [capturedAt, setCapturedAt] = useState("");
  const [columnMapJson, setColumnMapJson] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const canSubmit = useMemo(() => !!sourceId && !!commodityId && !!file && !loading, [sourceId, commodityId, file, loading]);

  async function loadLookups() {
    const [srcRes, commodityRes] = await Promise.all([
      fetch(`${API_BASE}/api/sources`, { cache: "no-store" }),
      fetch(`${API_BASE}/api/commodities`, { cache: "no-store" }),
    ]);

    const srcJson = srcRes.ok ? await srcRes.json() : { rows: [] };
    const commodityJson = commodityRes.ok ? await commodityRes.json() : { rows: [] };

    setSources(srcJson.rows || []);
    setCommodities(commodityJson.rows || []);

    if (!sourceId && srcJson.rows?.length) {
      setSourceId(srcJson.rows[0].id);
    }
    if (!commodityId && commodityJson.rows?.length) {
      setCommodityId(commodityJson.rows[0].id);
    }
  }

  async function loadUploads() {
    const res = await fetch(`${API_BASE}/api/uploads?limit=25`, { cache: "no-store" });
    const json = res.ok ? await res.json() : { rows: [] };
    setUploads(json.rows || []);
  }

  useEffect(() => {
    loadLookups().catch((err) => setError(String(err)));
    loadUploads().catch((err) => setError(String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || !file) {
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      const form = new FormData();
      form.set("source_id", sourceId);
      form.set("commodity_id", commodityId);
      if (capturedAt.trim()) {
        form.set("captured_at", capturedAt.trim());
      }
      if (columnMapJson.trim()) {
        form.set("column_map_json", columnMapJson.trim());
      }
      form.set("file", file);

      const res = await fetch(`${API_BASE}/api/uploads/csv`, {
        method: "POST",
        body: form,
      });

      const payload = (await res.json()) as UploadResponse | { detail?: string };
      if (!res.ok) {
        const detail = (payload as { detail?: string }).detail || "Upload failed";
        throw new Error(detail);
      }

      const data = payload as UploadResponse;
      setSuccess(`Upload complete. Inserted ${data.inserted_rows} normalized rows.`);
      setFile(null);
      (event.currentTarget.querySelector("input[type=file]") as HTMLInputElement | null)?.value = "";
      await loadUploads();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Bids</p>
          <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Upload Bid CSV</h1>
          <p className="mt-2 text-sm text-black/65">Map source + commodity, ingest CSV, and inspect upload history.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/dashboard" className="rounded-xl border border-black/15 bg-white/70 px-4 py-2 text-sm hover:border-black/30">
            Dashboard
          </Link>
          <Link href="/" className="rounded-xl border border-black/15 bg-white/70 px-4 py-2 text-sm hover:border-black/30">
            Home
          </Link>
        </div>
      </header>

      <section className="mt-8 rounded-2xl border border-black/10 bg-white/65 p-6 backdrop-blur">
        <form className="grid gap-4 md:grid-cols-2" onSubmit={onSubmit}>
          <label className="text-sm">
            Source
            <select value={sourceId} onChange={(e) => setSourceId(e.target.value)} className="mt-1 w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm">
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.name}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            Commodity
            <select value={commodityId} onChange={(e) => setCommodityId(e.target.value)} className="mt-1 w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm">
              {commodities.map((commodity) => (
                <option key={commodity.id} value={commodity.id}>
                  {commodity.name} ({commodity.unit})
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            Captured at (optional ISO datetime)
            <input
              value={capturedAt}
              onChange={(e) => setCapturedAt(e.target.value)}
              placeholder="2026-04-17T08:30:00Z"
              className="mt-1 w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm"
            />
          </label>

          <label className="text-sm">
            Column map JSON (optional)
            <input
              value={columnMapJson}
              onChange={(e) => setColumnMapJson(e.target.value)}
              placeholder='{"location":"Site","commodity":"Crop"}'
              className="mt-1 w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm"
            />
          </label>

          <label className="text-sm md:col-span-2">
            CSV file
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="mt-1 w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm"
            />
          </label>

          <div className="md:col-span-2 flex items-center gap-3">
            <button
              type="submit"
              disabled={!canSubmit}
              className="rounded-xl border border-black/20 bg-black px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Uploading..." : "Upload CSV"}
            </button>
            {success ? <span className="text-sm text-emerald-700">{success}</span> : null}
            {error ? <span className="text-sm text-red-700">{error}</span> : null}
          </div>
        </form>
      </section>

      <section className="mt-8 rounded-2xl border border-black/10 bg-white/65 p-6 backdrop-blur">
        <h2 className="text-lg font-semibold">Recent Uploads</h2>
        <p className="mt-1 text-xs text-black/55">Latest records from `raw_uploads`.</p>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">File</th>
                <th className="px-2 py-2">Rows</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {uploads.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-2 py-4 text-black/55">
                    No uploads yet.
                  </td>
                </tr>
              ) : (
                uploads.map((row) => (
                  <tr key={row.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{row.file_name}</td>
                    <td className="px-2 py-2">{row.row_count ?? "-"}</td>
                    <td className="px-2 py-2">{row.status}</td>
                    <td className="px-2 py-2">{row.uploaded_at ? new Date(row.uploaded_at).toLocaleString() : "-"}</td>
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

