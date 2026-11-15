# Pixel Bangkok

An interactive isometric pixel-art map of Bangkok generated from open geographic data.
The current build covers one proof-of-concept area: a 500 m × 500 m square around
Wat Arun and the Chao Phraya riverside.

- `SPEC.md` — product and architecture specification
- `AGENTS.md` — engineering rules
- `docs/` — data sources, decisions and how to add an area

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
| `extract` | Overpass API | `data/raw/<id>/osm.json`, `extract-metadata.json` (skipped if present; `--force` re-downloads) |
| `normalise` | raw extract | `data/processed/<id>/*.geojson`, `metadata.json` |
| `enrich` | buildings, `landmarks.json` | `buildings.enriched.geojson` with height provenance |
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
| Geometry operations | EPSG:32647 (UTM 47N), metres |
| World | metres east/north of the area's south-west corner, z up |
| Image | master-image pixels, origin top-left |
| Viewer | OpenSeadragon viewport units (image x / image width) |

`pipeline/pixel_bangkok/crs.py` and `projection.py` are the only places the geographic and
isometric transforms are defined. The published manifest carries the world→image matrix, and
published POIs carry image pixels computed with it.

## Attribution

Map data © OpenStreetMap contributors, ODbL 1.0. See `docs/data-sources.md`.
