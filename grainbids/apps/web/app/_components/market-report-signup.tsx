"use client";

import { FormEvent, useState } from "react";

import { API_BASE } from "@/lib/api";

type FormStatus = "idle" | "submitting" | "success" | "error";

export default function MarketReportSignup() {
  const [status, setStatus] = useState<FormStatus>("idle");
  const [message, setMessage] = useState("");
  const [farmerBetaInterest, setFarmerBetaInterest] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("submitting");
    setMessage("");

    const form = new FormData(event.currentTarget);
    const payload = {
      email: String(form.get("email") || ""),
      first_name: String(form.get("first_name") || ""),
      region: "Eastern Ontario",
      audience: String(form.get("audience") || "farmer"),
      signup_source: farmerBetaInterest ? "homepage_farmer_beta" : "homepage_market_report",
      consent: form.get("consent") === "on",
      website: String(form.get("website") || ""),
    };

    try {
      const response = await fetch(`${API_BASE}/api/newsletter/subscribers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail?.[0]?.msg || detail?.detail || "Signup could not be completed.");
      }
      setStatus("success");
      setMessage(
        farmerBetaInterest
          ? "You're on the list. We'll send the market report and may ask for brief farmer-beta feedback."
          : "You're on the list. The first GrainBids market report will arrive by email.",
      );
      event.currentTarget.reset();
      setFarmerBetaInterest(false);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Signup could not be completed.");
    }
  }

  return (
    <section id="market-report" className="rounded-2xl border border-black/10 bg-[#121317] p-8 text-white shadow-sm">
      <div className="grid gap-8 lg:grid-cols-[1fr_1.1fr] lg:items-center">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-[#d9b45d]">Free weekly market report</p>
          <h2 className="mt-3 font-[family-name:var(--font-serif)] text-4xl leading-tight">
            Know where Eastern Ontario grain bids are moving.
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-white/70">
            Get the strongest local bids, meaningful weekly changes, and market context drawn from GrainBids data.
            No generic market filler.
          </p>
        </div>

        <form onSubmit={submit} className="grid gap-3" aria-label="Join the GrainBids market report">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-xs text-white/70">
              First name
              <input
                name="first_name"
                autoComplete="given-name"
                className="rounded-md border border-white/20 bg-white px-3 py-2.5 text-sm text-black outline-none focus:border-[#d9b45d]"
              />
            </label>
            <label className="grid gap-1 text-xs text-white/70">
              Email address
              <input
                name="email"
                type="email"
                autoComplete="email"
                required
                className="rounded-md border border-white/20 bg-white px-3 py-2.5 text-sm text-black outline-none focus:border-[#d9b45d]"
              />
            </label>
          </div>

          <label className="grid gap-1 text-xs text-white/70">
            I work primarily as a
            <select
              name="audience"
              defaultValue="farmer"
              className="rounded-md border border-white/20 bg-white px-3 py-2.5 text-sm text-black outline-none focus:border-[#d9b45d]"
            >
              <option value="farmer">Farmer</option>
              <option value="grain_business">Grain business</option>
              <option value="ag_professional">Agricultural professional</option>
              <option value="other">Other</option>
            </select>
          </label>

          <label className="flex items-start gap-2 text-xs leading-5 text-white/65">
            <input
              name="farmer_beta_interest"
              type="checkbox"
              checked={farmerBetaInterest}
              onChange={(event) => setFarmerBetaInterest(event.target.checked)}
              className="mt-1"
            />
            <span>I want to help test GrainBids as a farmer during the free beta.</span>
          </label>

          <label className="hidden" aria-hidden="true">
            Website
            <input name="website" tabIndex={-1} autoComplete="off" />
          </label>

          <label className="flex items-start gap-2 text-xs leading-5 text-white/65">
            <input name="consent" type="checkbox" required className="mt-1" />
            <span>I agree to receive the GrainBids market report and related product updates. I can unsubscribe at any time.</span>
          </label>

          <button
            type="submit"
            disabled={status === "submitting" || status === "success"}
            className="rounded-md bg-[#d9b45d] px-5 py-2.5 text-sm font-medium text-black transition hover:bg-[#e6c979] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {status === "submitting" ? "Joining…" : status === "success" ? "You're on the list" : "Send me the market report"}
          </button>

          {message ? (
            <p className={`text-sm ${status === "error" ? "text-red-300" : "text-emerald-300"}`} role="status">
              {message}
            </p>
          ) : null}
        </form>
      </div>
    </section>
  );
}
