# Pixel Bangkok

An interactive isometric pixel-art map of Bangkok generated from open geographic data:
OpenStreetMap for roads, water and building footprints, Google Open Buildings 2.5D for building
heights, and the Meta/WRI canopy-height map for trees.
The current build covers one proof-of-concept area: a 500 m × 500 m square around
Wat Arun and the Chao Phraya riverside.

- `SPEC.md` — product and architecture specification
- `AGENTS.md` — engineering rules

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
| `extract` | Overpass API, height and canopy rasters | `data/raw/<id>/osm.json`, `building_heights.tif`, `tree_canopy.tif`, `extract-metadata.json` (each skipped if present; `--force` re-downloads) |
| `normalise` | raw extract | `data/processed/<id>/*.geojson`, `metadata.json` |
| `enrich` | buildings, rasters, `landmarks.json` | `buildings.enriched.geojson` with height provenance, `trees.enriched.geojson` |
| `render` | processed layers | `build/<id>/render.png` and `layers/*.png` (geometry reference) |
| `style` | `render.png` | `build/<id>/master.png` |
| `tile` | `master.png` | `build/<id>/tiles/`, `manifest.json` |
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
published POIs carry image pixels computed with it.

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
these forms are stylised and sit inside each building's real footprint.

## Attribution

- Map data © OpenStreetMap contributors, ODbL 1.0
- Building heights: Google Open Buildings 2.5D Temporal, CC BY 4.0
- Tree canopy: Meta and World Resources Institute, CC BY 4.0

The viewer lists every source used for a map in its footer and Credits dialog.
