"use client";

import { useEffect, useRef, useState } from "react";
import type { GeocodeResult } from "../types";

interface SearchBoxProps {
  onSelect: (result: GeocodeResult) => void;
  disabled?: boolean;
}

export default function SearchBox({ onSelect, disabled }: SearchBoxProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 3) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/geocode?q=${encodeURIComponent(query.trim())}`);
        const data = await res.json();
        if (data.ok) {
          setResults(data.results ?? []);
          setOpen(true);
          setActiveIdx(-1);
        }
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (activeIdx >= 0 && activeIdx < results.length) {
        e.preventDefault();
        pick(results[activeIdx]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  function pick(result: GeocodeResult) {
    setQuery(result.display_name);
    setOpen(false);
    onSelect(result);
  }

  return (
    <div className="search-wrap" ref={wrapRef}>
      <input
        className="search-input"
        type="text"
        placeholder="Search for a park, cemetery, or campus (e.g. &quot;Golden Gate Park&quot;)…"
        value={query}
        disabled={disabled}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => {
          if (results.length > 0) setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        aria-label="Search for a location"
      />
      {open && results.length > 0 && (
        <div className="search-results">
          {results.map((r, i) => (
            <div
              key={`${r.lat}-${r.lon}-${i}`}
              className={`search-result-item${i === activeIdx ? " active" : ""}`}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(r);
              }}
              onMouseEnter={() => setActiveIdx(i)}
            >
              {r.display_name}
            </div>
          ))}
        </div>
      )}
      {loading && <div className="subtle" style={{ marginTop: 4 }}>Searching…</div>}
    </div>
  );
}
