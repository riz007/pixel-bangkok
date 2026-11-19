# Pixel Bangkok

An interactive isometric pixel-art map of Bangkok generated from open geographic data:
OpenStreetMap for roads, water, land use and building footprints, Google Open Buildings 2.5D for
building heights, the Meta/WRI canopy-height map for trees, and Wikidata for landmark descriptions.

Published areas:

| Area | Size | Contents |
|---|---|---|
| `inner-bangkok` | 10 km × 10 km | Old town, Chinatown, Silom/Sathorn, Siam, Pratunam, Victory Monument, Sukhumvit to Asok, Thonburi riverside |
| `old-town` | 3 km × 3 km | Rattanakosin Island and the Thonburi bank |
| `wat-arun` | 500 m × 500 m | The original proof-of-concept area |

## Layout

| Path | Purpose |
|---|---|
| `config/areas/<id>.json` | Area bounds, CRS and data source |
| `config/render.json` | Camera, pixel scale, palette, height defaults, tile settings (shared by all areas) |
| `data/curated/<id>/` | Hand-maintained POIs and landmark overrides |
| `data/raw/`, `data/processed/`, `build/` | Generated; gitignored |
| `pipeline/` | Python asset pipeline (`pixel_bangkok` package) |
| `apps/web/` | Next.js viewer; reads published assets from `public/maps/` (gitignored) |

## Requirements

- Node 24+ and pnpm 11
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and the pipeline dependencies)

## Setup and generation

```bash
pnpm install
pnpm pipeline all            # extract → normalise → enrich → render → style → tile → publish
pnpm dev                     # http://localhost:3000
```

Each stage also runs on its own, for example `pnpm pipeline render --area wat-arun`.

| Stage | Reads | Writes |
|---|---|---|
| `extract` | Overpass API or a regional PBF extract, height and canopy rasters | `data/raw/<id>/osm.json`, `building_heights.tif`, `tree_canopy.tif`, `extract-metadata.json` (each skipped if present; `--force` re-downloads) |
| `normalise` | raw extract | `data/processed/<id>/*.geojson`, `metadata.json` |
| `enrich` | buildings, rasters, `landmarks.json` | `buildings.enriched.geojson` with height provenance, `trees.enriched.geojson` |
| `pois` | `poi-candidates.json`, Wikidata API | `data/processed/<id>/pois.json` (top landmarks by Wikipedia coverage) |
| `motion` | raw OSM | `data/processed/<id>/motion.json`: drivable roads, river/canal centrelines, ferry routes |
| `render` | processed layers | `build/<id>/render.png` and `layers/*.png` (geometry reference) |
| `style` | `render.png`, render layers | `build/<id>/master.png`, `overlay.png` (buildings and trees only) |
| `tile` | `master.png`, `overlay.png` | `build/<id>/tiles/`, `overlay/`, `manifest.json` |
| `publish` | tiles, manifest, `pois.json` | `apps/web/public/maps/<id>/`, `maps/index.json` |

The render is deterministic: the same raw extract and configuration produce a byte-identical
`master.png`. Re-running `extract --force` fetches current OSM data, which may differ.

## Checks

```bash
pnpm pipeline:lint    # ruff
pnpm pipeline:test    # pytest (no network)
pnpm lint             # eslint
pnpm typecheck        # tsc
pnpm test             # node:test unit tests for manifest parsing, transforms, search
pnpm build            # next build
pnpm test:e2e         # Playwright; needs `pnpm pipeline all`, `pnpm build` and
                      # `pnpm --filter web exec playwright install chromium` first
```

## Coordinate systems

| Boundary | CRS / units |
|---|---|
| Raw extract, processed GeoJSON, curated POIs | WGS84 (EPSG:4326), longitude then latitude, degrees |
| Raw rasters (`*.tif`) | area CRS, origin at the area's north-west corner, square pixels |
| Geometry operations | EPSG:32647 (UTM 47N), metres |
| World | metres east/north of the area's south-west corner, z up |
| Image | master-image pixels, origin top-left |
| Viewer | OpenSeadragon viewport units (image x / image width) |

`pipeline/pixel_bangkok/crs.py` and `projection.py` are the only places the geographic and
isometric transforms are defined. The published manifest carries the world→image matrix, and
published POIs carry image pixels computed with it. For lat, long search and the Report link,
`publish` adds quadratic lon/lat↔world fits (`projection.geographic`) with their worst error on a
grid over the area (about 1 cm for 20 km).

## Transit

Rail ways and transit route relations come from OSM. Lines underground (MRT Blue) are drawn as a
dashed trace, at-grade rail as ballast and rails, and BTS, elevated metro and expressways as
viaducts on pillars. OSM has no deck heights: they are estimated from the `layer` tag and marked
`elevation_provenance: "estimated-layer"` in `rail.geojson` and `roads.geojson`. Re-rendering
re-queues any AI window whose procedural input changed.

## OSM source per area

`source.method` in `config/areas/<id>.json` is `overpass` (default, fine for small areas) or `pbf`,
which downloads a regional extract once (Geofabrik Thailand, ~330 MB, MD5-checked) into
`data/raw/_cache/pbf/` and selects the area locally with pyosmium using the same tag rules. Use
`pbf` for anything larger than about 1 km²; public Overpass servers often time out.

## Landmarks

Curated POIs in `data/curated/<id>/pois.json` are combined with generated ones from the `pois`
stage. Generated POIs are named OSM features with a Wikidata ID; names come from OSM or Wikidata and
descriptions from Wikidata, never written by hand. Curated entries win, and a generated POI within
25 m of a curated one of the same category is dropped.

## Building heights

Each building's drawn height comes from the first available of: a curated override in
`data/curated/<id>/landmarks.json`, an OSM `height` tag, OSM `building:levels` × 3 m, the
75th percentile of the Open Buildings 2.5D raster inside the footprint, or a 6 m default. The
choice is stored per building as `height_source` and `height_provenance`. Raster heights are model
estimates (stated error 1.5 m, measured outside Southeast Asia), and the model cannot resolve
spires, so tall landmarks need curated values.

Trees are symbols placed on a fixed-seed jittered grid wherever the canopy model shows canopy at
least 3 m tall; they are not individually surveyed trees. Gabled temple roofs, façade windows,
roof tiles and dither textures are drawn for illustration. Buildings OSM tags as pagodas or stupas are
drawn as bell-shaped chedis, and Wat Arun's central and satellite prangs (curated) as tiered prangs;
these forms are stylised and sit inside each building's real footprint. Buildings inside temple or
palace grounds are drawn in traditional style; other buildings get a material (concrete, pastel
shophouse, corrugated metal, glass) chosen deterministically from their OSM ID and size, and flat roofs
over 8 m get decorative water tanks and AC units. None of these details are source data.

## Large areas

Rendering, styling and tiling work in 4096 px blocks (`build/<id>/blocks/`), so area size is limited by
disk and time, not memory. Block output is pixel-identical to a whole-image render, and the tile pyramid
is streamed from blocks with 2×2 mode pooling. Inner Bangkok is about 42,000 × 21,000 px.

## AI illustration (optional, slow)

An optional AI pass repaints the procedural map with Qwen-Image 2.1 Turbo running locally through
[mflux](https://github.com/filipstrand/mflux). The model is under the Qwen Research License: personal,
non-commercial use only. The procedural map stays the geometry reference and the fallback.

```bash
uv tool install mflux                                     # once; the model downloads on first use (~17 GB)
pnpm pipeline ai-plan --area inner-bangkok --focus 100.4913,13.7500
pnpm pipeline ai-run --area inner-bangkok --limit 200     # resumable; ~70 s per window on an M5
pnpm pipeline ai-compose --area inner-bangkok
pnpm pipeline tile --area inner-bangkok && pnpm pipeline publish --area inner-bangkok
```

Windows are 1024 px with 256 px overlap, processed outward from the focus point, snapped to a 64-colour
palette, aligned for small uniform offsets and checked against the procedural render. A window is
rejected if any confidently matched 128 px block moved more than 2 px, fewer than 90% of edges survive,
or more than 30% of textured blocks no longer match; rejected windows are retried once at lower strength
and otherwise stay procedural. Accepted windows are feather-blended. The viewer shows the AI layer by
default where it exists, with an "AI" button to switch to the plain drawing.

## Animation

Cars, taxis, tuk-tuks, buses, motorbikes and boats move along OSM roads, the Chao Phraya, canals
and ferry routes, keeping left as in Thailand and respecting one-way streets. Vehicles are drawn
between the map and an overlay of the same map's buildings and trees, so they pass behind buildings.
Trains run on rail and viaduct paths in their OSM line colour (BTS green, Silom teal, and so on), at
the estimated deck height. Elevated trains draw on a second canvas, below a `front/` overlay holding
only the buildings and trees the renderer drew in front of a viaduct, so towers still hide them.
Elevated expressways have no traffic yet. Underground lines show no trains.
The animation is illustrative: vehicle counts and positions are not traffic data. It starts paused
when the system asks for reduced motion and has a play/pause control; it is hidden when zoomed far out.

## Image quality

Pyramid levels are made by taking the most common colour of each 2×2 block, so every level keeps the
original pixel-art colours instead of averaging them. The viewer draws with smoothing off, prefers
full-resolution levels (`minPixelRatio` 1) and caches up to 1,500 tiles.

## Deploying

The web app (Vercel) and the map files (Cloudflare R2) are deployed separately: the published maps
are about 1.6 GB and 85,000 files, far beyond what a page host should serve. `apps/web/public/maps/`
is gitignored, so a Vercel build from Git never includes it.

### Map files on R2

1. Create an R2 bucket (for example `pixel-bangkok-maps`) and connect a custom domain to it, such
   as `maps.example.com`. The `r2.dev` address is rate-limited and meant for testing only.
2. Allow the site to read JSON from the bucket: set the bucket's CORS policy from
   `deploy/r2-cors.json`, with your site's origin in `AllowedOrigins`. Tiles would draw without it,
   but `index.json`, `manifest.json`, `pois.json` and `motion.json` are fetched by script.
3. Create an R2 API token with object read and write access to that bucket, then add an rclone
   remote with provider `Cloudflare` and those keys (`rclone config`).
4. Upload: `deploy/upload-maps.sh <remote> <bucket>` (or name areas to upload only those).
   Tiles, overlays, thumbnails and `motion.json` carry a content version (`?v=`) and are sent
   with a one-year immutable cache; `index.json`, `manifest.json` and `pois.json` get 5 minutes.
   Blank background tiles are not published; the manifest lists which tiles exist, so the viewer
   never requests them.

### Web app on Vercel

1. Import the GitHub repository and set **Root Directory** to `apps/web` (framework: Next.js,
   package manager: pnpm).
2. Environment variables:
   - `NEXT_PUBLIC_MAP_ASSETS_URL` = the bucket's public URL, e.g. `https://maps.example.com`
   - `NEXT_PUBLIC_MAKER_NAME` = the name credited in the About dialog
   - `NEXT_PUBLIC_REPO_URL` = the source repository linked in the About dialog (optional)
3. Deploy, then check: the map loads, the About dialog credits are complete, a deep link such as
   `/?area=bangkok&place=wat-arun` opens the place, and the browser console shows no CORS errors.

When a map is regenerated, upload it first and only then redeploy (or not at all: the site reads
the current `index.json` and manifests at runtime).

## Attribution

- Map data © OpenStreetMap contributors, ODbL 1.0
- Building heights: Google Open Buildings 2.5D Temporal, CC BY 4.0
- Tree canopy: Meta and World Resources Institute, CC BY 4.0

The viewer lists every source used for a map in its footer and Credits dialog.
