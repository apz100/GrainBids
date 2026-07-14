import type { Metadata } from "next";
import { Instrument_Sans, Instrument_Serif } from "next/font/google";
import TopNav from "./_components/top-nav";
import "./globals.css";

const sans = Instrument_Sans({ subsets: ["latin"], variable: "--font-sans" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", variable: "--font-serif" });

export const metadata: Metadata = {
  title: "GrainBids | Eastern Ontario Grain Prices and Market Intelligence",
  description: "Compare Eastern Ontario grain bids, follow basis movement, and receive practical local market intelligence."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body className="min-h-screen antialiased">
        <TopNav />
        {children}
      </body>
    </html>
  );
}
