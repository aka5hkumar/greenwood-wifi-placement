/**
 * Copy MapLibre's web worker bundle into public/ so it can be served at a
 * stable URL.
 *
 * MapLibre resolves its worker with `new URL('./maplibre-gl-worker.mjs',
 * import.meta.url)`. Once Next bundles maplibre-gl into a hashed chunk under
 * /_next/static/chunks/, that resolves to a path where the worker file does
 * not exist — the request 404s, the worker never starts, and the map renders
 * as a blank grey canvas with no tiles.
 *
 * Copying the worker here (and calling setWorkerUrl in ResultMap.tsx) gives
 * it a real URL to load from. The worker bundle is self-contained — it has no
 * imports of its own — so this single file is all that's needed.
 *
 * Run from the `prebuild`/`predev` npm scripts so the copy always matches the
 * installed maplibre-gl version rather than being committed and drifting.
 */

import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);

const pkgJson = require.resolve("maplibre-gl/package.json");
const distDir = join(dirname(pkgJson), "dist");
const outDir = join(process.cwd(), "public", "maplibre");

mkdirSync(outDir, { recursive: true });
copyFileSync(
  join(distDir, "maplibre-gl-worker.mjs"),
  join(outDir, "maplibre-gl-worker.mjs")
);

console.log("Copied maplibre-gl-worker.mjs -> public/maplibre/");
