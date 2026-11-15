# AGENTS.md — Engineering Rules for Pixel Bangkok

These instructions apply to coding agents and contributors working in this repository. Read `SPEC.md` for product requirements and `CLAUDE.md` for the project execution workflow.

## 1. General engineering principles

- Prefer small, focused changes over broad rewrites.
- Keep modules cohesive and responsibilities explicit.
- Use descriptive names and straightforward control flow.
- Avoid premature abstractions and unnecessary dependencies.
- Do not add functionality outside the current milestone without approval.
- Preserve existing project conventions unless there is a documented reason to change them.
- Never fabricate geographic data, measurements, citations or test results.

## 2. Repository hygiene

- Keep source code, source data, processed data and generated assets in separate locations.
- Keep raw extracts, large processed datasets, rendered masters, tile pyramids, caches and temporary files out of Git by default.
- Add explicit `.gitignore` rules for generated and local-only data.
- Commit small fixtures and representative samples only when they are useful for tests and legally distributable.
- Never commit `.env` files, API keys, credentials or private tokens.
- Provide `.env.example` with variable names and safe placeholders when environment variables are needed.
- Do not overwrite user-created data or assets without checking first.

## 3. TypeScript and JavaScript

- Use TypeScript for application and shared package code.
- Enable strict type checking where practical.
- Avoid `any`; use `unknown` and narrow it when input is untrusted.
- Validate external data at runtime at system boundaries.
- Keep domain types separate from UI component props where that improves clarity.
- Prefer pure functions for coordinate transforms, geometry conversion and configuration processing.
- Handle errors explicitly; do not swallow exceptions.
- Avoid unnecessary client components in Next.js.
- Keep browser-only libraries behind client-side boundaries.
- Do not expose server-only environment variables to the browser.

## 4. Python and geospatial processing

- Use type hints for public functions and non-trivial data structures.
- Keep extraction, validation, reprojection, enrichment and export as separate steps.
- Use explicit CRS definitions; never assume coordinates are metres.
- Do not perform distance, area or buffer calculations directly in longitude/latitude.
- Validate geometry before rendering. Report invalid, empty or repaired geometries.
- Make geometry repair behaviour explicit and measurable.
- Preserve source identifiers and source metadata.
- Keep source values separate from derived values.
- Record units for heights and dimensions.
- Treat missing data as missing. Do not silently substitute plausible-looking factual values.
- Make extraction bounds, CRS, output paths and processing defaults configurable.
- Make scripts safe to rerun and avoid destructive side effects.
- Log counts, skipped features, invalid geometries and output paths.

## 5. Coordinate-system contract

- Document the CRS of every input and output dataset.
- Use a suitable projected CRS for local metric geometry operations.
- Convert to renderer coordinates in one shared, tested module.
- Document axis order and units at each boundary.
- Do not duplicate coordinate conversion formulas in UI components or rendering layers.
- Test known control points and bounding-box corners.
- POI overlays must use the same transform as the rendered map.
- If the map is rotated or transformed, encode that transform in metadata rather than relying on undocumented UI offsets.

## 6. Data provenance and licensing

Every external dataset must have documented:

- Provider and dataset name.
- Source URL or access method.
- Retrieval date.
- Licence and attribution requirements.
- Geographic coverage.
- Processing steps.
- Any known limitations.

Do not assume that publicly accessible data is free of redistribution restrictions.

For OpenStreetMap-derived data, retain required attribution and assess ODbL implications for the intended distribution. For Overture or other datasets, verify the current licence and applicable notices. Do not scrape or redistribute proprietary map tiles or imagery without permission.

## 7. Rendering standards

- Rendering must be deterministic for a fixed input dataset and configuration.
- Fix camera orientation, projection, lighting and random seeds.
- Keep world units and output pixel scale documented.
- Use one shared render configuration for all adjacent regions.
- Preserve the relative positions of source geometry.
- Use separate layers for terrain, water, roads, buildings, vegetation, labels and animation.
- Keep landmark-specific art replaceable without corrupting source geometry.
- Make render dimensions and output paths configurable.
- Include a small test scene or fixture so rendering changes can be compared.
- Do not use AI output as the authoritative source of geographic geometry.

## 8. AI-assisted image processing

AI image transformation is optional and must remain isolated from the deterministic pipeline.

- Preserve the source render.
- Version prompts, model identifiers, parameters and reference assets.
- Record approximate cost and processing settings.
- Use overlapping context when processing adjacent image regions.
- Check seams, duplicated objects, missing objects and geographic drift.
- Do not automatically publish generated output without a validation step.
- Keep a procedural fallback available.
- Do not send confidential or restricted data to external model providers.

## 9. Image tiling and assets

- Generate tiles from a known master image and record its dimensions.
- Generate a manifest containing tile size, overlap, image format and zoom levels.
- Ensure tile coordinates and viewer coordinates have a documented relationship.
- Test edge tiles and non-square images.
- Optimise output size without introducing visible artefacts.
- Do not load the full master image in the browser.
- Make asset paths configurable.
- Avoid committing large tile pyramids to the source repository.

## 10. Frontend and accessibility

- Use semantic HTML and accessible names for controls.
- Support keyboard focus and visible focus indicators.
- Ensure controls are usable at mobile viewport sizes.
- Provide loading, empty and error states.
- Avoid relying on colour alone for meaning.
- Respect `prefers-reduced-motion`.
- Keep map overlays aligned during pan and zoom.
- Clean up event listeners, observers and animation loops.
- Avoid unnecessary re-renders in the map viewer.
- Keep interactive POI data separate from the raster map image.

## 11. Testing

Add tests at the boundaries where errors would be expensive:

- Coordinate transformation and axis order.
- CRS conversion and bounds.
- Geometry validation and height derivation.
- Render configuration parsing.
- POI-to-image coordinate alignment.
- Tile manifest generation and parsing.
- Viewer pan/zoom and overlay alignment.
- Loading and failure states.

Use small, deterministic fixtures. Do not make normal unit tests depend on live Overpass, Overture, cloud storage or AI services.

Mock external services in automated tests. Keep any live integration test explicit and opt-in.

## 12. Performance

- Measure before optimising.
- Avoid unnecessary full-scene browser rendering.
- Lazy-load assets and load only visible tiles.
- Avoid processing large geographic datasets repeatedly when cached intermediate outputs are valid.
- Use streaming or chunked processing when data size warrants it.
- Record image dimensions and output sizes.
- Keep the first POC small enough to regenerate locally.

## 13. Documentation

Update documentation when changing:

- Setup instructions.
- Environment variables.
- Data sources or licences.
- CRS or coordinate transforms.
- Render configuration.
- Tile format or manifest.
- CLI commands.
- Deployment or storage workflow.

Document decisions that materially affect future compatibility in `docs/decisions/`.

## 14. Definition of done

A change is complete when:

- It meets the requested scope.
- Relevant automated checks pass.
- Errors and edge cases are handled.
- No secrets or accidental bulk assets are included.
- Documentation is updated where needed.
- Data provenance and licensing information are preserved.
- The result is reproducible by another developer following the repository instructions.
