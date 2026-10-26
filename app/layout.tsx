import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

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
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="site-header-inner">
            <Link href="/" className="brand">
              <span className="brand-mark" aria-hidden>
                ◎
              </span>
              Solar WiFi Placement
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
      </body>
    </html>
  );
}
