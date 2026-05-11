import type { Metadata } from "next";
import { Instrument_Sans, Instrument_Serif } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const sans = Instrument_Sans({ subsets: ["latin"], variable: "--font-sans" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", variable: "--font-serif" });

export const metadata: Metadata = {
  title: "GrainBids",
  description: "GrainBids Bids module: see where your bid sits versus the local market in under 60 seconds."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body className="min-h-screen antialiased">
        <div className="border-b border-black/10 bg-white/70 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
            <Link href="/" className="font-[family-name:var(--font-serif)] text-2xl leading-none">
              GrainBids
            </Link>
            <nav className="flex items-center gap-2 text-sm text-black/70">
              <Link href="/bids" className="rounded-lg px-3 py-1.5 hover:bg-black/5">
                Bids
              </Link>
              <Link href="/sources" className="rounded-lg px-3 py-1.5 hover:bg-black/5">
                Sources
              </Link>
              <Link href="/alerts" className="rounded-lg px-3 py-1.5 hover:bg-black/5">
                Alerts
              </Link>
              <Link href="/quotes" className="rounded-lg px-3 py-1.5 hover:bg-black/5">
                Quotes
              </Link>
            </nav>
          </div>
        </div>
        {children}
      </body>
    </html>
  );
}

