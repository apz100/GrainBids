"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { API_BASE, buildApiHeaders } from "@/lib/api";

type QuoteRun = {
  id: string;
  generated_at: string | null;
  assumptions_json: Record<string, unknown> | null;
  output_file_url: string | null;
  status: string;
};

type FacetsResponse = {
  commodities?: string[];
  locations?: string[];
  company_names?: string[];
};

export default function QuotesPage() {
  const headers = buildApiHeaders();
  const formRef = useRef<HTMLFormElement | null>(null);
  const [runs, setRuns] = useState<QuoteRun[]>([]);
  const [facets, setFacets] = useState<FacetsResponse>({});
  const [estimateCount, setEstimateCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [estimating, setEstimating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadRuns() {
    const response = await fetch(`${API_BASE}/api/quotes/runs?limit=25`, { cache: "no-store", headers });
    if (!response.ok) {
      throw new Error("Failed to load quote runs");
    }
    const json = await response.json();
    setRuns(json.rows || []);
  }

  async function loadFacets() {
    const response = await fetch(`${API_BASE}/api/normalized-prices/facets`, { cache: "no-store", headers });
    if (!response.ok) {
      throw new Error("Failed to load quote filters");
    }
    const json = await response.json();
    setFacets(json || {});
  }

  useEffect(() => {
    Promise.all([loadRuns(), loadFacets()]).catch((err) => setError(String(err)));
  }, []);

  function buildExportParams(formData: FormData) {
    const params = new URLSearchParams();
    for (const key of ["export_format", "commodity", "location", "source_name", "captured_date", "trucking_cost_bu", "trucking_cost_mt"]) {
      const value = String(formData.get(key) || "").trim();
      if (value) params.set(key, value);
    }
    return params;
  }

  async function runEstimate() {
    setEstimating(true);
    setError("");
    setMessage("");
    const formEl = formRef.current;
    if (!formEl) {
      setEstimating(false);
      return;
    }
    const formData = new FormData(formEl);
    const params = buildExportParams(formData);
    try {
      const response = await fetch(`${API_BASE}/api/normalized-prices/summary?${params.toString()}`, { cache: "no-store", headers });
      if (!response.ok) {
        throw new Error("Failed to estimate matching rows");
      }
      const json = await response.json();
      setEstimateCount(typeof json.row_count === "number" ? json.row_count : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setEstimateCount(null);
    } finally {
      setEstimating(false);
    }
  }

  async function runExport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    const formData = new FormData(event.currentTarget);
    const params = buildExportParams(formData);

    try {
      const response = await fetch(`${API_BASE}/api/quotes/export?${params.toString()}`, { method: "POST", headers });
      const json = await response.json();
      if (!response.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Quote export failed");
      }
      setMessage(`Export created (${json.row_count} rows).`);
      setEstimateCount(json.row_count ?? null);
      await loadRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Quotes</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Quotes</h1>
      <p className="mt-2 text-sm text-black/65">Generate delivered-value exports from normalized bids.</p>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Generate export</h2>
        <form ref={formRef} className="mt-3 grid gap-3 md:grid-cols-4" onSubmit={runExport}>
          <SelectField name="export_format" label="Format" options={["csv", "xlsx"]} />
          <SelectWithAny name="commodity" label="Commodity" options={facets.commodities || []} anyLabel="All commodities" />
          <SelectWithAny name="location" label="Location" options={facets.locations || []} anyLabel="All locations" />
          <SelectWithAny name="source_name" label="Company" options={facets.company_names || []} anyLabel="All companies" />
          <TextField name="captured_date" label="Date (optional)" type="date" />
          <TextField name="trucking_cost_bu" label="Trucking/Bu" type="number" step="0.01" placeholder="0.00" />
          <TextField name="trucking_cost_mt" label="Trucking/MT" type="number" step="0.01" placeholder="0.00" />
          <div className="flex items-end gap-2">
            <button
              type="button"
              disabled={estimating}
              onClick={() => runEstimate()}
              className="rounded-md border border-black/20 bg-white px-4 py-2 text-sm disabled:opacity-50"
            >
              {estimating ? "Estimating..." : "Estimate"}
            </button>
            <button
              disabled={loading}
              className="rounded-md border border-black/20 bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {loading ? "Running..." : "Export"}
            </button>
          </div>
        </form>
        <p className="mt-3 text-xs text-black/60">
          {estimateCount == null ? "Estimate matching rows before export." : `Estimated rows: ${estimateCount}`}
        </p>
        {message ? <p className="mt-3 text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Recent quote runs</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Generated</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Assumptions</th>
                <th className="px-2 py-2">Download</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={4}>
                    No quote runs yet.
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr key={run.id} className="border-b border-black/5 align-top">
                    <td className="px-2 py-2">{run.generated_at ? new Date(run.generated_at).toLocaleString() : "-"}</td>
                    <td className="px-2 py-2">{run.status}</td>
                    <td className="px-2 py-2 text-xs text-black/70">
                      {run.assumptions_json ? JSON.stringify(run.assumptions_json) : "-"}
                    </td>
                    <td className="px-2 py-2">
                      {run.output_file_url ? (
                        <a
                          href={`${API_BASE}/api/quotes/runs/${run.id}/download`}
                          className="rounded border border-black/20 bg-white px-3 py-1 text-xs"
                        >
                          Download
                        </a>
                      ) : (
                        "-"
                      )}
                    </td>
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

function TextField({
  name,
  label,
  placeholder,
  type = "text",
  step,
}: {
  name: string;
  label: string;
  placeholder?: string;
  type?: string;
  step?: string;
}) {
  return (
    <label className="text-sm">
      <span className="text-xs uppercase tracking-wide text-black/50">{label}</span>
      <input
        name={name}
        type={type}
        step={step}
        placeholder={placeholder}
        className="mt-1 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
      />
    </label>
  );
}

function SelectField({ name, label, options }: { name: string; label: string; options: string[] }) {
  return (
    <label className="text-sm">
      <span className="text-xs uppercase tracking-wide text-black/50">{label}</span>
      <select name={name} className="mt-1 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function SelectWithAny({
  name,
  label,
  options,
  anyLabel,
}: {
  name: string;
  label: string;
  options: string[];
  anyLabel: string;
}) {
  return (
    <label className="text-sm">
      <span className="text-xs uppercase tracking-wide text-black/50">{label}</span>
      <select name={name} className="mt-1 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
        <option value="">{anyLabel}</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}
