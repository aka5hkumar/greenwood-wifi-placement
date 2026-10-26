import type { Metadata } from "next";
import Link from "next/link";
import { Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

// Self-hosted at build time by next/font — no runtime request to Google,
// so the page stays keyless and dependency-free at runtime.
const display = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Solar WiFi Placement Optimizer",
  description:
    "Computes minimal solar-powered WiFi AP placement for any park, cemetery, or campus using OSM topology, elevation-based line-of-sight, and ILP set-cover optimization.",
  // Keeps this portfolio demo out of search indexes — it's reachable by
  // anyone with the link, just not crawled/surfaced, which cuts down on
  // bot traffic against the free upstream APIs (Nominatim/Overpass/
  // Open-Topo-Data) the live-compute path depends on.
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body>
        <header className="site-header">
          <div className="site-header-inner">
            <Link href="/" className="brand">
              <svg
                className="brand-mark"
                viewBox="0 0 24 24"
                aria-hidden
                focusable="false"
              >
                <circle cx="12" cy="12" r="9" />
                <circle cx="12" cy="12" r="3.5" />
                <path d="M12 0.5v5M12 18.5v5M0.5 12h5M18.5 12h5" />
              </svg>
              <span className="brand-text">
                Solar WiFi Placement
                <span className="brand-sub">site survey &amp; optimizer</span>
              </span>
            </Link>
            <nav className="site-nav">
              <Link href="/">Tool</Link>
              <Link href="/about">About</Link>
              <a
                href="https://github.com/aka5hkumar/greenwood-wifi-placement"
                target="_blank"
                rel="noreferrer"
                title="Source"
              >
                Source
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
        <footer className="site-footer">
          <div className="site-footer-inner">
            <span>
              Data: OpenStreetMap · USGS / Open-Topo-Data · NASA POWER. No API keys, no
              tracking.
            </span>
            <span className="footer-coord">40°39′04″N 073°59′38″W</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
