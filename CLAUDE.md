# CLAUDE.md — Pixel Bangkok

## Project mission

Build Pixel Bangkok: a geographically grounded, interactive isometric pixel-art exploration of Bangkok.

Read `SPEC.md` and `AGENTS.md` before making changes. `SPEC.md` is the product and architecture source of truth. `AGENTS.md` contains engineering and repository rules.

## How to work

1. Inspect the existing repository before proposing or changing its structure.
2. Read the relevant documentation and scripts before editing.
3. Work in small, verifiable increments.
4. Before a substantial phase, state:
   - what you intend to build;
   - which files or packages will change;
   - important assumptions;
   - how you will verify the result.
5. Implement only the current milestone. Do not silently start later phases.
6. Run the relevant tests, type checks, lint and build after changes.
7. Summarise what changed, commands run, test results, known limitations and the next recommended task.

Do not merely describe code that should be written. Implement the requested task when the requirements are sufficiently clear. Ask a concise question only when a missing decision materially affects correctness, cost, licensing or architecture.

## Product priorities

Use this priority order:

1. Geographic accuracy.
2. Reproducible data and rendering pipeline.
3. Clear separation between data processing, rendering, tiling and viewer.
4. Visual consistency.
5. Browser performance and accessibility.
6. Optional animation and polish.

Do not sacrifice real-world spatial relationships to make an image look attractive.

## Critical implementation constraints

- Begin with the Wat Arun / Chao Phraya riverside proof of concept defined in `SPEC.md`.
- Do not attempt to build all of Bangkok in the first milestone.
- Do not generate a huge master image before proving the small-area pipeline.
- Do not make AI image generation a required dependency for the first working renderer.
- Preserve the procedural render as the geometry reference and fallback.
- Keep the browser viewer independent from the offline asset-generation pipeline.
- Do not load a huge master image into the browser; use a tile pyramid.
- Do not invent geographic features, building heights, coordinates or POI facts.
- Track whether heights are sourced, estimated, manual or unknown.
- Do not add a database, cloud service, paid API or AI provider without demonstrating why it is needed.
- Do not commit raw geographic extracts, large renders, tile pyramids, secrets or generated bulk assets unless explicitly required.
- Do not use proprietary imagery or map tiles without verifying the relevant terms for transformation and redistribution.

## Recommended execution plan

Follow the phases in `SPEC.md`:

- Phase 0: inspect repository, validate data access/licensing, select bounds and CRS.
- Phase 1: extract and normalise geospatial data.
- Phase 2: deterministic procedural isometric renderer.
- Phase 3: pixel-art treatment and tile generation.
- Phase 4: browser viewer and POI interaction.
- Phase 5: search and expansion readiness.

Do not proceed to the next phase until the current phase's exit criteria are met or the user explicitly accepts a documented exception.

## Decision-making

- Prefer the simplest maintainable implementation that meets the specification.
- Do not introduce abstractions for hypothetical future requirements.
- Reuse existing dependencies and conventions where appropriate.
- Verify current library APIs and compatibility before using unfamiliar packages.
- Record material architecture decisions in `docs/decisions/` using short ADRs.
- If a requested approach conflicts with the specification, explain the conflict and propose the smallest correction.
- If data is incomplete, preserve the gap and document it instead of fabricating values.

## Geospatial and rendering rules

- Use one explicit coordinate transformation path.
- Document the CRS at every data boundary.
- Keep geometry operations in a suitable projected CRS.
- Keep source IDs and provenance wherever practical.
- Make rendering deterministic through fixed camera, lighting, configuration and random seeds.
- Use the same projection and camera parameters for adjacent areas.
- Test POI-to-image coordinate alignment.
- Keep optional animation on separate layers from the base map.
- Never let AI image transformation silently relocate roads, buildings, waterways or landmarks.

## Web application rules

- Keep the map as the primary experience.
- Use accessible controls with labels, focus states and keyboard support.
- Handle loading, missing assets and network errors.
- Load only visible tiles for the current zoom level.
- Keep map state and POI data separate from presentation components.
- Respect reduced-motion preferences for animation.
- Do not add accounts, analytics, social features or unrelated product functionality to the MVP.

## Commands and verification

First inspect the repository to discover its actual package manager and scripts. Do not assume commands exist.

For each relevant change, run the narrowest useful checks, then broader checks when practical:

- unit tests;
- Python tests;
- type checking;
- lint;
- production build;
- browser/e2e tests for viewer interactions.

If a check cannot run, report why. Never claim tests passed if they were not run.

## Communication format

At the end of each task, report:

### Implemented

- Concrete changes and key files.

### Verification

- Commands executed and their actual results.

### Decisions

- Important technical choices and why.

### Limitations

- Missing data, assumptions, known defects or deferred work.

### Next step

- The smallest useful next task.

Be concise, technically specific and honest. Do not claim that a map is geographically accurate without comparing it with a geographic reference.
