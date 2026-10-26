import type { Metadata } from "next";
import Link from "next/link";
import { Archivo, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

// Self-hosted at build time by next/font — no runtime request to Google,
// so the page stays keyless and dependency-free at runtime.
//
// Archivo is a sturdy American grotesque: close enough to the Helvetica
// Neue nycmesh.net uses that the tool reads as part of the same family,
// but with more presence at display weights.
const display = Archivo({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
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
              {/* Echoes the NYC Mesh mark — yellow disc, black glyph — but
                  draws a rooftop node radiating coverage instead of their
                  antenna, since that is what this tool places. */}
              <svg
                className="brand-mark"
                viewBox="0 0 32 32"
                aria-hidden
                focusable="false"
              >
                <circle className="brand-disc" cx="16" cy="16" r="16" />
                <g className="brand-glyph">
                  <path d="M16 20.5V12" />
                  <path d="M10.5 24.5 16 20.5l5.5 4" />
                  <path d="M11.4 11.2a6.5 6.5 0 0 1 9.2 0" />
                  <path d="M8.6 8a10.5 10.5 0 0 1 14.8 0" />
                </g>
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
